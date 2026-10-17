from django.shortcuts import render
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
