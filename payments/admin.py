from django.contrib import admin
from .models import Payment, KhaltiConfig, EsewaConfig


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('transaction_id', 'user', 'course', 'amount', 'payment_gateway', 'status', 'created_at')
    list_filter = ('status', 'payment_gateway')
    search_fields = ('transaction_id', 'user__email', 'course__title', 'gateway_transaction_id')
    ordering = ('-created_at',)
    readonly_fields = ('transaction_id', 'created_at', 'updated_at', 'completed_at')
    
    fieldsets = (
        (None, {'fields': ('transaction_id', 'user', 'course', 'amount')}),
        ('Payment Details', {'fields': ('payment_gateway', 'status', 'gateway_transaction_id')}),
        ('Gateway Response', {'fields': ('gateway_response',), 'classes': ('collapse',)}),
        ('Timestamps', {'fields': ('created_at', 'updated_at', 'completed_at')}),
    )


@admin.register(KhaltiConfig)
class KhaltiConfigAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'is_test_mode', 'is_active')
    list_filter = ('is_test_mode', 'is_active')


@admin.register(EsewaConfig)
class EsewaConfigAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'is_test_mode', 'is_active')
    list_filter = ('is_test_mode', 'is_active')
