from django.contrib import admin
from django.db import transaction
from django.urls import reverse
from .notifications import notify
from .forms import ClassSessionForm
from django.utils.html import format_html#<---Loick

from .models import (
    MembershipPass,
    Notification,
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
    SupportTicket,
    SupportTicketMessage,
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
    list_display = ("name", "operational_status", "phone", "is_active", "created_at")#which columns to display when viewing the Branch records.
    search_fields = ("name", "address")#which fields administrators can search through using the search box.
    list_filter = ("is_active", "operational_status",)
    fields = ("name", "address", "phone", "email", "opening_hours", "operational_status", "image", "is_active")

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
    fields = ("user", "branch", "specialties", "date_of_birth", "gender", "phone", "bio", "image")

 #>-------------------------------
 #jush========
 #jush========

@admin.register(ClassSession)
class ClassSessionAdmin(admin.ModelAdmin):
    form = ClassSessionForm
    list_display = ('title', 'date', 'time', 'coach', 'spaces_left', 'status')
    fields = ('title', 'category', 'description', 'branch', 'coach', 'date', 'time', 'capacity', 'status', 'image')

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        previous = ClassSession.objects.filter(pk=obj.pk).select_related('coach__user').first() if change else None
        super().save_model(request, obj, form, change)
        notify(
            obj.coach.user, 'Class schedule updated',
            f'Your assigned class {obj.title} on {obj.date:%d %b %Y} is {obj.status.lower()}.',
            reverse('myfit:manage_classes'),
        )
        if previous and previous.coach_id != obj.coach_id:
            notify(previous.coach.user, 'Class reassigned',
                   f'{obj.title} is no longer assigned to you.', reverse('myfit:manage_classes'))
        if obj.status == 'Cancelled' and (previous is None or previous.status != 'Cancelled'):
            for booking in ClassBooking.objects.filter(session=obj, status='Confirmed').select_related('client__user'):
                booking.status = 'Cancelled'
                booking.save(update_fields=['status'])
                notify(booking.client.user, 'Class cancelled',
                       f'{obj.title} on {obj.date:%d %b %Y} has been cancelled.',
                       reverse('myfit:client_bookings'))

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


#>---------Loick
from .models import SupportTicket
@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ('id','kind','subject','user','email','status','created_at')
    list_filter = ('kind','status','created_at')
    search_fields = ('subject','email','name','message')
    readonly_fields = ('created_at','updated_at')
#>--------
# Register support ticket model in Django Admin - Wizzy

class SupportTicketMessageInline(admin.TabularInline):
    model = SupportTicketMessage
    extra = 0

 