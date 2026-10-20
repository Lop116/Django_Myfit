from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from .models import WorkoutRecord
from django.utils import timezone
from django.db.models import Q
from .models import ClientBooking


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

@login_required
def client_bookings(request):

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'cancel':
            booking = get_object_or_404(
                ClientBooking,
                id=request.POST.get('booking_id'),
                user=request.user
            )

            today = timezone.localdate()

            if (booking.status == 'confirmed'
                    and booking.class_date >= today):

                booking.status = 'cancelled'
                booking.save(update_fields=['status'])

                messages.success(
                    request,
                    'Your booking has been cancelled.'
                )
            else:
                messages.error(
                    request,
                    'This booking cannot be cancelled.'
                )

        return redirect('myfit:client_bookings')

    today = timezone.localdate()
    current_time = timezone.localtime().time()

    bookings = ClientBooking.objects.filter(
        user=request.user
    )

    upcoming = bookings.filter(
        status='confirmed'
    ).filter(
        Q(class_date__gt=today) |
        Q(class_date=today, start_time__gt=current_time)
    ).order_by('class_date', 'start_time')

    past = bookings.exclude(
        id__in=upcoming.values('id')
    ).order_by('-class_date', '-start_time')

    context = {
        'upcoming_bookings': upcoming,
        'past_bookings': past,
        'upcoming_count': upcoming.count(),
        'completed_count': past.filter(
            status='confirmed'
        ).count(),
        'cancelled_count': bookings.filter(
            status='cancelled'
        ).count(),
    }

    return render(
        request,
        'myfit/client_bookings.html',
        context
    )