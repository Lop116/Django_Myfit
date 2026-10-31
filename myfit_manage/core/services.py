#jush
"""Create/cancel bookings using the canonical ClassBooking model."""
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


@transaction.atomic
def book_client_into_class(session_id, client):
    # Lock the class row on databases that support SELECT ... FOR UPDATE.
    session = ClassSession.objects.select_for_update().get(pk=session_id)
    if session.status != 'Scheduled' or not _is_future(session):
        raise ValidationError('This class is no longer available.')
    if not session.branch.is_active or not session.coach.user.is_active:
        raise ValidationError('This class is not available for booking.')
    if not client.user.is_active:
        raise ValidationError('Your account is inactive.')

    today = timezone.localdate()
    eligible = ClientMembership.objects.filter(
        user=client.user, status__in=['active', 'scheduled'],
        start_date__lte=today, end_date__gte=today,
    ).exists()
    if not eligible:
        raise ValidationError('An active MyFit membership is required to book classes.')
    permitted = ClientMembership.objects.filter(
        user=client.user, status__in=['active', 'scheduled'],
        start_date__lte=today, end_date__gte=today,
        plan__is_active=True, plan__allows_classes=True,
    ).exists()
    if not permitted:
        raise ValidationError('Your current membership plan does not include classes.')
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

    booking.status = 'Cancelled'
    booking.save(update_fields=['status'])
    notify(
        booking.client.user, 'Class booking cancelled',
        f'Your booking for {booking.session.title} was cancelled.',
        reverse('myfit:client_bookings'),
    )
    return booking