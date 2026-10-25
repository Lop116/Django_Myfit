
# ==========================================================
# MYFIT - TASK 2: MEMBERSHIPS AND ATTENDANCE
# Developer: Deshrao Saccaram
# Purpose: Membership assignment business logic


from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import ClientMembership, MembershipPlan


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


# END TASK 2 - MEMBERSHIP ASSIGNMENT SERVICE
