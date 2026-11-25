from django.utils import timezone
from django.db.models import Q, Count
from .models import JobShipment, ExpenseVoucher, UserRole, ClientInvoice
from .permissions import get_user_role


def global_stats(request):
    today = timezone.localdate()
    base_context = {
        'global_total_staff_count': 0,
        'global_active_jobs': 0,
        'global_stage_1_count': 0,
        'global_stage_2_count': 0,
        'global_stage_3_count': 0,
        'global_stage_4_count': 0,
        'global_stage_5_count': 0,
        'global_stage_6_count': 0,
        'global_pending_expenses': 0,
        'global_unpaid_invoices': 0,
        'global_pending_intakes': 0,
        'global_pending_declarations': 0,
        'global_pending_assessments': 0,
        'global_jobs_at_tra': 0,
        'global_field_today_jobs': 0,
        'global_open_field_issues': 0,
        'global_dispatch_ready_count': 0,
        'global_vehicles_available_count': 0,
        'global_yard_ready_count': 0,
        'global_bond_count': 0,
        'global_vehicles_in_transit_count': 0,
        'global_driver_active_jobs': 0,
        'global_today_staff_present': 0,
        'global_overdue_count': 0,
        'global_pending_receipts_count': 0,
        'global_pending_receipts_jobs': [],
        'current_user_role': None,
        'current_user_role_display': 'Guest',
        'is_ceo': False,
        'is_ops': False,
        'is_manager': False,
        'is_finance': False,
        'is_clearing': False,
        'is_doc': False,
        'is_port': False,
        'is_dispatch': False,
        'is_driver': False,
        'is_admin': False,
        'can_manage_finance': False,
        'can_view_financials': False,
        'can_view_all_stages': False,
        'can_create_shipment': False,
        'can_view_audit': False,
        'can_manage_users': False,
        'can_edit': True,
        'is_read_only': False,
        'today': today,
    }

    if not request.user.is_authenticated:
        return base_context

    try:
        user_role = get_user_role(request.user)
        is_ceo = (user_role in [UserRole.CEO, UserRole.ADMIN] or request.user.is_superuser)
        is_finance = (user_role == UserRole.FINANCE)
        is_ops = (not is_ceo and not is_finance)  # Everyone else belongs to OPERATIONS

        if is_ceo:
            user_role_display = "CEO / Management"
        elif is_finance:
            user_role_display = "Finance / Accountant"
        else:
            user_role_display = "Operations"

        unpaid_invoices_count = 0
        if is_finance or is_ceo:
            unpaid_invoices_count = ClientInvoice.objects.filter(
                status__in=['ISSUED', 'PARTIALLY_PAID', 'OVERDUE']
            ).count()

        active_jobs_count = 0
        stage_1_count = 0
        stage_2_count = 0
        stage_3_count = 0
        stage_4_count = 0
        stage_5_count = 0
        stage_6_count = 0

        if is_ceo:
            active_jobs_count = JobShipment.objects.filter(status__in=['ACTIVE', 'DELAYED']).count()
        elif is_ops:
            active_qs = JobShipment.objects.filter(status__in=['ACTIVE', 'DELAYED'])
            stage_agg = active_qs.aggregate(
                active_total=Count('id'),
                s1=Count('id', filter=Q(current_stage_number=1, documentation_officer=request.user)),
                s2=Count('id', filter=Q(current_stage_number=2, clearing_officer=request.user)),
                s3=Count('id', filter=Q(current_stage_number=3, tbs_officer=request.user)),
                s4=Count('id', filter=Q(current_stage_number=4, port_officer=request.user)),
            )
            active_jobs_count = stage_agg['active_total'] or 0
            stage_1_count = stage_agg['s1'] or 0
            stage_2_count = stage_agg['s2'] or 0
            stage_3_count = stage_agg['s3'] or 0
            stage_4_count = stage_agg['s4'] or 0

            stage_5_count = active_qs.filter(
                current_stage_number=5,
            ).filter(Q(driver=request.user) | Q(stages__stage_number=5, stages__responsible_officer=request.user)).distinct().count()

        pending_receipts_qs = JobShipment.objects.filter(
            duty_paid=False,
            documents__document_type='DUTY_PAYMENT_RECEIPT',
        ).select_related('customer').distinct()
        pending_receipts_jobs = list(pending_receipts_qs[:5])
        if len(pending_receipts_jobs) < 5:
            pending_receipts_count = len(pending_receipts_jobs)
        else:
            pending_receipts_count = pending_receipts_qs.count()

        is_manager = (is_ops or is_ceo)
        can_manage_finance = (is_finance or is_ceo)
        can_view_financials = (is_finance or is_ceo)
        can_create_shipment = (is_ops or is_ceo)
        can_view_audit = (is_ceo or is_finance)
        can_manage_users = is_ceo
        can_view_all_stages = (is_ops or is_ceo)

        base_context.update({
            'global_active_jobs': active_jobs_count,
            'global_stage_1_count': stage_1_count,
            'global_stage_2_count': stage_2_count,
            'global_stage_3_count': stage_3_count,
            'global_stage_4_count': stage_4_count,
            'global_stage_5_count': stage_5_count,
            'global_stage_6_count': stage_6_count,
            'global_unpaid_invoices': unpaid_invoices_count,
            'global_pending_receipts_count': pending_receipts_count,
            'global_pending_receipts_jobs': pending_receipts_jobs,
            'current_user_role': user_role,
            'current_user_role_display': user_role_display,
            'is_ceo': is_ceo,
            'is_ops': is_ops,
            'is_manager': is_manager,
            'is_finance': is_finance,
            'is_clearing': is_ops,
            'is_doc': is_ops,
            'is_port': is_ops,
            'is_dispatch': is_ops,
            'is_driver': is_ops,
            'is_admin': is_ceo,
            'can_manage_finance': can_manage_finance,
            'can_view_financials': can_view_financials,
            'can_view_all_stages': can_view_all_stages,
            'can_create_shipment': can_create_shipment,
            'can_view_audit': can_view_audit,
            'can_manage_users': can_manage_users,
        })
        return base_context
    except Exception as e:
        import logging
        logging.getLogger('malkia.context_processors').exception("global_stats failed: %s", e)
        return base_context
