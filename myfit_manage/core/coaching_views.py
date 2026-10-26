
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Sum
from django.shortcuts import (
    render, redirect, get_object_or_404
)
from django.views.decorators.http import require_POST

from .models import (
    CoachClientAssignment,
    WorkoutLog,
    ProgressEntry
)

from .coaching_forms import (
    AssignmentForm,
    WorkoutLogForm,
    ProgressEntryForm
)

from .coaching_permissions import (
    get_own_client,
    get_authorized_client
)

from .permissions import has_role


# Shortcut for the HTML template folder.
TEMPLATE = 'myfit/Trial_html/'


# ==========================================
# 1. MAIN PAGE - trial.html
# ==========================================

@login_required(login_url='myfit:login')
def trial(request):

    # Determine which links the user can access.
    context = {
        'is_client': has_role(request.user, 'Client'),
        'is_coach': has_role(request.user, 'Coach'),
        'is_admin': has_role(request.user, 'Admin'),
    }

    return render(
        request,
        TEMPLATE + 'trial.html',
        context
    )


# ==========================================
# 2. ADMIN - VIEW ASSIGNMENTS
# ==========================================

@login_required(login_url='myfit:login')
def assignments(request):

    if not has_role(request.user, 'Admin'):
        raise PermissionDenied

    records = CoachClientAssignment.objects.select_related(
        'coach__user',
        'client__user'
    ).order_by('client__user__username')

    return render(
        request,
        TEMPLATE + 'assignments.html',
        {
            'form': AssignmentForm(),
            'assignments': records
        }
    )


# ==========================================
# 3. ADMIN - ASSIGN OR REASSIGN CLIENT
# ==========================================

@login_required(login_url='myfit:login')
@require_POST
def assign_client(request):

    if not has_role(request.user, 'Admin'):
        raise PermissionDenied

    form = AssignmentForm(request.POST)

    if form.is_valid():

        coach = form.cleaned_data['coach']
        client = form.cleaned_data['client']

        # Create or update the client's assignment.
        # The unique client relationship prevents
        # multiple active coaches for one client.
        with transaction.atomic():
            assignment, created = (
                CoachClientAssignment.objects.select_for_update()
                .get_or_create(
                    client=client,
                    defaults={'coach': coach}
                )
            )

            if not created:
                assignment.coach = coach

            # Validate the assignment before saving.
            assignment.full_clean()
            assignment.save()

        messages.success(
            request,
            'Client assigned successfully.'
        )

    else:
        # Redisplay the form with validation errors.
        records = CoachClientAssignment.objects.select_related(
            'coach__user', 'client__user'
        )

        return render(
            request,
            TEMPLATE + 'assignments.html',
            {
                'form': form,
                'assignments': records
            },
            status=400
        )

    return redirect('myfit:coaching_assignments')


# ==========================================
# 4. ADMIN - REMOVE ASSIGNMENT
# ==========================================

@login_required(login_url='myfit:login')
@require_POST
def remove_assignment(request, assignment_id):

    if not has_role(request.user, 'Admin'):
        raise PermissionDenied

    assignment = get_object_or_404(
        CoachClientAssignment,
        pk=assignment_id
    )

    assignment.delete()

    messages.success(request, 'Assignment removed.')

    return redirect('myfit:coaching_assignments')


# ==========================================
# 5. CLIENT - ADD AND VIEW WORKOUTS
# ==========================================

@login_required(login_url='myfit:login')
def workout_logs(request):

    client = get_own_client(request.user)

    form = WorkoutLogForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():

        workout = form.save(commit=False)

        # Never accept the client ID from the form.
        # Always use the logged-in user's profile.
        workout.client = client
        workout.full_clean()
        workout.save()

        messages.success(request, 'Workout saved.')

        return redirect('myfit:coaching_workouts')

    # Only retrieve the logged-in client's workouts.
    logs = WorkoutLog.objects.filter(client=client)

    # Calculate basic workout statistics.
    stats = logs.aggregate(
        total=Count('id'),
        minutes=Sum('duration_minutes')
    )

    return render(
        request,
        TEMPLATE + 'workout_logs.html',
        {
            'form': form,
            'logs': logs,
            'stats': stats
        }
    )


