
# ==========================================================
# MYFIT - TASK 2: MEMBERSHIPS AND ATTENDANCE
# Developer: Deshrao Saccaram
# Purpose: Membership assignment business logic


from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import (
    AttendanceVisit,
    ClientMembership,
    MembershipPass,
    MembershipPlan,
)


@transaction.atomic
def assign_membership(user, plan, start_date):
    """
    Assign a membership plan to a registered client.

    - Uses the selected plan's duration and price.
    - Calculates the membership end date.
    - Prevents overlapping non-suspended memberships.
    """

    # Validate that the plan can be assigned.
    if not plan.is_active:
        raise ValidationError(
            "Cannot assign an inactive membership plan."
        )

    # Calculate the expiry date.
    # The starting day counts as Day 1.
    end_date = start_date + timedelta(
        days=plan.duration_days - 1
    )

    # Prevent overlapping memberships.
    overlapping_memberships = (
        ClientMembership.objects
        .select_for_update()
        .filter(
            user=user,
            start_date__lte=end_date,
            end_date__gte=start_date,
        )
        .exclude(status="suspended")
    )

    if overlapping_memberships.exists():
        raise ValidationError(
            "This client already has a membership "
            "covering part of the selected period."
        )

    # Save the membership.
    membership = ClientMembership.objects.create(
        user=user,
        plan=plan,
        start_date=start_date,
        end_date=end_date,
        agreed_price=plan.price,
        status=(
            "scheduled"
            if start_date > timezone.localdate()
            else "active"
        ),
    )

    return membership


# ==========================================================
# TASK 2 - ATTENDANCE MANAGEMENT
# Developer: Deshrao Saccaram


@transaction.atomic
def check_in_membership(membership_id):
    membership = (
        ClientMembership.objects
        .select_for_update()
        .select_related('user', 'plan')
        .get(pk=membership_id)
    )
    if membership.current_status != 'active':
        raise ValidationError(
            'This membership is not currently valid for check-in.'
        )
    if AttendanceVisit.objects.filter(
        membership=membership,
        check_out__isnull=True,
    ).exists():
        raise ValidationError(
            'This client is already checked in for this membership.'
        )

    return AttendanceVisit.objects.create(
        membership=membership,
        check_in=timezone.now(),
    )


@transaction.atomic
def check_out_visit(visit_id):
    visit = (
        AttendanceVisit.objects
        .select_for_update()
        .get(pk=visit_id)
    )
    if visit.check_out is not None:
        raise ValidationError('This attendance visit has already been checked out.')

    check_out = timezone.now()
    if check_out < visit.check_in:
        raise ValidationError(
            'Checkout time cannot be earlier than check-in time.'
        )

    visit.check_out = check_out
    visit.save(update_fields=('check_out',))
    return visit


# END TASK 2 - ATTENDANCE MANAGEMENT


# ==========================================================
# TASK 2 - MEMBERSHIP PASS SYNCHRONIZATION
# Developer: Deshrao Saccaram


@transaction.atomic
def synchronize_membership_pass(user, membership_id):
    locked_user = (
        get_user_model().objects
        .select_for_update()
        .get(pk=user.pk)
    )
    membership = (
        ClientMembership.objects
        .select_for_update()
        .get(pk=membership_id, user=locked_user)
    )
    if membership.current_status != 'active':
        raise ValidationError(
            'A currently active membership is required for a membership pass.'
        )

    member_pass, _ = MembershipPass.objects.select_for_update().get_or_create(
        user=locked_user,
        defaults={
            'plan': MembershipPass.Plan.NEUTRAL,
            'status': MembershipPass.Status.ACTIVE,
            'expiry_date': membership.end_date,
        },
    )

    updated_fields = []
    if member_pass.plan != MembershipPass.Plan.NEUTRAL:
        member_pass.plan = MembershipPass.Plan.NEUTRAL
        updated_fields.append('plan')
    if member_pass.status != MembershipPass.Status.ACTIVE:
        member_pass.status = MembershipPass.Status.ACTIVE
        updated_fields.append('status')
    if member_pass.expiry_date != membership.end_date:
        member_pass.expiry_date = membership.end_date
        updated_fields.append('expiry_date')
    if updated_fields:
        member_pass.save(update_fields=updated_fields)

    return member_pass


# END TASK 2 - MEMBERSHIP PASS SYNCHRONIZATION


# END TASK 2 - MEMBERSHIP ASSIGNMENT SERVICE
