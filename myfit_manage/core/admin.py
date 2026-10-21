from django.contrib import admin

from .models import MembershipPass, Notification


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
