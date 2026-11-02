from django.utils import timezone
from django.db.models import Q
from .models import JobShipment, ExpenseVoucher, JobStageInstance, UserRole, ClientInvoice, FieldIssue, FleetVehicle, StaffAttendance, UserProfile
from .permissions import get_user_role

def global_stats(request):
    try:
        total_staff_count = UserProfile.objects.count()
        active_jobs_count = JobShipment.objects.filter(status__in=['ACTIVE', 'DELAYED']).count()
        pending_expenses_count = ExpenseVoucher.objects.filter(approval_status__in=['REQUESTED', 'VERIFIED'], is_paid=False).count()
        unpaid_invoices_count = ClientInvoice.objects.filter(status__in=['ISSUED', 'PARTIALLY_PAID', 'OVERDUE']).count()
        overdue_stages_count = JobStageInstance.objects.filter(
            status__in=['IN_PROGRESS', 'DELAYED', 'BLOCKED']
        ).count()
        pending_intakes_count = JobShipment.objects.filter(
            current_stage_number__in=[1, 2], status__in=['ACTIVE', 'DELAYED']
        ).count()
        pending_declarations_count = JobShipment.objects.filter(
            current_stage_number__in=[2, 3], status__in=['ACTIVE', 'DELAYED'], declaration_number=''
        ).count()
        pending_assessments_count = JobShipment.objects.filter(
            current_stage_number=3, status__in=['ACTIVE', 'DELAYED'], assessed_duty_amount=0
        ).count()
        jobs_at_tra_count = JobShipment.objects.filter(
            current_stage_number__in=[3, 4], status__in=['ACTIVE', 'DELAYED']
        ).count()
        open_field_issues_count = FieldIssue.objects.filter(status='OPEN').count()
        dispatch_ready_count = JobShipment.objects.filter(
            current_stage_number__in=[9, 10], status__in=['ACTIVE', 'DELAYED']
        ).count()
        vehicles_available_count = FleetVehicle.objects.filter(current_status='AVAILABLE').count()
        vehicles_in_transit_count = FleetVehicle.objects.filter(current_status='IN_TRANSIT').count()
        field_today_jobs_count = 0
        driver_active_jobs_count = 0
        today_staff_present = 0
        # Client uploaded receipts pending verification
        pending_receipts_jobs = JobShipment.objects.filter(
            duty_paid=False,
            documents__document_type='DUTY_PAYMENT_RECEIPT'
        ).distinct()
        pending_receipts_count = pending_receipts_jobs.count()
        yard_ready_count = JobShipment.objects.filter(
            vehicle_arrived_at_office=True,
            clearance_mode='DIRECT',
            status__in=['ACTIVE', 'DELAYED']
        ).count()
        bond_count = JobShipment.objects.filter(
            vehicle_arrived_at_office=True,
            clearance_mode='BOND',
            status__in=['ACTIVE', 'DELAYED']
        ).count()

        # User profile & RBAC flags
        user_role = None
        user_role_display = "Guest"
        is_ceo = False
        is_ops = False
        is_finance = False
        is_clearing = False
        is_doc = False
        is_port = False
        is_dispatch = False
        is_driver = False
        is_admin = False

        if request.user.is_authenticated:
            user_role = get_user_role(request.user)
            if hasattr(request.user, 'profile'):
                user_role_display = request.user.profile.get_role_display()
            elif request.user.is_superuser:
                user_role_display = "Super Administrator"

            is_ceo = (user_role == UserRole.CEO)
            is_ops = (user_role == UserRole.OPERATIONS_MGR)
            is_finance = (user_role == UserRole.FINANCE)
            is_clearing = (user_role == UserRole.CLEARING_OFFICER)
            is_doc = (user_role == UserRole.DOC_OFFICER)
            is_port = (user_role == UserRole.PORT_OFFICER)
            is_dispatch = False
            is_driver = False
            is_admin = (user_role == UserRole.ADMIN or request.user.is_superuser)
            if is_ceo and not is_admin:
                # CEO only gets badged for vouchers verified by Finance awaiting CEO payout
                pending_expenses_count = ExpenseVoucher.objects.filter(approval_status='VERIFIED', is_paid=False).count()
            elif is_finance:
                # Finance gets badged for field requests needing review & audit
                pending_expenses_count = ExpenseVoucher.objects.filter(approval_status='REQUESTED').count()

            if is_port:
                field_today_jobs_count = JobShipment.objects.filter(
                    status__in=['ACTIVE', 'DELAYED']
                ).filter(Q(port_officer=request.user) | Q(port_officer__isnull=True)).count()
            elif is_driver:
                driver_active_jobs_count = JobShipment.objects.filter(
                    driver=request.user, status__in=['ACTIVE', 'DELAYED']
                ).count()
            elif is_ops or is_ceo or is_admin:
                field_today_jobs_count = JobShipment.objects.filter(
                    status__in=['ACTIVE', 'DELAYED'],
                    current_stage_number__in=[5, 8, 10]
                ).count()
                today_staff_present = StaffAttendance.objects.filter(
                    date=timezone.now().date(), status__in=['PRESENT', 'LATE']
                ).count()

        is_manager = (is_ops or is_ceo or is_admin)
        can_manage_finance = (is_finance or is_admin or is_ceo)
        can_view_financials = (is_finance or is_ceo or is_admin or is_ops)
        can_create_shipment = (is_doc or is_ops) and not is_ceo
        can_view_audit = (is_ceo or is_ops or is_finance or is_admin)
        can_manage_users = (is_ceo or is_admin)
        can_edit = not is_ceo
        is_read_only = is_ceo

        can_view_all_stages = (is_ceo or is_ops or is_admin)

        return {
            'global_total_staff_count': total_staff_count,
            'global_active_jobs': active_jobs_count,
            'global_pending_expenses': pending_expenses_count,
            'global_unpaid_invoices': unpaid_invoices_count,
            'global_pending_intakes': pending_intakes_count,
            'global_pending_declarations': pending_declarations_count,
            'global_pending_assessments': pending_assessments_count,
            'global_jobs_at_tra': jobs_at_tra_count,
            'global_field_today_jobs': field_today_jobs_count,
            'global_open_field_issues': open_field_issues_count,
            'global_dispatch_ready_count': dispatch_ready_count,
            'global_vehicles_available_count': vehicles_available_count,
        'global_yard_ready_count': yard_ready_count,
        'global_bond_count': bond_count,
            'global_vehicles_in_transit_count': vehicles_in_transit_count,
            'global_driver_active_jobs': driver_active_jobs_count,
            'global_today_staff_present': today_staff_present,
            'global_overdue_count': overdue_stages_count,
            'global_pending_receipts_count': pending_receipts_count,
            'global_pending_receipts_jobs': list(pending_receipts_jobs[:5]),
            'current_user_role': user_role,
            'current_user_role_display': user_role_display,
            'is_ceo': is_ceo,
            'is_ops': is_ops,
            'is_manager': is_manager,
            'is_finance': is_finance,
            'is_clearing': is_clearing,
            'is_doc': is_doc,
            'is_port': is_port,
            'is_dispatch': is_dispatch,
            'is_driver': is_driver,
            'is_admin': is_admin,
            'can_manage_finance': can_manage_finance,
            'can_view_financials': can_view_financials,
            'can_view_all_stages': can_view_all_stages,
            'can_create_shipment': can_create_shipment,
            'can_view_audit': can_view_audit,
            'can_manage_users': can_manage_users,
            'can_edit': can_edit,
            'is_read_only': is_read_only,
            'today': timezone.now().date(),
        }
    except Exception as e:
        import logging
        logging.getLogger('malkia.context_processors').exception("global_stats failed: %s", e)
        return {}
