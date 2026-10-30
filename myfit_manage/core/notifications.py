from django.urls import reverse

from .models import Notification


def notify(user, type, title, message, link=""):
    """Create one notification for one user. Returns None if user is None."""
    if user is None:
        return None
    return Notification.objects.create(
        user=user,
        type=type,
        title=title,
        message=message,
        link=link,
    )


def notify_ticket_update(ticket, title, message):
    """Notify the client who owns a support ticket."""
    return notify(
        ticket.client,
        Notification.Type.SUPPORT_UPDATE,
        title,
        message,
        reverse("myfit:support_ticket_detail", args=[ticket.pk]),
    )


def notify_ticket_admin(ticket, title, message):
    """Notify the admin assigned to a ticket, if there is one."""
    return notify(
        ticket.assigned_admin,
        Notification.Type.SUPPORT_UPDATE,
        title,
        message,
        reverse("myfit:support_ticket_detail", args=[ticket.pk]),
    )