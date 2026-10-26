from io import BytesIO
from functools import wraps
from urllib.parse import parse_qs, urlsplit

import qrcode
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login as auth_login
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core import signing
from django.db.models import Q
from django.http import Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlencode, url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import MembershipVerificationForm, RegistrationForm
from .membership_tokens import (
    create_membership_verification_token,
    get_membership_from_verification_token,
)
from .models import ClientBooking, MembershipPass, Notification, WorkoutRecord


def authorized_membership_staff_required(view_func):
    @login_required(login_url='myfit:login')
    @wraps(view_func)
    def wrapped_view(request, *args, **kwargs):
        if (
            not request.user.is_staff
            or not request.user.has_perm('core.view_membershippass')
        ):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return wrapped_view


def extract_membership_token(value):
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc:
        return parse_qs(parsed.query).get('token', [''])[0]
    return value


# Create your views here.
def home(request):
    return render(request, 'myfit/home.html')

def register(request):
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            auth_login(request, user)
            return redirect('myfit:home')
    else:
        form = RegistrationForm()
    return render(request, 'myfit/register.html', {'form': form})

def branches(request):
    return render(request, 'myfit/branches.html')
def coaches(request):
    return render(request, 'myfit/coaches.html')
def classes(request):
    return render(request, 'myfit/classes.html')
def plans(request):
    return render(request, 'myfit/plans.html')


@login_required(login_url='myfit:login')
def membership_pass(request):
    try:
        member_pass = request.user.membership_pass
    except MembershipPass.DoesNotExist:
        member_pass = None

    qr_image_url = None
    if member_pass is not None:
        token = create_membership_verification_token(member_pass)
        qr_image_url = '{}?{}'.format(
            reverse('myfit:membership_qr'),
            urlencode({'token': token}),
        )

    return render(
        request,
        'myfit/membership_pass.html',
        {'member_pass': member_pass, 'qr_image_url': qr_image_url},
    )


@login_required(login_url='myfit:login')
def membership_qr(request):
    token = request.GET.get('token', '')
    try:
        member_pass = get_membership_from_verification_token(token)
    except signing.BadSignature:
        return HttpResponseBadRequest('This membership QR code is invalid or expired.')

    if member_pass is None or member_pass.user_id != request.user.pk:
        raise Http404

    verification_url = request.build_absolute_uri(
        '{}?{}'.format(
            reverse('myfit:membership_verify'),
            urlencode({'token': token}),
        )
    )
    image = qrcode.make(verification_url)
    image_buffer = BytesIO()
    image.save(image_buffer, format='PNG')
    return HttpResponse(image_buffer.getvalue(), content_type='image/png')


def membership_verify(request):
    token = request.GET.get('token', '')
    try:
        member_pass = get_membership_from_verification_token(token)
    except signing.BadSignature:
        return render(
            request,
            'myfit/membership_verify.html',
            {'verification_status': 'invalid'},
            status=400,
        )

    if member_pass is None:
        verification_status = 'invalid'
    else:
        verification_status = member_pass.current_status

    return render(
        request,
        'myfit/membership_verify.html',
        {'verification_status': verification_status},
    )


@authorized_membership_staff_required
def membership_scanner(request):
    form = MembershipVerificationForm(request.POST or None)
    verification_status = None

    if request.method == 'POST' and form.is_valid():
        token = extract_membership_token(form.cleaned_data['verification_input'].strip())
        try:
            member_pass = get_membership_from_verification_token(token)
        except signing.SignatureExpired:
            verification_status = 'expired_qr_token'
        except signing.BadSignature:
            verification_status = 'invalid_token'
        else:
            if member_pass is None:
                verification_status = 'invalid_token'
            elif member_pass.current_status == MembershipPass.Status.ACTIVE:
                verification_status = 'valid'
            elif member_pass.current_status == MembershipPass.Status.EXPIRED:
                verification_status = 'expired_membership'
            else:
                verification_status = 'inactive_membership'

    return render(
        request,
        'myfit/membership_scanner.html',
        {'form': form, 'verification_status': verification_status},
        status=400 if verification_status in ('invalid_token', 'expired_qr_token') else 200,
    )


