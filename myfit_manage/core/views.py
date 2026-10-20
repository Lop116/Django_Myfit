from django.shortcuts import render
from django.contrib.auth.decorators import login_required
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