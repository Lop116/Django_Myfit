from datetime import timedelta
from io import BytesIO
from functools import wraps
from urllib.parse import parse_qs, urlsplit


from django.contrib.auth.models import Group #Loick
from django.contrib.auth.views import LoginView #Loick
from .permissions import has_role, role_required #Loick
from .models import WebsiteImage #Loick

from .notifications import notify, notify_ticket_update


import qrcode
from django.contrib.auth.decorators import login_required, permission_required, user_passes_test
from django.contrib.auth import login as auth_login
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core import signing
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlencode, url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.core.exceptions import ValidationError
from .forms import (
    AttendanceCheckInForm,
    ClientMembershipAssignmentForm,
    MembershipChangeRequestForm,
    PaymentForm,
    SupportTicketReplyForm,
)
from .membership_services import (
    assign_membership,
    check_in_membership,
    check_out_visit,
    synchronize_membership_pass,
)


from .forms import MembershipVerificationForm, RegistrationForm, MembershipPlanForm
from .membership_tokens import (
    create_membership_verification_token,
    get_membership_from_verification_token,
)
from .models import (
    AttendanceVisit,
    ClientBooking,
    ClientMembership,
    MembershipChangeRequest,
    MembershipPass,
    MembershipPlan,
    Payment,
    Notification,
    ClientProfile,
    Branch,
    CoachProfile,
    ClassSession,
    CoachSpecialty,
    WorkoutRecord,
)


def authorized_membership_staff_required(view_func):
    @login_required(login_url='myfit:login')
    @wraps(view_func)
    def wrapped_view(request, *args, **kwargs):
        if not (request.user.is_staff or has_role(request.user, 'Admin')) or not request.user.has_perm(
            'core.view_membershippass'
        ):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return wrapped_view


def membership_change_staff_required(view_func):
    @login_required(login_url='myfit:login')
    @wraps(view_func)
    def wrapped_view(request, *args, **kwargs):
        if not (request.user.is_staff or has_role(request.user, 'Admin')) or not request.user.has_perm(
            'core.change_membershipchangerequest'
        ):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return wrapped_view


def extract_membership_token(value):
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc:
        return parse_qs(parsed.query).get('token', [''])[0]
    return value


# Developer: Deshrao Saccaram
def get_attendance_membership_for_user(user):
    today = timezone.localdate()
    eligible_memberships = [
        membership
        for membership in (
            ClientMembership.objects
            .filter(
                user=user,
                status__in=('active', 'scheduled'),
                start_date__lte=today,
                end_date__gte=today,
            )
            .select_related('plan')
            .order_by('pk')
        )
        if membership.current_status == 'active'
    ]
    if not eligible_memberships:
        return None, 'No currently valid client membership is available for check-in.'
    if len(eligible_memberships) > 1:
        return None, 'Multiple valid memberships were found. Ask an administrator to resolve this before check-in.'
    return eligible_memberships[0], None


# Create your views here.
#>>>Loick-------------------------------
def website_images():
    # Each active placement has at most one picture (unique=True in the model).
    # Templates use the returned dictionary and otherwise show original art.
    return {picture.placement: picture for picture in WebsiteImage.objects.filter(is_active=True)}

def home(request):
    # Live homepage cards come from the database rather than example HTML data.
    # Changes saved in Django Admin show on the site after refreshing.
    return render(request, 'myfit/home.html', {
        'site_images': website_images(),
        'home_classes': ClassSession.objects.filter(status='Scheduled', date__gte=timezone.localdate(), branch__is_active=True, coach__user__is_active=True).select_related('branch','coach__user').order_by('date','time')[:4],
        'home_plans': MembershipPlan.objects.filter(is_active=True).order_by('price')[:3],
        'home_branches': Branch.objects.filter(is_active=True).order_by('name')[:4],
        'home_branch_count': Branch.objects.filter(is_active=True, operational_status='Open').count(),
        'home_coach_count': CoachProfile.objects.filter(user__is_active=True).count(),
        'home_client_count': ClientProfile.objects.filter(user__is_active=True).count(),
        'home_class_count': ClassSession.objects.filter(status='Scheduled', date__gte=timezone.localdate()).count(),
        'home_specialties': CoachSpecialty.objects.filter(
            is_active=True, coaches__user__is_active=True
        ).distinct()[:4],
    })
 
 
class RoleAwareLoginView(LoginView):
    """Respect a safe ?next= URL; otherwise send members to their role dashboard."""
    redirect_authenticated_user = True

    def get_success_url(self):
        from .permissions import dashboard_name

        redirect_url = self.get_redirect_url()
        if (
            redirect_url
            and has_role(self.request.user, "Admin")
            and urlsplit(redirect_url).path == reverse("myfit:home")
        ):
            return reverse("myfit:admin_dashboard")
        return redirect_url or reverse(dashboard_name(self.request.user))
 
 
def register(request):
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            # A public signup creates a Client account, not only a bare Django User.
            with transaction.atomic():
                user = form.save()
                client_group, _ = Group.objects.get_or_create(name='Client')
                user.groups.add(client_group)
                ClientProfile.objects.get_or_create(user=user)
            auth_login(request, user)
            # Preserve the existing welcome flow; subsequent logins use the role dashboard.
            return redirect('myfit:home')
    else:
        form = RegistrationForm()
    return render(request, 'myfit/register.html', {'form': form})
 
def classes(request):
    return render(request, 'myfit/classes.html', {
        'site_images': website_images(),
        'upcoming_sessions': ClassSession.objects.filter(status='Scheduled', date__gte=timezone.localdate(), branch__is_active=True, coach__user__is_active=True).select_related('branch','coach__user').order_by('date','time'),
        'filter_branches': Branch.objects.filter(is_active=True, operational_status='Open'),
        'filter_categories': ClassSession.objects.filter(status='Scheduled', date__gte=timezone.localdate()).values_list('category', flat=True).distinct(),
    })



@login_required(login_url='myfit:login')
#<<<<<<<<<<<<<<<---------------------------

