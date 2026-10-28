from django.contrib import admin

from .models import MembershipPass, Notification, SupportTicket, SupportTicketMessage


@admin.register(MembershipPass)
class MembershipPassAdmin(admin.ModelAdmin):
    list_display = ('membership_id', 'user', 'plan', 'status', 'expiry_date')
    list_filter = ('plan', 'status')
    search_fields = ('membership_id', 'user__username', 'user__email')
    readonly_fields = ('membership_id', 'created_at')


#Loick >----------------------------
from .models import Branch, ClientProfile, CoachProfile, CoachSpecialty
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

 #Wizzy>-------------------------------
@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "type", "is_read", "created_at")
    list_filter = ("type", "is_read")
    search_fields = ("title", "user__username")


class SupportTicketMessageInline(admin.TabularInline):
    model = SupportTicketMessage
    extra = 0


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ("id", "subject", "client", "status", "priority", "assigned_admin")
    list_filter = ("status", "priority")
    search_fields = ("subject", "client__username")
    inlines = [SupportTicketMessageInline]