from django.contrib import admin
from .models import (
    UserProfile, Customer, WorkflowStageDefinition, JobShipment,
    JobStageInstance, JobDocument, ExpenseVoucher, ClientInvoice,
    ClientPayment, AuditLog
)

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'title', 'phone_number')
    list_filter = ('role',)
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'title')

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('company_name', 'contact_person', 'phone', 'tin_number', 'credit_limit', 'payment_terms')
    search_fields = ('company_name', 'contact_person', 'tin_number', 'phone')

@admin.register(WorkflowStageDefinition)
class WorkflowStageDefinitionAdmin(admin.ModelAdmin):
    list_display = ('stage_number', 'name_en', 'name_sw', 'target_days', 'required_role', 'is_controlled_gate')
    ordering = ('stage_number',)

class JobStageInstanceInline(admin.TabularInline):
    model = JobStageInstance
    extra = 0
    fields = ('stage_number', 'name_en', 'status', 'target_days', 'responsible_officer', 'started_at', 'completed_at')
    readonly_fields = ('stage_number', 'name_en')

class JobDocumentInline(admin.TabularInline):
    model = JobDocument
    extra = 0
    fields = ('document_type', 'title', 'file', 'uploaded_by', 'uploaded_at')
    readonly_fields = ('uploaded_at',)

class ExpenseVoucherInline(admin.TabularInline):
    model = ExpenseVoucher
    extra = 0
    fields = ('voucher_number', 'category', 'amount', 'approval_status', 'required_role', 'is_paid')

@admin.register(JobShipment)
class JobShipmentAdmin(admin.ModelAdmin):
    list_display = ('job_number', 'customer', 'bl_number', 'vessel_name', 'current_stage_number', 'status', 'eta_arrival_date')
    list_filter = ('status', 'current_stage_number', 'port_of_arrival')
    search_fields = ('job_number', 'bl_number', 'container_numbers', 'customer__company_name')
    inlines = [JobStageInstanceInline, JobDocumentInline, ExpenseVoucherInline]

@admin.register(ExpenseVoucher)
class ExpenseVoucherAdmin(admin.ModelAdmin):
    list_display = ('voucher_number', 'job', 'category', 'amount', 'approval_status', 'required_role', 'requester', 'is_paid')
    list_filter = ('approval_status', 'category', 'required_role', 'is_paid')
    search_fields = ('voucher_number', 'job__job_number', 'description')

@admin.register(ClientInvoice)
class ClientInvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'customer', 'job', 'issue_date', 'total_amount', 'amount_paid', 'status')
    list_filter = ('status',)
    search_fields = ('invoice_number', 'customer__company_name', 'job__job_number')

@admin.register(ClientPayment)
class ClientPaymentAdmin(admin.ModelAdmin):
    list_display = ('invoice', 'amount', 'payment_date', 'payment_method', 'payment_reference')
    search_fields = ('invoice__invoice_number', 'payment_reference')

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'user', 'action', 'job', 'ip_address')
    list_filter = ('action',)
    search_fields = ('details', 'user__username', 'job__job_number')
