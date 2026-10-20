from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from .models import WorkoutRecord
# Create your views here.
def home(request):
    return render(request, 'myfit/home.html')
def branches(request):
    return render(request, 'myfit/branches.html')
def coaches(request):
    return render(request, 'myfit/coaches.html')
def classes(request):
    return render(request, 'myfit/classes.html')
def plans(request):
    return render(request, 'myfit/plans.html')
def contact(request):
    return render(request, 'myfit/contact.html')
def workouts(request):
    return render(request, 'myfit/workouts.html')

@login_required
def client_dashboard(request):
    return render(request, 'myfit/client_dashboard.html')

@login_required
def progress(request):
    records = WorkoutRecord.objects.filter(
        user=request.user
    ).order_by('-workout_date')

    workout_data = [
        {
            'date': record.workout_date.isoformat(),
            'exercise': record.exercise,
            'sets': record.sets,
            'reps': record.reps,
            'weight': float(record.weight_kg),
        }
        for record in records
    ]

    return render(request, 'myfit/progress.html', {
        'workout_data': workout_data,
        'visit_data': []
    })