# Developer: Deshrao Saccaram
def membership_pass(request):
    membership, eligibility_message = get_attendance_membership_for_user(
        request.user
    )
    member_pass = None
    if membership is not None:
        try:
            member_pass = synchronize_membership_pass(
                request.user,
                membership.pk,
            )
        except (ClientMembership.DoesNotExist, ValidationError):
            membership = None
            eligibility_message = (
                'Membership eligibility changed. Refresh to check your current pass status.'
            )

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
        {
            'member_pass': member_pass,
            'client_membership': membership,
            'membership_eligibility_message': eligibility_message,
            'qr_image_url': qr_image_url,
        },
    )


@login_required(login_url='myfit:login')
def membership_qr(request):
    token = request.GET.get('token', '')
    try:
        member_pass = get_membership_from_verification_token(token)
    except signing.BadSignature:
        return HttpResponseBadRequest('This membership QR code is invalid or expired.')

    if (
        member_pass is None
        or member_pass.user_id != request.user.pk
        or member_pass.current_status != MembershipPass.Status.ACTIVE
    ):
        raise Http404

    membership, _ = get_attendance_membership_for_user(member_pass.user)
    if membership is None:
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


# Developer: Deshrao Saccaram
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
    elif member_pass.current_status != MembershipPass.Status.ACTIVE:
        verification_status = member_pass.current_status
    else:
        membership, _ = get_attendance_membership_for_user(member_pass.user)
        verification_status = (
            MembershipPass.Status.ACTIVE
            if membership is not None
            else 'inactive'
        )

    return render(
        request,
        'myfit/membership_verify.html',
        {'verification_status': verification_status},
    )


@authorized_membership_staff_required
# Developer: Deshrao Saccaram
def membership_scanner(request):
    form = MembershipVerificationForm(request.POST or None)
    verification_status = None
    attendance_membership = None
    attendance_message = None
    verified_token = None

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
                attendance_membership, attendance_message = (
                    get_attendance_membership_for_user(member_pass.user)
                )
                if attendance_membership is not None:
                    verification_status = 'valid'
                    if request.user.has_perm('core.add_attendancevisit'):
                        verified_token = token
                    else:
                        attendance_message = (
                            'This staff account is not permitted to check in clients.'
                        )
                elif attendance_message and attendance_message.startswith(
                    'Multiple valid memberships'
                ):
                    verification_status = 'ambiguous_membership'
                else:
                    verification_status = 'inactive_membership'
            elif member_pass.current_status == MembershipPass.Status.EXPIRED:
                verification_status = 'expired_membership'
            else:
                verification_status = 'inactive_membership'

    return render(
        request,
        'myfit/membership_scanner.html',
        {
            'form': form,
            'verification_status': verification_status,
            'attendance_membership': attendance_membership,
            'attendance_message': attendance_message,
            'verified_token': verified_token,
        },
        status=400 if verification_status in ('invalid_token', 'expired_qr_token') else 200,
    )


# ==========================================================
# TASK 2 - QR SCANNER AND ATTENDANCE INTEGRATION
# Developer: Deshrao Saccaram


@login_required(login_url='myfit:login')
@require_POST
def membership_qr_check_in(request):
    if not (request.user.is_staff or has_role(request.user, 'Admin')) or not request.user.has_perm(
        'core.add_attendancevisit'
    ):
        raise PermissionDenied

    token = extract_membership_token(request.POST.get('token', '').strip())
    try:
        member_pass = get_membership_from_verification_token(token)
    except signing.SignatureExpired:
        messages.error(request, 'This QR token has expired. Scan the member’s current pass again.')
        return redirect('myfit:membership_scanner')
    except signing.BadSignature:
        messages.error(request, 'This QR token is invalid. Scan a valid membership pass.')
        return redirect('myfit:membership_scanner')

    if member_pass is None:
        messages.error(request, 'This QR token does not identify a membership pass.')
        return redirect('myfit:membership_scanner')
    if member_pass.current_status != MembershipPass.Status.ACTIVE:
        messages.error(request, 'The membership pass is not active; check-in was not recorded.')
        return redirect('myfit:membership_scanner')

    membership, eligibility_error = get_attendance_membership_for_user(
        member_pass.user
    )
    if membership is None:
        messages.error(request, eligibility_error)
        return redirect('myfit:membership_scanner')

    try:
        check_in_membership(membership.pk)
    except ClientMembership.DoesNotExist as error:
        raise Http404 from error
    except ValidationError as error:
        messages.error(request, error.messages[0])
    except IntegrityError:
        if AttendanceVisit.objects.filter(
            membership=membership,
            check_out__isnull=True,
        ).exists():
            messages.error(request, 'This client is already checked in.')
        else:
            raise
    else:
        messages.success(request, 'Client check-in recorded successfully.')

    return redirect('myfit:membership_scanner')


# END TASK 2 - QR SCANNER AND ATTENDANCE INTEGRATION


def workouts(request):
    return render(request, 'myfit/workouts.html')

@role_required('Client')
def client_dashboard(request):
    from datetime import timedelta
    from .models import CoachClientAssignment

    today = timezone.localdate()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    attendance = AttendanceVisit.objects.filter(membership__user=request.user)
    membership = ClientMembership.objects.filter(
        user=request.user, status__in=('active', 'scheduled'),
        start_date__lte=today, end_date__gte=today,
    ).select_related('plan').first()
    bookings = ClassBooking.objects.filter(
        client__user=request.user, status='Confirmed',
        session__status='Scheduled', session__date__gte=today,
    ).select_related('session__branch').order_by('session__date', 'session__time')
    coach_assignment = CoachClientAssignment.objects.filter(
        client__user=request.user,
    ).select_related('coach__user').prefetch_related('coach__specialties').first()
    return render(request, 'myfit/client_dashboard.html', {
        'member_pass': MembershipPass.objects.filter(user=request.user).first(),
        'membership': membership, 'current_membership': membership,
        'visits_this_week': attendance.filter(check_in__date__gte=week_start).count(),
        'visits_this_month': attendance.filter(check_in__date__gte=month_start).count(),
        'total_visits': attendance.count(),
        'upcoming_bookings': bookings[:5],
        'recent_workouts': WorkoutRecord.objects.filter(user=request.user).order_by('-workout_date')[:5],
        'recent_attendance': attendance.order_by('-check_in')[:5],
        'coach_assignment': coach_assignment,
        'latest_notifications': Notification.objects.filter(user=request.user)[:5],
        'client': ClientProfile.objects.filter(user=request.user).first(),
    })

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

