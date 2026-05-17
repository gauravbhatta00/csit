from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (
    ContactMessage,
    CustomUser,
    EmailSubscription,
    Notification,
    PaymentTransaction,
    SubscriptionPlan,
    UserSubscription,
)


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = ['username', 'email', 'is_premium', 'premium_expires_at', 'is_staff']
    list_editable = ['is_premium', 'premium_expires_at']
    search_fields = ['username', 'email']
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
    list_display = [
        'name',
        'price',
        'billing_period',
        'duration_days',
        'is_active',
        'sort_order',
    ]
    list_editable = ['price', 'is_active', 'sort_order']
    list_filter = ['billing_period', 'is_active']
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ['name', 'description']
    ordering = ['sort_order', 'price']


@admin.register(UserSubscription)
class UserSubscriptionAdmin(admin.ModelAdmin):
    list_display = ['user', 'plan', 'starts_at', 'expires_at', 'is_active']
    list_filter = ['is_active', 'plan']
    search_fields = ['user__username', 'user__email', 'plan__name']
    autocomplete_fields = ['user', 'plan']
    date_hierarchy = 'starts_at'


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = [
        'user',
        'plan',
        'payment_method',
        'amount',
        'status',
        'pidx',
        'khalti_transaction_id',
        'created_at',
        'completed_at',
    ]
    list_filter = ['status', 'payment_method', 'plan']
    search_fields = [
        'user__username',
        'user__email',
        'pidx',
        'khalti_transaction_id',
        'purchase_order_id',
    ]
    readonly_fields = [
        'raw_initiate_response',
        'raw_lookup_response',
        'created_at',
        'updated_at',
        'completed_at',
    ]
    autocomplete_fields = ['user', 'plan', 'subscription']
    date_hierarchy = 'created_at'


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ['name', 'email', 'is_resolved', 'created_at']
    list_filter = ['is_resolved']
    search_fields = ['name', 'email', 'message']
    list_editable = ['is_resolved']
    readonly_fields = ['created_at']
    date_hierarchy = 'created_at'


@admin.register(EmailSubscription)
class EmailSubscriptionAdmin(admin.ModelAdmin):
    list_display = ['email', 'is_active', 'created_at', 'updated_at']
    list_filter = ['is_active']
    search_fields = ['email']
    list_editable = ['is_active']
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'created_at'


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['user', 'type', 'message', 'is_read', 'created_at']
    list_filter = ['type', 'is_read']
    search_fields = ['user__username', 'user__email', 'message']
    date_hierarchy = 'created_at'
