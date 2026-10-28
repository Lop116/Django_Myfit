"""Statistics for the Admin dashboard (Task 6).

Kept in its own module so it does not collide with other members' files.
Every number is a plain database query against the merged models, so a wrong
field name or status value fails loudly in the tests instead of showing 0.
"""
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone

from .models import (
    AttendanceVisit,
    Branch,
    ClassBooking,
    ClassSession,
    ClientMembership,
    MembershipChangeRequest,
    SupportTicket,
)


def _role_counts(role):
    users = get_user_model().objects.filter(groups__name=role).distinct()
    return {"total": users.count(), "active": users.filter(is_active=True).count()}


def _membership_stats(today):
    # Same rule as ClientMembership.current_status: a stored "active" or
    # "scheduled" membership is judged by its dates; "suspended" stays suspended.
    dated = Q(status__in=("active", "scheduled"))
    memberships = ClientMembership.objects
    return {
        "active": memberships.filter(dated, start_date__lte=today, end_date__gte=today).count(),
        "expired": memberships.filter(
            Q(status="expired") | (dated & Q(end_date__lt=today))
        ).count(),
        "suspended": memberships.filter(status="suspended").count(),
        "pending_requests": MembershipChangeRequest.objects.filter(status="pending").count(),
    }


def get_dashboard_stats():
    """Everything the Admin dashboard shows."""
    today = timezone.localdate()
    return {
        "clients": _role_counts("Client"),
        "coaches": _role_counts("Coach"),
        "branches": {
            "total": Branch.objects.count(),
            "active": Branch.objects.filter(is_active=True).count(),
        },
        "memberships": _membership_stats(today),
        "classes": {
            "scheduled": ClassSession.objects.filter(status="Scheduled").count(),
            "cancelled": ClassSession.objects.filter(status="Cancelled").count(),
        },
        "bookings": {
            "total": ClassBooking.objects.count(),
            "confirmed": ClassBooking.objects.filter(status="Confirmed").count(),
        },
        "attendance": {"today": AttendanceVisit.objects.filter(check_in__date=today).count()},
        "support": {"open": SupportTicket.objects.exclude(status="resolved").count()},
    }