@role_required('Client')
def client_bookings(request):
    """Show both booking generations; new bookings use real ClassSession records."""
    if request.method == 'POST':
        if request.POST.get('action') == 'cancel':
            ident = request.POST.get('booking_id', '')
            source = request.POST.get('booking_source', 'legacy')
            if not ident.isdecimal():
                messages.error(request, 'Invalid booking reference.')
            elif source == 'session':
                try:
                    cancel_booking(int(ident), request.user)
                except ClassBooking.DoesNotExist:
                    messages.error(request, 'Booking not found.')
                except ValidationError as exc:
                    messages.error(request, '; '.join(exc.messages))
                else:
                    messages.success(request, 'Booking cancelled.')
            elif source == 'legacy':
                booking = get_object_or_404(ClientBooking, pk=int(ident), user=request.user)
                today = timezone.localdate()
                if booking.status == 'confirmed' and booking.class_date >= today:
                    booking.status = 'cancelled'
                    booking.save(update_fields=['status'])
                    messages.success(request, 'Booking cancelled.')
                else:
                    messages.error(request, 'This booking cannot be cancelled.')
            else:
                messages.error(request, 'Unknown booking type.')
        return redirect('myfit:client_bookings')

    today = timezone.localdate()
    now = timezone.localtime().time()
    entries = []
    for booking in ClientBooking.objects.filter(user=request.user):
        entries.append({
            'id': booking.pk, 'booking_source': 'legacy',
            'class_name': booking.class_name, 'class_date': booking.class_date,
            'start_time': booking.start_time, 'trainer': booking.trainer,
            'location': booking.location, 'duration_minutes': booking.duration_minutes,
            'status': booking.status,
        })
    for booking in ClassBooking.objects.filter(client__user=request.user).select_related(
        'session__coach__user', 'session__branch',
    ):
        session = booking.session
        entries.append({
            'id': booking.pk, 'booking_source': 'session',
            'class_name': session.title, 'class_date': session.date,
            'start_time': session.time,
            'trainer': session.coach.user.get_full_name() or session.coach.user.username,
            'location': session.branch.name,
            'duration_minutes': None,
            'status': booking.status.lower() if session.status != 'Cancelled' else 'cancelled',
        })
    upcoming = [b for b in entries if b['status'] == 'confirmed' and (
        b['class_date'] > today or (b['class_date'] == today and b['start_time'] > now)
    )]
    upcoming.sort(key=lambda b: (b['class_date'], b['start_time']))
    past = [b for b in entries if b not in upcoming]
    past.sort(key=lambda b: (b['class_date'], b['start_time']), reverse=True)
    return render(request, 'myfit/client_bookings.html', {
        'upcoming_bookings': upcoming, 'past_bookings': past,
        'upcoming_count': len(upcoming),
        'completed_count': sum(b['status'] == 'confirmed' for b in past),
        'cancelled_count': sum(b['status'] == 'cancelled' for b in entries),
    })


# ==========================================================
# MYFIT - TASK 2: MEMBERSHIP CHANGE REQUESTS
# Developer: Deshrao Saccaram
# ==========================================================

@login_required(login_url='myfit:login')
def client_membership(request):

    # Retrieve only memberships belonging to this client.
    memberships = (
        ClientMembership.objects
        .filter(user=request.user)
        .select_related('plan')
        .order_by('-start_date', '-id')
    )

    # Find the current valid membership.
    today = timezone.localdate()

    current_membership = memberships.filter(
        status__in=('active', 'scheduled'),
        start_date__lte=today,
        end_date__gte=today
    ).first()
    change_requests = (
        MembershipChangeRequest.objects
        .filter(membership__user=request.user)
        .select_related('membership__plan', 'requested_plan', 'reviewed_by')
        .order_by('-requested_at')
    )
    # Calculate remaining membership days.
    days_remaining = None

    if current_membership:
        days_remaining = (
            current_membership.end_date - today
        ).days + 1

    context = {
        'current_membership': current_membership,
        'memberships': memberships,
        'days_remaining': days_remaining,
        'change_requests': change_requests,
        'change_request_form': (
            MembershipChangeRequestForm(current_plan=current_membership.plan)
            if current_membership else None
        ),
    }

    return render(
        request,
        'myfit/client_membership.html',
        context
    )

# END TASK 2 - CLIENT MEMBERSHIP DASHBOARD


@role_required('Admin')
def manage_bookings(request):
    bookings = ClassBooking.objects.select_related(
        'session__branch', 'client__user',
    ).order_by('-booked_at')
    return render(request, 'myfit/manage_bookings.html', {'bookings': bookings})


@role_required('Admin')
def manage_payments(request):
    if request.method == 'POST':
        form = PaymentForm(request.POST)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.recorded_by = request.user
            payment.save()
            messages.success(request, 'Payment transaction recorded.')
            return redirect('myfit:manage_payments')
    else:
        form = PaymentForm()

    payments = Payment.objects.select_related(
        'client__user',
        'recorded_by',
    )
    return render(
        request,
        'myfit/manage_payments.html',
        {'form': form, 'payments': payments},
    )


# ==========================================================
# TASK 2 - ATTENDANCE MANAGEMENT
# Developer: Deshrao Saccaram
# ==========================================================

@login_required(login_url='myfit:login')
def attendance_dashboard(request):
    if not (request.user.is_staff or has_role(request.user, 'Admin')) or not request.user.has_perm(
        'core.view_attendancevisit'
    ):
        raise PermissionDenied

    open_visits = (
        AttendanceVisit.objects
        .filter(check_out__isnull=True)
        .select_related('membership__user', 'membership__plan')
        .order_by('check_in')
    )
    recent_visits = (
        AttendanceVisit.objects
        .select_related('membership__user', 'membership__plan')
        .order_by('-check_in')[:50]
    )
    context = {
        'open_visits': open_visits,
        'recent_visits': recent_visits,
        'check_in_form': (
            AttendanceCheckInForm()
            if request.user.has_perm('core.add_attendancevisit')
            else None
        ),
        'can_check_out': request.user.has_perm('core.change_attendancevisit'),
    }
    return render(request, 'myfit/attendance_dashboard.html', context)


