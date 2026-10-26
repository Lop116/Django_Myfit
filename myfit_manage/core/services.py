from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import ClassSession, ClassBooking

def trigger_notification(message, user):
    print(f"NOTIFICATION to {user.username}: {message}")

@transaction.atomic
def book_client_into_class(session_id, client):
    session = ClassSession.objects.select_for_update().get(id=session_id)
    if session.status != 'Scheduled':
        raise ValidationError("This class is no longer available.")
    if session.date < timezone.localdate():
        raise ValidationError("Cannot book a class in the past.")
    if ClassBooking.objects.filter(session=session, client=client, status='Confirmed').exists():
        raise ValidationError("You already have a confirmed booking for this class.")
    if session.spaces_left <= 0:
        raise ValidationError("This class is fully booked.")

    booking = ClassBooking.objects.create(session=session, client=client, status='Confirmed')
    trigger_notification(f"Successfully booked {session.title}", client.user)
    return booking

@transaction.atomic
def cancel_booking(booking_id, user):
    booking = ClassBooking.objects.get(id=booking_id)
    is_client_owner = hasattr(user, 'client_profile') and booking.client == user.client_profile
    is_coach = hasattr(user, 'coach_profile') and booking.session.coach == user.coach_profile
    is_admin = user.groups.filter(name='Admin').exists() or user.is_superuser

    if not (is_client_owner or is_coach or is_admin):
        raise ValidationError("Permission denied.")
    if booking.status == 'Cancelled':
        raise ValidationError("Booking is already cancelled.")

    booking.status = 'Cancelled'
    booking.save()
    trigger_notification(f"Booking for {booking.session.title} was cancelled.", booking.client.user)
    return booking
#<----