from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, SubscriptionPlan,Notification



@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = ['username', 'email', 'college', 'is_premium', 'current_plan', 'is_staff']
    list_editable = ['is_premium']
    search_fields = ['username', 'email', 'college']
    fieldsets = UserAdmin.fieldsets + (
        ('Profile Info', {
            'fields': ('phone', 'profile_picture', 'college', 'semester', 'bio')
        }),
        ('Premium Info', {
            'fields': ('is_premium', 'premium_expires_at', 'current_plan', 'active_token')
        }),
    )


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ['name', 'duration', 'price', 'is_active']
    list_editable = ['is_active']


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['user', 'type', 'message', 'is_read', 'created_at']
    list_filter = ['type', 'is_read']
    search_fields = ['user__username', 'message']
    list_editable = ['is_read']