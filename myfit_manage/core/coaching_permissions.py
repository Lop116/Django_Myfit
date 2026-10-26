
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404

from .models import (
    ClientProfile,
    CoachClientAssignment
)

# Reuse your team's existing role checker.
from .permissions import has_role


# Get the profile of the logged-in client.
def get_own_client(user):

    if not has_role(user, 'Client'):
        raise PermissionDenied(
            'Only clients can access this page.'
        )

    return get_object_or_404(
        ClientProfile,
        user=user
    )


# Verify that a coach is assigned to the client.
def get_authorized_client(coach_user, client_id):

    if not has_role(coach_user, 'Coach'):
        raise PermissionDenied(
            'Only coaches can access this page.'
        )

    # Filter by BOTH the coach and client.
    # This prevents a coach from viewing another
    # coach's private client records.
    assignment = get_object_or_404(
        CoachClientAssignment.objects.select_related(
            'client__user'
        ),
        coach__user=coach_user,
        client_id=client_id
    )

    return assignment.client