# ==========================================
# 6. CLIENT - EDIT OWN WORKOUT
# ==========================================

@login_required(login_url='myfit:login')
def edit_workout(request, record_id):

    client = get_own_client(request.user)

    # A client cannot edit another user's workout.
    workout = get_object_or_404(
        WorkoutLog,
        pk=record_id,
        client=client
    )

    form = WorkoutLogForm(
        request.POST or None,
        instance=workout
    )

    if request.method == 'POST' and form.is_valid():

        form.save()

        messages.success(request, 'Workout updated.')

        return redirect('myfit:coaching_workouts')

    return render(
        request,
        TEMPLATE + 'edit_workout.html',
        {'form': form}
    )


# ==========================================
# 7. CLIENT - DELETE OWN WORKOUT
# ==========================================

@login_required(login_url='myfit:login')
@require_POST
def delete_workout(request, record_id):

    client = get_own_client(request.user)

    workout = get_object_or_404(
        WorkoutLog,
        pk=record_id,
        client=client
    )

    workout.delete()

    messages.success(request, 'Workout deleted.')

    return redirect('myfit:coaching_workouts')


# ==========================================
# 8. CLIENT - ADD AND VIEW PROGRESS
# ==========================================

@login_required(login_url='myfit:login')
def progress_entries(request):

    client = get_own_client(request.user)

    form = ProgressEntryForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():

        entry = form.save(commit=False)
        entry.client = client

        entry.full_clean()
        entry.save()

        messages.success(
            request,
            'Progress measurement saved.'
        )

        return redirect('myfit:coaching_progress')

    entries = ProgressEntry.objects.filter(
        client=client
    )

    # Compare the latest two entries with
    # the same measurement type AND unit.
    changes = []

    for kind, label in ProgressEntry.MEASUREMENT_TYPES:

        for unit in ProgressEntry.ALLOWED_UNITS[kind]:

            recent = list(
                entries.filter(
                    measurement_type=kind,
                    unit=unit
                ).order_by(
                    '-recorded_on', '-id'
                )[:2]
            )

            if len(recent) == 2:
                changes.append({
                    'label': label,
                    'unit': unit,
                    'latest': recent[0].value,
                    'previous': recent[1].value,
                    'difference': (
                        recent[0].value - recent[1].value
                    )
                })

    return render(
        request,
        TEMPLATE + 'progress_entries.html',
        {
            'form': form,
            'entries': entries,
            'changes': changes
        }
    )


# ==========================================
# 9. COACH - VIEW ASSIGNED CLIENTS
# ==========================================

@login_required(login_url='myfit:login')
def assigned_clients(request):

    if not has_role(request.user, 'Coach'):
        raise PermissionDenied

    # Filter by the currently logged-in coach.
    records = CoachClientAssignment.objects.filter(
        coach__user=request.user
    ).select_related('client__user')

    return render(
        request,
        TEMPLATE + 'assigned_clients.html',
        {'assignments': records}
    )


# ==========================================
# 10. COACH - VIEW CLIENT FITNESS RECORDS
# ==========================================

@login_required(login_url='myfit:login')
def client_records(request, client_id):

    # This function verifies the coach-client relationship.
    client = get_authorized_client(
        request.user,
        client_id
    )

    logs = WorkoutLog.objects.filter(client=client)

    entries = ProgressEntry.objects.filter(client=client)

    # Basic statistics for the assigned client.
    stats = logs.aggregate(
        workouts=Count('id'),
        minutes=Sum('duration_minutes')
    )

    stats['measurements'] = entries.count()

    return render(
        request,
        TEMPLATE + 'client_records.html',
        {
            'client': client,
            'logs': logs,
            'entries': entries,
            'stats': stats
        }
    )
