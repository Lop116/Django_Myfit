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
from . import admin_views, views
from . import coaching_views

app_name = 'myfit' # namespace for named URLs

urlpatterns = [
    #<------------------------Loick
    path('staff/specialties/', views.specialty_manage, name='specialty_manage'),
    path('staff/specialties/add/', views.specialty_edit, name='specialty_add'),
    path('staff/specialties/<int:specialty_id>/edit/', views.specialty_edit, name='specialty_edit'),
    path('staff/support/', views.support_manage, name='support_manage'),
    path('staff/support/<int:ticket_id>/status/', views.support_update, name='support_update'),
    path('staff/branches/', views.manage_branches, name='manage_branches'),
    path('staff/coaches/', views.manage_coaches, name='manage_coaches'),
    # Public management, profiles and private support tickets.
    path('profile/edit/', views.edit_profile, name='edit_profile'),
    path('staff/branches/add/', views.branch_edit, name='branch_add'),
    path('staff/branches/<int:branch_id>/edit/', views.branch_edit, name='branch_edit'),
    path('staff/branches/<int:branch_id>/toggle/', views.branch_toggle, name='branch_toggle'),
    path('staff/coaches/add/', views.coach_edit, name='coach_add'),
    path('staff/coaches/<int:coach_id>/edit/', views.coach_edit, name='coach_edit'),
    path('staff/coaches/<int:coach_id>/toggle/', views.coach_toggle, name='coach_toggle'),
    path('support/tickets/<int:ticket_id>/', views.support_ticket_detail, name='support_ticket_detail'),
#<------------------------
    path('', views.home, name='home'),
    path('admin-dashboard/', admin_views.admin_dashboard, name='admin_dashboard'),
    path('login/', views.RoleAwareLoginView.as_view(template_name='myfit/login.html'), name='login'),
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
    # Developer: Deshrao Saccaram
    path(
        'staff/membership-scanner/check-in/',
        views.membership_qr_check_in,
        name='membership_qr_check_in',
    ),
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
    
    
    # Developer: Deshrao Saccaram
    path(
        'attendance/history/',
        views.client_attendance_history,
        name='client_attendance_history',
    ),
    # Developer: Deshrao Saccaram
    path(
        'membership/change-request/',
        views.submit_membership_change_request,
        name='submit_membership_change_request',
    ),
    path('manage-bookings/', views.manage_bookings, name='manage_bookings'),
    path('manage-payments/', views.manage_payments, name='manage_payments'),
    path('membership-requests/', views.membership_requests, name='membership_requests'),
    # Developer: Deshrao Saccaram
    path(
        'membership-requests/<int:request_id>/<str:decision>/',
        views.review_membership_change_request,
        name='review_membership_change_request',
    ),
    path('manage-plans/', views.manage_plans, name='manage_plans'),
    # Developer: Deshrao Saccaram
    path(
        'staff/attendance/',
        views.attendance_dashboard,
        name='attendance_dashboard',
    ),
    path(
        'staff/attendance/check-in/',
        views.attendance_check_in,
        name='attendance_check_in',
    ),
    path(
        'staff/attendance/<int:visit_id>/check-out/',
        views.attendance_check_out,
        name='attendance_check_out',
    ),

# ==========================================================
# TASK 2 - CLIENT MEMBERSHIP ASSIGNMENT
# Developer: Deshrao Saccaram


path(
    'manage-memberships/assign/',
    views.assign_client_membership,
    name='assign_client_membership'
),

    # START TASK 2 - Edit Membership Plan
path(
    'manage-plans/<int:plan_id>/edit/',
    views.edit_membership_plan,
    name='edit_membership_plan',
),
# END TASK 2
    #path for the coaches pages
    path("coach/dashboard/", views.coach_dashboard, name="coach_dashboard"),
    path("coach/clients/", views.coach_clients, name="coach_clients"),
    path("coach/branches/", views.manage_branches, name="manage_branches_legacy"),
    path("coach/coaches/", views.manage_coaches, name="manage_coaches_legacy"),

    #jush
    path('class-list/', views.class_list, name='class_list'),
    path('classes/<int:session_id>/book/', views.book_class_view, name='book_class'),
    path('manage-classes/', views.manage_classes, name='manage_classes'),
    path('bookings/<int:booking_id>/cancel/', views.cancel_booking_view, name='cancel_booking'),


    #ankush
    # Main entry page
    path('trial/', coaching_views.trial, name='coaching_trial' ),

    # Admin assignment management
    path('coaching/assignments/',coaching_views.assignments,name='coaching_assignments'),

    path('coaching/assign/', coaching_views.assign_client, name='coaching_assign' ),

    path('coaching/assignments/<int:assignment_id>/remove/', coaching_views.remove_assignment,name='coaching_remove_assignment' ),

    # Client workout tracking
    path( 'coaching/workouts/',coaching_views.workout_logs, name='coaching_workouts' ),

    path('coaching/workouts/<int:record_id>/edit/',coaching_views.edit_workout, name='coaching_edit_workout'  ),

    path( 'coaching/workouts/<int:record_id>/delete/',coaching_views.delete_workout, name='coaching_delete_workout'
    ),

    # Client progress tracking
    path('coaching/progress/',coaching_views.progress_entries,name='coaching_progress'),

    # Coach views
    path( 'coaching/clients/', coaching_views.assigned_clients, name='coaching_clients' ),

    path('coaching/clients/<int:client_id>/',coaching_views.client_records,name='coaching_client_records' ),

]
