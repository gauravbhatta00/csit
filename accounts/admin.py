from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (
    ContactMessage,
    ContributionSubmission,
    CustomUser,
    EmailSubscription,
    Notification,
    Testimonial,
)


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = [
        'username',
        'email',
        'account_status',
        'suspended_until',
        'is_active',
        'is_staff',
    ]
    list_filter = ['account_status', 'is_active', 'is_staff']
    search_fields = ['username', 'email']
    fieldsets = UserAdmin.fieldsets + (
        ('Profile Info', {
            'fields': ('phone', 'profile_picture', 'college', 'semester', 'bio')
        }),
        ('Account Access', {
            'fields': ('account_status', 'suspended_until', 'active_token')
        }),
    )

    def save_model(self, request, obj, form, change):
        if 'account_status' in form.changed_data:
            obj.set_account_status(obj.account_status, obj.suspended_until)
        super().save_model(request, obj, form, change)


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ['name', 'email', 'is_resolved', 'created_at']
    list_filter = ['is_resolved']
    search_fields = ['name', 'email', 'message']
    list_editable = ['is_resolved']
    readonly_fields = ['created_at']
    date_hierarchy = 'created_at'


@admin.register(ContributionSubmission)
class ContributionSubmissionAdmin(admin.ModelAdmin):
    list_display = [
        'contribution_type',
        'name',
        'email',
        'subject',
        'status',
        'reviewed_by',
        'created_at',
    ]
    list_filter = ['status', 'contribution_type', 'created_at']
    search_fields = ['name', 'email', 'subject', 'semester', 'details']
    readonly_fields = ['created_at', 'updated_at', 'reviewed_at']
    date_hierarchy = 'created_at'


@admin.register(EmailSubscription)
class EmailSubscriptionAdmin(admin.ModelAdmin):
    list_display = ['email', 'is_active', 'created_at', 'updated_at']
    list_filter = ['is_active']
    search_fields = ['email']
    list_editable = ['is_active']
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'created_at'


@admin.register(Testimonial)
class TestimonialAdmin(admin.ModelAdmin):
    list_display = ['name', 'rating', 'status', 'user', 'reviewed_by', 'created_at']
    list_filter = ['status', 'rating', 'created_at']
    search_fields = ['name', 'role', 'review', 'user__username', 'user__email']
    list_editable = ['status']
    readonly_fields = ['created_at', 'updated_at', 'reviewed_at']
    autocomplete_fields = ['user', 'reviewed_by']
    date_hierarchy = 'created_at'


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['user', 'type', 'message', 'is_read', 'created_at']
    list_filter = ['type', 'is_read']
    search_fields = ['user__username', 'user__email', 'message']
    date_hierarchy = 'created_at'
