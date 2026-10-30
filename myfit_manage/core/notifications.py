"""Persistence helpers for the single core.Notification model."""
from django.urls import reverse
from .models import Notification


def notify(user, title, message, link=""):
    if user is None:
        return None
    return Notification.objects.create(
        user=user, title=title, message=message, link=link,
    )


def notify_ticket_update(ticket, title, message):
    return notify(
        ticket.user,
        title,
        message,
        reverse('myfit:support_ticket_detail', args=[ticket.pk]),
    )

 