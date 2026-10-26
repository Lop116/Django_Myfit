from django.contrib import admin

from .models import (
    MembershipPass,
    Notification,
    MembershipPlan,
    ClientMembership,
    MembershipChangeRequest,
    AttendanceVisit,
    Branch,
    ClientProfile,
    CoachProfile,
    CoachSpecialty,
    ClassSession,
    ClassBooking,
    CoachClientAssignment,
    WorkoutLog,
    ProgressEntry,
)


@admin.register(MembershipPass)
class MembershipPassAdmin(admin.ModelAdmin):
    list_display = ('membership_id', 'user', 'plan', 'status', 'expiry_date')
    list_filter = ('plan', 'status')
    search_fields = ('membership_id', 'user__username', 'user__email')
    readonly_fields = ('membership_id', 'created_at')


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'is_read', 'created_at', 'read_at')
    list_filter = ('is_read', 'created_at')
    search_fields = ('title', 'message', 'user__username', 'user__email')
    readonly_fields = ('created_at',)



# ==========================================================
# START TASK 2 - MEMBERSHIPS AND ATTENDANCE
# Developer: Deshrao Saccaram
# Please coordinate before modifying this section.
# ==========================================================

@admin.register(MembershipPlan)
class MembershipPlanAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'price',
        'duration_days',
        'is_active',
    )
    list_filter = ('is_active',)
    search_fields = ('name',)


@admin.register(ClientMembership)
class ClientMembershipAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'plan',
        'start_date',
        'end_date',
        'status',
    )
    list_filter = ('status', 'plan')
    search_fields = ('user__username',)


@admin.register(MembershipChangeRequest)
class MembershipChangeRequestAdmin(admin.ModelAdmin):
    list_display = (
        'membership',
        'requested_plan',
        'status',
        'requested_at',
        'reviewed_by',
    )
    list_filter = ('status',)
    readonly_fields = ('requested_at',)


@admin.register(AttendanceVisit)
class AttendanceVisitAdmin(admin.ModelAdmin):
    list_display = (
        'membership',
        'check_in',
        'check_out',
        'is_checked_in',
    )
    list_filter = ('check_in',)


# END TASK 2 - MEMBERSHIPS AND ATTENDANCE

#Loick >----------------------------
@admin.register(Branch) #Display name in admin panel
class BranchAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "is_active", "created_at")#which columns to display when viewing the Branch records.
    search_fields = ("name", "address")#which fields administrators can search through using the search box.
    list_filter = ("is_active",)

@admin.register(CoachSpecialty)
class CoachSpecialtyAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active")
    search_fields = ("name",)
    list_filter = ("is_active",)

@admin.register(ClientProfile)
class ClientProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "phone", "created_at")
    search_fields = ("user__username", "user__email", "phone")

@admin.register(CoachProfile)
class CoachProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "branch", "created_at")
    search_fields = ("user__username", "user__email")
    list_filter = ("branch",)
    filter_horizontal = ("specialties",)

 #>-------------------------------
 #jush========
 #jush========

@admin.register(ClassSession)
class ClassSessionAdmin(admin.ModelAdmin):
    list_display = ('title', 'date', 'time', 'coach', 'spaces_left', 'status')

@admin.register(ClassBooking)
class ClassBookingAdmin(admin.ModelAdmin):
    list_display = ('client', 'session', 'status')
#>-------

#ankush
# Register coaching and fitness models in Django Admin.

@admin.register(CoachClientAssignment)
class AssignmentAdmin(admin.ModelAdmin):

    # Columns shown in the admin panel.
    list_display = (
        'client',
        'coach',
        'assigned_at'
    )

    search_fields = (
        'client__user__username',
        'coach__user__username'
    )


@admin.register(WorkoutLog)
class WorkoutLogAdmin(admin.ModelAdmin):

    list_display = (
        'client',
        'workout_type',
        'workout_date',
        'duration_minutes'
    )

    list_filter = ('workout_type', 'workout_date')

    search_fields = ('client__user__username',)


@admin.register(ProgressEntry)
class ProgressEntryAdmin(admin.ModelAdmin):

    list_display = (
        'client',
        'measurement_type',
        'value',
        'unit',
        'recorded_on'
    )

    list_filter = ('measurement_type', 'unit')
    search_fields = ('client__user__username',)
#>-------
#>-------