def contact(request):
    return render(request, 'myfit/contact.html')
def workouts(request):
    return render(request, 'myfit/workouts.html')

@login_required
def client_dashboard(request):
    return render(request, 'myfit/client_dashboard.html')

@login_required
def progress(request):
    records = WorkoutRecord.objects.filter(
        user=request.user
    ).order_by('-workout_date')

    workout_data = [
        {
            'date': record.workout_date.isoformat(),
            'exercise': record.exercise,
            'sets': record.sets,
            'reps': record.reps,
            'weight': float(record.weight_kg),
        }
        for record in records
    ]

    return render(request, 'myfit/progress.html', {
        'workout_data': workout_data,
        'visit_data': []
    })

@login_required
def client_bookings(request):

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'cancel':
            booking = get_object_or_404(
                ClientBooking,
                id=request.POST.get('booking_id'),
                user=request.user
            )

            today = timezone.localdate()

            if (booking.status == 'confirmed'
                    and booking.class_date >= today):

                booking.status = 'cancelled'
                booking.save(update_fields=['status'])

                messages.success(
                    request,
                    'Your booking has been cancelled.'
                )
            else:
                messages.error(
                    request,
                    'This booking cannot be cancelled.'
                )

        return redirect('myfit:client_bookings')

    today = timezone.localdate()
    current_time = timezone.localtime().time()

    bookings = ClientBooking.objects.filter(
        user=request.user
    )

    upcoming = bookings.filter(
        status='confirmed'
    ).filter(
        Q(class_date__gt=today) |
        Q(class_date=today, start_time__gt=current_time)
    ).order_by('class_date', 'start_time')

    past = bookings.exclude(
        id__in=upcoming.values('id')
    ).order_by('-class_date', '-start_time')

    context = {
        'upcoming_bookings': upcoming,
        'past_bookings': past,
        'upcoming_count': upcoming.count(),
        'completed_count': past.filter(
            status='confirmed'
        ).count(),
        'cancelled_count': bookings.filter(
            status='cancelled'
        ).count(),
    }

    return render(
        request,
        'myfit/client_bookings.html',
        context
    )


def _notification_redirect(request):
    next_url = request.POST.get('next', '')
    if url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect('myfit:home')


@login_required(login_url='myfit:login')
@require_POST
def mark_notification_read(request, notification_id):
    notification = get_object_or_404(
        Notification,
        pk=notification_id,
        user=request.user,
    )
    if not notification.is_read or notification.read_at is None:
        notification.is_read = True
        notification.read_at = timezone.now()
        notification.save(update_fields=('is_read', 'read_at'))
    return _notification_redirect(request)


@login_required(login_url='myfit:login')
@require_POST
def mark_all_notifications_read(request):
    request.user.notifications.filter(is_read=False).update(
        is_read=True,
        read_at=timezone.now(),
    )
    return _notification_redirect(request)


def client_membership(request):
    return render(request, 'myfit/client_membership.html')

def manage_bookings(request):
    return render(request, 'myfit/manage_bookings.html')

def manage_payments(request):
    return render(request, 'myfit/manage_payments.html')

def membership_requests(request):
    return render(request, 'myfit/membership_requests.html')

def manage_plans(request):
    return render(request, 'myfit/manage_plans.html')

def coach_dashboard(request):
    context = {
        "active_client_count": 6,
        "sessions_this_week": 12,
        "avg_visits_per_week": 3,
        "classes_this_month": 8,
        "clients": [
            {"name": "Ava Mitchell", "email": "ava.m@example.com", "membership": "Weight Loss", "visits_this_week": 3},
            {"name": "Liam Carter", "email": "liam.c@example.com", "membership": "Strength", "visits_this_week": 2},
            {"name": "Sofia Patel", "email": "sofia.p@example.com", "membership": "Endurance", "visits_this_week": 4},
            {"name": "Noah Johnson", "email": "noah.j@example.com", "membership": "General Fitness", "visits_this_week": 0},
            {"name": "Ella Chen", "email": "ella.c@example.com", "membership": "Strength", "visits_this_week": 1},
            {"name": "Oliver Brown", "email": "oliver.b@example.com", "membership": "Weight Loss", "visits_this_week": 2},
        ]
    }
    return render(request, "myfit/coach_dashboard.html", context)

