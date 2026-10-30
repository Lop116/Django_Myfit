"""Statistics for the Admin dashboard (Task 6).

Kept in its own module so it does not collide with other members' files.

The dashboard is built before the Task 2-5 models are merged, so every
section here degrades gracefully: if a model (or an expected field) is not
in the project yet, its value is ``None`` and the template shows "—" with a
"not connected yet" note. That list doubles as an integration checklist.

Where the spec model exists (ClientMembership, ClassBooking, ...) it is used;
otherwise we fall back to the model already in the repo (MembershipPass,
ClientBooking) so the dashboard shows real numbers today.

INTEGRATION: the field names/status values marked below are assumptions based
on the task sheet. Check them against the real models once merged.
"""
from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.exceptions import FieldError
from django.db import models
from django.db.models import Q
from django.utils import timezone


def _get_model(name):
    """Return core.<name> or None if that model is not in the project yet."""
    try:
        return apps.get_model("core", name)
    except LookupError:
        return None


def _safe(compute):
    """Run a count; None if a field/lookup we assumed does not exist."""
    try:
        return compute()
    except (FieldError, LookupError):
        return None


def _first_field(model, candidates):
    """First candidate field name that exists on the model, else None."""
    for name in candidates:
        try:
            model._meta.get_field(name)
        except Exception:  # FieldDoesNotExist
            continue
        return name
    return None


def _role_counts(role):
    users = get_user_model().objects.filter(groups__name=role).distinct()
    return {"total": users.count(), "active": users.filter(is_active=True).count()}


def _membership_stats(today):
    """Active / expired memberships and pending membership requests."""
    stats = {"active": None, "expired": None, "pending_requests": None}

    ClientMembership = _get_model("ClientMembership")
    MembershipPass = _get_model("MembershipPass")

    if ClientMembership is not None:
        # INTEGRATION: assumes status in {"active","expired","suspended"} + end_date
        objects = ClientMembership.objects
        stats["active"] = _safe(
            lambda: objects.filter(status="active", end_date__gte=today).count()
        )
        stats["expired"] = _safe(
            lambda: objects.filter(Q(status="expired") | Q(end_date__lt=today)).count()
        )
    elif MembershipPass is not None:
        # Fallback: the existing MembershipPass model.
        objects = MembershipPass.objects
        stats["active"] = objects.filter(status="active").filter(
            Q(expiry_date__isnull=True) | Q(expiry_date__gte=today)
        ).count()
        stats["expired"] = objects.filter(
            Q(status="expired") | Q(status="active", expiry_date__lt=today)
        ).count()

    ChangeRequest = _get_model("MembershipChangeRequest")
    if ChangeRequest is not None:
        # INTEGRATION: assumes status == "pending"
        stats["pending_requests"] = _safe(
            lambda: ChangeRequest.objects.filter(status="pending").count()
        )
    elif MembershipPass is not None:
        # Fallback: passes still waiting to be approved.
        stats["pending_requests"] = MembershipPass.objects.filter(status="pending").count()

    return stats


def _class_stats():
    """Scheduled vs cancelled classes (ClassSession, Task 3)."""
    stats = {"scheduled": None, "cancelled": None}
    ClassSession = _get_model("ClassSession")
    if ClassSession is not None:
        # ClassSession defines title-cased status choices.
        stats["scheduled"] = _safe(lambda: ClassSession.objects.filter(status="Scheduled").count())
        stats["cancelled"] = _safe(lambda: ClassSession.objects.filter(status="Cancelled").count())
    return stats


def _booking_total():
    """Total bookings: ClassBooking (Task 3), else the existing ClientBooking."""
    model = _get_model("ClassBooking") or _get_model("ClientBooking")
    return model.objects.count() if model is not None else None


def _attendance_today(today):
    """Check-ins that happened today (AttendanceVisit, Task 2)."""
    AttendanceVisit = _get_model("AttendanceVisit")
    if AttendanceVisit is None:
        return None
    # INTEGRATION: add the real check-in field name to this list if it differs.
    name = _first_field(
        AttendanceVisit,
        ("check_in_time", "checked_in_at", "check_in_at", "check_in", "created_at"),
    )
    if name is None:
        return None
    field = AttendanceVisit._meta.get_field(name)
    lookup = f"{name}__date" if isinstance(field, models.DateTimeField) else name
    return _safe(lambda: AttendanceVisit.objects.filter(**{lookup: today}).count())


def get_dashboard_stats():
    """Everything the Admin dashboard shows. ``None`` = not available yet."""
    today = timezone.localdate()
    Branch = _get_model("Branch")

    return {
        "clients": _role_counts("Client"),
        "coaches": _role_counts("Coach"),
        "branches": {
            "total": Branch.objects.count(),
            "active": Branch.objects.filter(is_active=True).count(),
        },
        "memberships": _membership_stats(today),
        "classes": _class_stats(),
        "bookings": {"total": _booking_total()},
        "attendance": {"today": _attendance_today(today)},
    }

 