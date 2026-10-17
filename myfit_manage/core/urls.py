from django.urls import path
from . import views
app_name = 'myfit' # namespace for named URLs

urlpatterns = [
    path('', views.home, name='home'),
    path('branches/', views.branches, name='branches'),
    path('coaches/', views.coaches, name='coaches'),
    path('classes/', views.classes, name='classes'),
    path('plans/', views.plans, name='plans'),
    path('contact/', views.contact, name='contact'),
]