@login_required(login_url='myfit:login')
@require_POST
def attendance_check_in(request):
    if (
        not request.user.is_staff
        or not request.user.has_perm('core.add_attendancevisit')
    ):
        raise PermissionDenied

    form = AttendanceCheckInForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Select a currently valid client membership.')
        return redirect('myfit:attendance_dashboard')

    try:
        visit = check_in_membership(form.cleaned_data['membership'].pk)
    except ClientMembership.DoesNotExist:
        messages.error(request, 'The selected membership is no longer available.')
    except ValidationError as error:
        messages.error(request, error.messages[0])
    except IntegrityError:
        if AttendanceVisit.objects.filter(
            membership=form.cleaned_data['membership'],
            check_out__isnull=True,
        ).exists():
            messages.error(
                request,
                'This client is already checked in for this membership.',
            )
        else:
            raise
    else:
        messages.success(
            request,
            f'{visit.membership.user.get_full_name() or visit.membership.user.username} '
            'was checked in successfully.',
        )
    return redirect('myfit:attendance_dashboard')


@login_required(login_url='myfit:login')
@require_POST
def attendance_check_out(request, visit_id):
    if not (request.user.is_staff or has_role(request.user, 'Admin')) or not request.user.has_perm(
        'core.change_attendancevisit'
    ):
        raise PermissionDenied

    try:
        visit = check_out_visit(visit_id)
    except AttendanceVisit.DoesNotExist as error:
        raise Http404 from error
    except ValidationError as error:
        messages.error(request, error.messages[0])
    else:
        messages.success(
            request,
            f'{visit.membership.user.get_full_name() or visit.membership.user.username} '
            'was checked out successfully.',
        )
    return redirect('myfit:attendance_dashboard')


@login_required(login_url='myfit:login')
def client_attendance_history(request):
    attendance_history = (
        AttendanceVisit.objects
        .filter(membership__user=request.user)
        .select_related('membership__plan')
        .order_by('-check_in')[:100]
    )
    return render(
        request,
        'myfit/client_attendance_history.html',
        {'attendance_history': attendance_history},
    )


# ==========================================================
# MYFIT - TASK 2: MEMBERSHIP CHANGE REQUESTS
# Developer: Deshrao Saccaram
# ==========================================================

@login_required(login_url='myfit:login')
@require_POST
def submit_membership_change_request(request):
    today = timezone.localdate()
    membership = (
        ClientMembership.objects
        .filter(
            user=request.user,
            status__in=('active', 'scheduled'),
            start_date__lte=today,
            end_date__gte=today,
        )
        .select_related('plan')
        .order_by('-start_date', '-id')
        .first()
    )
    if membership is None:
        messages.error(request, 'A current active membership is required to request a plan change.')
        return redirect('myfit:client_membership')

    form = MembershipChangeRequestForm(
        request.POST,
        current_plan=membership.plan,
    )
    if not form.is_valid():
        messages.error(
            request,
            f'Please correct the membership change request: {form.errors.as_text()}',
        )
        return redirect('myfit:client_membership')

    requested_plan = form.cleaned_data['requested_plan']
    try:
        with transaction.atomic():
            locked_membership = (
                ClientMembership.objects
                .select_for_update()
                .get(pk=membership.pk, user=request.user)
            )
            today = timezone.localdate()
            if not (
                locked_membership.status in ('active', 'scheduled')
                and locked_membership.start_date <= today <= locked_membership.end_date
            ):
                messages.error(request, 'Your current membership is no longer eligible for a plan change.')
                return redirect('myfit:client_membership')

            locked_plan = MembershipPlan.objects.select_for_update().get(
                pk=requested_plan.pk
            )
            if not locked_plan.is_active or locked_plan.pk == locked_membership.plan_id:
                messages.error(request, 'Select an active plan different from your current plan.')
                return redirect('myfit:client_membership')

            if MembershipChangeRequest.objects.filter(
                membership=locked_membership,
                status='pending',
            ).exists():
                messages.error(request, 'You already have a pending request for this membership.')
                return redirect('myfit:client_membership')

            change_request = form.save(commit=False)
            change_request.membership = locked_membership
            change_request.requested_plan = locked_plan
            change_request.status = 'pending'
            change_request.save()
    except IntegrityError:
        if MembershipChangeRequest.objects.filter(
            membership_id=membership.pk,
            status='pending',
        ).exists():
            messages.error(request, 'You already have a pending request for this membership.')
            return redirect('myfit:client_membership')
        raise

    messages.success(request, 'Your membership change request has been submitted for review.')
    return redirect('myfit:client_membership')


@membership_change_staff_required
def membership_requests(request):
    pending_requests = (
        MembershipChangeRequest.objects
        .filter(status='pending')
        .select_related(
            'membership__user',
            'membership__plan',
            'requested_plan',
        )
        .order_by('requested_at')
    )
    return render(
        request,
        'myfit/membership_requests.html',
        {'pending_requests': pending_requests},
    )


@membership_change_staff_required
@require_POST
def review_membership_change_request(request, request_id, decision):
    if decision not in ('approve', 'reject'):
        raise Http404

    with transaction.atomic():
        change_request = get_object_or_404(
            MembershipChangeRequest.objects.select_for_update(),
            pk=request_id,
        )
        if change_request.status != 'pending':
            messages.error(request, 'This membership change request has already been reviewed.')
            return redirect('myfit:membership_requests')

        if decision == 'reject':
            change_request.status = 'rejected'
            change_request.reviewed_by = request.user
            change_request.reviewed_at = timezone.now()
            change_request.save(
                update_fields=('status', 'reviewed_by', 'reviewed_at')
            )
            messages.success(request, 'The membership change request was rejected.')
            return redirect('myfit:membership_requests')

        membership = (
            ClientMembership.objects
            .select_for_update()
            .select_related('plan')
            .get(pk=change_request.membership_id)
        )
        requested_plan = MembershipPlan.objects.select_for_update().get(
            pk=change_request.requested_plan_id
        )
        today = timezone.localdate()
        if not (
            membership.status in ('active', 'scheduled')
            and membership.start_date <= today <= membership.end_date
        ):
            messages.error(request, 'The current membership is no longer valid; this request remains pending.')
            return redirect('myfit:membership_requests')
        if not requested_plan.is_active or requested_plan.pk == membership.plan_id:
            messages.error(request, 'The requested plan is no longer eligible; this request remains pending.')
            return redirect('myfit:membership_requests')

        try:
            assign_membership(
                user=membership.user,
                plan=requested_plan,
                start_date=membership.end_date + timedelta(days=1),
            )
        except ValidationError as error:
            messages.error(
                request,
                f'The request cannot be approved: {error.messages[0]}',
            )
            return redirect('myfit:membership_requests')

        change_request.status = 'approved'
        change_request.reviewed_by = request.user
        change_request.reviewed_at = timezone.now()
        change_request.save(
            update_fields=('status', 'reviewed_by', 'reviewed_at')
        )

    messages.success(request, 'The membership change request was approved.')
    return redirect('myfit:membership_requests')