def coach_clients(request):
    context = {
        "total_clients": 12,
        "active_this_week": 8,
        "active_percent": 67,
        "need_attention": 3,
        "goals_achieved": 5,
        "clients": [
            {"name": "Ava Mitchell", "email": "ava.m@example.com", "plan": "Weight Loss", "last_session": "Today, 9:00 AM", "status": "On track"},
            {"name": "Liam Carter", "email": "liam.c@example.com", "plan": "Strength", "last_session": "Yesterday", "status": "In progress"},
            {"name": "Sofia Patel", "email": "sofia.p@example.com", "plan": "Endurance", "last_session": "Today, 8:15 AM", "status": "On track"},
            {"name": "Noah Johnson", "email": "noah.j@example.com", "plan": "General Fitness", "last_session": "12 days ago", "status": "Needs attention"},
            {"name": "Ella Chen", "email": "ella.c@example.com", "plan": "Strength", "last_session": "3 days ago", "status": "In progress"},
            {"name": "Oliver Brown", "email": "oliver.b@example.com", "plan": "Weight Loss", "last_session": "Yesterday", "status": "On track"},
            {"name": "Mia Lopez", "email": "mia.l@example.com", "plan": "Yoga", "last_session": "5 days ago", "status": "Needs attention"},
            {"name": "Ethan Wright", "email": "ethan.w@example.com", "plan": "CrossFit", "last_session": "Today, 7:30 AM", "status": "On track"},
            {"name": "Grace Kim", "email": "grace.k@example.com", "plan": "Pilates", "last_session": "2 days ago", "status": "In progress"},
            {"name": "Daniel Smith", "email": "daniel.s@example.com", "plan": "Cardio", "last_session": "Yesterday", "status": "On track"},
            {"name": "Isabella Rossi", "email": "isabella.r@example.com", "plan": "Strength", "last_session": "10 days ago", "status": "Needs attention"},
            {"name": "James Okafor", "email": "james.o@example.com", "plan": "General Fitness", "last_session": "Today, 6:45 AM", "status": "On track"},
        ]
    }
    return render(request, "myfit/coach_clients.html", context)

def manage_branches(request):
    return render(request, "myfit/manage_branches.html")

def manage_coaches(request):
    return render(request, "myfit/manage_coaches.html")
#jush=====
from .models import ClassSession, ClassBooking
from .services import book_client_into_class, cancel_booking
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect

def class_list(request):
    classes = ClassSession.objects.filter(status='Scheduled').order_by('date', 'time')
    return render(request, 'core/class_list.html', {'classes': classes})

@login_required
def book_class_view(request, session_id):
    if request.method == 'POST':
        try:
            book_client_into_class(session_id, request.user.client_profile)
            messages.success(request, "Class booked successfully!")
        except ValidationError as e:
            messages.error(request, str(e.message))
    return redirect('myfit:class_list')

@login_required
def manage_classes(request):
    if request.user.groups.filter(name='Admin').exists() or request.user.is_superuser:
        classes = ClassSession.objects.all().order_by('-date')
    elif hasattr(request.user, 'coach_profile'):
        classes = ClassSession.objects.filter(coach=request.user.coach_profile).order_by('-date')
    else:
        messages.error(request, "Unauthorized")
        return redirect('myfit:home')
    return render(request, 'core/manage_classes.html', {'classes': classes})

@login_required
def cancel_booking_view(request, booking_id):
    if request.method == 'POST':
        try:
            cancel_booking(booking_id, request.user)
            messages.success(request, "Booking cancelled.")
        except ValidationError as e:
            messages.error(request, str(e.message))
    return redirect(request.META.get('HTTP_REFERER', '/'))
#<----