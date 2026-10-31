from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Sum, F, DecimalField, ExpressionWrapper
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from .models import AttendanceVisit, WorkoutRecord
from .permissions import role_required
from .workout_forms import WorkoutRecordForm
 
 
@role_required('Client')
def workouts(request):
    """Create, edit and delete only the logged-in client's exercise records."""
    if request.method == 'POST':
        action = request.POST.get('action', '')
        record = None
        if action in ('update', 'delete'):
            record_id = request.POST.get('workout_id', '')
            if not record_id.isdecimal():
                messages.error(request, 'Invalid workout reference.')
                return redirect('myfit:workouts')
            record = get_object_or_404(
                WorkoutRecord, pk=int(record_id), user=request.user
            )
        if action == 'delete':
            record.delete()
            messages.success(request, 'Workout removed.')
        elif action in ('add', 'update'):
            data = request.POST.copy()
            data['weight_kg'] = request.POST.get('weight', '0')
            form = WorkoutRecordForm(data, instance=record)
            if form.is_valid():
                entry = form.save(commit=False)
                entry.user = request.user  # Never trust a client ID sent by the browser.
                entry.save()
                messages.success(request, 'Workout saved.')
            else:
                messages.error(request, 'Workout could not be saved: ' + '; '.join(
                    f'{field}: {", ".join(str(e) for e in errors)}'
                    for field, errors in form.errors.items()
                ))
        else:
            messages.error(request, 'Unknown workout action.')
        return redirect('myfit:workouts')
 
    records = WorkoutRecord.objects.filter(user=request.user)
    total_volume = sum(
        record.sets * record.reps * record.weight_kg for record in records
    )
    return render(request, 'myfit/workouts.html', {
        'workouts': records, 'today': timezone.localdate(),
        'total_records': records.count(),
        'total_sets': sum(r.sets for r in records),
        'total_volume': total_volume,
    })
 
 
@role_required('Client')
def progress(request):
    """Real workouts and attendance only; no demonstration data."""
    records = WorkoutRecord.objects.filter(user=request.user).order_by('-workout_date')
    visits = AttendanceVisit.objects.filter(membership__user=request.user).order_by('-check_in')
    return render(request, 'myfit/progress.html', {
        'workout_data': [
            {'date': r.workout_date.isoformat(), 'exercise': r.exercise,
             'sets': r.sets, 'reps': r.reps, 'weight': float(r.weight_kg)}
            for r in records
        ],
        'visit_data': [
            {'date': timezone.localtime(v.check_in).date().isoformat(),
             'activity': 'Gym visit',
             'details': 'Checked in at ' + timezone.localtime(v.check_in).strftime('%H:%M')}
            for v in visits
        ],
    })