# ==========================================================
# START TASK 2 - MEMBERSHIP PLAN MANAGEMENT
# Developer: Deshrao Saccaram


@permission_required('core.change_membershipplan', raise_exception=True)
def manage_plans(request):
    plans = MembershipPlan.objects.all().order_by('name')

    if request.method == 'POST':
        if not request.user.has_perm('core.add_membershipplan'):
            raise PermissionDenied

        form = MembershipPlanForm(request.POST)

        if form.is_valid():
            form.save()
            messages.success(request, 'Membership plan created successfully.')
            return redirect('myfit:manage_plans')
    else:
        form = MembershipPlanForm()

    return render(request, 'myfit/manage_plans.html', {
        'plans': plans,
        'form': form,
    })

@permission_required('core.change_membershipplan', raise_exception=True)
def edit_membership_plan(request, plan_id):
    # Find the membership plan using its database ID.
    # If it does not exist, Django returns a 404 error.
    plan = get_object_or_404(MembershipPlan, pk=plan_id)

    if request.method == 'POST':
        # Load submitted data into the EXISTING plan.
        form = MembershipPlanForm(request.POST, instance=plan)

        if form.is_valid():
            form.save()

            messages.success(
                request,
                'Membership plan updated successfully.'
            )

            return redirect('myfit:manage_plans')

    else:
        # Display the current details of the plan.
        form = MembershipPlanForm(instance=plan)

    return render(request, 'myfit/edit_membership_plan.html', {
        'form': form,
        'plan': plan,
    })

# END TASK 2 - MEMBERSHIP PLAN MANAGEMENT

def _coach_directory(user, query=''):
    from datetime import timedelta
    from .models import CoachClientAssignment
    today = timezone.localdate()
    week_start = today - timedelta(days=today.weekday())
    assignments = CoachClientAssignment.objects.filter(
        coach__user=user,
    ).select_related('client__user')
    if query:
        assignments = assignments.filter(
            Q(client__user__first_name__icontains=query)
            | Q(client__user__last_name__icontains=query)
            | Q(client__user__username__icontains=query)
            | Q(client__user__email__icontains=query)
        )
    rows = []
    for assignment in assignments:
        member = assignment.client.user
        latest = ClientMembership.objects.filter(user=member).select_related('plan').order_by('-start_date').first()
        last_workout = WorkoutRecord.objects.filter(user=member).order_by('-workout_date').first()
        visits = AttendanceVisit.objects.filter(
            membership__user=member, check_in__date__gte=week_start,
        ).count()
        rows.append({
            'name': member.get_full_name() or member.username,
            'email': member.email,
            'membership': latest.plan.name if latest else 'No membership',
            'plan': latest.plan.name if latest else 'No membership',
            'last_session': last_workout.workout_date.strftime('%d %b %Y') if last_workout else 'Not recorded',
            'visits_this_week': visits,
            'status': 'Active' if member.is_active else 'Inactive',
        })
    return rows


@role_required('Coach')
def coach_dashboard(request):
    from datetime import timedelta
    today = timezone.localdate()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    month_end = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
    clients = _coach_directory(request.user)
    visits = sum(row['visits_this_week'] for row in clients)
    coach = CoachProfile.objects.filter(user=request.user).first()
    sessions = ClassSession.objects.filter(coach=coach) if coach else ClassSession.objects.none()
    return render(request, 'myfit/coach_dashboard.html', {
        'active_client_count': len(clients),
        'sessions_this_week': sessions.filter(date__range=(week_start, week_end)).count(),
        'avg_visits_per_week': round(visits / len(clients), 1) if clients else 0,
        'classes_this_month': sessions.filter(date__gte=today.replace(day=1), date__lt=month_end).count(),
        'clients': clients,
    })


@role_required('Coach')
def coach_clients(request):
    clients = _coach_directory(request.user, request.GET.get('q', '').strip()[:100])
    active = sum(client['visits_this_week'] > 0 for client in clients)
    return render(request, 'myfit/coach_clients.html', {
        'clients': clients, 'total_clients': len(clients),
        'active_this_week': active,
        'active_percent': round(100 * active / len(clients)) if clients else 0,
        'need_attention': sum(client['visits_this_week'] == 0 for client in clients),
        'goals_achieved': 0,  # no goal achievement model exists yet
    })

#jush=====
from .models import ClassSession, ClassBooking
from .services import book_client_into_class, cancel_booking
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect


# ==========================================================
# MYFIT - TASK 2: CLIENT MEMBERSHIP ASSIGNMENT
# Developer: Deshrao Saccaram


@permission_required('core.add_clientmembership', raise_exception=True)
def assign_client_membership(request):

    if request.method == 'POST':
        form = ClientMembershipAssignmentForm(request.POST)

        if form.is_valid():
            user = form.cleaned_data['user']
            plan = form.cleaned_data['plan']
            start_date = form.cleaned_data['start_date']

            try:
                membership = assign_membership(
                    user=user,
                    plan=plan,
                    start_date=start_date
                )

            except ValidationError as error:
                form.add_error(None, error)

            else:
                messages.success(
                    request,
                    f'Membership assigned successfully to '
                    f'{membership.user.username}.'
                )
                return redirect('myfit:assign_client_membership')

    else:
        form = ClientMembershipAssignmentForm()

    return render(
        request,
        'myfit/assign_client_membership.html',
        {'form': form}
    )

