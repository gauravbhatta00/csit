# payments/admin.py
from django.contrib import admin
from .models import Payment

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['user', 'amount', 'status', 'transaction_id', 'created_at']
    list_filter = ['status']
    search_fields = ['user__username', 'transaction_id', 'pidx']
    readonly_fields = ['pidx', 'transaction_id', 'created_at']