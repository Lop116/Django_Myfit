from django.urls import path
from django.contrib.auth.views import (
    LoginView,
    LogoutView,
    PasswordResetCompleteView,
    PasswordResetConfirmView,
    PasswordResetDoneView,
    PasswordResetView,
)
from django.urls import reverse_lazy
from . import views
app_name = 'myfit' # namespace for named URLs

urlpatterns = [
    path('', views.home, name='home'),
    path('login/', LoginView.as_view(template_name='myfit/login.html', next_page='myfit:home'), name='login'),
    path('logout/', LogoutView.as_view(next_page=reverse_lazy('myfit:home')), name='logout'),
    path(
        'password-reset/',
        PasswordResetView.as_view(
            template_name='myfit/password_reset_form.html',
            email_template_name='myfit/password_reset_email.html',
            subject_template_name='myfit/password_reset_subject.txt',
            success_url=reverse_lazy('myfit:password_reset_done'),
        ),
        name='password_reset',
    ),
    path(
        'password-reset/done/',
        PasswordResetDoneView.as_view(template_name='myfit/password_reset_done.html'),
        name='password_reset_done',
    ),
    path(
        'password-reset/confirm/<uidb64>/<token>/',
        PasswordResetConfirmView.as_view(
            template_name='myfit/password_reset_confirm.html',
            success_url=reverse_lazy('myfit:password_reset_complete'),
        ),
        name='password_reset_confirm',
    ),
    path(
        'password-reset/complete/',
        PasswordResetCompleteView.as_view(template_name='myfit/password_reset_complete.html'),
        name='password_reset_complete',
    ),
    path('register/', views.register, name='register'),
    path('membership/pass/', views.membership_pass, name='membership_pass'),
    path('membership/qr/', views.membership_qr, name='membership_qr'),
    path('membership/verify/', views.membership_verify, name='membership_verify'),
    path('staff/membership-scanner/', views.membership_scanner, name='membership_scanner'),
    path(
        'notifications/<int:notification_id>/read/',
        views.mark_notification_read,
        name='notification_read',
    ),
    path(
        'notifications/read-all/',
        views.mark_all_notifications_read,
        name='notifications_read_all',
    ),
    path('branches/', views.branches, name='branches'),
    path('coaches/', views.coaches, name='coaches'),
    path('classes/', views.classes, name='classes'),
    path('plans/', views.plans, name='plans'),
    path('contact/', views.contact, name='contact'),
    path('client-dashboard/', views.client_dashboard, name='client_dashboard'),
    path('workouts/', views.workouts, name='workouts'),
    path('progress/', views.progress, name='progress'),
    path('client-bookings/', views.client_bookings, name='client_bookings'),

    path('membership/', views.client_membership, name='client_membership'),
    path('manage-bookings/', views.manage_bookings, name='manage_bookings'),
    path('manage-payments/', views.manage_payments, name='manage_payments'),
    path('membership-requests/', views.membership_requests, name='membership_requests'),
    path('manage-plans/', views.manage_plans, name='manage_plans'),
    # START TASK 2 - Edit Membership Plan
    # deshrao
path(
    'manage-plans/<int:plan_id>/edit/',
    views.edit_membership_plan,
    name='edit_membership_plan',
),
# END TASK 2
    #path for the coaches pages
    path("coach/dashboard/", views.coach_dashboard, name="coach_dashboard"),
    path("coach/clients/", views.coach_clients, name="coach_clients"),
    path("coach/branches/", views.manage_branches, name="manage_branches"),
    path("coach/coaches/", views.manage_coaches, name="manage_coaches"),


]