# END TASK 2 - CLIENT MEMBERSHIP ASSIGNMENT

def class_list(request):
    today = timezone.localdate()
    classes = ClassSession.objects.filter(status='Scheduled', date__gte=today).order_by('date', 'time')
    return render(request, 'myfit/class_list.html', {'classes': classes})

@login_required(login_url='myfit:login')
@require_POST
def book_class_view(request, session_id):
    if not has_role(request.user, 'Client') or not hasattr(request.user, 'client_profile'):
        raise PermissionDenied('Only registered clients can book classes.')
    try:
        book_client_into_class(session_id, request.user.client_profile)
    except ClassSession.DoesNotExist:
        raise Http404('Class not found.')
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
    else:
        messages.success(request, 'Class booked successfully!')
    return redirect('myfit:class_list')


@login_required(login_url='myfit:login')
def manage_classes(request):
    if has_role(request.user, 'Admin'):
        classes = ClassSession.objects.all().order_by('-date')
    elif has_role(request.user, 'Coach') and hasattr(request.user, 'coach_profile'):
        classes = ClassSession.objects.filter(coach=request.user.coach_profile).order_by('-date')
    else:
        raise PermissionDenied('Only Admin and Coach accounts can manage classes.')
    classes = classes.select_related('coach__user', 'branch').prefetch_related('bookings__client__user')
    from django.db.models import Count
    totals = classes.aggregate(
        total=Count('pk', distinct=True),
        scheduled=Count('pk', filter=Q(status='Scheduled'), distinct=True),
        cancelled=Count('pk', filter=Q(status='Cancelled'), distinct=True),
    )
    return render(request, 'myfit/manage_classes.html', {
        'classes': classes,
        'class_totals': totals,
        'confirmed_bookings_count': ClassBooking.objects.filter(
            session__in=classes, status='Confirmed').count(),
    })


@login_required(login_url='myfit:login')
@transaction.atomic
def class_session_edit(request, session_id=None):
    """Admin manages any class; Coach creates/edits their own classes."""
    from .forms import ClassSessionForm

    is_admin = has_role(request.user, 'Admin')
    is_coach = has_role(request.user, 'Coach')
    if not (is_admin or is_coach):
        raise PermissionDenied('Only gym managers and coaches can edit classes.')
    session = get_object_or_404(ClassSession, pk=session_id) if session_id else None
    if not is_admin and (
        not hasattr(request.user, 'coach_profile')
        or (session and session.coach_id != request.user.coach_profile.pk)
    ):
        raise PermissionDenied('You may edit only your own classes.')

    original_status = session.status if session else None
    original_coach = session.coach if session else None
    form = ClassSessionForm(request.POST or None, request.FILES or None, instance=session)
    if not is_admin:
        form.fields['coach'].queryset = CoachProfile.objects.filter(user=request.user)
        form.fields['coach'].initial = request.user.coach_profile
    if request.method == 'POST' and form.is_valid():
        obj = form.save(commit=False)
        if not is_admin:
            obj.coach = request.user.coach_profile
        already_booked = (
            ClassBooking.objects.filter(session=session, status='Confirmed').count()
            if session else 0
        )
        if obj.capacity < already_booked:
            form.add_error('capacity', 'Capacity cannot be below the number of confirmed bookings.')
        else:
            obj.save()
            if obj.status == 'Cancelled' and original_status != 'Cancelled':
                # Keep booking records for history instead of deleting them.
                for booking in ClassBooking.objects.filter(
                    session=obj, status='Confirmed',
                ).select_related('client__user'):
                    booking.status = 'Cancelled'
                    booking.save(update_fields=['status'])
                    notify(
                        booking.client.user, 'Class cancelled',
                        f'{obj.title} on {obj.date:%d %b %Y} has been cancelled.',
                        reverse('myfit:client_bookings'),
                    )
            if is_admin:
                notify(
                    obj.coach.user, 'Class schedule updated',
                    f'Your assigned class {obj.title} on {obj.date:%d %b %Y} is {obj.status.lower()}.',
                    reverse('myfit:manage_classes'),
                )
                if original_coach and original_coach.pk != obj.coach_id:
                    notify(
                        original_coach.user, 'Class reassigned',
                        f'{obj.title} is no longer assigned to you.',
                        reverse('myfit:manage_classes'),
                    )
            messages.success(request, 'Class saved successfully.')
            return redirect('myfit:manage_classes')
    return render(request, 'myfit/class_session_form.html', {
        'form': form, 'session': session,
    })

@login_required(login_url='myfit:login')
@require_POST
def cancel_booking_view(request, booking_id):
    try:
        cancel_booking(booking_id, request.user)
    except ClassBooking.DoesNotExist:
        raise Http404('Booking not found.')
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
    else:
        messages.success(request, 'Booking cancelled.')
    if has_role(request.user, 'Admin') or has_role(request.user, 'Coach'):
        return redirect('myfit:manage_classes')
    return redirect('myfit:client_bookings')
#<----



#<<<<<<<<<<<---------Loick
# Public website, administration and support — all in the existing core app.
from django.contrib.auth import get_user_model
from .permissions import has_role
from .models import SupportTicket
from .forms import BranchForm, CoachAccountForm, AccountDetailsForm, ContactSubmissionForm, ClientProfileForm, CoachProfileForm
 
def branches(request):
    # Exclude inactive branches so the Admin toggle controls public visibility.
    return render(request, 'myfit/branches.html', {
        'branches': Branch.objects.filter(is_active=True),
        'site_images': website_images(),
        # Branch operational status is a database field; no hardcoded Plaisance exception.
    })
 
 
def coaches(request):
    # Load real coach accounts, their branches and their many-to-many specialties.
    # select_related/prefetch_related avoid many repeated database queries.
    return render(request, 'myfit/coaches.html', {
        'coaches': CoachProfile.objects.filter(user__is_active=True).select_related('user','branch').prefetch_related('specialties'),
        'site_images': website_images(),
        'filter_branches': Branch.objects.filter(is_active=True, operational_status='Open'),
        'filter_specialties': CoachSpecialty.objects.filter(is_active=True),
    })
 
 
