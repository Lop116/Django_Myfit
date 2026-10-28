from io import BytesIO
from functools import wraps
from urllib.parse import parse_qs, urlsplit
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST


import qrcode
from django.contrib.auth.decorators import login_required, user_passes_test
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
from .models import ClientBooking, MembershipPass, Notification, WorkoutRecord, SupportTicket, SupportTicketMessage
from .notifications import notify_ticket_admin, notify_ticket_update


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
    return render(request, 'myfit/Trial_html/home.html')

def register(request):
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            auth_login(request, user)
            return redirect('myfit:home')
    else:
        form = RegistrationForm()
    return render(request, 'myfit/Trial_html/register.html', {'form': form})

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

#### for Notifications############

# Display the logged-in user's notifications
@login_required
def notification_list(request):
    notifications = Notification.objects.filter(
        user=request.user
    ).order_by("-created_at")

    return render(
        request,
        "myfit/notifications.html",
        {"notifications": notifications},
    )
    
def _notification_redirect(request, default="myfit:notification_list"):
    next_url = request.POST.get('next', '')
    if url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect(default)


# Mark one notification as read
@login_required
@require_POST
def mark_notification_read(request, notification_id):
    notification = get_object_or_404(
        Notification,
        pk=notification_id,
        user=request.user,
    )

    notification.is_read = True
    notification.read_at = timezone.now()
    notification.save(update_fields=["is_read", "read_at"])

    return _notification_redirect(request)

# Mark one notification as unread
@login_required
@require_POST
def mark_notification_unread(request, notification_id):
    notification = get_object_or_404(
        Notification,
        pk=notification_id,
        user=request.user,
    )

    notification.is_read = False
    notification.read_at = None
    notification.save(update_fields=["is_read", "read_at"])

    return _notification_redirect(request)

#mark all notifications as read
@login_required
@require_POST
def mark_all_notifications_read(request):
    Notification.objects.filter(
        user=request.user,
        is_read=False,
    ).update(
        is_read=True,
        read_at=timezone.now(),
    )

    messages.success(request, "All notifications marked as read.")
    return _notification_redirect(request)

#Create a support ticket
@login_required
def create_support_ticket(request):
    if request.method == "POST":
        subject = request.POST.get("subject", "").strip()
        description = request.POST.get("description", "").strip()
        priority = request.POST.get("priority", "normal")

        valid_priorities = {
            choice[0] for choice in SupportTicket.Priority.choices
        }

        if not subject or not description:
            messages.error(
                request, "Please complete the subject and description."
            )
        elif priority not in valid_priorities:
            messages.error(request, "Please select a valid priority.")
        else:
            ticket = SupportTicket.objects.create(
                client=request.user,
                subject=subject,
                description=description,
                priority=priority,
            )

            # Store the initial description as the first conversation message.
            SupportTicketMessage.objects.create(
                ticket=ticket,
                sender=request.user,
                message=description,
            )
            notify_ticket_update(
                ticket,
                f"Ticket #{ticket.pk} received",
                f"We received your request \"{ticket.subject}\". Support will reply soon.",
            )

            messages.success(request, "Your support ticket was created.")
            return redirect("myfit:support_ticket_detail", ticket_id=ticket.pk)

    return render(request, "myfit/support_ticket_form.html")


#list the user's current tickets
@login_required
def support_ticket_list(request):
    if request.user.is_staff:
        tickets = SupportTicket.objects.all()
    else:
        tickets = SupportTicket.objects.filter(client=request.user)

    return render(
        request,
        "myfit/support_ticket_list.html",
        {"tickets": tickets},
    )
 
#View a ticket and its messages
@login_required
def support_ticket_detail(request, ticket_id):
    ticket = get_object_or_404(SupportTicket, pk=ticket_id)

    if not request.user.is_staff and ticket.client_id != request.user.id:
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied

    ticket_messages = ticket.messages.select_related("sender")

    if not request.user.is_staff:
        ticket_messages = ticket_messages.filter(is_internal=False)

    return render(
        request,
        "myfit/support_ticket_detail.html",
        {
            "ticket": ticket,
            "ticket_messages": ticket_messages,
        },
    )

#reply to a ticket
@login_required
#reply to a ticket
@login_required
@require_POST
def reply_to_support_ticket(request, ticket_id):
    ticket = get_object_or_404(SupportTicket, pk=ticket_id)

    if not request.user.is_staff and ticket.client_id != request.user.id:
        raise PermissionDenied

    if ticket.status == SupportTicket.Status.CLOSED and not request.user.is_staff:
        messages.error(request, "This ticket is closed and cannot be replied to.")
        return redirect("myfit:support_ticket_detail", ticket_id=ticket.pk)

    message_text = request.POST.get("message", "").strip()

    if not message_text:
        messages.error(request, "Please enter a message.")
        return redirect("myfit:support_ticket_detail", ticket_id=ticket.pk)

    # Only staff can write internal notes.
    is_internal = request.user.is_staff and request.POST.get("is_internal") == "on"

    SupportTicketMessage.objects.create(
        ticket=ticket,
        sender=request.user,
        message=message_text,
        is_internal=is_internal,
    )

    if request.user.is_staff:
        # Take the ticket if nobody has it yet.
        if ticket.assigned_admin is None:
            ticket.assigned_admin = request.user
        if not is_internal:
            ticket.status = SupportTicket.Status.WAITING_FOR_CLIENT
            notify_ticket_update(
                ticket,
                f"New reply on ticket #{ticket.pk}",
                f"Support replied to \"{ticket.subject}\".",
            )
    else:
        ticket.status = SupportTicket.Status.OPEN
        notify_ticket_admin(
            ticket,
            f"Client replied on ticket #{ticket.pk}",
            f"{request.user.username} replied to \"{ticket.subject}\".",
        )

    # Saves the changes above and bumps updated_at so the list reorders.
    ticket.save()

    messages.success(request, "Your reply was sent.")
    return redirect("myfit:support_ticket_detail", ticket_id=ticket.pk)


#restricts updates to staff accounts and validates submitted values
@login_required
@user_passes_test(lambda user: user.is_staff)
@require_POST
def update_support_ticket(request, ticket_id):
    ticket = get_object_or_404(SupportTicket, pk=ticket_id)

    status = request.POST.get("status")
    priority = request.POST.get("priority")

    valid_statuses = {
        choice[0] for choice in SupportTicket.Status.choices
    }
    valid_priorities = {
        choice[0] for choice in SupportTicket.Priority.choices
    }

    if status not in valid_statuses or priority not in valid_priorities:
        messages.error(request, "Invalid ticket status or priority.")
        return redirect("myfit:support_ticket_detail", ticket_id=ticket.pk)

    status_changed = ticket.status != status
    priority_changed = ticket.priority != priority

    ticket.status = status
    ticket.priority = priority
    ticket.save(update_fields=["status", "priority", "updated_at"])

    # Only notify if something actually changed.
    if status_changed or priority_changed:
        changes = []
        if status_changed:
            changes.append(f"Status is now {ticket.get_status_display()}.")
        if priority_changed:
            changes.append(f"Priority is now {ticket.get_priority_display()}.")
        notify_ticket_update(
            ticket,
            f"Ticket #{ticket.pk} updated",
            " ".join(changes),
        )

    messages.success(request, "Ticket updated successfully.")
    return redirect("myfit:support_ticket_detail", ticket_id=ticket.pk)

