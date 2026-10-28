from django.contrib import admin
from django.contrib.auth import get_user_model
from django.utils.html import format_html#<---Loick

from .models import (
    ClientBooking,
    MembershipPass,
    Notification,
    WorkoutRecord,
    MembershipPlan,
    ClientMembership,
    MembershipChangeRequest,
    AttendanceVisit,
    Branch,
    WebsiteImage,#<---Loick
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
    list_filter = ('status', 'plan', 'start_date', 'end_date')
    search_fields = ('user__username', 'user__email', 'plan__name')
    date_hierarchy = 'start_date'
    list_select_related = ('user', 'plan')


@admin.register(MembershipChangeRequest)
class MembershipChangeRequestAdmin(admin.ModelAdmin):
    list_display = (
        'membership',
        'requested_plan',
        'status',
        'requested_at',
        'reviewed_by',
    )
    list_filter = ('status', 'requested_plan')
    search_fields = ('membership__user__username', 'requested_plan__name')
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
    search_fields = ('membership__user__username', 'membership__user__email')
    date_hierarchy = 'check_in'


# END TASK 2 - MEMBERSHIPS AND ATTENDANCE

#Loick >----------------------------

# Edit the homepage/page-header pictures in one Django Admin section.
# No HTML modifications are needed for future photo replacements.
@admin.register(WebsiteImage)
class WebsiteImageAdmin(admin.ModelAdmin):
    list_display = ('placement', 'is_active', 'image_preview', 'updated_at')
    list_filter = ('is_active',)
    readonly_fields = ('image_preview', 'updated_at')
    fields = ('placement', 'image', 'image_preview', 'alt_text', 'is_active', 'updated_at')
 
    @admin.display(description='Preview')
    def image_preview(self, obj):
        if obj and obj.image:
            return format_html('<img src="{}" style="max-width:140px;max-height:80px;object-fit:cover" alt="" />', obj.image.url)
        return 'No uploaded image'



@admin.register(Branch) #Display name in admin panel
class BranchAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "is_active", "created_at")#which columns to display when viewing the Branch records.
    search_fields = ("name", "address")#which fields administrators can search through using the search box.
    list_filter = ("is_active",)
    fields = ("name", "address", "phone", "email", "opening_hours", "image", "is_active")

@admin.register(CoachSpecialty)
class CoachSpecialtyAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active")
    search_fields = ("name",)
    list_filter = ("is_active",)

@admin.register(ClientProfile)
class ClientProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "phone", "account_active", "created_at")
    list_filter = ("user__is_active",)
    search_fields = ("user__username", "user__email", "user__first_name", "user__last_name", "phone")
    actions = ("deactivate_accounts", "activate_accounts")

    @admin.display(boolean=True, description="Account active", ordering="user__is_active")
    def account_active(self, obj):
        return obj.user.is_active

    @admin.action(description="Deactivate selected accounts")
    def deactivate_accounts(self, request, queryset):
        # Never let an admin lock themselves out.
        users = get_user_model().objects.filter(pk__in=queryset.values("user")).exclude(pk=request.user.pk)
        count = users.update(is_active=False)
        self.message_user(request, f"{count} account(s) deactivated.")

    @admin.action(description="Activate selected accounts")
    def activate_accounts(self, request, queryset):
        count = get_user_model().objects.filter(pk__in=queryset.values("user")).update(is_active=True)
        self.message_user(request, f"{count} account(s) activated.")

@admin.register(CoachProfile)
class CoachProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "branch", "account_active", "created_at")
    search_fields = ("user__username", "user__email", "user__first_name", "user__last_name")
    list_filter = ("branch", "specialties", "user__is_active")

    @admin.display(boolean=True, description="Account active", ordering="user__is_active")
    def account_active(self, obj):
        return obj.user.is_active
    filter_horizontal = ("specialties",)
    fields = ("user", "branch", "specialties", "date_of_birth", "gender", "phone", "bio", "image")

 #>-------------------------------
 #jush========
 #jush========

@admin.register(ClassSession)
class ClassSessionAdmin(admin.ModelAdmin):
    list_display = ('title', 'date', 'time', 'branch', 'coach', 'capacity', 'spaces_left', 'status')
    list_filter = ('status', 'branch', 'date')
    search_fields = ('title', 'coach__user__username', 'branch__name')
    date_hierarchy = 'date'
    fields = ('title', 'branch', 'coach', 'date', 'time', 'capacity', 'status', 'image') #<----------------

@admin.register(ClassBooking)
class ClassBookingAdmin(admin.ModelAdmin):
    list_display = ('client', 'session', 'status', 'booked_at')
    list_filter = ('status', 'session__branch')
    search_fields = ('client__user__username', 'client__user__email', 'session__title')
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


#>---------Loick
from .models import SupportTicket
@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ('id','kind','subject','user','email','status','created_at')
    list_filter = ('kind','status','created_at')
    search_fields = ('subject','email','name','message')
    readonly_fields = ('created_at','updated_at')
#>--------

# ==========================================================
# TASK 6 - INTEGRATION: models that had no Django Admin page
# ==========================================================
# Legacy models from the first version of the site. They are still used by
# older pages, so Admins can search them but not edit history by accident.

@admin.register(WorkoutRecord)
class WorkoutRecordAdmin(admin.ModelAdmin):
    list_display = ('user', 'exercise', 'workout_date', 'sets', 'reps', 'weight_kg')
    list_filter = ('workout_date',)
    search_fields = ('user__username', 'exercise')


@admin.register(ClientBooking)
class ClientBookingAdmin(admin.ModelAdmin):
    list_display = ('user', 'class_name', 'class_date', 'trainer', 'location', 'status')
    list_filter = ('status', 'class_date')
    search_fields = ('user__username', 'class_name', 'trainer', 'location')