def plans(request):
    # Plan updates made by Task 2 automatically appear on this page. No duplicate prices.
    return render(request, 'myfit/plans.html', {
        'membership_plans': MembershipPlan.objects.filter(is_active=True).order_by('price'),
        'site_images': website_images(),
    })
 
 
def contact(request):
    initial = {'topic': request.GET.get('topic', '')[:100]}
    plan_name = request.GET.get('plan_name', '')[:100]
    if plan_name: initial['subject'] = f'Membership enquiry: {plan_name}'
    form = ContactSubmissionForm(request.POST or None, initial=initial)
    if request.method == 'POST' and form.is_valid():
        if form.cleaned_data['kind'] == 'ticket' and not request.user.is_authenticated:
            form.add_error('kind', 'Log in to create a trackable support ticket. You can send a general enquiry without an account.')
        else:
            ticket = form.save(commit=False)
            if request.user.is_authenticated:
                ticket.user = request.user
            ticket.save()
            messages.success(request, f'Your request MF-{ticket.pk} was saved successfully.')
            return redirect('myfit:contact')
    my_tickets = (SupportTicket.objects.filter(user=request.user, kind='ticket')
                  if request.user.is_authenticated else SupportTicket.objects.none())
    return render(request, 'myfit/contact.html', {
        'contact_form': form, 'my_tickets': my_tickets,
        'contact_branches': Branch.objects.filter(is_active=True),
    })
 
 
@role_required('Admin')
def manage_branches(request):
    return render(request, 'myfit/manage_branches.html', {
        'branches': Branch.objects.all().order_by('name'),
        'total_branch_count': Branch.objects.count(),
        'active_branch_count': Branch.objects.filter(is_active=True, operational_status='Open').count(),
        'attention_branch_count': Branch.objects.exclude(is_active=True, operational_status='Open').count(),
    })
 
 
@role_required('Admin')
def branch_edit(request, branch_id=None):
    branch = get_object_or_404(Branch, pk=branch_id) if branch_id else None
    form = BranchForm(request.POST or None, request.FILES or None, instance=branch)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Branch saved successfully.')
        return redirect('myfit:manage_branches')
    return render(request, 'myfit/management_form.html', {'form': form, 'heading': 'Edit branch' if branch else 'Add branch', 'back_url':reverse('myfit:manage_branches')})
 
 
@role_required('Admin')
@require_POST
def branch_toggle(request, branch_id):
    branch = get_object_or_404(Branch, pk=branch_id)
    branch.is_active = not branch.is_active
    branch.save(update_fields=['is_active', 'updated_at'])
    messages.success(request, f'{branch.name} {"activated" if branch.is_active else "deactivated"}.')
    return redirect('myfit:manage_branches')
 
 
@role_required('Admin')
def manage_coaches(request):
    return render(request, 'myfit/manage_coaches.html', {
        'coaches': CoachProfile.objects.select_related('user','branch').prefetch_related('specialties').order_by('user__first_name'),
        'total_coach_count': CoachProfile.objects.count(),
        'active_coach_count': CoachProfile.objects.filter(user__is_active=True).count(),
        'specialty_count': CoachSpecialty.objects.filter(coaches__isnull=False).distinct().count(),
        'branches': Branch.objects.filter(is_active=True),
        'specialties': CoachSpecialty.objects.filter(is_active=True),
    })
 
 
@role_required('Admin')
@transaction.atomic
def coach_edit(request, coach_id=None):
    coach = get_object_or_404(CoachProfile.objects.select_related('user'), pk=coach_id) if coach_id else None
    form = CoachAccountForm(request.POST or None, request.FILES or None, coach=coach)
    if request.method == 'POST' and form.is_valid():
        User = get_user_model()
        if coach:
            user = coach.user
        else:
            user = User()
        for field in ('username', 'first_name', 'last_name', 'email', 'is_active'):
            setattr(user, field, form.cleaned_data[field])
        if form.cleaned_data['password']:
            user.set_password(form.cleaned_data['password'])
        user.save()
        group, _ = Group.objects.get_or_create(name='Coach')
        user.groups.add(group)
        if coach is None:
            coach = CoachProfile(user=user)
        if form.cleaned_data['remove_image'] and coach.image:
            coach.image = None
        if form.cleaned_data.get('image'):
            coach.image = form.cleaned_data['image']
        for field in ('branch', 'bio', 'phone'):
            setattr(coach, field, form.cleaned_data[field])
        coach.save()
        coach.specialties.set(form.cleaned_data['specialties'])
        messages.success(request, 'Coach saved successfully.')
        return redirect('myfit:manage_coaches')
    return render(request, 'myfit/management_form.html', {'form':form, 'heading': 'Edit coach' if coach else 'Add coach', 'back_url':reverse('myfit:manage_coaches')})
 
 
@role_required('Admin')
@require_POST
def coach_toggle(request, coach_id):
    coach = get_object_or_404(CoachProfile.objects.select_related('user'), pk=coach_id)
    coach.user.is_active = not coach.user.is_active
    coach.user.save(update_fields=['is_active'])
    messages.success(request, 'Coach account status updated.')
    return redirect('myfit:manage_coaches')
 
 
@login_required(login_url='myfit:login')
@transaction.atomic
def edit_profile(request):
    # Exactly four editable personal details per role:
    # User.first_name, User.last_name, User.email, plus profile.phone.
    # Other structural fields remain in models for the team's existing logic.
    if has_role(request.user, 'Coach'):
        profile, _ = CoachProfile.objects.get_or_create(user=request.user)
        profile_form_class = CoachProfileForm
    elif has_role(request.user, 'Client'):
        profile, _ = ClientProfile.objects.get_or_create(user=request.user)
        profile_form_class = ClientProfileForm
    else:
        raise PermissionDenied('Only clients and coaches can use this profile editor.')
    account_form = AccountDetailsForm(request.POST or None, instance=request.user, prefix='account')
    profile_form = profile_form_class(request.POST or None, request.FILES or None, instance=profile, prefix='profile')
    if request.method == 'POST' and account_form.is_valid() and profile_form.is_valid():
        # Unique email isn't a DB constraint in the default Django User model.
        email = account_form.cleaned_data['email'].strip()
        if get_user_model().objects.filter(email__iexact=email).exclude(pk=request.user.pk).exists():
            account_form.add_error('email', 'An account is already using this email.')
        else:
            account_form.save()
            profile_form.save()
            messages.success(request, 'Profile updated successfully.')
            return redirect('myfit:edit_profile')
    return render(request, 'myfit/profile_edit.html', {
        'account_form': account_form, 'profile_form': profile_form,
    })
 
 
