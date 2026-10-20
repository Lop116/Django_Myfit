from django.contrib.auth import login as auth_login
from django.shortcuts import redirect, render
from .forms import RegistrationForm
# Create your views here.
def home(request):
    return render(request, 'myfit/home.html')

def register(request):
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            auth_login(request, user)
            return redirect('myfit:home')
    else:
        form = RegistrationForm()
    return render(request, 'myfit/register.html', {'form': form})

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
