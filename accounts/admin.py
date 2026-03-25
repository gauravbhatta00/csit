from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = ['username', 'email', 'is_premium', 'premium_expires_at', 'is_staff']
    list_editable = ['is_premium', 'premium_expires_at']
    search_fields = ['username', 'email']
    fieldsets = UserAdmin.fieldsets + (
        ('Premium Info', {
            'fields': ('is_premium', 'premium_expires_at', 'active_token')
        }),
    )