@role_required('Admin')
def specialty_manage(request):
    specialties = CoachSpecialty.objects.all()
    return render(request, 'myfit/specialty_manage.html', {'specialties': specialties})
 
 
@role_required('Admin')
def specialty_edit(request, specialty_id=None):
    from django import forms
    class SpecialtyForm(forms.ModelForm):
        class Meta:
            model = CoachSpecialty
            fields = ('name','is_active')
    instance = get_object_or_404(CoachSpecialty, pk=specialty_id) if specialty_id else None
    form = SpecialtyForm(request.POST or None, instance=instance)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Specialty saved.')
        return redirect('myfit:specialty_manage')
    return render(request, 'myfit/management_form.html', {'form': form, 'heading': 'Edit specialty' if instance else 'Add specialty', 'back_url': reverse('myfit:specialty_manage')})
 
 
@role_required('Admin')
def support_manage(request):
    return render(request, 'myfit/support_manage.html', {
        'tickets': SupportTicket.objects.select_related('user').all(),
    })
 
 

@role_required("Admin")
@require_POST
def support_update(request, ticket_id):
    ticket = get_object_or_404(
        SupportTicket,
        pk=ticket_id,
    )

    new_status = request.POST.get("status")

    if new_status not in dict(SupportTicket.STATUS_CHOICES):
        return HttpResponseBadRequest("Invalid ticket status.")

    old_status = ticket.status

    if old_status != new_status:
        ticket.status = new_status
        ticket.save(update_fields=["status", "updated_at"])

        if ticket.kind == "ticket" and ticket.user:
            Notification.objects.create(
                user=ticket.user,
                title="Support ticket status updated",
                message=(
                    f"Your ticket MF-{ticket.pk} is now "
                    f"{ticket.get_status_display()}."
                ),
                link=f"/support/tickets/{ticket.pk}/",
            )

    messages.success(request, f"Request MF-{ticket.pk} updated.")
    return redirect("myfit:support_manage")

 
#Wizzy dev TASK 5 - NOTIFICATIONS AND SUPPORT - -------------------

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
    
def _notification_redirect(request, default="myfit:home"):
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
@login_required(login_url='myfit:login')
def create_support_ticket(request):
    """Create a ticket using fields that really exist on SupportTicket."""
    if request.method == 'POST':
        subject = request.POST.get('subject', '').strip()[:130]
        description = request.POST.get('description', '').strip()[:2000]
        if not subject or len(description) < 10:
            messages.error(request, 'Enter a subject and a description of at least 10 characters.')
        elif not request.user.email:
            messages.error(request, 'Add an email address to your account before opening a ticket.')
        else:
            with transaction.atomic():
                ticket = SupportTicket.objects.create(
                    user=request.user, kind='ticket',
                    name=request.user.get_full_name() or request.user.username,
                    email=request.user.email, topic='Support',
                    subject=subject, message=description,
                )
                notify_ticket_update(ticket, 'Support ticket received',
                                     f'Your request MF-{ticket.pk} was received.')
            messages.success(request, 'Your support ticket was created.')
            return redirect('myfit:support_ticket_detail', ticket_id=ticket.pk)
    return render(request, 'myfit/support_ticket_form.html')


#list the user's current tickets
@login_required(login_url='myfit:login')
def support_ticket_list(request):
    tickets = SupportTicket.objects.filter(kind='ticket')
    if not has_role(request.user, 'Admin'):
        tickets = tickets.filter(user=request.user)
    return render(request, 'myfit/support_ticket_list.html', {
        'tickets': tickets.order_by('-updated_at'),
        'is_admin': has_role(request.user, 'Admin'),
    })


#View a ticket and its messages

@login_required(login_url="myfit:login")
def support_ticket_detail(request, ticket_id):
    ticket = get_object_or_404(
        SupportTicket,
        pk=ticket_id,
        kind="ticket",
    )

    is_admin = has_role(request.user, "Admin")

    # A client can only access their own ticket.
    if ticket.user_id != request.user.pk and not is_admin:
        raise PermissionDenied(
            "You cannot access another user's support ticket."
        )

    reply_form = SupportTicketReplyForm()

    if request.method == "POST":
        reply_form = SupportTicketReplyForm(request.POST)

        if reply_form.is_valid():
            # Clients cannot reply to closed/resolved tickets.
            if not is_admin and ticket.status == "resolved":
                messages.error(
                    request,
                    "This ticket has been resolved. "
                    "Contact support if you need further assistance.",
                )
                return redirect(
                    "myfit:support_ticket_detail",
                    ticket_id=ticket.pk,
                )

            reply = reply_form.save(commit=False)
            reply.ticket = ticket
            reply.sender = request.user

            # Only administrators may create internal notes.
            reply.is_internal_note = (
                is_admin
                and request.POST.get("is_internal_note") == "on"
            )
            reply.save()

            # Notify the client when an admin sends a public reply.
            if is_admin and not reply.is_internal_note and ticket.user:
                Notification.objects.create(
                    user=ticket.user,
                    title="Support ticket updated",
                    message=f"Your ticket MF-{ticket.pk} has a new reply.",
                    link=f"/support/tickets/{ticket.pk}/",
                )

            messages.success(request, "Your reply has been sent.")
            return redirect(
                "myfit:support_ticket_detail",
                ticket_id=ticket.pk,
            )

    conversation = ticket.messages.select_related("sender")

    # Never expose private admin notes to clients.
    if not is_admin:
        conversation = conversation.filter(is_internal_note=False)

    return render(
        request,
        "myfit/support_ticket_detail.html",
        {
            "ticket": ticket,
            "conversation": conversation,
            "reply_form": reply_form,
            "is_admin": is_admin,
        },
    )

 