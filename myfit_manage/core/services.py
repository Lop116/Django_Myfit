"""Create/cancel bookings and class status changes using the canonical
ClassBooking / ClassSession models. All multi-row changes are atomic."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from .models import ClassBooking, ClassSession, ClientMembership
from .notifications import notify
from .permissions import has_role


def _is_future(session):
    today = timezone.localdate()
    return session.date > today or (
        session.date == today and session.time > timezone.localtime().time()
    )


def _display_name(user):
    return user.get_full_name() or user.username


def current_class_membership(user):
    """The member's currently valid membership, or None.

    Single source of truth for booking eligibility (used by the booking
    service and by the class list to explain why booking is unavailable).
    """
    today = timezone.localdate()
    return (
        ClientMembership.objects
        .filter(user=user, status__in=('active', 'scheduled'),
                start_date__lte=today, end_date__gte=today)
        .select_related('plan')
        .order_by('-plan__allows_classes', '-end_date')
        .first()
    )


def booking_eligibility_error(user):
    """Return a message explaining why `user` cannot book classes, or None."""
    membership = current_class_membership(user)
    if membership is None:
        return 'An active MyFit membership is required to book classes.'
    if not membership.plan.allows_classes:
        return (f'Your {membership.plan.name} plan does not include group classes. '
                'Request a plan change from your Membership page.')
    return None


@transaction.atomic
def book_client_into_class(session_id, client):
    # Lock the class row. On SQLite the whole write transaction is serialised
    # (settings use transaction_mode=IMMEDIATE), so two simultaneous bookings
    # cannot both see the last free place.
    session = ClassSession.objects.select_for_update().select_related(
        'branch', 'coach__user',
    ).get(pk=session_id)
    if session.status != 'Scheduled' or not _is_future(session):
        raise ValidationError('This class is no longer available.')
    if not session.branch.is_active or not session.coach.user.is_active:
        raise ValidationError('This class is not available for booking.')
    if not client.user.is_active:
        raise ValidationError('Your account is inactive.')

    eligibility_error = booking_eligibility_error(client.user)
    if eligibility_error:
        raise ValidationError(eligibility_error)
    if ClassBooking.objects.filter(
        session=session, client=client, status='Confirmed',
    ).exists():
        raise ValidationError('You already have a confirmed booking for this class.')
    if session.spaces_left <= 0:
        raise ValidationError('This class is fully booked.')

    booking = ClassBooking.objects.create(
        session=session, client=client, status='Confirmed',
    )
    notify(
        client.user, 'Class booking confirmed',
        f'You booked {session.title} on {session.date:%d %b %Y} at {session.time:%H:%M}.',
        reverse('myfit:client_bookings'),
    )
    return booking


def _mark_cancelled(booking):
    booking.status = 'Cancelled'
    booking.cancelled_at = timezone.now()
    booking.save(update_fields=['status', 'cancelled_at'])


@transaction.atomic
def cancel_booking(booking_id, user):
    booking = ClassBooking.objects.select_for_update().select_related(
        'client__user', 'session__coach__user',
    ).get(pk=booking_id)
    is_owner = booking.client.user_id == user.pk
    is_coach = booking.session.coach.user_id == user.pk and has_role(user, 'Coach')
    is_admin = has_role(user, 'Admin')
    if not (is_owner or is_coach or is_admin):
        raise PermissionDenied('You cannot cancel another member\'s booking.')
    if booking.status == 'Cancelled':
        raise ValidationError('Booking is already cancelled.')
    if is_owner and not _is_future(booking.session):
        raise ValidationError('Past bookings cannot be cancelled.')

    # The row is kept (status change only) so booking history is preserved
    # and the place is released for capacity counts.
    _mark_cancelled(booking)
    session = booking.session
    if is_owner:
        notify(
            booking.client.user, 'Class booking cancelled',
            f'Your booking for {session.title} on {session.date:%d %b %Y} was cancelled.',
            reverse('myfit:client_bookings'),
        )
        notify(
            session.coach.user, 'Client cancelled a booking',
            f'{_display_name(booking.client.user)} cancelled their place in '
            f'{session.title} on {session.date:%d %b %Y}.',
            reverse('myfit:manage_classes'),
        )
    else:
        notify(
            booking.client.user, 'Class booking cancelled',
            f'MyFit staff removed your booking for {session.title} on {session.date:%d %b %Y}.',
            reverse('myfit:client_bookings'),
        )
    return booking


def cancel_session_bookings(session):
    """Cancel every confirmed booking of a cancelled class and tell the members."""
    bookings = ClassBooking.objects.select_for_update().filter(
        session=session, status='Confirmed',
    ).select_related('client__user')
    cancelled = 0
    for booking in bookings:
        _mark_cancelled(booking)
        cancelled += 1
        notify(
            booking.client.user, 'Class cancelled',
            f'{session.title} on {session.date:%d %b %Y} has been cancelled.',
            reverse('myfit:client_bookings'),
        )
    return cancelled


def notify_schedule_change(session):
    """Tell booked members that the date, time or place of their class changed."""
    for booking in session.bookings.filter(status='Confirmed').select_related('client__user'):
        notify(
            booking.client.user, 'Class details updated',
            f'{session.title} is now on {session.date:%d %b %Y} at {session.time:%H:%M} '
            f'({session.branch.name}).',
            reverse('myfit:client_bookings'),
        )


@transaction.atomic
def change_class_status(session_id, new_status, user):
    """Publish / cancel / complete a class (Admin, or the class's own Coach)."""
    session = ClassSession.objects.select_for_update().select_related(
        'coach__user', 'branch',
    ).get(pk=session_id)
    is_admin = has_role(user, 'Admin')
    is_own_coach = has_role(user, 'Coach') and session.coach.user_id == user.pk
    if not (is_admin or is_own_coach):
        raise PermissionDenied('You may change only your own classes.')
    if new_status not in dict(ClassSession.STATUS_CHOICES):
        raise ValidationError('Unknown class status.')
    if session.status == new_status:
        return session, 0
    if session.status == 'Cancelled':
        raise ValidationError('A cancelled class cannot be reopened; create a new class instead.')
    if new_status == 'Scheduled' and not _is_future(session):
        raise ValidationError('Only future classes can be published. Update the date first.')

    session.status = new_status
    session.save(update_fields=['status'])
    cancelled = cancel_session_bookings(session) if new_status == 'Cancelled' else 0
    if is_admin and session.coach.user_id != user.pk:
        notify(
            session.coach.user, 'Class schedule updated',
            f'Your assigned class {session.title} on {session.date:%d %b %Y} is {session.get_status_display().lower()}.',
            reverse('myfit:manage_classes'),
        )
    return session, cancelled
