from django.contrib import admin

from .models import (
    MembershipPass,
    Notification,
    MembershipPlan,
    ClientMembership,
    MembershipChangeRequest,
    AttendanceVisit,
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
