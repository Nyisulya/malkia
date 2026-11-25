import os
import uuid



import io



import json



from decimal import Decimal, InvalidOperation



from django.shortcuts import render, redirect, get_object_or_404



from django.http import HttpResponse, JsonResponse, FileResponse

import mimetypes, zipfile



from django.contrib import messages



from django.contrib.auth.models import User



from django.contrib.auth import login, logout, authenticate



from django.contrib.auth.decorators import login_required
from django.core import signing



from django.views.decorators.csrf import csrf_exempt



from django.utils import timezone
from django.utils.text import get_valid_filename



import time as time_module
from django.db import transaction
from django.db.models import Sum, Q, Count

from django.db.models.functions import TruncMonth

from django.urls import reverse



from datetime import time, timedelta, datetime, date







import openpyxl



from openpyxl.styles import Font, PatternFill, Alignment, Border, Side



from openpyxl.utils import get_column_letter







from .models import (



    UserRole, UserProfile, Customer, WorkflowStageDefinition,



    JobShipment, JobStageInstance, JobDocument, JobContainer, ExpenseVoucher, job_document_upload_path,



    ExpenseCategory, ClientInvoice, ClientPayment, OperatingExpenseCategory, OperatingExpense, OtherRevenue, Employee, SalaryPayment, AuditLog, FieldIssue, FleetVehicle,



    StaffAttendance, SystemConfig



)
from .payroll_utils import compute_statutory



from .permissions import (



    get_user_role, role_required, can_approve_expense, can_advance_stage, user_can_manage_docs



)











from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger


def paginate_queryset(request, queryset_or_list, per_page=20, default_per_page=None, page_param='page'):
    """
    Standard pagination helper for Malkia system.
    Returns (page_obj, extra_querystring).
    Preserves all existing GET query parameters across page transitions.
    """
    if default_per_page is not None:
        per_page = default_per_page
    per_page_param = request.GET.get('per_page')
    if per_page_param and per_page_param.isdigit():
        per_page = int(per_page_param)

    paginator = Paginator(queryset_or_list, per_page)
    page_number = request.GET.get(page_param, 1)
    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    try:
        page_obj.elided_pages = list(paginator.get_elided_page_range(page_obj.number, on_each_side=2, on_ends=1))
    except Exception:
        page_obj.elided_pages = paginator.page_range

    query_params = request.GET.copy()
    if page_param in query_params:
        del query_params[page_param]
    extra_qs = query_params.urlencode()
    extra_querystring = f'&{extra_qs}' if extra_qs else ''

    return page_obj, extra_querystring


def get_client_ip(request):



    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')



    if x_forwarded_for:



        return x_forwarded_for.split(',')[0]



    return request.META.get('REMOTE_ADDR', '')











def log_audit(request, action, details, job=None):



    user = request.user if hasattr(request, 'user') and request.user.is_authenticated else None



    AuditLog.objects.create(



        user=user,



        job=job,



        action=action,



        details=details,



        ip_address=get_client_ip(request)



    )











# ==============================================================================



# AUTHENTICATION: LOGIN & LOGOUT



# ==============================================================================







@csrf_exempt

def login_view(request):



    if request.user.is_authenticated:



        role = get_user_role(request.user)



        if role == UserRole.DRIVER:



            return redirect('driver_delivery')



        if role == UserRole.PORT_OFFICER:



            return redirect('field_today_jobs')



        if role == UserRole.DISPATCH_OFFICER:



            return redirect('logistics_dashboard')



        return redirect('dashboard')







    if request.method == 'POST':



        action_type = request.POST.get('action_type')







        # Fast Demo Login with Persona



        if action_type == 'quick_login':



            target_role = request.POST.get('role')



            target_user = User.objects.filter(profile__role=target_role).first()



            if target_user:



                login(request, target_user)



                log_audit(request, "LOGIN", f"User {target_user.username} logged in via role switcher ({target_role})")



                messages.success(request, f"Welcome back, {target_user.get_full_name() or target_user.username}! Logged in as {target_user.profile.get_role_display()}.")



                if target_role == UserRole.DRIVER:



                    return redirect('driver_delivery')



                if target_role == UserRole.PORT_OFFICER:



                    return redirect('field_today_jobs')



                if target_role == UserRole.DISPATCH_OFFICER:



                    return redirect('logistics_dashboard')



                return redirect('dashboard')







        # Standard Credentials Login (supports Username or Email)
        username_input = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        auth_username = username_input
        if '@' in username_input:
            matched_user = User.objects.filter(email__iexact=username_input).first()
            if matched_user:
                auth_username = matched_user.username

        user = authenticate(request, username=auth_username, password=password)







        if user is not None:



            login(request, user)



            log_audit(request, "LOGIN", f"User {user.username} authenticated successfully.")



            role = get_user_role(user)



            role_display = user.profile.get_role_display() if hasattr(user, 'profile') else role



            messages.success(request, f"Welcome, {user.get_full_name() or user.username} ({role_display})!")



            



            # Smart redirect based on role



            next_url = request.GET.get('next')



            if next_url:



                return redirect(next_url)



            if role == UserRole.DRIVER:



                return redirect('driver_delivery')



            if role == UserRole.PORT_OFFICER:



                return redirect('field_today_jobs')



            if role == UserRole.DISPATCH_OFFICER:



                return redirect('logistics_dashboard')



            return redirect('dashboard')



        else:



            messages.error(request, "Invalid username or password. Please try again.")







    demo_personas = [



        ('CEO', 'Hashim Mkwawa', 'Managing Director & CEO', 'fa-user-tie', '#1E40AF'),



        ('OPERATIONS_MGR', 'Grace Mushi', 'Operations Director', 'fa-clipboard-check', '#059669'),



        ('FINANCE', 'Subira Kilonzo', 'Chief Accountant / Finance', 'fa-receipt', '#D97706'),



        ('CLEARING_OFFICER', 'Rashid Nassor', 'Customs Declarer (TANCIS)', 'fa-stamp', '#7C3AED'),



        ('DOC_OFFICER', 'Amani Bakari', 'Documentation Officer', 'fa-folder-open', '#0284C7'),



        ('PORT_OFFICER', 'Juma Kavishe', 'Port Field Inspector', 'fa-anchor', '#0D9488'),



        ('DISPATCH_OFFICER', 'Baraka Makonda', 'Logistics & Dispatch Controller', 'fa-truck-fast', '#F59E0B'),



        ('DRIVER', 'Mohamed Said', 'Heavy Logistics Driver', 'fa-truck', '#DC2626'),



    ]







    return render(request, 'core/login.html', {'demo_personas': demo_personas})











def logout_view(request):



    if request.user.is_authenticated:



        log_audit(request, "LOGOUT", f"User {request.user.username} logged out.")



        logout(request)



        messages.info(request, "You have been logged out successfully.")



    return redirect('login')


@login_required
def change_password_view(request):
    if request.method == 'POST':
        current_pw = request.POST.get('current_password', '')
        new_pw = request.POST.get('new_password', '').strip()
        confirm_pw = request.POST.get('confirm_password', '').strip()
        if not request.user.check_password(current_pw):
            messages.error(request, "Current password is incorrect.")
        elif len(new_pw) < 6:
            messages.error(request, "New password must be at least 6 characters.")
        elif new_pw != confirm_pw:
            messages.error(request, "New passwords do not match.")
        else:
            request.user.set_password(new_pw)
            request.user.save()
            from django.contrib.auth import update_session_auth_hash
            update_session_auth_hash(request, request.user)
            log_audit(request, "PASSWORD_CHANGED", f"User {request.user.username} changed their own password.")
            messages.success(request, "Password updated successfully!")
            return redirect('dashboard')
    return render(request, 'core/change_password.html')











# ==============================================================================



# CORE VIEWS (PROTECTED BY RBAC)



# ==============================================================================







@login_required




def accountant_dashboard_view(request):
    """
    Dedicated Financial Dashboard for the Accountant (Subira Kilonzo / FINANCE role).
    Completely isolated from field micro-steps, port micro-status, and operational forms.
    Focuses 100% on:
      1. Vehicles Out & Direct Costing (Duty, DO, Wharfage, Handling, Fuel, Transport)
      2. Malkia Agency Fees & Gross Turnover
      3. Commercial Invoices & Buying Prices ($ USD)
      4. Pending Expense Vouchers & Audit Approvals
      5. Quick 1-Click Excel Export & Direct Cost Entry
    """
    role = get_user_role(request.user)
    if role not in [UserRole.FINANCE, UserRole.CEO, UserRole.ADMIN] and not request.user.is_superuser:
        messages.warning(request, "Access restricted: Financial dashboard is accessible to Finance and Management only.")
        return redirect("dashboard")
    now = timezone.now()
    current_year = now.year

    period = request.GET.get('period', '').strip()
    q = request.GET.get('q', '').strip()
    date_from_str = request.GET.get('date_from', '').strip()
    date_to_str = request.GET.get('date_to', '').strip()

    parsed_date_from = None
    parsed_date_to = None
    if date_from_str:
        try:
            parsed_date_from = datetime.strptime(date_from_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            parsed_date_from = None
    if date_to_str:
        try:
            parsed_date_to = datetime.strptime(date_to_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            parsed_date_to = None

    jobs_qs = JobShipment.objects.all().select_related('customer').prefetch_related('documents', 'invoices')
    salaries_qs = SalaryPayment.objects.filter(status='PAID')
    expenses_qs = OperatingExpense.objects.all()
    other_rev_qs = OtherRevenue.objects.all()
    invoices_qs = ClientInvoice.objects.all()

    if parsed_date_from or parsed_date_to:
        period = 'custom'
        if parsed_date_from and parsed_date_to:
            jobs_qs = jobs_qs.filter(created_at__date__gte=parsed_date_from, created_at__date__lte=parsed_date_to)
            salaries_qs = salaries_qs.filter(payment_date__gte=parsed_date_from, payment_date__lte=parsed_date_to)
            expenses_qs = expenses_qs.filter(date__gte=parsed_date_from, date__lte=parsed_date_to)
            other_rev_qs = other_rev_qs.filter(date__gte=parsed_date_from, date__lte=parsed_date_to)
            invoices_qs = invoices_qs.filter(issue_date__gte=parsed_date_from, issue_date__lte=parsed_date_to)
            filter_label = f"Custom ({parsed_date_from.strftime('%d %b %Y')} to {parsed_date_to.strftime('%d %b %Y')})"
        elif parsed_date_from:
            jobs_qs = jobs_qs.filter(created_at__date__gte=parsed_date_from)
            salaries_qs = salaries_qs.filter(payment_date__gte=parsed_date_from)
            expenses_qs = expenses_qs.filter(date__gte=parsed_date_from)
            other_rev_qs = other_rev_qs.filter(date__gte=parsed_date_from)
            invoices_qs = invoices_qs.filter(issue_date__gte=parsed_date_from)
            filter_label = f"From {parsed_date_from.strftime('%d %b %Y')}"
        else:
            jobs_qs = jobs_qs.filter(created_at__date__lte=parsed_date_to)
            salaries_qs = salaries_qs.filter(payment_date__lte=parsed_date_to)
            expenses_qs = expenses_qs.filter(date__lte=parsed_date_to)
            other_rev_qs = other_rev_qs.filter(date__lte=parsed_date_to)
            invoices_qs = invoices_qs.filter(issue_date__lte=parsed_date_to)
            filter_label = f"Up to {parsed_date_to.strftime('%d %b %Y')}"
    elif period == 'today':
        today_date = timezone.localdate()
        jobs_qs = jobs_qs.filter(created_at__date=today_date)
        salaries_qs = salaries_qs.filter(payment_date=today_date)
        expenses_qs = expenses_qs.filter(date=today_date)
        other_rev_qs = other_rev_qs.filter(date=today_date)
        invoices_qs = invoices_qs.filter(issue_date=today_date)
        filter_label = f"Today ({today_date.strftime('%d %b %Y')})"
    elif period == 'this_month':
        jobs_qs = jobs_qs.filter(created_at__year=current_year, created_at__month=now.month)
        salaries_qs = salaries_qs.filter(payment_date__year=current_year, payment_date__month=now.month)
        expenses_qs = expenses_qs.filter(date__year=current_year, date__month=now.month)
        other_rev_qs = other_rev_qs.filter(date__year=current_year, date__month=now.month)
        invoices_qs = invoices_qs.filter(issue_date__year=current_year, issue_date__month=now.month)
        filter_label = f"This Month ({now.strftime('%B %Y')})"
    elif period == 'all':
        filter_label = "All Time"
    else:
        period = 'this_year'
        jobs_qs = jobs_qs.filter(created_at__year=current_year)
        salaries_qs = salaries_qs.filter(payment_date__year=current_year)
        expenses_qs = expenses_qs.filter(date__year=current_year)
        other_rev_qs = other_rev_qs.filter(date__year=current_year)
        invoices_qs = invoices_qs.filter(issue_date__year=current_year)
        filter_label = f"Year {current_year}"

    if q:
        jobs_qs = jobs_qs.filter(
            Q(bl_number__icontains=q) |
            Q(chassis_number__icontains=q) |
            Q(vehicle_make__icontains=q) |
            Q(vehicle_model__icontains=q) |
            Q(customer__company_name__icontains=q) |
            Q(job_number__icontains=q)
        )

    all_jobs = list(jobs_qs.order_by('-created_at'))
    total_vehicles = len(all_jobs)

    # Bulk-preload container deposit refund totals before cost/margin loops to prevent N+1 queries
    if all_jobs:
        refund_rows = OtherRevenue.objects.filter(
            job_id__in=[j.id for j in all_jobs],
            inflow_type='CONTAINER_REFUND',
        ).values('job_id').annotate(
            total=Sum('returned_amount', filter=Q(deposit_status__in=['RETURNED_FULL', 'PARTIAL'])),
            resolved_cnt=Count('id', filter=Q(deposit_status__in=['RETURNED_FULL', 'PARTIAL', 'FORFEITED'])),
        )
        refund_totals = {r['job_id']: (r['total'] or Decimal('0')) for r in refund_rows}
        refund_counts = {r['job_id']: r['resolved_cnt'] for r in refund_rows}
        for j in all_jobs:
            j._deposit_refunded_cache = refund_totals.get(j.id, Decimal('0'))
            j.deposit_refund_logged = refund_counts.get(j.id, 0) > 0

    # Financial aggregations
    sum_cif_usd = sum(j.cif_usd or Decimal('0') for j in all_jobs)
    sum_duty = sum(j.cost_duty or Decimal('0') for j in all_jobs)
    sum_do = sum(j.cost_do or Decimal('0') for j in all_jobs)
    sum_wharfage = sum(j.cost_wharfage or Decimal('0') for j in all_jobs)
    sum_tiss = sum(j.cost_tiss_wharfage or Decimal('0') for j in all_jobs)
    sum_handling = sum(j.cost_handling or Decimal('0') for j in all_jobs)
    sum_facilitation = sum(j.cost_facilitation or Decimal('0') for j in all_jobs)
    sum_transport = sum(j.cost_transport or Decimal('0') for j in all_jobs)
    sum_agent_fee = sum(j.cost_agent_fee or Decimal('0') for j in all_jobs)
    sum_fuel = sum(j.cost_fuel or Decimal('0') for j in all_jobs)
    sum_ferry = sum(j.cost_ferry_charges or Decimal('0') for j in all_jobs)

    sum_direct_costs = sum(j.total_direct_costs for j in all_jobs)
    sum_client_billable_costs = sum(j.client_billable_costs for j in all_jobs)
    sum_vehicle_running_costs = sum(j.internal_running_costs for j in all_jobs)
    sum_net_agency_margin = sum(j.net_agency_margin for j in all_jobs)
    sum_grand_total = sum(j.total_disbursement_with_agent_fee for j in all_jobs)

    # Status counts
    costed_count = len([j for j in all_jobs if j.costing_status == 'FULLY_COSTED'])
    in_progress_count = len([j for j in all_jobs if j.costing_status == 'IN_PROGRESS'])
    uncosted_count = len([j for j in all_jobs if j.costing_status == 'PENDING'])

    # Status filtering
    status_param = request.GET.get('status', 'all').strip().lower()
    if status_param == 'costed':
        displayed_jobs = [j for j in all_jobs if j.costing_status == 'FULLY_COSTED']
    elif status_param == 'in_progress':
        displayed_jobs = [j for j in all_jobs if j.costing_status == 'IN_PROGRESS']
    elif status_param == 'pending':
        displayed_jobs = [j for j in all_jobs if j.costing_status == 'PENDING']
    else:
        status_param = 'all'
        displayed_jobs = all_jobs

    # Salaries net pay
    sum_salaries_paid = sum((s.net_pay or Decimal('0')) for s in salaries_qs)
    # Office operating expenses (exclude salaries to prevent double counting)
    office_expenses_qs = expenses_qs.exclude(category__name__icontains='Salary')
    sum_office_expenses = office_expenses_qs.aggregate(t=Sum('amount'))['t'] or Decimal('0.00')

    # Other Revenue & Cash Inflows (Business Revenue counts in profit; Refunds & Boss Capital tracked separately)
    other_rev_totals = other_rev_qs.aggregate(
        business=Sum('amount', filter=Q(inflow_type='OTHER_REVENUE')),
        refunds=Sum('returned_amount', filter=Q(inflow_type='CONTAINER_REFUND', deposit_status__in=['RETURNED_FULL', 'PARTIAL'])),
        capital=Sum('amount', filter=Q(inflow_type='CAPITAL_INJECTION')),
    )
    sum_other_business_revenue = other_rev_totals['business'] or Decimal('0.00')
    sum_container_refunds = other_rev_totals['refunds'] or Decimal('0.00')
    sum_capital_injections = other_rev_totals['capital'] or Decimal('0.00')
    total_other_inflows = sum_container_refunds + sum_capital_injections

    # Total Overheads & Salaries
    total_company_costs = sum_salaries_paid + sum_office_expenses

    # Total Company Revenue & Net Company Profit / Surplus
    total_company_revenue = sum_agent_fee + sum_other_business_revenue
    # True Net Company Profit: Net Agency Margin (Clearance Fee minus Vehicle Running Costs) + Other Revenue minus General Office Overhead & Salaries
    net_profit = sum_net_agency_margin + sum_other_business_revenue - total_company_costs

    # Invoices & Receivables
    all_period_invoices = list(invoices_qs)
    total_invoiced = sum((i.total_amount or Decimal('0')) for i in all_period_invoices)
    total_collected = sum((i.amount_paid or Decimal('0')) for i in all_period_invoices)
    total_due = max(Decimal('0'), total_invoiced - total_collected)

    # Attach document URLs & costing status ONLY for displayed recent jobs (uses prefetched documents)
    recent_jobs = displayed_jobs[:20]
    for j in recent_jobs:
        bl_doc = j.bl_doc
        inv_doc = j.invoice_doc
        j.bl_doc_url = bl_doc.file.url if bl_doc and bl_doc.file else None
        j.inv_doc_url = inv_doc.file.url if inv_doc and inv_doc.file else None
        j.is_costed = (j.cost_duty > 0 or j.cost_agent_fee > 0)

    # Pending Expense Vouchers for Accountant Review/Audit
    pending_vouchers = list(ExpenseVoucher.objects.filter(approval_status='REQUESTED').select_related('job', 'requester').order_by('-requested_at')[:8])
    pending_vouchers_count = ExpenseVoucher.objects.filter(approval_status='REQUESTED').count()

    context = {
        'selected_period': period,
        'date_from': date_from_str,
        'date_to': date_to_str,
        'filter_label': filter_label,
        'current_year': current_year,
        'search_q': q,
        'selected_status': status_param,
        'recent_jobs': recent_jobs,
        'total_vehicles': total_vehicles,
        'costed_count': costed_count,
        'in_progress_count': in_progress_count,
        'uncosted_count': uncosted_count,
        'sum_cif_usd': sum_cif_usd,
        'sum_direct_costs': sum_direct_costs,
        'sum_client_billable_costs': sum_client_billable_costs,
        'sum_vehicle_running_costs': sum_vehicle_running_costs,
        'sum_net_agency_margin': sum_net_agency_margin,
        'sum_agent_fee': sum_agent_fee,
        'sum_other_business_revenue': sum_other_business_revenue,
        'sum_container_refunds': sum_container_refunds,
        'sum_capital_injections': sum_capital_injections,
        'total_other_inflows': total_other_inflows,
        'total_company_revenue': total_company_revenue,
        'sum_grand_total': sum_grand_total,
        # Executive Cards
        'total_company_costs': total_company_costs,
        'sum_salaries_paid': sum_salaries_paid,
        'sum_office_expenses': sum_office_expenses,
        'net_profit': net_profit,
        'total_invoiced': total_invoiced,
        'total_collected': total_collected,
        'total_due': total_due,
        # Category breakdown
        'sum_duty': sum_duty,
        'sum_do': sum_do,
        'sum_wharfage_total': sum_wharfage + sum_tiss,
        'sum_handling': sum_handling,
        'sum_transport': sum_transport,
        'sum_fuel': sum_fuel,
        'sum_ferry_facil': sum_ferry + sum_facilitation,
        # Vouchers
        'pending_vouchers': pending_vouchers,
        'pending_vouchers_count': pending_vouchers_count,
    }
    return render(request, 'finance/accountant_dashboard.html', context)

def dashboard_view(request):

    role = get_user_role(request.user)

    is_ceo = (role == UserRole.CEO)

    is_admin = (role == UserRole.ADMIN or request.user.is_superuser)

    is_finance = (role == UserRole.FINANCE)

    # 1. ACCOUNTANT ISOLATION: Dedicated Finance Dashboard
    if is_finance:
        return accountant_dashboard_view(request)



    # Drivers and Port Officers have specialized operational field consoles



    # Unified Team flow: all staff can access dashboard

    pass







    can_view_all_stages = (role in [UserRole.CEO, UserRole.OPERATIONS_MGR, UserRole.ADMIN] or request.user.is_superuser)







    # Date Filter Engine (Defaults to Today, supports presets & custom range)



    today_date = timezone.localdate()



    preset = request.GET.get('preset')



    date_from_str = request.GET.get('date_from', '').strip()



    date_to_str = request.GET.get('date_to', '').strip()







    if date_from_str and date_to_str:



        preset = 'custom'



        try:



            date_from = datetime.strptime(date_from_str, '%Y-%m-%d').date()



            date_to = datetime.strptime(date_to_str, '%Y-%m-%d').date()



        except Exception:



            preset = 'today'



            date_from = today_date



            date_to = today_date



    elif preset == 'today':

        date_from = today_date

        date_to = today_date

    elif preset == 'this_year':

        date_from = date(today_date.year, 1, 1)

        date_to = date(today_date.year, 12, 31)

    elif preset == 'last_year':

        date_from = date(today_date.year - 1, 1, 1)

        date_to = date(today_date.year - 1, 12, 31)

    elif preset == 'all':

        date_from = None

        date_to = None

    else:

        preset = 'this_month'

        date_from = today_date.replace(day=1)

        date_to = today_date

    # Human-readable filter label

    if preset == 'today':

        filter_label = f"Today ({today_date.strftime('%d %b %Y')})"

    elif preset == 'this_month':

        filter_label = f"This Month ({today_date.strftime('%b %Y')})"



    elif preset == 'this_year':



        filter_label = f"This Year ({today_date.year})"



    elif preset == 'last_year':



        filter_label = f"Last Year ({today_date.year - 1})"



    elif preset == 'all':



        filter_label = "All Time Records"



    else:



        filter_label = f"Custom ({date_from.strftime('%d %b %Y')} to {date_to.strftime('%d %b %Y')})"







    all_jobs_raw = JobShipment.objects.all().select_related('customer', 'documentation_officer', 'clearing_officer', 'port_officer')



    



    # Financial QuerySets



    inv_qs = ClientInvoice.objects.all()



    exp_qs = ExpenseVoucher.objects.filter(approval_status='APPROVED')







    if date_from and date_to:



        inv_filtered = inv_qs.filter(issue_date__range=(date_from, date_to))



        exp_filtered = exp_qs.filter(Q(paid_at__date__range=(date_from, date_to)) | Q(approval_date__date__range=(date_from, date_to)))



        



        # Financial Totals for this period



        total_revenue = inv_filtered.aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')



        total_expenses = exp_filtered.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')



        



        # Jobs in range: Active operations up to date_to, and completed delivered in range



        completed_jobs = all_jobs_raw.filter(status__in=['COMPLETED', 'CLOSED']).filter(Q(delivered_date__date__range=(date_from, date_to)) | Q(updated_at__date__range=(date_from, date_to)) | Q(created_at__date__range=(date_from, date_to)))



        active_jobs = all_jobs_raw.filter(status__in=['ACTIVE', 'DELAYED'], created_at__date__lte=date_to)



        delayed_jobs = all_jobs_raw.filter(status='DELAYED', created_at__date__lte=date_to)



        jobs = all_jobs_raw.filter(Q(status__in=['ACTIVE', 'DELAYED'], created_at__date__lte=date_to) | Q(status__in=['COMPLETED', 'CLOSED'], delivered_date__date__range=(date_from, date_to)) | Q(status__in=['COMPLETED', 'CLOSED'], updated_at__date__range=(date_from, date_to)) | Q(status__in=['COMPLETED', 'CLOSED'], created_at__date__range=(date_from, date_to)))



    else:



        total_revenue = inv_qs.aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')



        total_expenses = exp_qs.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')



        completed_jobs = all_jobs_raw.filter(status='COMPLETED')



        active_jobs = all_jobs_raw.filter(status__in=['ACTIVE', 'DELAYED'])



        delayed_jobs = all_jobs_raw.filter(status='DELAYED')



        jobs = all_jobs_raw







    gross_margin = total_revenue - total_expenses



    gross_margin_pct = round((gross_margin / total_revenue * 100), 1) if total_revenue > 0 else 0.0







    total_collected = inv_qs.aggregate(total=Sum('amount_paid'))['total'] or Decimal('0.00')



    outstanding_receivables = total_revenue - total_collected







    # Daily Financials



    daily_income = ClientPayment.objects.filter(payment_date=today_date).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')



    if daily_income == 0:



        daily_income = ClientInvoice.objects.filter(issue_date=today_date).aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')



    daily_expenses = ExpenseVoucher.objects.filter(paid_at__date=today_date, is_paid=True).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')



    if daily_expenses == 0:



        daily_expenses = ExpenseVoucher.objects.filter(approval_date__date=today_date, approval_status='APPROVED').aggregate(total=Sum('amount'))['total'] or Decimal('0.00')







    # Port & Field KPIs



    containers_at_port = jobs.filter(current_stage_number__in=[4, 5, 6, 7, 8, 9]).count()



    in_transit_count = jobs.filter(current_stage_number=10).count()



    under_verification_count = jobs.filter(current_stage_number=5).count()







    # Role-to-Stage Permission Mapping



    ROLE_STAGE_MAPPING = {



        UserRole.DOC_OFFICER: [1],



        UserRole.CLEARING_OFFICER: [2, 3, 4, 6, 7],



        UserRole.PORT_OFFICER: [4, 5, 6, 7, 8],



        UserRole.FINANCE: [3, 4, 6],



        UserRole.DISPATCH_OFFICER: [7, 8, 9],



        UserRole.DRIVER: [7, 8, 9],



    }







    ROLE_STAGE_TITLES = {



        UserRole.CLEARING_OFFICER: ("Customs & Clearance Stages Health", "Active shipments count across your assigned customs and declaration stages"),



        UserRole.DOC_OFFICER: ("Documentation & Intake Stages Health", "Active shipments count across document receipt and digital file opening"),



        UserRole.PORT_OFFICER: ("Port Operations Stages Health", "Active shipments count across verification, port billing, and gate loading"),



        UserRole.FINANCE: ("Finance & Statutory Payment Stages", "Active shipments count across duty and port charge disbursement stages"),



        UserRole.DISPATCH_OFFICER: ("Haulage & Delivery Stages Health", "Active shipments count across gate pass, haulage, and client delivery"),



    }







    # Alerts: Delayed/Bottleneck Stages (Strictly scoped to user role & assigned tasks)



    overdue_stages = JobStageInstance.objects.filter(



        job__status__in=['ACTIVE', 'DELAYED'],



        status__in=['IN_PROGRESS', 'DELAYED', 'BLOCKED']



    ).select_related(



        'job', 'job__customer', 'stage_definition',



        'job__documentation_officer', 'job__clearing_officer', 'job__port_officer', 'job__driver'



    ).order_by('started_at')



    



    flagged_delayed_list = []



    for s in overdue_stages:



        # A stage is only overdue/bottlenecked if it is the job's current active stage



        if s.stage_number != s.job.current_stage_number:



            continue



        if not s.is_overdue:



            continue







        # 1. Management (CEO, Operations Manager, Admin) see all company-wide bottlenecks



        if can_view_all_stages:



            flagged_delayed_list.append(s)



            continue







        # 2. Operational staff only see bottlenecks in their own designated role stages AND their assigned shipments



        allowed_stages = ROLE_STAGE_MAPPING.get(role, [])



        if s.stage_number not in allowed_stages:



            continue







        is_assigned = False



        if role == UserRole.DOC_OFFICER:



            is_assigned = (s.job.documentation_officer == request.user or s.responsible_officer == request.user or s.job.documentation_officer is None)



        elif role == UserRole.CLEARING_OFFICER:



            is_assigned = (s.job.clearing_officer == request.user or s.responsible_officer == request.user or s.job.clearing_officer is None)



        elif role == UserRole.PORT_OFFICER:



            is_assigned = (s.job.port_officer == request.user or s.responsible_officer == request.user or s.job.port_officer is None)



        elif role == UserRole.DRIVER:



            is_assigned = (s.job.driver == request.user)



        elif role == UserRole.DISPATCH_OFFICER:



            is_assigned = True



        elif role == UserRole.FINANCE:



            # Finance only sees statutory payment stages (Stage 4, 9) if vouchers are requested/delayed



            is_assigned = (s.stage_number in [4, 9])



        



        if is_assigned:



            flagged_delayed_list.append(s)







    # Pending approvals for current role



    # Pending approvals for current role (CEO disburses, Finance audits & forwards)

    if is_ceo and not is_admin:

        # CEO strictly sees vouchers that have already been audited & verified by Finance!

        pending_expenses = ExpenseVoucher.objects.filter(

            approval_status='VERIFIED', is_paid=False

        ).select_related('job', 'job__customer', 'requester', 'audited_by').order_by('-requested_at')

    elif is_admin:

        pending_expenses = ExpenseVoucher.objects.filter(

            approval_status__in=['VERIFIED', 'REQUESTED'], is_paid=False

        ).select_related('job', 'job__customer', 'requester', 'audited_by').order_by('-requested_at')

    elif is_finance:

        pending_expenses = ExpenseVoucher.objects.filter(

            approval_status__in=['REQUESTED', 'VERIFIED'], is_paid=False

        ).select_related('job', 'job__customer', 'requester', 'audited_by').order_by('-requested_at')

    else:

        pending_expenses = ExpenseVoucher.objects.filter(

            approval_status='REQUESTED', is_paid=False

        ).select_related('job', 'job__customer', 'requester', 'audited_by').order_by('-requested_at')







    # Stage distribution for visual health card and chart (batched in 2 queries)
    all_stage_defs = list(WorkflowStageDefinition.objects.all().order_by('stage_number'))
    active_stage_map = {
        row['current_stage_number']: row['cnt']
        for row in jobs.filter(status__in=['ACTIVE', 'DELAYED'])
        .values('current_stage_number')
        .annotate(cnt=Count('id'))
    }
    stage_counts = [
        {
            'stage_number': sdef.stage_number,
            'name_en': sdef.name_en,
            'name_sw': sdef.name_sw,
            'count': active_stage_map.get(sdef.stage_number, 0),
        }
        for sdef in all_stage_defs
    ]

    jobs_metrics = jobs.aggregate(
        visible_total=Count('id'),
        active_total=Count('id', filter=Q(status__in=['ACTIVE', 'DELAYED'])),
        completed_total=Count('id', filter=Q(status='COMPLETED')),
        delayed_total=Count('id', filter=Q(status='DELAYED')),
        bond_total=Count('id', filter=Q(clearance_mode='BOND')),
        s1_all=Count('id', filter=Q(current_stage_number=1)),
        s2_all=Count('id', filter=Q(current_stage_number=2)),
        s3_all=Count('id', filter=Q(current_stage_number=3)),
        docs_today=Count('id', filter=Q(created_at__date=today_date)),
        customs_attn=Count('id', filter=Q(current_stage_number__in=[2, 3], status='DELAYED')),
    )

    active_jobs_count = jobs_metrics['active_total'] or 0
    completed_jobs_count = jobs_metrics['completed_total'] or 0
    delayed_jobs_count = jobs_metrics['delayed_total'] or 0
    visible_jobs_count = jobs_metrics['visible_total'] or 0
    pulse_all_count = visible_jobs_count
    pulse_active_count = active_jobs_count
    pulse_bond_count = jobs_metrics['bond_total'] or 0

    stage_1_count = active_stage_map.get(1, 0)
    stage_2_count = active_stage_map.get(2, 0)
    stage_3_count = active_stage_map.get(3, 0)
    stage_4_count = active_stage_map.get(4, 0)
    stage_5_count = active_stage_map.get(5, 0)
    stage_6_count = active_stage_map.get(6, 0)

    pulse_tra_count = stage_2_count
    jobs_at_tra = stage_2_count
    pulse_tbs_count = stage_3_count
    jobs_at_tbs = stage_3_count
    pulse_port_count = stage_4_count
    jobs_at_port = stage_4_count
    pulse_yard_count = stage_5_count
    jobs_at_yard = stage_5_count
    in_bond_count = stage_5_count
    pulse_completed_count = completed_jobs_count
    pulse_delayed_count = delayed_jobs_count
    can_view_financials = (role in [UserRole.CEO, UserRole.ADMIN, UserRole.FINANCE] or request.user.is_superuser)

    new_files_count = jobs_metrics['s1_all'] or 0
    pending_files_count = new_files_count
    pending_file_opening = new_files_count
    docs_received_today = jobs_metrics['docs_today'] or 0
    completed_documents_count = completed_jobs_count
    pending_declarations_count = jobs_metrics['s2_all'] or 0
    assessed_declarations_count = jobs_metrics['s3_all'] or 0
    awaiting_assessment_count = pending_declarations_count
    customs_attention_count = jobs_metrics['customs_attn'] or 0
    stage_1_count = new_files_count
    stage_2_count = pending_declarations_count



    context = {

        'can_view_all_stages': True,
        'can_view_financials': can_view_financials,
        'pulse_yard_count': pulse_yard_count,
        'jobs_at_yard': jobs_at_yard,

        'filter_label': filter_label,

        'preset': preset,

        'date_from': date_from,

        'date_to': date_to,

        'total_revenue': total_revenue,

        'total_expenses': total_expenses,

        'gross_margin': gross_margin,

        'gross_margin_pct': gross_margin_pct,

        'total_collected': total_collected,

        'outstanding_receivables': outstanding_receivables,

        'daily_income': daily_income,

        'daily_expenses': daily_expenses,

        'active_jobs_count': active_jobs_count,

        'completed_jobs_count': completed_jobs_count,

        'delayed_jobs_count': delayed_jobs_count,

        'visible_jobs_count': visible_jobs_count,

        'pulse_all_count': pulse_all_count,

        'pulse_active_count': pulse_active_count,

        'pulse_bond_count': pulse_bond_count,

        'pulse_port_count': pulse_port_count,

        'pulse_tra_count': pulse_tra_count,
        'pulse_tbs_count': pulse_tbs_count,
        'jobs_at_tbs': jobs_at_tbs,
        'stage_3_count': stage_3_count,
        'stage_6_count': stage_6_count,

        'pulse_completed_count': pulse_completed_count,

        'pulse_delayed_count': pulse_delayed_count,

        'jobs_at_tra': jobs_at_tra,

        'jobs_at_port': jobs_at_port,

        'in_bond_count': in_bond_count,

        'new_files_count': new_files_count,

        'pending_files_count': pending_files_count,

        'pending_file_opening': pending_file_opening,

        'docs_received_today': docs_received_today,

        'completed_documents_count': completed_documents_count,

        'pending_declarations_count': pending_declarations_count,

        'assessed_declarations_count': assessed_declarations_count,

        'awaiting_assessment_count': awaiting_assessment_count,

        'customs_attention_count': customs_attention_count,

        'stage_1_count': stage_1_count,

        'stage_2_count': stage_2_count,

        'containers_at_port': containers_at_port,

        'in_transit_count': in_transit_count,

        'under_verification_count': under_verification_count,

        'flagged_delayed_list': flagged_delayed_list,

        'pending_expenses': pending_expenses,

        'stage_counts': stage_counts,

        'stage_section_title': "Shipment Workflow Overview",

        'stage_section_desc': "Active consignments across operational stages",

        'pipeline_desc': "Total consignments in progress",

        'jobs': (jobs.prefetch_related('stages', 'invoices', 'expenses') if can_view_financials else jobs.prefetch_related('stages')).order_by('-created_at')[:20],

        'is_ceo': (role in [UserRole.CEO, UserRole.ADMIN] or request.user.is_superuser),

        'is_admin': (role == UserRole.ADMIN or request.user.is_superuser),

        'is_finance': (role == UserRole.FINANCE),

        'is_ops': (role not in [UserRole.CEO, UserRole.ADMIN, UserRole.FINANCE] and not request.user.is_superuser),

        'is_clearing': (role == UserRole.CLEARING_OFFICER),

        'is_doc': (role == UserRole.DOC_OFFICER),

        'is_port': (role == UserRole.PORT_OFFICER),

    }



    if role == UserRole.CEO and not request.user.is_superuser:
        ceo_period_jobs = list(all_jobs_raw.filter(created_at__date__range=(date_from, date_to))) if (date_from and date_to) else list(all_jobs_raw)
        ceo_salaries_qs = SalaryPayment.objects.filter(status='PAID')
        ceo_op_exp_qs = OperatingExpense.objects.exclude(category__name__icontains='Salary')
        ceo_other_rev_qs = OtherRevenue.objects.all()
        ceo_invoices_qs = ClientInvoice.objects.all()

        if date_from and date_to:
            ceo_salaries_qs = ceo_salaries_qs.filter(payment_date__range=(date_from, date_to))
            ceo_op_exp_qs = ceo_op_exp_qs.filter(date__range=(date_from, date_to))
            ceo_other_rev_qs = ceo_other_rev_qs.filter(date__range=(date_from, date_to))
            ceo_invoices_qs = ceo_invoices_qs.filter(issue_date__range=(date_from, date_to))

        sum_agent_fee = sum((j.cost_agent_fee or Decimal('0')) for j in ceo_period_jobs)
        sum_direct_costs = sum(j.total_direct_costs for j in ceo_period_jobs)
        sum_duty = sum((j.cost_duty or Decimal('0')) for j in ceo_period_jobs)
        sum_do = sum((j.cost_do or Decimal('0')) for j in ceo_period_jobs)
        sum_wharfage = sum((j.cost_wharfage or Decimal('0')) for j in ceo_period_jobs)
        sum_tiss = sum((j.cost_tiss_wharfage or Decimal('0')) for j in ceo_period_jobs)
        sum_handling = sum((j.cost_handling or Decimal('0')) for j in ceo_period_jobs)
        sum_facilitation = sum((j.cost_facilitation or Decimal('0')) for j in ceo_period_jobs)
        sum_transport = sum((j.cost_transport or Decimal('0')) for j in ceo_period_jobs)
        sum_fuel = sum((j.cost_fuel or Decimal('0')) for j in ceo_period_jobs)
        sum_ferry = sum((j.cost_ferry_charges or Decimal('0')) for j in ceo_period_jobs)

        sum_salaries_paid = sum((s.net_pay or Decimal('0')) for s in ceo_salaries_qs)
        sum_office_expenses = ceo_op_exp_qs.aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
        total_company_costs = sum_salaries_paid + sum_office_expenses

        other_rev_totals = ceo_other_rev_qs.aggregate(
            business=Sum('amount', filter=Q(inflow_type='OTHER_REVENUE')),
            refunds=Sum('returned_amount', filter=Q(inflow_type='CONTAINER_REFUND', deposit_status__in=['RETURNED_FULL', 'PARTIAL'])),
            capital=Sum('amount', filter=Q(inflow_type='CAPITAL_INJECTION')),
        )
        sum_other_business_revenue = other_rev_totals['business'] or Decimal('0.00')
        sum_container_refunds = other_rev_totals['refunds'] or Decimal('0.00')
        sum_capital_injections = other_rev_totals['capital'] or Decimal('0.00')
        total_other_inflows = sum_container_refunds + sum_capital_injections

        total_company_revenue = sum_agent_fee + sum_other_business_revenue
        net_profit = total_company_revenue - total_company_costs

        ceo_period_invoices = list(ceo_invoices_qs)
        ceo_total_invoiced = sum((i.total_amount or Decimal('0')) for i in ceo_period_invoices)
        ceo_total_collected = sum((i.amount_paid or Decimal('0')) for i in ceo_period_invoices)
        ceo_total_due = max(Decimal('0'), ceo_total_invoiced - ceo_total_collected)

        ceo_jobs_qs = jobs.exclude(job_number__icontains='TEST').exclude(customer__company_name__icontains='Test Logistics')
        ceo_agg = ceo_jobs_qs.aggregate(
            all_cnt=Count('id'),
            active_cnt=Count('id', filter=Q(status__in=['ACTIVE', 'DELAYED'])),
            completed_cnt=Count('id', filter=Q(status__in=['COMPLETED', 'CLOSED'])),
            tra_cnt=Count('id', filter=Q(current_stage_number=2, status__in=['ACTIVE', 'DELAYED'])),
            tbs_cnt=Count('id', filter=Q(current_stage_number=3, status__in=['ACTIVE', 'DELAYED'])),
            port_cnt=Count('id', filter=Q(current_stage_number=4, status__in=['ACTIVE', 'DELAYED'])),
            yard_cnt=Count('id', filter=Q(current_stage_number=5, status__in=['ACTIVE', 'DELAYED'])),
        )
        ceo_active_count = ceo_agg['active_cnt'] or 0
        ceo_completed_count = ceo_agg['completed_cnt'] or 0
        ceo_all_count = ceo_agg['all_cnt'] or 0

        context.update({
            'total_company_revenue': total_company_revenue,
            'sum_agent_fee': sum_agent_fee,
            'sum_other_business_revenue': sum_other_business_revenue,
            'total_company_costs': total_company_costs,
            'sum_salaries_paid': sum_salaries_paid,
            'sum_office_expenses': sum_office_expenses,
            'net_profit': net_profit,
            'sum_direct_costs': sum_direct_costs,
            'total_invoiced': ceo_total_invoiced,
            'total_collected': ceo_total_collected,
            'total_due': ceo_total_due,
            'total_other_inflows': total_other_inflows,
            'sum_container_refunds': sum_container_refunds,
            'sum_capital_injections': sum_capital_injections,
            'sum_duty': sum_duty,
            'sum_do': sum_do,
            'sum_wharfage_total': sum_wharfage + sum_tiss,
            'sum_handling': sum_handling,
            'sum_transport': sum_transport,
            'sum_fuel': sum_fuel,
            'sum_ferry_facil': sum_ferry + sum_facilitation,
            'ceo_jobs': ceo_jobs_qs.prefetch_related('stages', 'invoices', 'expenses').order_by('-created_at')[:30],
            'ceo_active_count': ceo_active_count,
            'ceo_completed_count': ceo_completed_count,
            'ceo_all_count': ceo_all_count,
            'pulse_tra_count': ceo_agg['tra_cnt'] or 0,
            'pulse_tbs_count': ceo_agg['tbs_cnt'] or 0,
            'pulse_port_count': ceo_agg['port_cnt'] or 0,
            'pulse_yard_count': ceo_agg['yard_cnt'] or 0,
        })
        return render(request, 'core/ceo_dashboard.html', context)

    return render(request, 'core/dashboard.html', context)











@login_required



def job_detail_view(request, job_id):



    job = get_object_or_404(JobShipment.objects.select_related('customer'), id=job_id)



    role = get_user_role(request.user)

    is_ceo = (role == UserRole.CEO)



    # Driver role check: if driver, only allow viewing if assigned to this shipment



    if role == UserRole.DRIVER:



        if job.driver_id != request.user.id:



            messages.error(request, "Access Restricted: You can only view jobs assigned directly to your vehicle.")



            return redirect('field_mobile')







    stages = job.stages.all().select_related('stage_definition', 'responsible_officer').order_by('stage_number')



    containers = job.containers.all().select_related('assigned_driver').order_by('container_number')



    documents = job.documents.all().select_related('uploaded_by', 'stage')



    expenses = job.expenses.all().select_related('requester', 'approver')

    if get_user_role(request.user) == UserRole.CEO and not request.user.is_superuser:

        expenses = expenses.exclude(approval_status='REQUESTED')



    invoices = job.invoices.all()



    audit_logs = job.audit_logs.all().order_by('-timestamp')[:20]







    all_users = User.objects.select_related('profile').all()



    available_vehicles = FleetVehicle.objects.all().order_by('plate_number')



    drivers = User.objects.filter(profile__role=UserRole.DRIVER).select_related('profile')



    doc_types = JobDocument.DOC_TYPES



    expense_categories = ExpenseCategory.choices



    container_types = JobShipment.CONTAINER_TYPES



    container_statuses = JobContainer.STATUS_CHOICES







    # RBAC action check for current user on this active stage



    user_can_advance_current = can_advance_stage(request.user, job.current_stage_number)







    # Strict RBAC: Only Operations Manager, CEO and Admin can track container fleet & logistics



    can_track_containers = role in [UserRole.OPERATIONS_MGR, UserRole.CEO, UserRole.ADMIN]







    # Simplified 9 Real-World Vehicle Clearing Milestones



    milestones = get_vehicle_tracking_milestones(job)



    completed_milestones_count = sum(1 for m in milestones if m['done'])







    # Itemized Financial Costing Ledger (Billed vs Field Spending)

    # Only include expenses that have been APPROVED / PAID by Finance

    paid_expenses = job.expenses.filter(

        Q(is_paid=True) | Q(approval_status__in=['APPROVED', 'PAID'])

    ).select_related('requester', 'approver').order_by('-requested_at')

    expenses = paid_expenses



    if job.invoices.exists():

        primary_invoice = auto_compile_customer_final_bill(job)

    else:

        primary_invoice = None



    exp_by_cat = {}

    for exp in paid_expenses:

        cat = exp.category

        desc_lower = (exp.description or '').lower()

        if cat == 'FUEL' or 'mafuta' in desc_lower or 'fuel' in desc_lower:

            cat = 'FUEL'

        elif cat in ['PORT_HANDLING', 'DOCUMENTATION', 'OTHER']:

            cat = 'SUNDRY'

        exp_by_cat[cat] = exp_by_cat.get(cat, Decimal('0.00')) + exp.amount



    ship_actual = exp_by_cat.get('SHIPPING_LINE', Decimal('0.00'))

    port_actual = exp_by_cat.get('PORT_CHARGES', Decimal('0.00'))

    trans_actual = exp_by_cat.get('TRANSPORT', Decimal('0.00'))

    fuel_actual = exp_by_cat.get('FUEL', Decimal('0.00'))

    sundry_actual = exp_by_cat.get('SUNDRY', Decimal('0.00'))

    agency_billed = primary_invoice.amount_clearing_agency_fee if primary_invoice else (job.contracted_revenue or Decimal('0.00'))



    raw_costing_items = [

        {

            'category': 'SHIPPING_LINE',

            'title': 'Shipping Line D/O (Delivery Order)',

            'subtitle': 'Shipping line release & D/O bill settled by Finance',

            'icon': 'fa-ship',

            'color': '#2563EB',

            'billed': ship_actual,

            'actual': ship_actual,

        },

        {

            'category': 'PORT_CHARGES',

            'title': 'Port, Wharfage & ICD Charges',

            'subtitle': 'TPA / ICD storage & wharfage bill settled by Finance',

            'icon': 'fa-anchor',

            'color': '#0284C7',

            'billed': port_actual,

            'actual': port_actual,

        },

        {

            'category': 'TRANSPORT',

            'title': 'Transport & Haulage (Trucking & Driver)',

            'subtitle': 'Driver & haulage allowance settled by Finance',

            'icon': 'fa-truck',

            'color': '#D97706',

            'billed': trans_actual,

            'actual': trans_actual,

        },

        {

            'category': 'FUEL',

            'title': 'Fuel & Port Extras (Mafuta ya Gari)',

            'subtitle': 'Vehicle fuel top-up requested by Port Officer & paid by Finance',

            'icon': 'fa-gas-pump',

            'color': '#EA580C',

            'billed': fuel_actual,

            'actual': fuel_actual,

        },

        {

            'category': 'SUNDRY',

            'title': 'Sundry, Tally & Port Handling',

            'subtitle': 'Additional port operational expenses paid by Finance',

            'icon': 'fa-receipt',

            'color': '#7C3AED',

            'billed': sundry_actual,

            'actual': sundry_actual,

        },

        {

            'category': 'AGENCY_FEE',

            'title': 'Clearing Agency Fee (Malkia Agency)',

            'subtitle': 'Malkia Cargo Wave service fee',

            'icon': 'fa-handshake',

            'color': '#16A34A',

            'billed': agency_billed,

            'actual': Decimal('0.00'),

        },

    ]



    # Only display rows that have actual non-zero amounts (hide all 0 TSh unused items)

    costing_items = []

    for item in raw_costing_items:

        if item['actual'] > 0 or item['billed'] > 0:

            item['margin'] = item['billed'] - item['actual']

            costing_items.append(item)



    total_itemized_billed = sum((i['billed'] for i in costing_items), Decimal('0.00'))

    total_itemized_actual = sum((i['actual'] for i in costing_items), Decimal('0.00'))

    total_itemized_margin = total_itemized_billed - total_itemized_actual







    context = {



        'job': job,



        'milestones': milestones,



        'completed_milestones_count': completed_milestones_count,



        'stages': stages,



        'containers': containers,



        'available_vehicles': available_vehicles,



        'drivers': drivers,



        'documents': documents,



        'expenses': expenses,



        'invoices': invoices,



        'audit_logs': audit_logs,



        'all_users': all_users,



        'doc_types': doc_types,



        'expense_categories': expense_categories,



        'container_types': container_types,



        'container_statuses': container_statuses,



        'next_stage_num': min(5, job.current_stage_number + 1),



        'user_can_advance_current': user_can_advance_current,



        'can_track_containers': can_track_containers,



        'client_duty_receipt': job.documents.filter(document_type='DUTY_PAYMENT_RECEIPT').order_by('-uploaded_at').first(),



        'costing_items': costing_items,



        'total_itemized_billed': total_itemized_billed,



        'total_itemized_actual': total_itemized_actual,



        'total_itemized_margin': total_itemized_margin,



        'primary_invoice': primary_invoice,

        'is_ceo': is_ceo,

        'can_edit_documents': user_can_manage_docs(request.user, job),

    }



    if role == UserRole.CEO and not request.user.is_superuser:
        context['ceo_wharfage_total'] = (job.cost_wharfage or Decimal('0')) + (job.cost_tiss_wharfage or Decimal('0'))
        context['ceo_ferry_facil'] = (job.cost_ferry_charges or Decimal('0')) + (job.cost_facilitation or Decimal('0'))
        return render(request, 'core/ceo_job_detail.html', context)

    return render(request, 'core/job_detail.html', context)











@login_required

def jobs_list_view(request):

    role = get_user_role(request.user)
    if role == UserRole.FINANCE and not request.user.is_superuser:
        return redirect('finance_vehicles_out')

    search_query = request.GET.get('q', '').strip()

    selected_customer = request.GET.get('customer', '').strip()

    selected_status = request.GET.get('status', '').strip()



    jobs = JobShipment.objects.all().select_related(

        'customer', 'documentation_officer', 'clearing_officer', 'port_officer'

    ).order_by('-created_at', '-id')



    if search_query:

        jobs = jobs.filter(

            Q(job_number__icontains=search_query) |

            Q(bl_number__icontains=search_query) |

            Q(chassis_number__icontains=search_query) |

            Q(cargo_description__icontains=search_query) |

            Q(customer__company_name__icontains=search_query)

        )



    if selected_customer:

        jobs = jobs.filter(customer_id=selected_customer)



    if selected_status:

        jobs = jobs.filter(status=selected_status)



    can_view_financials = (role in [UserRole.CEO, UserRole.ADMIN, UserRole.FINANCE] or request.user.is_superuser)

    jobs = jobs.prefetch_related('stages', 'invoices', 'expenses') if can_view_financials else jobs.prefetch_related('stages')

    customers = Customer.objects.all().order_by('company_name')



    context = {

        'jobs': jobs,

        'customers': customers,

        'search_query': search_query,

        'selected_customer': selected_customer,

        'selected_status': selected_status,

        'can_view_financials': can_view_financials,

        'is_ceo': (role in [UserRole.CEO, UserRole.ADMIN] or request.user.is_superuser),

    }

    return render(request, 'core/jobs_list.html', context)





@login_required



@role_required([UserRole.DOC_OFFICER, UserRole.OPERATIONS_MGR, UserRole.ADMIN])



def job_create_view(request):



    if request.method == 'POST':



        client_mode = request.POST.get('client_mode', 'existing')



        if client_mode == 'new':



            c_name = request.POST.get('new_client_name', '').strip()



            c_email = request.POST.get('new_client_email', '').strip()



            c_phone = request.POST.get('new_client_phone', '').strip()



            c_tin = request.POST.get('new_client_tin', '').strip()



            c_id = request.POST.get('new_client_id', '').strip()



            customer = Customer.objects.create(



                company_name=c_name,



                contact_person=c_name,



                email=c_email,



                phone=c_phone,



                tin_number=c_tin,



                id_number=c_id,



            )



            log_audit(request, "CREATE_CUSTOMER", f"Registered new client {customer.company_name} (TIN: {c_tin}, ID: {c_id})")



        else:



            customer_id = request.POST.get('customer')



            customer = get_object_or_404(Customer, id=customer_id)







        bl_number = request.POST.get('bl_number', '').strip().upper()



        chassis_number = request.POST.get('chassis_number', '').strip().upper()



        vessel_name = request.POST.get('vessel_name', '').strip()



        shipping_line = request.POST.get('shipping_line', 'OTHER').strip()



        port_of_origin = request.POST.get('port_of_origin', 'Yokohama, Japan').strip()

        vehicle_make = request.POST.get('vehicle_make', '').strip().upper()
        vehicle_model = request.POST.get('vehicle_model', '').strip().upper()
        registration_year = request.POST.get('registration_year', '').strip()
        cif_usd_raw = request.POST.get('cif_usd', '0').strip().replace(',', '').replace('$', '')
        try:
            cif_usd = Decimal(cif_usd_raw) if cif_usd_raw else Decimal('0')
        except Exception:
            cif_usd = Decimal('0')

        cargo_description = request.POST.get('cargo_description', '').strip()
        if not cargo_description or cargo_description == '1 Unit Motor Vehicle':
            desc_parts = [p for p in [vehicle_make, vehicle_model, registration_year] if p]
            if desc_parts:
                cargo_description = " ".join(desc_parts)
            else:
                cargo_description = '1 Unit Motor Vehicle'

        clearance_mode = request.POST.get('clearance_mode', 'DIRECT')



        if clearance_mode not in ['DIRECT', 'BOND', 'EX_BOND']:



            clearance_mode = 'DIRECT'







        doc_receive_method = request.POST.get('doc_receive_method', 'PHYSICAL')

        doc_bl_received = (request.POST.get('doc_bl_received') == '1') or bool(request.FILES.get('file_bl'))

        doc_invoice_received = (request.POST.get('doc_invoice_received') == '1') or bool(request.FILES.get('file_invoice'))

        doc_packing_list_received = (request.POST.get('doc_packing_list_received') == '1') or bool(request.FILES.get('file_packing_list'))

        doc_tbs_cert_received = (request.POST.get('doc_tbs_cert_received') == '1') or bool(request.FILES.get('file_tbs_cert'))

        doc_export_cert_received = (request.POST.get('doc_export_cert_received') == '1') or bool(request.FILES.get('file_export_cert'))







        job_number = JobShipment.generate_next_job_number()



        now = timezone.now()



        c41_ref = f"TRA-C41/{job_number}"



        tbs_ref = f"MALKIA/TBS/{job_number}"







        # Direct handover: Documentation Officer → Customs Declarer (no Operations approval step)



        declarer = User.objects.filter(



            profile__role=UserRole.CLEARING_OFFICER, is_active=True



        ).order_by('id').first()







        cargo_mode = request.POST.get('cargo_mode', 'vehicle').strip()
        if cargo_mode == 'container':
            chassis_number = ''
            vehicle_make = ''
            vehicle_model = ''
            registration_year = ''
            container_numbers = request.POST.get('container_numbers', '').strip().upper() or bl_number
            try:
                container_qty = max(1, int(request.POST.get('container_qty', 1) or 1))
            except (ValueError, TypeError):
                container_qty = 1
            container_size_type = request.POST.get('container_size_type', '40FT').strip()
            if container_size_type not in dict(JobShipment.CONTAINER_TYPES):
                container_size_type = '40FT'
            cargo_description = request.POST.get('container_item_desc', '').strip().upper() or 'Containerized Cargo'
        else:
            container_numbers = chassis_number or bl_number
            container_qty = 1
            container_size_type = 'RORO'

        job = JobShipment.objects.create(
            job_number=job_number,
            customer=customer,
            bl_number=bl_number,
            chassis_number=chassis_number,
            vessel_name=vessel_name,
            shipping_line=shipping_line,
            port_of_origin=port_of_origin,
            shipment_type='BONDED_WH' if clearance_mode == 'BOND' else 'IMPORT',
            clearance_mode=clearance_mode,
            container_numbers=container_numbers,
            container_qty=container_qty,
            container_size_type=container_size_type,



            cargo_description=cargo_description,
            vehicle_make=vehicle_make,
            vehicle_model=vehicle_model,
            registration_year=registration_year,
            cif_usd=cif_usd,



            doc_receive_method=doc_receive_method,



            doc_bl_received=doc_bl_received,



            doc_invoice_received=doc_invoice_received,



            doc_packing_list_received=doc_packing_list_received,



            doc_tbs_cert_received=doc_tbs_cert_received,



            doc_export_cert_received=doc_export_cert_received,



            doc_received_at=now,



            doc_c41_generated=True,



            doc_tbs_letter_generated=True,



            c41_reference_no=c41_ref,



            tbs_letter_reference_no=tbs_ref,



            file_opened_at=now,



            eta_arrival_date=now.date(),



            documentation_officer=request.user,



            clearing_officer=None,



            current_stage_number=2,



            status='ACTIVE'



        )







        # Initialize active workflow stage definitions with single bulk_create

        stage_defs = list(WorkflowStageDefinition.objects.all().order_by('stage_number'))

        stage_instances = []

        for sdef in stage_defs:

            is_first = (sdef.stage_number == 1)

            is_declaration = (sdef.stage_number == 2)

            stage_instances.append(

                JobStageInstance(

                    job=job,

                    stage_definition=sdef,

                    stage_number=sdef.stage_number,

                    name_en=sdef.name_en,

                    name_sw=sdef.name_sw,

                    status='COMPLETED' if is_first else ('IN_PROGRESS' if is_declaration else 'PENDING'),

                    target_days=sdef.target_days,

                    responsible_officer=request.user if is_first else (declarer if is_declaration else None),

                    started_at=now if (is_first or is_declaration) else None,

                    completed_at=now if is_first else None,

                    remarks=(

                        f"Client documents received & scanned ({job.get_doc_receive_method_display()}), Clearance Mode: {job.get_clearance_mode_display()}, and File opened with auto-generated C41 & TBS Letter."

                        if is_first else (

                            "File handed over directly to Customs Declarer for TRA TANESW & TBS declaration."

                            if is_declaration else ""

                        )

                    )

                )

            )



        JobStageInstance.objects.bulk_create(stage_instances)

        first_stage_instance = JobStageInstance.objects.filter(job=job, stage_number=1).first()







        # 1. Save individual dedicated document slots (BL, Invoice, Packing List, TBS, Export)

        dedicated_slots = [

            ('file_bl', 'BILL_OF_LADING', 'Bill of Lading (BL)', 'doc_bl_received'),

            ('file_invoice', 'COMMERCIAL_INVOICE', 'Commercial Invoice', 'doc_invoice_received'),

            ('file_packing_list', 'PACKING_LIST', 'Packing List', 'doc_packing_list_received'),

            ('file_tbs_cert', 'TBS_CERT', 'TBS Inspection Certificate', 'doc_tbs_cert_received'),

            ('file_export_cert', 'EXPORT_CERT', 'Export Certificate', 'doc_export_cert_received'),

        ]

        total_attached = 0

        for input_key, dtype, label, check_field in dedicated_slots:

            f = request.FILES.get(input_key)

            if f:

                total_attached += 1

                JobDocument.objects.create(

                    job=job,

                    stage=first_stage_instance,

                    document_type=dtype,

                    title=f"{label} ({f.name})",

                    file=f,

                    uploaded_by=request.user,

                    notes=f"Attached in dedicated slot for TANCIS customs declaration."

                )

                setattr(job, check_field, True)



        # 2. Save batch multi-files (if any dropped in batch dropzone)

        scanned_files = request.FILES.getlist('scanned_documents')

        for idx, sfile in enumerate(scanned_files, 1):

            lower_name = sfile.name.lower()

            dtype = 'OTHER'

            doc_label = 'Supporting Document'

            if 'bl' in lower_name or 'lading' in lower_name:

                dtype = 'BILL_OF_LADING'

                doc_label = 'Bill of Lading (BL)'

                job.doc_bl_received = True

            elif 'inv' in lower_name:

                dtype = 'COMMERCIAL_INVOICE'

                doc_label = 'Commercial Invoice'

                job.doc_invoice_received = True

            elif 'pack' in lower_name:

                dtype = 'PACKING_LIST'

                doc_label = 'Packing List'

                job.doc_packing_list_received = True

            elif 'tbs' in lower_name:

                dtype = 'TBS_CERT'

                doc_label = 'TBS Certificate'

                job.doc_tbs_cert_received = True

            elif 'export' in lower_name or 'origin' in lower_name:

                dtype = 'EXPORT_CERT'

                doc_label = 'Export Certificate'

                job.doc_export_cert_received = True

            

            total_attached += 1

            JobDocument.objects.create(

                job=job,

                stage=first_stage_instance,

                document_type=dtype,

                title=f"{doc_label} ({sfile.name})",

                file=sfile,

                uploaded_by=request.user,

                notes=f"Scanned batch file auto-categorized as {doc_label}."

            )



        job.save(update_fields=['doc_bl_received', 'doc_invoice_received', 'doc_packing_list_received', 'doc_tbs_cert_received', 'doc_export_cert_received'])



        rec_names = [name for name, ok in job.received_docs_checklist if ok]



        rec_str = ", ".join(rec_names) if rec_names else "None"



        log_audit(



            request,



            "OPEN_FILE_AND_SCAN_DOCS",



            f"Opened File BL: {bl_number or job_number} ({job_number}) for {customer.company_name}. Mode: {job.get_clearance_mode_display()}. Scanned Files: {len(scanned_files)}. Bundled with C41 ({c41_ref}) & TBS Letter ({tbs_ref}). Handed over directly to Customs Declarer ({declarer.username if declarer else 'no declarer found'}) for TANESW/TBS.",



            job=job



        )







        # Automated Client Notification: 1. Documents Received (Non-blocking background thread)

        try:

            from .email_service import send_stage_update_email

            send_stage_update_email(

                job,

                1,

                extra_note=f"Your documents have been received ({job.get_doc_receive_method_display()}): {rec_str} and your File (BL: {bl_number or job.job_number}) has been officially opened.",

                async_send=True

            )

        except Exception as e:

            print(f"[Email Notification Error] {e}")



        # Direct notification to the Customs Declarer (Non-blocking background thread)

        try:

            from .email_service import send_declarer_intake_notification

            send_declarer_intake_notification(job, declarer, async_send=True)

        except Exception as e:

            print(f"[Declarer Notification Error] {e}")







        messages.success(
            request,
            f"Shipment file {job.job_number} (BL: {bl_number or job.job_number}) opened successfully. Official TRA & TBS authorization letters are ready for 1-click printing."
        )
        return redirect(f'/jobs/{job.id}/?intake=success#documentCenter')







    customers = Customer.objects.all()



    context = {



        'customers': customers,



        'next_job_number': JobShipment.generate_next_job_number(),



        'today': timezone.now().date(),



    }



    return render(request, 'core/job_create.html', context)











@login_required



def update_doc_checklist_action(request, job_id):



    job = get_object_or_404(JobShipment, id=job_id)



    if request.method == 'POST':



        job.doc_bl_received = request.POST.get('doc_bl_received') == '1'



        job.doc_invoice_received = request.POST.get('doc_invoice_received') == '1'



        job.doc_packing_list_received = request.POST.get('doc_packing_list_received') == '1'



        job.doc_tbs_cert_received = request.POST.get('doc_tbs_cert_received') == '1'



        job.doc_export_cert_received = request.POST.get('doc_export_cert_received') == '1'



        method = request.POST.get('doc_receive_method')



        if method in ['PHYSICAL', 'EMAIL', 'BOTH']:



            job.doc_receive_method = method



        clearance_mode = request.POST.get('clearance_mode')



        if clearance_mode in ['DIRECT', 'BOND', 'EX_BOND']:



            job.clearance_mode = clearance_mode



            job.shipment_type = 'BONDED_WH' if clearance_mode == 'BOND' else 'IMPORT'



        bl_no = request.POST.get('bl_number')



        if bl_no is not None:



            job.bl_number = bl_no.strip().upper()



        chassis_no = request.POST.get('chassis_number')



        if chassis_no is not None:



            job.chassis_number = chassis_no.strip().upper()



        box_no = request.POST.get('box_number', '').strip()



        job.box_number = box_no



        if not job.c41_reference_no:



            job.c41_reference_no = f"TRA-C41/{job.job_number}"



            job.doc_c41_generated = True



        if not job.tbs_letter_reference_no:



            job.tbs_letter_reference_no = f"MALKIA/TBS/{job.job_number}"



            job.doc_tbs_letter_generated = True



        job.save()







        # Also handle any newly scanned files uploaded from the Quick Scanner Dropzone on job_detail



        scanned_files = request.FILES.getlist('scanned_documents')



        first_stage = job.stages.filter(stage_number=1).first()



        for idx, sfile in enumerate(scanned_files, 1):



            lower_name = sfile.name.lower()



            dtype = 'OTHER'



            if 'bl' in lower_name or 'lading' in lower_name:



                dtype = 'BL'



            elif 'inv' in lower_name:



                dtype = 'COMMERCIAL_INVOICE'



            elif 'pack' in lower_name:



                dtype = 'PACKING_LIST'



            elif 'tbs' in lower_name:



                dtype = 'TBS_PERMIT'



            elif 'export' in lower_name:



                dtype = 'CERTIFICATE_ORIGIN'



            JobDocument.objects.create(



                job=job,



                stage=first_stage,



                document_type=dtype,



                title=f"Scanned Client Doc: {sfile.name}",



                file=sfile,



                uploaded_by=request.user,



                notes=f"Scanned and bundled into Unified File Pack ({job.job_number})"



            )







        rec_names = [name for name, ok in job.received_docs_checklist if ok]



        log_audit(request, "UPDATE_DOCUMENTS", f"Updated File & Scanned Docs ({', '.join(rec_names)}) | Mode: {job.get_clearance_mode_display()} | New Scans: {len(scanned_files)} | Box No: {box_no or 'N/A'}", job=job)



        messages.success(request, "File details, clearance mode, and scanned document bundle updated successfully!")



    return redirect('job_detail', job_id=job.id)











@login_required



def print_tra_letter_view(request, job_id):
    job = get_object_or_404(JobShipment.objects.select_related('customer', 'documentation_officer'), id=job_id)
    if not job.c41_reference_no:
        job.c41_reference_no = f"TRA-AUTH/{job.job_number}"
        job.doc_c41_generated = True
        job.save(update_fields=['c41_reference_no', 'doc_c41_generated'])
    return render(request, 'core/print_c41.html', {'job': job, 'today': timezone.now()})

# Backwards compatibility alias
print_c41_document_view = print_tra_letter_view

@login_required
def print_letters_pack_view(request, job_id):
    """Prints both TRA & TBS client authorization letters back-to-back in 1 single print job"""
    job = get_object_or_404(JobShipment.objects.select_related('customer', 'documentation_officer'), id=job_id)
    if not job.c41_reference_no:
        job.c41_reference_no = f"TRA-AUTH/{job.job_number}"
        job.doc_c41_generated = True
    if not job.tbs_letter_reference_no:
        job.tbs_letter_reference_no = f"MALKIA/TBS/{job.job_number}"
        job.doc_tbs_letter_generated = True
    job.save(update_fields=['c41_reference_no', 'doc_c41_generated', 'tbs_letter_reference_no', 'doc_tbs_letter_generated'])
    return render(request, 'core/print_letters_pack.html', {'job': job, 'today': timezone.now()})

@login_required
def print_handover_note_view(request, job_id):
    job = get_object_or_404(JobShipment.objects.select_related('customer', 'documentation_officer', 'clearing_officer'), id=job_id)
    return render(request, 'core/print_handover_note.html', {'job': job, 'today': timezone.now()})












@login_required



def print_tbs_letter_view(request, job_id):



    job = get_object_or_404(JobShipment.objects.select_related('customer', 'documentation_officer'), id=job_id)



    if not job.tbs_letter_reference_no:



        job.tbs_letter_reference_no = f"MALKIA/TBS/{job.job_number}"



        job.doc_tbs_letter_generated = True



        job.save(update_fields=['tbs_letter_reference_no', 'doc_tbs_letter_generated'])



    return render(request, 'core/print_tbs_letter.html', {'job': job, 'today': timezone.now()})


@login_required
def print_shipping_auth_letter_view(request, job_id):
    job = get_object_or_404(JobShipment.objects.select_related('customer'), id=job_id)
    line = (request.GET.get('line') or 'PRIME').strip().upper()
    if line not in ('PRIME', 'WOSAC', 'CUSTOM'):
        line = 'PRIME'
    return render(request, 'core/print_shipping_auth_letter.html', {'job': job, 'today': timezone.now(), 'shipping_line': line})











@login_required



def print_combined_pack_view(request, job_id):



    job = get_object_or_404(JobShipment.objects.select_related('customer', 'documentation_officer'), id=job_id)



    if not job.c41_reference_no:



        job.c41_reference_no = f"TRA-C41/{job.job_number}"



        job.doc_c41_generated = True



    if not job.tbs_letter_reference_no:



        job.tbs_letter_reference_no = f"MALKIA/TBS/{job.job_number}"



        job.doc_tbs_letter_generated = True



    job.save(update_fields=['c41_reference_no', 'doc_c41_generated', 'tbs_letter_reference_no', 'doc_tbs_letter_generated'])



    scanned_docs = job.documents.all().order_by('uploaded_at')



    return render(request, 'core/print_combined_pack.html', {



        'job': job,



        'scanned_docs': scanned_docs,



        'today': timezone.now(),



    })











def _can_assign_declarer(user):
    return _can_assign_stage(user, 2)


def _can_assign_stage(user, stage_number):
    if not user or not user.is_authenticated:
        return False
    profile = getattr(user, 'profile', None)
    if stage_number in (2, 3):
        return bool(getattr(profile, 'can_assign_declaration', False))
    if stage_number == 4:
        return bool(getattr(profile, 'can_assign_port', False))
    return False


def _is_stage2_supervisor_viewer(user):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    profile = getattr(user, 'profile', None)
    return getattr(profile, 'role', None) in (UserRole.CEO, UserRole.ADMIN, UserRole.OPERATIONS_MGR)


def _assign_stage_officer(request, job_id, stage_number, field_name, default_redirect):
    if request.method != 'POST':
        return redirect(default_redirect)
    if not _can_assign_stage(request.user, stage_number):
        messages.error(request, "Huna ruhusa ya kugawa kazi za hatua hii.")
        return redirect(request.META.get('HTTP_REFERER') or default_redirect)

    job = get_object_or_404(JobShipment, id=job_id)
    officer_id = (request.POST.get('declarer_id') or '').strip()
    if officer_id:
        officer = get_object_or_404(User, id=officer_id, is_active=True)
        setattr(job, field_name, officer)
        job.save(update_fields=[field_name, 'updated_at'])
        officer_name = officer.get_full_name() or officer.username
        log_audit(request, "ASSIGN_STAGE_OFFICER", f"Assigned Stage {stage_number} to {officer_name} for {job.job_number}", job=job)
        messages.success(request, f"Kazi {job.job_number} imepangiwa {officer_name}.")
    else:
        setattr(job, field_name, None)
        job.save(update_fields=[field_name, 'updated_at'])
        log_audit(request, "UNASSIGN_STAGE_OFFICER", f"Cleared Stage {stage_number} assignment for {job.job_number}", job=job)
        messages.info(request, f"Kazi {job.job_number} imewekwa Unassigned.")

    return redirect(request.META.get('HTTP_REFERER') or default_redirect)


@login_required
def assign_declarer_view(request, job_id):
    return _assign_stage_officer(request, job_id, 2, 'clearing_officer', 'stage_customs')


@login_required
def assign_tbs_officer_view(request, job_id):
    return _assign_stage_officer(request, job_id, 3, 'tbs_officer', 'stage_tbs')


@login_required
def assign_port_officer_view(request, job_id):
    return _assign_stage_officer(request, job_id, 4, 'port_officer', 'stage_port')


@login_required
def advance_stage_action(request, job_id):
    if request.method == 'POST':
        job = get_object_or_404(JobShipment, id=job_id)
        current_stage = job.stages.filter(stage_number=job.current_stage_number).first()
        now = timezone.now()

        if job.current_stage_number in (2, 3, 4):
            stage_map = {
                2: ('clearing_officer', 'stage_customs'),
                3: ('tbs_officer', 'stage_tbs'),
                4: ('port_officer', 'stage_port'),
            }
            officer_field, default_redir = stage_map[job.current_stage_number]
            assigned_officer = getattr(job, officer_field)
            if not assigned_officer:
                messages.error(request, "Kazi hii bado haijapangiwa afisa. Mkuu wa hatua hii anatakiwa aigawe kwanza.")
                return redirect(request.META.get('HTTP_REFERER') or default_redir)
            if assigned_officer.id != request.user.id:
                assigned_name = assigned_officer.get_full_name() or assigned_officer.username
                messages.error(request, f"Kazi hii imepangiwa {assigned_name}. Yeye ndiye anayepaswa kubonyeza Complete.")
                return redirect(request.META.get('HTTP_REFERER') or default_redir)

        # Update stage-specific attributes automatically without requiring any form input
        if job.current_stage_number == 1:
            job.documentation_officer = request.user
            if not job.file_opened_at:
                job.file_opened_at = now
        elif job.current_stage_number == 2:
            if not job.clearing_officer:
                job.clearing_officer = request.user
            if not job.tanesw_lodged_at:
                job.tanesw_lodged_at = now
        elif job.current_stage_number == 3:
            if not job.tbs_officer:
                job.tbs_officer = request.user
        elif job.current_stage_number == 4:
            # Port Clearance & Gate Exit: consolidates D/O, Physical Verification, Port/ICD, Gate Exit
            if not job.port_officer:
                job.port_officer = request.user
            job.vehicle_inspection_done = True
            job.vehicle_inspection_at = now
            job.vehicle_inspection_by = request.user
            job.vehicle_dispatched_to_office = True
            job.vehicle_dispatched_at = now
        elif job.current_stage_number == 5:
            # Vehicle Arrival at Yard / Office
            job.vehicle_arrived_at_office = True
            job.vehicle_arrived_at = now
        elif job.current_stage_number >= 6:
            # Customer Handover
            if not job.received_by_name:
                job.received_by_name = job.customer.company_name
            job.delivered_date = now
            job.status = 'COMPLETED'

        # Complete current stage record
        if current_stage:
            current_stage.status = 'COMPLETED'
            current_stage.completed_at = now
            current_stage.responsible_officer = request.user
            if not current_stage.started_at:
                current_stage.started_at = job.created_at
            current_stage.save()

        user_name = request.user.get_full_name() or request.user.username

        # Advance to next stage or finish
        if job.current_stage_number < 6:
            completed_num = job.current_stage_number
            next_num = completed_num + 1
            job.current_stage_number = next_num
            next_stage = job.stages.filter(stage_number=next_num).first()
            if next_stage:
                next_stage.status = 'IN_PROGRESS'
                next_stage.started_at = now
                next_stage.save()

            log_audit(request, "ADVANCE_STAGE", f"Stage {completed_num} ({current_stage.name_en if current_stage else ''}) completed by {user_name}. Shipment advanced to Stage {next_num}: {next_stage.name_en if next_stage else ''}", job=job)

            try:
                from .email_service import send_stage_update_email
                send_stage_update_email(job, next_num)
            except Exception as e:
                print(f"[Email Notification Error] {e}")

            messages.success(request, f"Stage {completed_num} completed by {user_name}! Shipment advanced to Stage {next_num}.")
        else:
            job.status = 'COMPLETED'
            if not job.delivered_date:
                job.delivered_date = now

            log_audit(request, "COMPLETE_JOB", f"Job {job.job_number} completed and handed over successfully by {user_name}.", job=job)

            try:
                from .email_service import send_stage_update_email
                send_stage_update_email(job, 5)
            except Exception as e:
                print(f"[Email Notification Error] {e}")

            messages.success(request, f"Congratulations! Shipment {job.job_number} has been completed and handed over by {user_name}!")

        job.save()

    referer = request.META.get('HTTP_REFERER', '')
    if referer and 'login' not in referer:
        return redirect(referer)
    return redirect('job_detail', job_id=job_id)





# ==============================================================================



# INDIVIDUAL CONTAINER MANAGEMENT ACTIONS



# ==============================================================================







@login_required



def job_container_add_action(request, job_id):



    job = get_object_or_404(JobShipment, id=job_id)



    if request.method == 'POST':



        if get_user_role(request.user) == UserRole.CEO:



            messages.error(request, "Akaunti ya Boss ina mamlaka ya ukaguzi tu (Read-Only) na haina ruhusa ya kuongeza kontena.")



            return redirect('job_detail', job_id=job.id)







        c_number = request.POST.get('container_number', '').strip().upper()



        size_type = request.POST.get('size_type', job.container_size_type)



        seal_number = request.POST.get('seal_number', '').strip()



        truck_number = request.POST.get('assigned_truck', '').strip()



        trailer_number = request.POST.get('assigned_trailer', '').strip()



        driver_id = request.POST.get('driver_id')



        tare_weight = request.POST.get('tare_weight_kg', '').strip()



        gross_weight = request.POST.get('gross_weight_kg', '').strip()







        driver = User.objects.filter(id=driver_id).first() if driver_id else None







        container = JobContainer.objects.create(



            job=job,



            container_number=c_number,



            size_type=size_type,



            seal_number=seal_number,



            assigned_truck=truck_number,



            assigned_trailer=trailer_number,



            assigned_driver=driver,



            tare_weight_kg=Decimal(tare_weight) if tare_weight else None,



            gross_weight_kg=Decimal(gross_weight) if gross_weight else None,



            status='LOADED' if truck_number else 'AT_PORT'



        )







        # Sync comma-separated list on job if not present



        existing_list = [c.strip() for c in job.container_numbers.split(',') if c.strip()]



        if c_number not in existing_list:



            existing_list.append(c_number)



            job.container_numbers = ", ".join(existing_list)



            job.save(update_fields=['container_numbers'])







        log_audit(request, "ADD_CONTAINER", f"Added container {c_number} ({size_type}) to Job {job.job_number}", job=job)



        messages.success(request, f"Kontena {c_number} ({size_type}) limeongezwa kikamilifu kwenye Job {job.job_number}!")



    return redirect('job_detail', job_id=job.id)











@login_required



def job_container_update_action(request, container_id):



    container = get_object_or_404(JobContainer.objects.select_related('job'), id=container_id)



    job = container.job



    if request.method == 'POST':



        if get_user_role(request.user) == UserRole.CEO:



            messages.error(request, "Akaunti ya Boss ina mamlaka ya ukaguzi tu (Read-Only) na haina ruhusa ya kurekebisha kontena.")



            return redirect('job_detail', job_id=job.id)



        c_num = request.POST.get('container_number', '').strip()



        size_type = request.POST.get('size_type', '').strip()



        seal_number = request.POST.get('seal_number', '').strip()



        assigned_truck = request.POST.get('assigned_truck', '').strip()



        assigned_trailer = request.POST.get('assigned_trailer', '').strip()



        driver_id = request.POST.get('driver_id')



        status = request.POST.get('status', container.status)



        gate_pass_number = request.POST.get('gate_pass_number', '').strip()



        empty_free_days_str = request.POST.get('empty_free_days', '').strip()



        empty_return_depot = request.POST.get('empty_return_depot', '').strip()



        eir_number = request.POST.get('eir_number', '').strip()



        empty_returned_date_str = request.POST.get('empty_returned_date', '').strip()



        deposit_str = request.POST.get('container_deposit_amount', '').strip()



        is_deposit_refunded = request.POST.get('is_deposit_refunded') in ['1', 'true', 'True', 'on']



        tare_weight_str = request.POST.get('tare_weight_kg', '').strip()



        gross_weight_str = request.POST.get('gross_weight_kg', '').strip()



        notes = request.POST.get('notes', '').strip()







        if c_num:



            container.container_number = c_num



        if size_type:



            container.size_type = size_type



        if seal_number:



            container.seal_number = seal_number



        if assigned_truck:



            container.assigned_truck = assigned_truck



        if assigned_trailer:



            container.assigned_trailer = assigned_trailer



        if driver_id:



            container.assigned_driver = User.objects.filter(id=driver_id).first()



        elif driver_id == '':



            container.assigned_driver = None







        if gate_pass_number:



            container.gate_pass_number = gate_pass_number



        if empty_free_days_str and empty_free_days_str.isdigit():



            container.empty_free_days = int(empty_free_days_str)



        if deposit_str:



            try:



                container.container_deposit_amount = Decimal(deposit_str)



            except Exception:



                pass



        if tare_weight_str:



            try:



                container.tare_weight_kg = Decimal(tare_weight_str)



            except Exception:



                pass



        if gross_weight_str:



            try:



                container.gross_weight_kg = Decimal(gross_weight_str)



            except Exception:



                pass



        if notes:



            container.notes = notes







        container.status = status



        now = timezone.now()







        if status == 'LOADED' and not container.loaded_at:



            container.loaded_at = now



        elif status == 'IN_TRANSIT' and not container.gate_out_at:



            container.gate_out_at = now



        elif status == 'DELIVERED' and not container.delivered_at:



            container.delivered_at = now



        elif status == 'EMPTY_RETURNED':



            if not container.delivered_at:



                container.delivered_at = now



            if empty_returned_date_str:



                try:



                    container.empty_returned_date = timezone.datetime.strptime(empty_returned_date_str, '%Y-%m-%d').date()



                except ValueError:



                    container.empty_returned_date = now.date()



            else:



                container.empty_returned_date = now.date()







        if empty_return_depot:



            container.empty_return_depot = empty_return_depot



        if eir_number:



            container.eir_number = eir_number



        container.is_deposit_refunded = is_deposit_refunded







        container.save()







        # Keep job fields updated if this is the primary or first container



        if container.assigned_truck and not job.truck_number:



            job.truck_number = container.assigned_truck



            if container.assigned_trailer:



                job.trailer_number = container.assigned_trailer



            if container.assigned_driver:



                job.driver = container.assigned_driver



            job.save(update_fields=['truck_number', 'trailer_number', 'driver'])







        log_audit(



            request,



            "UPDATE_CONTAINER",



            f"Updated Container {container.container_number} to {container.get_status_display()} (Truck: {container.assigned_truck or 'N/A'}, Driver: {container.assigned_driver or 'N/A'}, EIR: {container.eir_number or 'N/A'})",



            job=job



        )



        messages.success(request, f"Container {container.container_number} details updated successfully ({container.get_status_display()})!")







    next_url = request.POST.get('next')



    if next_url == 'logistics_jobs':



        return redirect('logistics_jobs')



    elif next_url == 'container_tracking':



        return redirect('container_tracking_list')



    return redirect('job_detail', job_id=job.id)











@login_required



@role_required([UserRole.OPERATIONS_MGR, UserRole.CEO, UserRole.ADMIN])



def container_tracking_view(request):



    """



    Central Container Tracking & Demurrage Monitor



    - Tracks all active and historical containers



    - Calculates free days remaining vs detention overdue days



    - Tracks shipping line security deposits & EIR return receipts



    - Filters: All, At Port, In Transit, Delivered (Awaiting Return), Empty Returned, Overdue Demurrage



    """



    tab = request.GET.get('tab', 'all')



    search_q = request.GET.get('q', '').strip()



    depot_filter = request.GET.get('depot', '').strip()







    containers_qs = JobContainer.objects.select_related('job', 'job__customer', 'assigned_driver').order_by('-updated_at')







    if search_q:



        containers_qs = containers_qs.filter(



            Q(container_number__icontains=search_q) |



            Q(seal_number__icontains=search_q) |



            Q(job__job_number__icontains=search_q) |



            Q(job__bl_number__icontains=search_q) |



            Q(job__customer__company_name__icontains=search_q) |



            Q(assigned_truck__icontains=search_q) |



            Q(eir_number__icontains=search_q) |



            Q(empty_return_depot__icontains=search_q)



        )







    if depot_filter:



        containers_qs = containers_qs.filter(empty_return_depot__icontains=depot_filter)







    all_containers = list(containers_qs)







    # Metrics calculation



    total_tracked = len(all_containers)



    at_port_count = sum(1 for c in all_containers if c.status in ['AT_PORT', 'VERIFIED'])



    in_transit_count = sum(1 for c in all_containers if c.status in ['LOADED', 'IN_TRANSIT'])



    delivered_awaiting_return_count = sum(1 for c in all_containers if c.status == 'DELIVERED')



    empty_returned_count = sum(1 for c in all_containers if c.status == 'EMPTY_RETURNED')



    



    # Overdue & expiring soon



    overdue_count = sum(1 for c in all_containers if c.is_detention_overdue)



    expiring_soon_count = sum(1 for c in all_containers if c.is_detention_expiring_soon)



    



    # Financial: Deposits held & unrefunded



    total_deposits_held = sum(c.container_deposit_amount for c in all_containers if not c.is_deposit_refunded)







    # Filter according to tab



    if tab == 'at_port':



        displayed_containers = [c for c in all_containers if c.status in ['AT_PORT', 'VERIFIED']]



    elif tab == 'transit':



        displayed_containers = [c for c in all_containers if c.status in ['LOADED', 'IN_TRANSIT']]



    elif tab == 'delivered':



        displayed_containers = [c for c in all_containers if c.status == 'DELIVERED']



    elif tab == 'returned':



        displayed_containers = [c for c in all_containers if c.status == 'EMPTY_RETURNED']



    elif tab == 'overdue':



        displayed_containers = [c for c in all_containers if c.is_detention_overdue or c.is_detention_expiring_soon]



    else:



        displayed_containers = all_containers







    available_vehicles = FleetVehicle.objects.all()



    drivers = User.objects.filter(profile__role=UserRole.DRIVER).select_related('profile')







    context = {



        'containers': displayed_containers,



        'tab': tab,



        'search_q': search_q,



        'depot_filter': depot_filter,



        'total_tracked': total_tracked,



        'at_port_count': at_port_count,



        'in_transit_count': in_transit_count,



        'delivered_awaiting_return_count': delivered_awaiting_return_count,



        'empty_returned_count': empty_returned_count,



        'overdue_count': overdue_count,



        'expiring_soon_count': expiring_soon_count,



        'total_deposits_held': total_deposits_held,



        'available_vehicles': available_vehicles,



        'drivers': drivers,



        'status_choices': JobContainer.STATUS_CHOICES,



    }



    return render(request, 'core/container_tracking.html', context)















@login_required



@role_required([UserRole.DOC_OFFICER, UserRole.OPERATIONS_MGR, UserRole.CEO, UserRole.ADMIN])



def document_register_view(request):



    query = request.GET.get('q', '').strip()



    jobs = JobShipment.objects.all().select_related('customer').order_by('-created_at')



    if query:



        jobs = jobs.filter(



            Q(job_number__icontains=query) |



            Q(bl_number__icontains=query) |



            Q(chassis_number__icontains=query) |



            Q(customer__company_name__icontains=query)



        )







    context = {



        'jobs': jobs,



        'search_query': query,



    }



    return render(request, 'core/document_register.html', context)











@login_required



@role_required([UserRole.OPERATIONS_MGR, UserRole.CLEARING_OFFICER, UserRole.CEO, UserRole.ADMIN])



def customs_declarations_view(request):



    query = request.GET.get('q', '').strip()



    status_filter = request.GET.get('status', '')







    jobs = JobShipment.objects.filter(



        status__in=['ACTIVE', 'DELAYED']



    ).select_related('customer', 'clearing_officer', 'documentation_officer').order_by('current_stage_number')







    if query:



        jobs = jobs.filter(



            Q(job_number__icontains=query) |



            Q(bl_number__icontains=query) |



            Q(declaration_number__icontains=query) |



            Q(customer__company_name__icontains=query)



        )







    # Breakdown of customs stages



    awaiting_declaration = jobs.filter(current_stage_number=3).count()



    duty_payment_stage = jobs.filter(current_stage_number=4).count()



    customs_released = jobs.filter(current_stage_number__gte=7).count()







    context = {



        'jobs': jobs,



        'search_query': query,



        'awaiting_declaration': awaiting_declaration,



        'duty_payment_stage': duty_payment_stage,



        'customs_released': customs_released,



    }



    return render(request, 'core/customs_declarations.html', context)











@login_required



@role_required([UserRole.OPERATIONS_MGR, UserRole.CEO, UserRole.ADMIN])



def jobs_archive_view(request):



    query = request.GET.get('q', '').strip()



    archived_jobs = JobShipment.objects.filter(



        status__in=['COMPLETED', 'CLOSED']



    ).select_related('customer', 'documentation_officer', 'clearing_officer', 'port_officer').order_by('-updated_at')







    if query:



        archived_jobs = archived_jobs.filter(



            Q(job_number__icontains=query) |



            Q(bl_number__icontains=query) |



            Q(container_numbers__icontains=query) |



            Q(customer__company_name__icontains=query) |



            Q(box_number__icontains=query)



        )







    context = {



        'archived_jobs': archived_jobs,



        'search_query': query,



        'total_archived': archived_jobs.count(),



    }



    return render(request, 'core/jobs_archive.html', context)











@login_required



@role_required([UserRole.CLEARING_OFFICER, UserRole.DOC_OFFICER, UserRole.OPERATIONS_MGR, UserRole.CEO, UserRole.ADMIN])



def customs_pending_declarations_view(request):



    query = request.GET.get('q', '').strip()



    channel_filter = request.GET.get('channel', '')







    base_qs = JobShipment.objects.filter(



        status__in=['ACTIVE', 'DELAYED']



    ).select_related(



        'customer', 'documentation_officer', 'clearing_officer'



    ).prefetch_related(



        'documents', 'containers'



    )







    if query:



        base_qs = base_qs.filter(



            Q(job_number__icontains=query) |



            Q(bl_number__icontains=query) |



            Q(chassis_number__icontains=query) |



            Q(declaration_number__icontains=query) |



            Q(duty_control_number__icontains=query) |



            Q(container_numbers__icontains=query) |



            Q(customer__company_name__icontains=query) |



            Q(box_number__icontains=query) |



            Q(vessel_name__icontains=query) |



            Q(customs_manifest_number__icontains=query)



        )







    if channel_filter:



        base_qs = base_qs.filter(customs_channel=channel_filter)







    # 4 Real-World Step 3 Queues:



    # 1. Awaiting Lodgement into TRA TANESW



    awaiting_lodgement_jobs = base_qs.filter(



        Q(tra_status='PENDING_LODGEMENT') | Q(declaration_number='')



    ).exclude(



        tra_status__in=['LODGED_76H', 'ACCEPTED', 'OBJECTION']



    ).order_by('current_stage_number', '-created_at')







    # 2. Lodged into TANESW (76-Hour SLA Countdown in progress)



    tanesw_76h_jobs = base_qs.filter(



        tra_status='LODGED_76H'



    ).order_by('tanesw_lodged_at', '-created_at')







    # 3. Accepted & Control Number Generated



    accepted_jobs = base_qs.filter(



        Q(tra_status='ACCEPTED') | (Q(assessed_duty_amount__gt=0) & Q(duty_control_number__gt=''))



    ).order_by('-tra_accepted_at', '-updated_at')







    # 4. Objections / Queries raised by TRA



    objection_jobs = base_qs.filter(



        tra_status='OBJECTION'



    ).order_by('-tra_objection_at', '-updated_at')







    # Legacy compatibility aliases



    pending_jobs = awaiting_lodgement_jobs



    assessed_jobs = accepted_jobs



    all_jobs = base_qs.filter(



        current_stage_number__in=[2, 3, 4, 5, 6]



    ).order_by('current_stage_number', '-updated_at')







    # Metrics



    awaiting_lodgement_count = awaiting_lodgement_jobs.count()



    tanesw_76h_count = tanesw_76h_jobs.count()



    accepted_count = accepted_jobs.count()



    objection_count = objection_jobs.count()







    pending_count = awaiting_lodgement_count



    green_channel_count = base_qs.filter(customs_channel='GREEN').count()



    red_channel_count = base_qs.filter(customs_channel='RED').count()







    context = {



        'awaiting_lodgement_jobs': awaiting_lodgement_jobs,



        'tanesw_76h_jobs': tanesw_76h_jobs,



        'accepted_jobs': accepted_jobs,



        'objection_jobs': objection_jobs,



        'pending_jobs': pending_jobs,



        'assessed_jobs': assessed_jobs,



        'all_jobs': all_jobs,



        'search_query': query,



        'channel_filter': channel_filter,



        'awaiting_lodgement_count': awaiting_lodgement_count,



        'tanesw_76h_count': tanesw_76h_count,



        'accepted_count': accepted_count,



        'objection_count': objection_count,



        'pending_count': pending_count,



        'assessed_count': accepted_count,



        'green_channel_count': green_channel_count,



        'red_channel_count': red_channel_count,



    }



    return render(request, 'core/customs_pending_declarations.html', context)











@login_required



@role_required([UserRole.CLEARING_OFFICER, UserRole.OPERATIONS_MGR, UserRole.CEO, UserRole.ADMIN])



def customs_lodge_tanesw_action(request, job_id):



    if request.method == 'POST':



        job = get_object_or_404(JobShipment, id=job_id)



        declaration_number = request.POST.get('declaration_number', '').strip()



        customs_channel = request.POST.get('customs_channel', 'YELLOW').strip()



        tbs_reference_no = request.POST.get('tbs_reference_no', '').strip()



        lodge_tbs = request.POST.get('lodge_tbs') == '1' or bool(tbs_reference_no)



        notes = request.POST.get('notes', '').strip()







        if not declaration_number:



            messages.error(request, "TANSAD Entry Number is required to lodge into TRA TANESW.")



            return redirect('customs_pending_declarations')







        now = timezone.now()



        job.declaration_number = declaration_number



        job.customs_channel = customs_channel



        job.tanesw_lodged_at = now



        job.tra_status = 'LODGED_76H'







        if not job.clearing_officer:



            job.clearing_officer = request.user







        if lodge_tbs:



            job.tbs_status = 'PENDING_APPROVAL'



            job.tbs_submitted_at = now



            if tbs_reference_no:



                job.tbs_reference_no = tbs_reference_no







        # Update Workflow Stage: Advance Stage 2 to COMPLETED, Stage 3 to IN_PROGRESS



        st2 = job.stages.filter(stage_number=2).first()



        if st2 and st2.status != 'COMPLETED':



            st2.status = 'COMPLETED'



            st2.completed_at = now



            st2.save()







        st3 = job.stages.filter(stage_number=3).first()



        if st3:



            st3.status = 'IN_PROGRESS'



            st3.started_at = st3.started_at or now



            st3.responsible_officer = request.user



            st3.remarks = f"Lodged in TRA TANESW (TANSAD: {declaration_number}) | Risk: {customs_channel} | 76h SLA Review Running"



            st3.save()







        job.current_stage_number = 3



        job.save()







        log_audit(



            request,



            "TANESW_LODGED",



            f"Lodged TANSAD {declaration_number} [{customs_channel}] into TRA TANESW for {job.job_number}. 76h SLA review counter started.",



            job=job



        )



        messages.success(



            request,



            f"TANSAD Entry '{declaration_number}' successfully lodged into TRA TANESW! 76-hour SLA review countdown is actively running."



        )



        next_url = request.POST.get('next')



        if next_url:



            return redirect(next_url)



        return redirect('/customs/declarations/?tab=tanesw_76h')







    return redirect('customs_pending_declarations')











@login_required



@role_required([UserRole.CLEARING_OFFICER, UserRole.OPERATIONS_MGR, UserRole.CEO, UserRole.ADMIN])



def customs_record_tra_outcome_action(request, job_id):



    if request.method == 'POST':



        job = get_object_or_404(JobShipment, id=job_id)



        outcome = request.POST.get('outcome', '').strip().upper()



        now = timezone.now()







        if outcome == 'ACCEPTED':



            assessment_file = request.FILES.get('assessment_file')



            notes = request.POST.get('notes', '').strip()







            if job.clearance_mode == 'BOND':



                removal_order = request.POST.get('removal_order_no', '').strip() or request.POST.get('control_number', '').strip() or 'IN-BOND-C41'



                job.tra_status = 'ACCEPTED'



                job.tra_accepted_at = now



                job.duty_control_number = removal_order



                job.duty_payment_reference = removal_order



                job.assessed_duty_amount = Decimal('0.00')







                # Complete Stage 3



                st3 = job.stages.filter(stage_number=3).first()



                if st3:



                    st3.status = 'COMPLETED'



                    st3.completed_at = now



                    st3.remarks = f"TRA In-Bond Clearance Accepted. Removal Order / Bond: {removal_order}"



                    st3.save()







                # Complete Stage 4 (Direct Duty is Bypassed at Port under Bond)



                st4 = job.stages.filter(stage_number=4).first()



                if st4:



                    st4.status = 'COMPLETED'



                    st4.completed_at = now



                    st4.remarks = "TRA Port duty payment waived under Customs Bond C.41. Ex-Bond payable upon yard release."



                    st4.save()







                # Advance directly to Stage 5 (Port Verification & Delivery Order)



                job.current_stage_number = 5



                st5 = job.stages.filter(stage_number=5).first()



                if st5:



                    st5.status = 'IN_PROGRESS'



                    st5.started_at = st5.started_at or now



                    st5.save()







                if assessment_file:



                    JobDocument.objects.create(



                        job=job,



                        stage=st3,



                        document_type='DECLARATION_ASSESSMENT',



                        title=f"TRA Bond Release / Removal Order - {job.bl_number or job.job_number}",



                        file=assessment_file,



                        uploaded_by=request.user,



                        notes=f"Bond Ref: {removal_order} | Notes: {notes}"



                    )







                job.save()







                log_audit(



                    request,



                    "TRA_BOND_RELEASE_ACCEPTED",



                    f"TRA In-Bond Release approved for B/L: {job.bl_number}. Removal Order: {removal_order}. Direct tax payment bypassed, consignment advanced to Stage 5 (Port Verification).",



                    job=job



                )



                messages.success(



                    request,



                    f"Kibali cha In-Bond (Removal Order: {removal_order}) kimekubaliwa na TRA! Hakuna kodi ya kulipa bandarini — mzigo umeruhusiwa kuelekea bandarini moja kwa moja (Stage 5: Port Verification)."



                )



                return redirect('/customs/declarations/?tab=tanesw_76h')







            else:



                control_number = request.POST.get('control_number', '').strip()



                duty_amount_str = request.POST.get('assessed_duty_amount', '0').strip().replace(',', '')



                customs_channel = request.POST.get('customs_channel', '').strip()







                try:



                    duty_amount = Decimal(duty_amount_str) if duty_amount_str else Decimal('0.00')



                except Exception:



                    duty_amount = Decimal('0.00')







                job.tra_status = 'ACCEPTED'

                job.tra_accepted_at = now

                job.duty_control_number = control_number

                job.duty_payment_reference = ''

                job.duty_paid = False

                job.assessed_duty_amount = duty_amount

                if customs_channel in ['GREEN', 'YELLOW', 'RED']:

                    job.customs_channel = customs_channel



                # Complete Stage 2 (Customs Declaration & Assessment)

                st2 = job.stages.filter(stage_number=2).first()

                if st2 and st2.status != 'COMPLETED':

                    st2.status = 'COMPLETED'

                    st2.completed_at = now

                    st2.save()



                # Consignment is now at Stage 3 (TRA Duty Payment - Awaiting payment by client & finance verification)

                job.current_stage_number = 3

                st3 = job.stages.filter(stage_number=3).first()

                if st3:

                    st3.status = 'IN_PROGRESS'

                    st3.started_at = st3.started_at or now

                    st3.remarks = f"TRA Assessment Accepted. GePG Control No: {control_number} | Assessed Duty: TSh {duty_amount:,.2f} | Awaiting Finance & Client Payment"

                    st3.save()



                # Ensure Stage 4 remains PENDING

                st4 = job.stages.filter(stage_number=4).first()

                if st4 and st4.status != 'PENDING':

                    st4.status = 'PENDING'

                    st4.completed_at = None

                    st4.save()







                # Save uploaded assessment notice if provided



                if assessment_file:



                    JobDocument.objects.create(



                        job=job,



                        stage=st3,



                        document_type='DECLARATION_ASSESSMENT',



                        title=f"TRA Assessment Notice - {job.declaration_number or job.job_number}",



                        file=assessment_file,



                        uploaded_by=request.user,



                        notes=f"Duty: TSh {duty_amount:,.2f} | GePG: {control_number} | Notes: {notes}"



                    )







                job.save()







                # Dispatch notification email to client



                try:



                    from .email_service import send_stage_update_email



                    from .email_service import notify_client_milestone

                    notify_client_milestone(job, 'TRA_DUTY_ISSUED', extra_note=f"GePG Control No: {control_number} | Kiasi cha Kodi: TSh {duty_amount:,.0f}.")



                except Exception as e:



                    print(f"[Email Notification Error] {e}")







                log_audit(



                    request,



                    "TRA_ASSESSMENT_ACCEPTED",



                    f"TRA Assessment Accepted for {job.job_number} (TANSAD: {job.declaration_number}). GePG Control No: {control_number}, Assessed Duty: TSh {duty_amount:,.2f}.",



                    job=job



                )



                messages.success(



                    request,



                    f"TRA Assessment Accepted! GePG Control No: '{control_number}', Assessed Duty: TSh {duty_amount:,.2f}. Assessment notice generated."



                )



                next_url = request.POST.get('next') or '/customs/declarations/?tab=accepted'



                return redirect(next_url)







        elif outcome == 'OBJECTION':



            objection_notes = request.POST.get('tra_objection_notes', '').strip()



            job.tra_status = 'OBJECTION'



            job.tra_objection_at = now



            job.tra_objection_notes = objection_notes



            job.save(update_fields=['tra_status', 'tra_objection_at', 'tra_objection_notes'])







            st3 = job.stages.filter(stage_number=3).first()



            if st3:



                st3.remarks = f"TRA Objection: {objection_notes}"



                st3.save(update_fields=['remarks'])







            log_audit(



                request,



                "TRA_ASSESSMENT_OBJECTION",



                f"TRA Objection lodged against {job.job_number} (TANSAD: {job.declaration_number}). Reason: {objection_notes}",



                job=job



            )



            messages.warning(



                request,



                f"TRA Objection recorded for TANSAD '{job.declaration_number}'. The file has been moved to Objections tab for query rectification."



            )



            next_url = request.POST.get('next') or '/customs/declarations/?tab=objection'



            return redirect(next_url)







    return redirect('customs_pending_declarations')











@login_required



@role_required([UserRole.CLEARING_OFFICER, UserRole.OPERATIONS_MGR, UserRole.CEO, UserRole.ADMIN])



def customs_update_tbs_action(request, job_id):



    if request.method == 'POST':



        job = get_object_or_404(JobShipment, id=job_id)



        tbs_status = request.POST.get('tbs_status', 'PENDING_APPROVAL').strip()



        tbs_reference_no = request.POST.get('tbs_reference_no', '').strip()



        tbs_notes = request.POST.get('tbs_notes', '').strip()







        job.tbs_status = tbs_status



        if tbs_reference_no:



            job.tbs_reference_no = tbs_reference_no



        if tbs_notes:



            job.tbs_notes = tbs_notes







        now = timezone.now()



        if tbs_status == 'APPROVED' and not job.tbs_approved_at:



            job.tbs_approved_at = now



        elif tbs_status == 'PENDING_APPROVAL' and not job.tbs_submitted_at:



            job.tbs_submitted_at = now







        job.save()







        log_audit(



            request,



            "TBS_STATUS_UPDATED",



            f"Updated TBS status to {tbs_status} (Ref: {job.tbs_reference_no}) for {job.job_number}.",



            job=job



        )



        messages.success(request, f"TBS clearance status for {job.job_number} updated to '{tbs_status}'.")



        next_url = request.POST.get('next') or '/customs/declarations/?tab=tanesw_76h'



        return redirect(next_url)







    return redirect('customs_pending_declarations')











@login_required



@role_required([UserRole.DOC_OFFICER, UserRole.CLEARING_OFFICER, UserRole.OPERATIONS_MGR, UserRole.CEO, UserRole.ADMIN])



def handover_original_docs_action(request, job_id):



    if request.method == 'POST':



        job = get_object_or_404(JobShipment, id=job_id)



        recipient = request.POST.get('original_docs_recipient', '').strip() or "Port / Field Agent"



        notes = request.POST.get('original_docs_dispatch_notes', '').strip()







        job.original_docs_dispatched_to_field = True



        job.original_docs_dispatched_at = timezone.now()



        job.original_docs_recipient = recipient



        job.original_docs_dispatch_notes = notes



        job.save(update_fields=[



            'original_docs_dispatched_to_field',



            'original_docs_dispatched_at',



            'original_docs_recipient',



            'original_docs_dispatch_notes'



        ])







        log_audit(



            request,



            "ORIGINAL_DOCS_DISPATCHED",



            f"Physical original documents handed over to {recipient} for Shipping Line D/O processing. Job: {job.job_number}",



            job=job



        )



        messages.success(



            request,



            f"Physical original documents successfully handed over to '{recipient}' for Shipping Line D/O processing."



        )



        next_url = request.POST.get('next')



        if next_url:



            return redirect(next_url)



        return redirect('job_detail', job_id=job.id)







    return redirect('job_detail', job_id=job_id)











@login_required



def print_assessment_notice_view(request, job_id):



    job = get_object_or_404(



        JobShipment.objects.select_related('customer', 'documentation_officer', 'clearing_officer').prefetch_related('containers'),



        id=job_id



    )



    containers = list(job.containers.all())



    return render(request, 'core/print_assessment_notice.html', {



        'job': job,



        'containers': containers,



        'today': timezone.now()



    })















@login_required



@role_required([UserRole.CLEARING_OFFICER, UserRole.OPERATIONS_MGR])



def customs_lodge_declaration_action(request, job_id):



    if request.method == 'POST':



        job = get_object_or_404(JobShipment, id=job_id)



        declaration_number = request.POST.get('declaration_number', '').strip()



        customs_channel = request.POST.get('customs_channel', 'YELLOW').strip()



        duty_amount_str = request.POST.get('assessed_duty_amount', '0').strip().replace(',', '')



        control_number = request.POST.get('control_number', '').strip()



        notes = request.POST.get('notes', '').strip()



        assessment_file = request.FILES.get('assessment_file')







        if not declaration_number:



            messages.error(request, "TANCIS Declaration / Entry Number is required.")



            return redirect('customs_pending_declarations')







        try:



            duty_amount = Decimal(duty_amount_str) if duty_amount_str else Decimal('0.00')



        except Exception:



            duty_amount = Decimal('0.00')







        job.declaration_number = declaration_number

        job.customs_channel = customs_channel

        job.assessed_duty_amount = duty_amount

        job.duty_control_number = control_number

        job.duty_payment_reference = ''

        job.duty_paid = False

        if not job.clearing_officer:

            job.clearing_officer = request.user



        now = timezone.now()



        # Complete Stage 2 if still in Stage 2

        st2 = job.stages.filter(stage_number=2).first()

        if st2 and st2.status != 'COMPLETED':

            st2.status = 'COMPLETED'

            st2.completed_at = now

            st2.save()



        # Consignment is now at Stage 3 (TRA Duty Payment - Awaiting payment confirmation)

        job.current_stage_number = 3

        st3 = job.stages.filter(stage_number=3).first()

        if st3:

            st3.status = 'IN_PROGRESS'

            st3.started_at = st3.started_at or now

            st3.remarks = f"TANCIS Entry: {declaration_number} | Channel: {customs_channel} | Assessed Duty: TSh {duty_amount:,.2f} | GePG: {control_number} (Awaiting Payment)"

            st3.save()



        # Ensure Stage 4 remains PENDING

        st4 = job.stages.filter(stage_number=4).first()

        if st4 and st4.status != 'PENDING':

            st4.status = 'PENDING'

            st4.completed_at = None

            st4.save()



        # Attach Assessment Notice Document if provided

        if assessment_file:

            JobDocument.objects.create(

                job=job,

                stage=st3,

                document_type='DECLARATION_ASSESSMENT',

                title=f"TRA TANCIS Assessment Notice - {declaration_number}",

                file=assessment_file,

                uploaded_by=request.user,

                notes=f"Channel: {customs_channel} | Duty: TSh {duty_amount:,.2f} | Control No: {control_number} | Notes: {notes}"

            )







        job.save()







        # Automated Customer Email Notification: Stage 4 (Duty Payment & GePG Control Number)



        try:



            from .email_service import send_stage_update_email



            from .email_service import notify_client_milestone

            notify_client_milestone(job, 'TRA_DUTY_ISSUED', extra_note=notes)



        except Exception as e:



            print(f"[Email Notification Error] {e}")







        log_audit(



            request,



            "TANCIS_DECLARATION_LODGED",



            f"Lodged TANCIS Entry {declaration_number} [{customs_channel}] for {job.job_number}. Assessed Duty: TSh {duty_amount:,.2f}, GePG Control No: {control_number}.",



            job=job



        )



        messages.success(



            request,



            f"TANCIS Declaration '{declaration_number}' [{customs_channel}] lodged successfully! Assessed Duty: TSh {duty_amount:,.2f} (GePG Control: {control_number}). Mteja ametumiwa barua pepe yenye maelezo ya kodi na Control Number."



        )



        return redirect('/customs/declarations/?tab=assessed')







    return redirect('customs_pending_declarations')











@login_required



@role_required([UserRole.FINANCE, UserRole.OPERATIONS_MGR, UserRole.ADMIN])



def customs_confirm_duty_payment_action(request, job_id):



    if request.method == 'POST':



        job = get_object_or_404(JobShipment, id=job_id)



        payment_reference = request.POST.get('payment_reference', '').strip()



        payment_date_str = request.POST.get('payment_date', '').strip()



        amount_paid_str = request.POST.get('amount_paid', '').strip().replace(',', '')



        notes = request.POST.get('notes', '').strip()



        receipt_file = request.FILES.get('receipt_file')







        # Auto-fallback to GePG Control Number if finance didn't manually type a reference



        if not payment_reference:



            payment_reference = f"GePG-{job.duty_control_number}" if job.duty_control_number else f"REC-{job.id}" 







        now = timezone.now()



        payment_date = now.date()



        if payment_date_str:



            try:



                payment_date = datetime.strptime(payment_date_str, '%Y-%m-%d').date()



            except Exception:



                pass







        if amount_paid_str:



            try:



                job.assessed_duty_amount = Decimal(amount_paid_str)



            except Exception:



                pass







        job.duty_paid = True



        job.duty_payment_reference = payment_reference



        job.duty_payment_date = payment_date







        # Complete Stage 3 (TRA Duty Payment)

        st3 = job.stages.filter(stage_number=3).first()

        if st3:

            st3.status = 'COMPLETED'

            st3.completed_at = now

            st3.responsible_officer = request.user

            st3.remarks = f"TRA Duty Settled & Verified by Finance: TSh {job.assessed_duty_amount:,.2f} | Ref: {payment_reference} | Date: {payment_date}"

            if notes:

                st3.remarks += f" | Notes: {notes}"

            st3.save()



        # Save official TRA receipt document if uploaded under Stage 3

        if receipt_file:

            JobDocument.objects.create(

                job=job,

                stage=st3,

                document_type='DUTY_PAYMENT_RECEIPT',

                title=f"TRA Electronic Payment Receipt - {payment_reference}",

                file=receipt_file,

                uploaded_by=request.user,

                notes=f"Paid to TRA. Amount: TSh {job.assessed_duty_amount:,.2f}"

            )



        # Advance to Stage 4 (Delivery Order - Port Processing)

        job.current_stage_number = 4

        st4 = job.stages.filter(stage_number=4).first()

        if st4:

            st4.status = 'IN_PROGRESS'

            st4.started_at = st4.started_at or now

            st4.save()







        job.save()







        # Automated Customer Email Notification: Stage 5 (Verification at Port/ICD)



        try:



            from .email_service import send_stage_update_email



            send_stage_update_email(job, 5, extra_note=notes)



        except Exception as e:



            print(f"[Email Notification Error] {e}")







        log_audit(



            request,



            "CLIENT_DUTY_PAYMENT_VERIFIED",



            f"Verified client TRA Duty payment of TSh {job.assessed_duty_amount:,.2f} for {job.job_number} (TRA Ref: {payment_reference}). Shipment advanced to Stage 5.",



            job=job



        )







        messages.success(



            request,



            f"✅ Client Duty Payment for {job.job_number} (TSh {job.assessed_duty_amount:,.2f}) verified! Mteja ametumiwa barua pepe ya kuanza kwa ukaguzi bandarini (Verification)."



        )







        next_url = request.POST.get('next')



        if next_url == 'job_detail':



            return redirect('job_detail', job_id=job.id)



        if next_url == 'finance':



            return redirect('finance_pending_payments')



        if next_url:



            return redirect(next_url)



        return redirect('/customs/declarations/?tab=assessed')







    return redirect('customs_pending_declarations')











@login_required



def send_job_stage_email_action(request, job_id):
    """
    Client email & SMS notifications are currently disabled upon request.
    """
    job = get_object_or_404(JobShipment, id=job_id)
    messages.info(request, "Utumaji wa barua pepe na SMS kwa wateja umezimwa kwenye mfumo.")
    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or f'/jobs/{job.id}/'
    return redirect(next_url)











@login_required



@role_required([UserRole.CLEARING_OFFICER, UserRole.OPERATIONS_MGR, UserRole.CEO, UserRole.ADMIN])



def customs_assessments_view(request):



    # Redirect to the unified TANCIS declarations hub (Assessed tab)



    return redirect('/customs/declarations/?tab=assessed')











@login_required



@role_required([UserRole.CLEARING_OFFICER, UserRole.OPERATIONS_MGR])



def customs_record_assessment_action(request, job_id):



    # Delegate to the unified lodge action



    return customs_lodge_declaration_action(request, job_id)











@login_required



@role_required([UserRole.CLEARING_OFFICER, UserRole.OPERATIONS_MGR, UserRole.CEO, UserRole.ADMIN])



def customs_archive_view(request):



    query = request.GET.get('q', '').strip()







    # Historical customs records: jobs with assessment or stage >= 4 or completed



    jobs = JobShipment.objects.filter(



        Q(assessed_duty_amount__gt=0) | Q(current_stage_number__gte=4) | Q(status__in=['COMPLETED', 'CLOSED'])



    ).select_related('customer', 'clearing_officer', 'documentation_officer').prefetch_related('documents').order_by('-updated_at')







    if query:



        jobs = jobs.filter(



            Q(job_number__icontains=query) |



            Q(bl_number__icontains=query) |



            Q(declaration_number__icontains=query) |



            Q(duty_payment_reference__icontains=query) |



            Q(customer__company_name__icontains=query)



        )







    total_duty_assessed = jobs.aggregate(total=Sum('assessed_duty_amount'))['total'] or Decimal('0.00')







    context = {



        'archived_jobs': jobs,



        'search_query': query,



        'total_declarations': jobs.count(),



        'total_duty_assessed': total_duty_assessed,



    }



    return render(request, 'core/customs_archive.html', context)











@login_required



@role_required([UserRole.FINANCE, UserRole.CEO, UserRole.ADMIN])



def finance_pending_payments_view(request):



    query = request.GET.get('q', '').strip()



    category_filter = request.GET.get('category', '')



    status_filter = request.GET.get('status', 'pending')







    expenses = ExpenseVoucher.objects.all().select_related('job', 'job__customer', 'requester', 'approver').order_by('-requested_at')



    _role = get_user_role(request.user)

    _ceo_only = (_role == UserRole.CEO and not request.user.is_superuser)

    if _ceo_only:

        expenses = expenses.exclude(approval_status='REQUESTED')







    if query:



        expenses = expenses.filter(



            Q(voucher_number__icontains=query) |



            Q(job__job_number__icontains=query) |



            Q(job__bl_number__icontains=query) |



            Q(job__customer__company_name__icontains=query) |



            Q(description__icontains=query)



        )







    if category_filter:



        expenses = expenses.filter(category=category_filter)







    role = get_user_role(request.user)

    is_ceo = (role == UserRole.CEO)

    is_admin = (role == UserRole.ADMIN or request.user.is_superuser)



    if status_filter == 'pending':

        if is_ceo and not is_admin:

            # CEO strictly sees vouchers verified by Finance awaiting CEO payout

            expenses = expenses.filter(approval_status='VERIFIED', is_paid=False)

        else:

            expenses = expenses.filter(Q(approval_status__in=['REQUESTED', 'VERIFIED']) | Q(approval_status='APPROVED', is_paid=False))

    elif status_filter == 'requested':

        expenses = expenses.filter(approval_status='REQUESTED')

    elif status_filter == 'verified':

        expenses = expenses.filter(approval_status='VERIFIED')

    elif status_filter == 'approved':

        expenses = expenses.filter(approval_status='APPROVED', is_paid=False)

    elif status_filter == 'paid':

        expenses = expenses.filter(is_paid=True)



    # Breakdown metrics by payment type according to spec

    if is_ceo and not is_admin:

        all_active_vouchers = ExpenseVoucher.objects.filter(approval_status='VERIFIED', is_paid=False)

    else:

        all_active_vouchers = ExpenseVoucher.objects.filter(Q(approval_status__in=['REQUESTED', 'VERIFIED']) | Q(approval_status='APPROVED', is_paid=False))

    requested_count = 0 if _ceo_only else ExpenseVoucher.objects.filter(approval_status='REQUESTED').count()

    verified_count = ExpenseVoucher.objects.filter(approval_status='VERIFIED').count()



    pending_duty_jobs = JobShipment.objects.filter(

        duty_paid=False,

        status__in=['ACTIVE', 'DELAYED']

    ).filter(

        (Q(duty_control_number__isnull=False) & ~Q(duty_control_number='')) | Q(assessed_duty_amount__gt=0) | Q(current_stage_number=3)

    ).exclude(clearance_mode='BOND').select_related('customer')



    tra_duty_count = pending_duty_jobs.count() + all_active_vouchers.filter(category=ExpenseCategory.CUSTOMS_DUTY).count()



    shipping_do_count = all_active_vouchers.filter(category=ExpenseCategory.SHIPPING_LINE).count()



    port_charges_count = all_active_vouchers.filter(category=ExpenseCategory.PORT_CHARGES).count()



    gate_pass_count = all_active_vouchers.filter(category=ExpenseCategory.PORT_HANDLING).count()



    fuel_count = all_active_vouchers.filter(category__in=[ExpenseCategory.TRANSPORT, ExpenseCategory.FUEL]).count()



    other_count = all_active_vouchers.filter(category__in=[ExpenseCategory.OTHER, ExpenseCategory.DOCUMENTATION]).count()







    total_pending_amount = all_active_vouchers.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')







    paid_duty_jobs = JobShipment.objects.filter(duty_paid=True).select_related('customer').order_by('-duty_payment_date', '-updated_at')



    if query:



        paid_duty_jobs = paid_duty_jobs.filter(



            Q(job_number__icontains=query) |



            Q(bl_number__icontains=query) |



            Q(duty_control_number__icontains=query) |



            Q(duty_payment_reference__icontains=query) |



            Q(customer__company_name__icontains=query)



        )







    context = {



        'expenses': expenses,



        'pending_duty_jobs': pending_duty_jobs,



        'paid_duty_jobs': paid_duty_jobs,



        'paid_duty_count': paid_duty_jobs.count(),



        'search_query': query,



        'category_filter': category_filter,



        'status_filter': status_filter,



        'tra_duty_count': tra_duty_count,



        'shipping_do_count': shipping_do_count,



        'port_charges_count': port_charges_count,



        'gate_pass_count': gate_pass_count,



        'fuel_count': fuel_count,

        'requested_count': requested_count,

        'verified_count': verified_count,



        'other_count': other_count,



        'total_pending_count': all_active_vouchers.count() + pending_duty_jobs.count(),



        'total_pending_amount': total_pending_amount,



        'jobs': JobShipment.objects.filter(status__in=['ACTIVE', 'DELAYED']).select_related('customer'),



        'categories': ExpenseCategory.choices,



    }



    return render(request, 'core/finance_pending_payments.html', context)











# Alias for backward compatibility



finance_view = finance_pending_payments_view











@login_required



@role_required([UserRole.FINANCE, UserRole.CEO, UserRole.ADMIN])



def finance_transactions_view(request):



    query = request.GET.get('q', '').strip()



    type_filter = request.GET.get('type', '')



    method_filter = request.GET.get('method', '')







    income_qs = ClientPayment.objects.all().select_related('invoice', 'invoice__customer', 'invoice__job', 'recorded_by').order_by('-payment_date')



    if query:



        income_qs = income_qs.filter(



            Q(payment_reference__icontains=query) |



            Q(invoice__invoice_number__icontains=query) |



            Q(invoice__customer__company_name__icontains=query) |



            Q(invoice__job__job_number__icontains=query)



        )



    if method_filter:



        income_qs = income_qs.filter(payment_method=method_filter)







    expense_qs = ExpenseVoucher.objects.filter(is_paid=True).select_related('job', 'job__customer', 'requester', 'approver').order_by('-paid_at')



    if query:



        expense_qs = expense_qs.filter(



            Q(voucher_number__icontains=query) |



            Q(payment_reference__icontains=query) |



            Q(job__job_number__icontains=query) |



            Q(description__icontains=query)



        )







    # TRA Customs Duty settlements verified across customer shipments



    duty_qs = JobShipment.objects.filter(duty_paid=True, assessed_duty_amount__gt=0).select_related('customer').order_by('-duty_payment_date', '-updated_at')



    if query:



        duty_qs = duty_qs.filter(



            Q(job_number__icontains=query) |



            Q(bl_number__icontains=query) |



            Q(duty_control_number__icontains=query) |



            Q(duty_payment_reference__icontains=query) |



            Q(declaration_number__icontains=query) |



            Q(customer__company_name__icontains=query)



        )







    client_income_total = ClientPayment.objects.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    other_rev_inflow_qs = OtherRevenue.objects.filter(
        Q(inflow_type__in=['OTHER_REVENUE', 'CAPITAL_INJECTION']) |
        Q(inflow_type='CONTAINER_REFUND', deposit_status__in=['RETURNED_FULL', 'PARTIAL'])
    ).select_related('job', 'job__customer', 'recorded_by').order_by('-date', '-id')
    if query:
        other_rev_inflow_qs = other_rev_inflow_qs.filter(
            Q(source__icontains=query) |
            Q(description__icontains=query) |
            Q(job__bl_number__icontains=query) |
            Q(job__job_number__icontains=query)
        )
    if method_filter:
        other_rev_inflow_qs = other_rev_inflow_qs.filter(payment_method=method_filter)

    other_income_total = OtherRevenue.objects.aggregate(
        total=Sum('returned_amount', filter=Q(inflow_type='CONTAINER_REFUND', deposit_status__in=['RETURNED_FULL', 'PARTIAL']))
    )['total'] or Decimal('0.00')
    other_income_total += OtherRevenue.objects.filter(inflow_type__in=['OTHER_REVENUE', 'CAPITAL_INJECTION']).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    total_income = client_income_total + other_income_total

    op_exp_qs = OperatingExpense.objects.exclude(category__name__icontains='Salary').select_related('category', 'recorded_by').order_by('-date', '-id')
    sal_exp_qs = SalaryPayment.objects.filter(status='PAID').select_related('employee', 'recorded_by').order_by('-payment_date', '-id')
    if query:
        op_exp_qs = op_exp_qs.filter(Q(payee__icontains=query) | Q(description__icontains=query) | Q(category__name__icontains=query))
        sal_exp_qs = sal_exp_qs.filter(Q(employee__full_name__icontains=query))
    if method_filter:
        op_exp_qs = op_exp_qs.filter(payment_method=method_filter)
        sal_exp_qs = sal_exp_qs.filter(payment_method=method_filter)

    paid_voucher_job_ids = set(ExpenseVoucher.objects.filter(is_paid=True).values_list('job_id', flat=True))
    job_disb_qs = JobShipment.objects.exclude(id__in=paid_voucher_job_ids).select_related('customer').order_by('-updated_at', '-id')
    if query:
        job_disb_qs = job_disb_qs.filter(
            Q(job_number__icontains=query) |
            Q(bl_number__icontains=query) |
            Q(customer__company_name__icontains=query) |
            Q(chassis_number__icontains=query)
        )
    job_disb_list = [j for j in job_disb_qs if (j.total_direct_costs or Decimal('0')) > 0]

    voucher_exp_total = ExpenseVoucher.objects.filter(is_paid=True).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    op_exp_total = OperatingExpense.objects.exclude(category__name__icontains='Salary').aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    sal_exp_total = sum((s.net_pay or Decimal('0')) for s in SalaryPayment.objects.filter(status='PAID'))
    job_disb_total = sum(j.total_direct_costs for j in JobShipment.objects.exclude(id__in=paid_voucher_job_ids))
    total_expenses = voucher_exp_total + op_exp_total + sal_exp_total + job_disb_total

    total_duty_settled = JobShipment.objects.filter(duty_paid=True).aggregate(total=Sum('assessed_duty_amount'))['total'] or Decimal('0.00')

    net_cashflow = total_income - total_expenses







    transactions = []



    if type_filter in ['', 'income']:



        for p in income_qs:



            inv = p.invoice



            cust = inv.customer



            job = inv.job



            transactions.append({



                'id': p.id,



                'date': p.payment_date,



                'type': 'INCOME',



                'title': f"Client Payment: {cust.company_name}",



                'reference': p.payment_reference,



                'method': p.get_payment_method_display(),



                'method_code': p.payment_method,



                'related_doc': inv.invoice_number,



                'related_job': job.job_number,



                'amount': p.amount,



                'receipt_url': p.receipt_file.url if p.receipt_file else None,



                'recorded_by': p.recorded_by.get_full_name() if p.recorded_by else "Subira Kilonzo",



                # Rich Receipt Metadata for Printable Malkia Official Receipt



                'receipt_no': f"REC/{p.payment_date.year}/{p.id:04d}",



                'customer_name': cust.company_name,



                'customer_tin': cust.tin_number or "N/A",



                'customer_vrn': getattr(cust, 'vrn_number', "N/A") or "N/A",



                'customer_address': cust.physical_address or "Dar es Salaam, Tanzania",



                'invoice_total': inv.total_amount,



                'invoice_balance': inv.balance_due,



                'bl_number': job.bl_number,



                'chassis_number': job.chassis_number,



                'vessel_name': job.vessel_name,



                'notes': p.notes or "Payment received in full settlement of Malkia Cargo Wave port and customs clearance charges.",



            })

        for rev in other_rev_inflow_qs:
            inflow_amt = rev.returned_amount if rev.inflow_type == 'CONTAINER_REFUND' else rev.amount
            if not inflow_amt or inflow_amt <= 0:
                continue
            transactions.append({
                'id': f"REV-{rev.id}",
                'date': rev.date,
                'type': 'INCOME',
                'title': f"{rev.get_inflow_type_display()}: {rev.description or rev.source}",
                'reference': rev.payment_reference or '—',
                'method': rev.get_payment_method_display(),
                'method_code': rev.payment_method,
                'related_doc': rev.job.bl_number if rev.job else 'General',
                'related_job': rev.job.job_number if rev.job else '—',
                'amount': inflow_amt,
                'receipt_url': rev.receipt_file.url if rev.receipt_file else None,
                'recorded_by': rev.recorded_by.get_full_name() if rev.recorded_by else "Accounts",
                'receipt_no': f"INFLOW/{rev.date.year}/{rev.id:04d}",
                'customer_name': rev.source,
                'bl_number': rev.job.bl_number if rev.job else '',
                'chassis_number': '',
            })







    if type_filter in ['', 'expense']:



        for exp in expense_qs:



            job = exp.job



            cust = job.customer



            transactions.append({



                'id': exp.id,



                'date': exp.paid_at.date() if exp.paid_at else exp.requested_at.date(),



                'type': 'EXPENSE',



                'title': f"{exp.get_category_display()} ({exp.voucher_number})",



                'reference': exp.payment_reference or "Direct Cash/Bank",



                'method': exp.get_payment_method_display() if hasattr(exp, 'get_payment_method_display') else "Bank / Cash Voucher",



                'method_code': 'BANK_TRANSFER' if 'BANK' in (exp.payment_reference or '').upper() else 'CASH',



                'related_doc': exp.voucher_number,



                'related_job': job.job_number,



                'amount': exp.amount,



                'receipt_url': exp.supporting_document.url if exp.supporting_document else None,



                'recorded_by': exp.approver.get_full_name() if exp.approver else "Accounts",



                # Rich Voucher Metadata



                'voucher_no': exp.voucher_number,



                'category_name': exp.get_category_display(),



                'description': exp.description or f"Operational disbursement for {job.job_number}",



                'requester_name': exp.requester.get_full_name() if exp.requester else "Staff",



                'approver_name': exp.approver.get_full_name() if exp.approver else "CEO / Managing Director",



                'customer_name': cust.company_name,



                'bl_number': job.bl_number,



                'chassis_number': job.chassis_number,



            })

        for op in op_exp_qs:
            transactions.append({
                'id': f"OP-{op.id}",
                'date': op.date,
                'type': 'EXPENSE',
                'title': f"{op.category.name}: {op.payee}",
                'reference': op.payment_reference or '—',
                'method': op.get_payment_method_display(),
                'method_code': op.payment_method,
                'related_doc': 'Office Expense',
                'related_job': '—',
                'amount': op.amount,
                'receipt_url': op.receipt_file.url if op.receipt_file else None,
                'recorded_by': op.recorded_by.get_full_name() if op.recorded_by else "Accounts",
                'voucher_no': f"OP/{op.date.year}/{op.id:04d}",
                'category_name': op.category.name,
                'description': op.description or op.category.name,
                'customer_name': op.payee,
                'bl_number': '',
                'chassis_number': '',
            })

        for sal in sal_exp_qs:
            s_date = sal.payment_date or sal.period
            transactions.append({
                'id': f"SAL-{sal.id}",
                'date': s_date,
                'type': 'EXPENSE',
                'title': f"Salary Paid: {sal.employee.full_name}",
                'reference': sal.payment_reference or 'Payroll',
                'method': sal.get_payment_method_display(),
                'method_code': sal.payment_method,
                'related_doc': sal.period.strftime('%b %Y'),
                'related_job': 'Payroll',
                'amount': sal.net_pay,
                'receipt_url': None,
                'recorded_by': sal.recorded_by.get_full_name() if sal.recorded_by else "Accounts",
                'voucher_no': f"PAY/{s_date.year}/{sal.id:04d}",
                'category_name': 'Salary Payroll',
                'description': f"Net salary for {sal.period.strftime('%B %Y')}",
                'customer_name': sal.employee.full_name,
                'bl_number': '',
                'chassis_number': '',
            })

        if not method_filter or method_filter == 'BANK':
            for j in job_disb_list:
                j_date = (j.updated_at or j.created_at).date()
                transactions.append({
                    'id': f"JOB-{j.id}",
                    'date': j_date,
                    'type': 'EXPENSE',
                    'title': f"Direct Job Disbursements (D/O, Port, Transport): {j.customer.company_name}",
                    'reference': j.job_number,
                    'method': 'Bank / Cash Disbursement',
                    'method_code': 'BANK',
                    'related_doc': j.job_number,
                    'related_job': j.job_number,
                    'amount': j.total_direct_costs,
                    'receipt_url': None,
                    'recorded_by': "Accounts",
                    'voucher_no': j.job_number,
                    'category_name': 'Direct Job Disbursements',
                    'description': f"D/O, Wharfage, Handling, Transport & Port costs for {j.bl_number or j.job_number}",
                    'customer_name': j.customer.company_name,
                    'bl_number': j.bl_number or j.job_number,
                    'chassis_number': j.chassis_number,
                })







    if type_filter in ['', 'duty']:



        for job in duty_qs:



            receipt_doc = job.documents.filter(document_type='DUTY_PAYMENT_RECEIPT').order_by('-uploaded_at').first()



            p_date = job.duty_payment_date or (job.updated_at.date() if job.updated_at else timezone.now().date())



            transactions.append({



                'id': f"DUTY_{job.id}",



                'raw_id': job.id,



                'date': p_date,



                'type': 'DUTY_SETTLEMENT',



                'title': f"TRA Customs Duty Settlement: {job.customer.company_name}",



                'reference': job.duty_payment_reference or job.duty_control_number or "GePG Settled",



                'method': 'GePG / Direct TRA Bank Deposit',



                'method_code': 'BANK_TRANSFER',



                'related_doc': f"GePG: {job.duty_control_number or 'N/A'}",



                'related_job': job.job_number,



                'amount': job.assessed_duty_amount,



                'receipt_url': receipt_doc.file.url if receipt_doc and receipt_doc.file else None,



                'recorded_by': "Finance Officer (Verified)",



                # Rich Metadata for inspection/modal



                'receipt_no': job.duty_payment_reference or f"TRA/{p_date.year}/{job.id:04d}",



                'control_number': job.duty_control_number or "N/A",



                'declaration_number': job.declaration_number or "N/A",



                'customs_channel': job.customs_channel or "GREEN",



                'customer_name': job.customer.company_name,



                'customer_tin': job.customer.tin_number or "N/A",



                'customer_vrn': getattr(job.customer, 'vrn_number', "N/A") or "N/A",



                'customer_address': job.customer.physical_address or "Dar es Salaam, Tanzania",



                'bl_number': job.bl_number or "N/A",



                'chassis_number': job.chassis_number,



                'vessel_name': job.vessel_name or "Ocean Vessel",



                'notes': f"Direct statutory import duty settled to TRA under GePG Control No {job.duty_control_number}. Verified by Accounts for cargo release.",



            })







    def _tx_sort_key(item):
        d = item['date']
        if hasattr(d, 'date'):
            d = d.date()
        raw_id = str(item.get('id', '0'))
        num_id = int(raw_id.split('-')[-1]) if raw_id.split('-')[-1].isdigit() else 0
        return (d, num_id)

    transactions.sort(key=_tx_sort_key, reverse=True)







    context = {



        'transactions': transactions,



        'search_query': query,



        'type_filter': type_filter,



        'method_filter': method_filter,



        'total_income': total_income,



        'total_expenses': total_expenses,



        'total_duty_settled': total_duty_settled,



        'net_cashflow': net_cashflow,



        'payment_methods': ClientPayment.PAYMENT_METHODS,



    }



    return render(request, 'core/finance_transactions.html', context)











# ==============================================================================
# OPERATING EXPENSES (COMPANY OVERHEADS) & REVENUE REPORTING
# Salary, commissions, internet, rent and every other non-job payment.
# ==============================================================================

OPERATING_EXPENSE_ROLES = [UserRole.FINANCE, UserRole.CEO, UserRole.ADMIN]


def _operating_expenses_redirect(month=None):
    url = reverse('operating_expenses')
    if month:
        return redirect(f"{url}?month={month}")
    return redirect(url)


def _operating_expenses_context(request):
    today = timezone.now().date()

    date_from_str = request.GET.get('date_from', '').strip()
    date_to_str = request.GET.get('date_to', '').strip()
    date_from = None
    date_to = None
    if date_from_str:
        try:
            date_from = datetime.strptime(date_from_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            date_from = None
    if date_to_str:
        try:
            date_to = datetime.strptime(date_to_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            date_to = None

    month_param = request.GET.get('month', '').strip()
    try:
        selected_month = datetime.strptime(month_param, '%Y-%m').date().replace(day=1)
    except (ValueError, TypeError):
        selected_month = today.replace(day=1)

    if selected_month.month == 12:
        month_end = date(selected_month.year + 1, 1, 1) - timedelta(days=1)
    else:
        month_end = date(selected_month.year, selected_month.month + 1, 1) - timedelta(days=1)

    if date_from or date_to:
        range_start = date_from or date(selected_month.year, 1, 1)
        range_end = date_to or today
        is_custom_range = True
        range_label = f"{range_start.strftime('%d %b %Y')} – {range_end.strftime('%d %b %Y')}"
    else:
        range_start = selected_month
        range_end = month_end
        is_custom_range = False
        range_label = selected_month.strftime('%B %Y')

    categories = OperatingExpenseCategory.objects.all()
    expenses = OperatingExpense.objects.select_related('category', 'recorded_by').filter(
        date__gte=range_start, date__lte=range_end
    )

    category_filter = request.GET.get('category', '').strip()
    if category_filter.isdigit():
        expenses = expenses.filter(category_id=int(category_filter))

    query = request.GET.get('q', '').strip()
    if query:
        expenses = expenses.filter(
            Q(payee__icontains=query) |
            Q(description__icontains=query) |
            Q(payment_reference__icontains=query) |
            Q(category__name__icontains=query)
        )

    expenses = expenses.order_by('-date', '-id')
    expense_total = expenses.aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
    revenue_total = ClientPayment.objects.filter(
        payment_date__gte=range_start, payment_date__lte=range_end
    ).aggregate(t=Sum('amount'))['t'] or Decimal('0.00')

    # Pull Cargo & Vehicle Direct Running Costs (Fuel, Transport, Ferry, Facilitation, Other)
    running_jobs_qs = JobShipment.objects.filter(
        created_at__date__gte=range_start, created_at__date__lte=range_end
    ).filter(
        Q(cost_fuel__gt=0) |
        Q(cost_transport__gt=0) |
        Q(cost_facilitation__gt=0) |
        Q(cost_ferry_charges__gt=0) |
        Q(cost_running_other__gt=0)
    ).select_related('customer').order_by('-created_at')

    if query:
        running_jobs_qs = running_jobs_qs.filter(
            Q(job_number__icontains=query) |
            Q(bl_number__icontains=query) |
            Q(chassis_number__icontains=query) |
            Q(cargo_description__icontains=query) |
            Q(vehicle_make__icontains=query) |
            Q(vehicle_model__icontains=query) |
            Q(customer__company_name__icontains=query) |
            Q(cost_running_other_description__icontains=query)
        )

    running_aggregates = running_jobs_qs.aggregate(
        fuel=Sum('cost_fuel'),
        transport=Sum('cost_transport'),
        ferry=Sum('cost_ferry_charges'),
        facilitation=Sum('cost_facilitation'),
        running_other=Sum('cost_running_other')
    )
    job_fuel_total = running_aggregates['fuel'] or Decimal('0.00')
    job_transport_total = running_aggregates['transport'] or Decimal('0.00')
    job_ferry_total = running_aggregates['ferry'] or Decimal('0.00')
    job_facilitation_total = running_aggregates['facilitation'] or Decimal('0.00')
    job_running_other_total = running_aggregates['running_other'] or Decimal('0.00')
    job_running_total = job_fuel_total + job_transport_total + job_ferry_total + job_facilitation_total + job_running_other_total
    job_ferry_facilitation_total = job_ferry_total + job_facilitation_total
    total_combined_outflow = expense_total + job_running_total

    running_jobs = []
    for j in running_jobs_qs:
        j.calculated_running_total = (
            (j.cost_fuel or Decimal('0')) +
            (j.cost_transport or Decimal('0')) +
            (j.cost_facilitation or Decimal('0')) +
            (j.cost_ferry_charges or Decimal('0')) +
            (j.cost_running_other or Decimal('0'))
        )
        running_jobs.append(j)

    # -------------------------------------------------------------
    # GENERAL COST SUMMARY BY EXPENSE HEAD / CATEGORY
    # -------------------------------------------------------------
    from django.db.models import Count
    office_cat_qs = OperatingExpense.objects.filter(
        date__gte=range_start, date__lte=range_end
    )
    if category_filter.isdigit():
        office_cat_qs = office_cat_qs.filter(category_id=int(category_filter))
    if query:
        office_cat_qs = office_cat_qs.filter(
            Q(payee__icontains=query) |
            Q(description__icontains=query) |
            Q(payment_reference__icontains=query) |
            Q(category__name__icontains=query)
        )

    office_cat_summary = (
        office_cat_qs.values('category__id', 'category__name')
        .annotate(total=Sum('amount'), count=Count('id'))
        .order_by('-total')
    )

    category_summary = []
    office_fuel_total = Decimal('0.00')

    for c_row in office_cat_summary:
        c_name = c_row['category__name'] or 'Uncategorized'
        c_total = c_row['total'] or Decimal('0.00')
        c_count = c_row['count'] or 0
        if c_name.strip().upper() == 'FUEL':
            office_fuel_total += c_total
        category_summary.append({
            'name': c_name,
            'source': 'Office OPEX',
            'count': c_count,
            'count_label': f"{c_count} payment{'s' if c_count != 1 else ''}",
            'total': c_total,
            'is_cargo': False,
            'icon': 'fa-solid fa-building-columns',
            'badge_bg': '#EEF2FF',
            'badge_color': '#3730A3',
        })

    if job_transport_total > 0:
        c_count = running_jobs_qs.filter(cost_transport__gt=0).count()
        category_summary.append({
            'name': 'Transport & Carrier (Cargo)',
            'source': 'Cargo Direct',
            'count': c_count,
            'count_label': f"{c_count} job{'s' if c_count != 1 else ''}",
            'total': job_transport_total,
            'is_cargo': True,
            'icon': 'fa-solid fa-truck',
            'badge_bg': '#DBEAFE',
            'badge_color': '#1E40AF',
        })

    if job_fuel_total > 0:
        c_count = running_jobs_qs.filter(cost_fuel__gt=0).count()
        category_summary.append({
            'name': 'Fuel (Cargo & Vehicles Out)',
            'source': 'Cargo Direct',
            'count': c_count,
            'count_label': f"{c_count} job{'s' if c_count != 1 else ''}",
            'total': job_fuel_total,
            'is_cargo': True,
            'icon': 'fa-solid fa-gas-pump',
            'badge_bg': '#FEF3C7',
            'badge_color': '#92400E',
        })

    if job_facilitation_total > 0:
        c_count = running_jobs_qs.filter(cost_facilitation__gt=0).count()
        category_summary.append({
            'name': 'Facilitation (Ground Handling)',
            'source': 'Cargo Direct',
            'count': c_count,
            'count_label': f"{c_count} job{'s' if c_count != 1 else ''}",
            'total': job_facilitation_total,
            'is_cargo': True,
            'icon': 'fa-solid fa-handshake',
            'badge_bg': '#CCFBF1',
            'badge_color': '#0F766E',
        })

    if job_ferry_total > 0:
        c_count = running_jobs_qs.filter(cost_ferry_charges__gt=0).count()
        category_summary.append({
            'name': 'Ferry & Toll Charges (Kigamboni/Kivukoni)',
            'source': 'Cargo Direct',
            'count': c_count,
            'count_label': f"{c_count} job{'s' if c_count != 1 else ''}",
            'total': job_ferry_total,
            'is_cargo': True,
            'icon': 'fa-solid fa-ferry',
            'badge_bg': '#E0E7FF',
            'badge_color': '#4338CA',
        })

    if job_running_other_total > 0:
        c_count = running_jobs_qs.filter(cost_running_other__gt=0).count()
        category_summary.append({
            'name': 'Other Cargo Running Costs',
            'source': 'Cargo Direct',
            'count': c_count,
            'count_label': f"{c_count} job{'s' if c_count != 1 else ''}",
            'total': job_running_other_total,
            'is_cargo': True,
            'icon': 'fa-solid fa-screwdriver-wrench',
            'badge_bg': '#F3E8FF',
            'badge_color': '#6B21A8',
        })

    category_summary.sort(key=lambda x: x['total'], reverse=True)
    total_outflow = total_combined_outflow or Decimal('0.00')
    for item in category_summary:
        if total_outflow > 0:
            item['percentage'] = round((item['total'] / total_outflow) * 100, 1)
        else:
            item['percentage'] = 0.0

    all_fuel_grand_total = office_fuel_total + job_fuel_total

    year = selected_month.year
    revenue_by_month = {
        row['month'].month: row['total'] or Decimal('0.00')
        for row in ClientPayment.objects.filter(payment_date__year=year)
        .annotate(month=TruncMonth('payment_date'))
        .values('month')
        .annotate(total=Sum('amount'))
    }
    expense_by_month = {
        row['month'].month: row['total'] or Decimal('0.00')
        for row in OperatingExpense.objects.filter(date__year=year)
        .annotate(month=TruncMonth('date'))
        .values('month')
        .annotate(total=Sum('amount'))
    }
    running_by_month = {
        row['month'].month: (
            (row['fuel'] or Decimal('0.00')) +
            (row['transport'] or Decimal('0.00')) +
            (row['ferry'] or Decimal('0.00')) +
            (row['facilitation'] or Decimal('0.00')) +
            (row['running_other'] or Decimal('0.00'))
        )
        for row in JobShipment.objects.filter(created_at__year=year)
        .annotate(month=TruncMonth('created_at'))
        .values('month')
        .annotate(
            fuel=Sum('cost_fuel'),
            transport=Sum('cost_transport'),
            ferry=Sum('cost_ferry_charges'),
            facilitation=Sum('cost_facilitation'),
            running_other=Sum('cost_running_other'),
        )
    }
    monthly_rows = []
    for m in range(1, 13):
        rev = revenue_by_month.get(m, Decimal('0.00'))
        off_exp = expense_by_month.get(m, Decimal('0.00'))
        run_exp = running_by_month.get(m, Decimal('0.00'))
        tot_exp = off_exp + run_exp
        monthly_rows.append({
            'number': m,
            'label': date(year, m, 1).strftime('%b %Y'),
            'revenue': rev,
            'office_expenses': off_exp,
            'running_costs': run_exp,
            'total_expenses': tot_exp,
            'expenses': tot_exp,
            'net': rev - tot_exp,
        })

    editing = None
    edit_id = request.GET.get('edit', '').strip()
    if edit_id.isdigit():
        editing = OperatingExpense.objects.filter(id=int(edit_id)).first()

    form_categories = list(categories.filter(is_active=True))
    if editing and editing.category not in form_categories:
        form_categories.append(editing.category)

    year_revenue = sum((row['revenue'] for row in monthly_rows), Decimal('0.00'))
    year_office_expenses = sum((row['office_expenses'] for row in monthly_rows), Decimal('0.00'))
    year_running_costs = sum((row['running_costs'] for row in monthly_rows), Decimal('0.00'))
    year_total_expenses = sum((row['total_expenses'] for row in monthly_rows), Decimal('0.00'))
    year_net = year_revenue - year_total_expenses

    return {
        'selected_month': selected_month,
        'selected_month_label': selected_month.strftime('%B %Y'),
        'month_end': month_end,
        'range_start': range_start,
        'range_end': range_end,
        'range_label': range_label,
        'date_from': date_from.strftime('%Y-%m-%d') if date_from else '',
        'date_to': date_to.strftime('%Y-%m-%d') if date_to else '',
        'is_custom_range': is_custom_range,
        'categories': categories,
        'form_categories': form_categories,
        'expenses': expenses,
        'expense_total': expense_total,
        'revenue_total': revenue_total,
        'net_total': revenue_total - expense_total,
        'job_fuel_total': job_fuel_total,
        'job_transport_total': job_transport_total,
        'job_ferry_total': job_ferry_total,
        'job_facilitation_total': job_facilitation_total,
        'job_ferry_facilitation_total': job_ferry_facilitation_total,
        'job_running_other_total': job_running_other_total,
        'job_running_total': job_running_total,
        'running_jobs': running_jobs,
        'category_summary': category_summary,
        'all_fuel_grand_total': all_fuel_grand_total,
        'total_combined_outflow': total_combined_outflow,
        'monthly_rows': monthly_rows,
        'year_revenue': year_revenue,
        'year_office_expenses': year_office_expenses,
        'year_running_costs': year_running_costs,
        'year_total_expenses': year_total_expenses,
        'year_expenses': year_total_expenses,
        'year_net': year_net,
        'selected_year': year,
        'category_filter': category_filter,
        'search_query': query,
        'payment_methods': OperatingExpense.PAYMENT_METHOD_CHOICES,
        'editing': editing,
        'today': today,
    }


def _parse_operating_expense_form(request):
    date_raw = request.POST.get('date', '').strip()
    try:
        expense_date = datetime.strptime(date_raw, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None, "Please provide a valid expense date."

    category = OperatingExpenseCategory.objects.filter(id=request.POST.get('category', '')).first()
    if not category:
        return None, "Please choose an expense category."
    if not category.is_active:
        return None, "That category is inactive. Please choose an active category."

    try:
        amount = Decimal(request.POST.get('amount', '').strip())
    except (InvalidOperation, ValueError):
        return None, "Please provide a valid amount."
    if amount <= 0:
        return None, "Amount must be greater than zero."

    desc = request.POST.get('description', '').strip()
    payee = request.POST.get('payee', '').strip()
    if not payee:
        payee = desc if desc else category.name

    method = request.POST.get('payment_method', 'MOBILE_MONEY')
    if method not in dict(OperatingExpense.PAYMENT_METHOD_CHOICES):
        method = 'MOBILE_MONEY'

    return {
        'date': expense_date,
        'category': category,
        'amount': amount,
        'payee': payee,
        'payment_method': method,
        'payment_reference': request.POST.get('payment_reference', '').strip(),
        'description': desc,
        'receipt_file': request.FILES.get('receipt_file'),
    }, None


@login_required
@role_required(OPERATING_EXPENSE_ROLES)
def operating_expenses_view(request):
    return render(request, 'core/finance_operating_expenses.html', _operating_expenses_context(request))


@login_required
@role_required(OPERATING_EXPENSE_ROLES)
def operating_expense_create_action(request):
    if request.method != 'POST':
        return redirect('operating_expenses')

    data, error = _parse_operating_expense_form(request)
    if error:
        messages.error(request, error)
        return _operating_expenses_redirect(request.POST.get('return_month', '').strip())

    expense = OperatingExpense.objects.create(recorded_by=request.user, **data)
    log_audit(
        request,
        "OPERATING_EXPENSE_CREATED",
        f"{expense.category.name}: TSh {expense.amount:,.2f} paid to {expense.payee} on {expense.date} (ref {expense.payment_reference or 'N/A'})",
    )
    messages.success(request, f"Expense of TSh {expense.amount:,.2f} ({expense.category.name}) recorded successfully.")
    return _operating_expenses_redirect(expense.date.strftime('%Y-%m'))


@login_required
@role_required(OPERATING_EXPENSE_ROLES)
def operating_expense_update_action(request, expense_id):
    expense = get_object_or_404(OperatingExpense, id=expense_id)
    if request.method != 'POST':
        return redirect('operating_expenses')

    data, error = _parse_operating_expense_form(request)
    if error:
        messages.error(request, error)
        return _operating_expenses_redirect(request.POST.get('return_month', '').strip())

    for field, value in data.items():
        if field == 'receipt_file' and value is None:
            continue
        setattr(expense, field, value)
    expense.save()
    log_audit(
        request,
        "OPERATING_EXPENSE_UPDATED",
        f"{expense.category.name}: TSh {expense.amount:,.2f} paid to {expense.payee} on {expense.date} (ref {expense.payment_reference or 'N/A'})",
    )
    messages.success(request, "Expense record updated successfully.")
    return _operating_expenses_redirect(expense.date.strftime('%Y-%m'))


@login_required
@role_required(OPERATING_EXPENSE_ROLES)
def operating_expense_delete_action(request, expense_id):
    expense = get_object_or_404(OperatingExpense, id=expense_id)
    if request.method == 'POST':
        details = f"{expense.category.name}: TSh {expense.amount:,.2f} paid to {expense.payee} on {expense.date}"
        month = expense.date.strftime('%Y-%m')
        expense.delete()
        log_audit(request, "OPERATING_EXPENSE_DELETED", details)
        messages.success(request, "Expense record deleted.")
        return _operating_expenses_redirect(month)
    return redirect('operating_expenses')


@login_required
@role_required(OPERATING_EXPENSE_ROLES)
def operating_expenses_export_excel(request):
    """
    Exports filtered Operating Expenses to a beautifully formatted .xlsx Excel sheet.
    Supports ?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD or ?month=YYYY-MM with category & query filtering.
    """
    import io
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    today = timezone.now().date()
    date_from_str = request.GET.get('date_from', '').strip()
    date_to_str = request.GET.get('date_to', '').strip()

    date_from = None
    date_to = None
    if date_from_str:
        try:
            date_from = datetime.strptime(date_from_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            date_from = None
    if date_to_str:
        try:
            date_to = datetime.strptime(date_to_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            date_to = None

    month_param = request.GET.get('month', '').strip()
    try:
        selected_month = datetime.strptime(month_param, '%Y-%m').date().replace(day=1)
    except (ValueError, TypeError):
        selected_month = today.replace(day=1)

    if selected_month.month == 12:
        month_end = date(selected_month.year + 1, 1, 1) - timedelta(days=1)
    else:
        month_end = date(selected_month.year, selected_month.month + 1, 1) - timedelta(days=1)

    if date_from or date_to:
        range_start = date_from or date(selected_month.year, 1, 1)
        range_end = date_to or today
        range_label = f"{range_start.strftime('%d %b %Y')} – {range_end.strftime('%d %b %Y')}"
        filename_dates = f"{range_start.strftime('%Y%m%d')}_to_{range_end.strftime('%Y%m%d')}"
    else:
        range_start = selected_month
        range_end = month_end
        range_label = selected_month.strftime('%B %Y')
        filename_dates = selected_month.strftime('%Y_%m')

    expenses = OperatingExpense.objects.select_related('category', 'recorded_by').filter(
        date__gte=range_start, date__lte=range_end
    )

    category_filter = request.GET.get('category', '').strip()
    if category_filter.isdigit():
        expenses = expenses.filter(category_id=int(category_filter))

    query = request.GET.get('q', '').strip()
    if query:
        expenses = expenses.filter(
            Q(payee__icontains=query) |
            Q(description__icontains=query) |
            Q(payment_reference__icontains=query) |
            Q(category__name__icontains=query)
        )

    expenses = expenses.order_by('-date', '-id')

    # Pull Cargo & Vehicle Direct Running Costs for Excel
    running_jobs_qs = JobShipment.objects.filter(
        created_at__date__gte=range_start, created_at__date__lte=range_end
    ).filter(
        Q(cost_fuel__gt=0) |
        Q(cost_transport__gt=0) |
        Q(cost_facilitation__gt=0) |
        Q(cost_ferry_charges__gt=0) |
        Q(cost_running_other__gt=0)
    ).select_related('customer').order_by('-created_at')

    if query:
        running_jobs_qs = running_jobs_qs.filter(
            Q(job_number__icontains=query) |
            Q(bl_number__icontains=query) |
            Q(chassis_number__icontains=query) |
            Q(cargo_description__icontains=query) |
            Q(vehicle_make__icontains=query) |
            Q(vehicle_model__icontains=query) |
            Q(customer__company_name__icontains=query) |
            Q(cost_running_other_description__icontains=query)
        )

    running_aggregates = running_jobs_qs.aggregate(
        fuel=Sum('cost_fuel'),
        transport=Sum('cost_transport'),
        ferry=Sum('cost_ferry_charges'),
        facilitation=Sum('cost_facilitation'),
        running_other=Sum('cost_running_other')
    )
    job_fuel_total = running_aggregates['fuel'] or Decimal('0.00')
    job_transport_total = running_aggregates['transport'] or Decimal('0.00')
    job_ferry_total = running_aggregates['ferry'] or Decimal('0.00')
    job_facilitation_total = running_aggregates['facilitation'] or Decimal('0.00')
    job_running_other_total = running_aggregates['running_other'] or Decimal('0.00')
    job_running_total = job_fuel_total + job_transport_total + job_ferry_total + job_facilitation_total + job_running_other_total

    # Category Summary for Excel Sheet 1
    from django.db.models import Count
    office_cat_summary = (
        expenses.values('category__id', 'category__name')
        .annotate(total=Sum('amount'), count=Count('id'))
        .order_by('-total')
    )
    cat_summary_list = []
    for c_row in office_cat_summary:
        c_name = c_row['category__name'] or 'Uncategorized'
        c_total = c_row['total'] or Decimal('0.00')
        c_count = c_row['count'] or 0
        cat_summary_list.append({
            'name': c_name,
            'source': 'Office OPEX',
            'count': c_count,
            'count_label': f"{c_count} payments",
            'total': c_total,
        })

    if job_transport_total > 0:
        c_count = running_jobs_qs.filter(cost_transport__gt=0).count()
        cat_summary_list.append({
            'name': 'Transport & Carrier (Cargo)',
            'source': 'Cargo Direct',
            'count': c_count,
            'count_label': f"{c_count} jobs",
            'total': job_transport_total,
        })
    if job_fuel_total > 0:
        c_count = running_jobs_qs.filter(cost_fuel__gt=0).count()
        cat_summary_list.append({
            'name': 'Fuel (Cargo & Vehicles Out)',
            'source': 'Cargo Direct',
            'count': c_count,
            'count_label': f"{c_count} jobs",
            'total': job_fuel_total,
        })
    if job_facilitation_total > 0:
        c_count = running_jobs_qs.filter(cost_facilitation__gt=0).count()
        cat_summary_list.append({
            'name': 'Facilitation (Ground Handling)',
            'source': 'Cargo Direct',
            'count': c_count,
            'count_label': f"{c_count} jobs",
            'total': job_facilitation_total,
        })
    if job_ferry_total > 0:
        c_count = running_jobs_qs.filter(cost_ferry_charges__gt=0).count()
        cat_summary_list.append({
            'name': 'Ferry & Toll Charges (Kivukoni)',
            'source': 'Cargo Direct',
            'count': c_count,
            'count_label': f"{c_count} jobs",
            'total': job_ferry_total,
        })
    if job_running_other_total > 0:
        c_count = running_jobs_qs.filter(cost_running_other__gt=0).count()
        cat_summary_list.append({
            'name': 'Other Cargo Running Costs',
            'source': 'Cargo Direct',
            'count': c_count,
            'count_label': f"{c_count} jobs",
            'total': job_running_other_total,
        })

    cat_summary_list.sort(key=lambda x: x['total'], reverse=True)
    total_combined_export = expenses.aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
    total_combined_export += job_running_total
    for item in cat_summary_list:
        if total_combined_export > 0:
            item['percentage'] = round((item['total'] / total_combined_export) * 100, 1)
        else:
            item['percentage'] = 0.0

    wb = openpyxl.Workbook()

    navy_fill = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
    header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    teal_header_fill = PatternFill(start_color="0F766E", end_color="0F766E", fill_type="solid")
    amber_header_fill = PatternFill(start_color="B45309", end_color="B45309", fill_type="solid")
    total_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")

    title_font = Font(name="Calibri", size=13, bold=True, color="FFFFFF")
    subtitle_font = Font(name="Calibri", size=9, italic=True, color="E2E8F0")
    header_font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
    bold_font = Font(name="Calibri", size=9, bold=True, color="0F172A")
    regular_font = Font(name="Calibri", size=9, color="1E293B")
    money_font = Font(name="Calibri", size=9, bold=True, color="B91C1C")

    thin_border = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )
    double_bottom_border = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='double', color='0F172A')
    )

    # -------------------------------------------------------------
    # SHEET 1: GENERAL COST SUMMARY BY CATEGORY
    # -------------------------------------------------------------
    ws_sum = wb.active
    ws_sum.title = "Summary by Category"
    ws_sum.views.sheetView[0].showGridLines = True

    ws_sum.merge_cells("A1:F1")
    ts_cell = ws_sum["A1"]
    ts_cell.value = "MALKIA CARGO WAVES - GENERAL COST SUMMARY BY CATEGORY"
    ts_cell.font = title_font
    ts_cell.fill = navy_fill
    ts_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws_sum.row_dimensions[1].height = 28

    ws_sum.merge_cells("A2:F2")
    subs_cell = ws_sum["A2"]
    subs_cell.value = f"Period: {range_label}  |  Exported on: {today.strftime('%d %b %Y')}  |  Total Operational Outflow: TSh {float(total_combined_export):,.0f}"
    subs_cell.font = subtitle_font
    subs_cell.fill = navy_fill
    subs_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws_sum.row_dimensions[2].height = 18
    ws_sum.row_dimensions[3].height = 10

    headers_sum = [
        ("S/N", 6, Alignment(horizontal="center", vertical="center")),
        ("Expense Category / Cost Head", 32, Alignment(horizontal="left", vertical="center")),
        ("Classification (Source)", 25, Alignment(horizontal="left", vertical="center")),
        ("Volume / Count", 18, Alignment(horizontal="center", vertical="center")),
        ("Total Amount (TSh)", 22, Alignment(horizontal="right", vertical="center")),
        ("Share of Outflow (%)", 20, Alignment(horizontal="right", vertical="center")),
    ]

    ws_sum.row_dimensions[4].height = 24
    for col_idx, (col_name, width, align) in enumerate(headers_sum, start=1):
        cell = ws_sum.cell(row=4, column=col_idx, value=col_name)
        cell.font = header_font
        cell.fill = teal_header_fill
        cell.alignment = align
        cell.border = thin_border

    s_row = 5
    for idx, item in enumerate(cat_summary_list, start=1):
        ws_sum.row_dimensions[s_row].height = 20
        row_s_data = [
            (idx, Alignment(horizontal="center", vertical="center"), regular_font, None),
            (item['name'], Alignment(horizontal="left", vertical="center"), bold_font, None),
            (item['source'], Alignment(horizontal="left", vertical="center"), regular_font, None),
            (item['count_label'], Alignment(horizontal="center", vertical="center"), regular_font, None),
            (float(item['total']), Alignment(horizontal="right", vertical="center"), money_font, "#,##0"),
            (f"{item['percentage']}%", Alignment(horizontal="right", vertical="center"), bold_font, None),
        ]
        for col_idx, (val, align, font, num_fmt) in enumerate(row_s_data, start=1):
            cell = ws_sum.cell(row=s_row, column=col_idx, value=val)
            cell.alignment = align
            cell.font = font
            cell.border = thin_border
            if num_fmt:
                cell.number_format = num_fmt
        s_row += 1

    ws_sum.row_dimensions[s_row].height = 24
    ws_sum.merge_cells(start_row=s_row, start_column=1, end_row=s_row, end_column=4)
    st_label = ws_sum.cell(row=s_row, column=1, value="GRAND TOTAL OPERATIONAL EXPENDITURE (TSH)")
    st_label.font = bold_font
    st_label.alignment = Alignment(horizontal="right", vertical="center")
    st_label.fill = total_fill

    for c in range(1, 5):
        ws_sum.cell(row=s_row, column=c).border = double_bottom_border
        ws_sum.cell(row=s_row, column=c).fill = total_fill

    st_val = ws_sum.cell(row=s_row, column=5, value=float(total_combined_export))
    st_val.font = Font(name="Calibri", size=10, bold=True, color="B91C1C")
    st_val.alignment = Alignment(horizontal="right", vertical="center")
    st_val.number_format = "#,##0"
    st_val.border = double_bottom_border
    st_val.fill = total_fill

    st_pct = ws_sum.cell(row=s_row, column=6, value="100.0%")
    st_pct.font = bold_font
    st_pct.alignment = Alignment(horizontal="right", vertical="center")
    st_pct.border = double_bottom_border
    st_pct.fill = total_fill

    for col_idx, (_, width, _) in enumerate(headers_sum, start=1):
        col_letter = get_column_letter(col_idx)
        ws_sum.column_dimensions[col_letter].width = width

    # -------------------------------------------------------------
    # SHEET 2: OFFICE EXPENSES DETAIL (OPEX)
    # -------------------------------------------------------------
    ws = wb.create_sheet(title="Office Expenses Detail")
    ws.views.sheetView[0].showGridLines = True

    # Title block ws
    ws.merge_cells("A1:H1")
    t_cell = ws["A1"]
    t_cell.value = "MALKIA CARGO WAVES - OFFICE OPERATING EXPENSES DETAIL"
    t_cell.font = title_font
    t_cell.fill = navy_fill
    t_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 28

    ws.merge_cells("A2:H2")
    sub_cell = ws["A2"]
    sub_cell.value = f"Period: {range_label}  |  Exported on: {today.strftime('%d %b %Y')}  |  Records: {expenses.count()}"
    sub_cell.font = subtitle_font
    sub_cell.fill = navy_fill
    sub_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 18

    ws.row_dimensions[3].height = 10

    headers = [
        ("S/N", 6, Alignment(horizontal="center", vertical="center")),
        ("Date", 13, Alignment(horizontal="center", vertical="center")),
        ("Category", 20, Alignment(horizontal="left", vertical="center")),
        ("Description / Payee", 36, Alignment(horizontal="left", vertical="center")),
        ("Payment Method", 20, Alignment(horizontal="left", vertical="center")),
        ("Reference", 18, Alignment(horizontal="left", vertical="center")),
        ("Amount (TSh)", 18, Alignment(horizontal="right", vertical="center")),
        ("Recorded By", 18, Alignment(horizontal="left", vertical="center")),
    ]

    header_row = 4
    ws.row_dimensions[header_row].height = 24
    for col_idx, (col_name, width, align) in enumerate(headers, start=1):
        cell = ws.cell(row=header_row, column=col_idx, value=col_name)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = align
        cell.border = thin_border

    current_row = 5
    total_amount = Decimal('0.00')
    for idx, exp in enumerate(expenses, start=1):
        ws.row_dimensions[current_row].height = 20
        total_amount += (exp.amount or Decimal('0.00'))

        desc = exp.description or (f"Payment for {exp.category.name}" if exp.category else "")
        if exp.payee and exp.payee != desc:
            desc = f"{desc} ({exp.payee})"

        recorder_name = exp.recorded_by.get_full_name() or exp.recorded_by.username if exp.recorded_by else "-"

        row_data = [
            (idx, Alignment(horizontal="center", vertical="center"), regular_font, None),
            (exp.date.strftime("%d/%m/%Y") if exp.date else "-", Alignment(horizontal="center", vertical="center"), regular_font, None),
            (exp.category.name if exp.category else "-", Alignment(horizontal="left", vertical="center"), bold_font, None),
            (desc, Alignment(horizontal="left", vertical="center"), regular_font, None),
            (exp.get_payment_method_display(), Alignment(horizontal="left", vertical="center"), regular_font, None),
            (exp.payment_reference or "-", Alignment(horizontal="left", vertical="center"), regular_font, None),
            (float(exp.amount), Alignment(horizontal="right", vertical="center"), money_font, "#,##0"),
            (recorder_name, Alignment(horizontal="left", vertical="center"), regular_font, None),
        ]

        for col_idx, (val, align, font, num_fmt) in enumerate(row_data, start=1):
            cell = ws.cell(row=current_row, column=col_idx, value=val)
            cell.alignment = align
            cell.font = font
            cell.border = thin_border
            if num_fmt:
                cell.number_format = num_fmt

        current_row += 1

    # Total row ws
    ws.row_dimensions[current_row].height = 24
    ws.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=6)
    t_label = ws.cell(row=current_row, column=1, value="TOTAL OFFICE EXPENSES (TSH)")
    t_label.font = bold_font
    t_label.alignment = Alignment(horizontal="right", vertical="center")
    t_label.fill = total_fill

    for c in range(1, 7):
        ws.cell(row=current_row, column=c).border = double_bottom_border
        ws.cell(row=current_row, column=c).fill = total_fill

    t_val = ws.cell(row=current_row, column=7, value=float(total_amount))
    t_val.font = Font(name="Calibri", size=10, bold=True, color="B91C1C")
    t_val.alignment = Alignment(horizontal="right", vertical="center")
    t_val.number_format = "#,##0"
    t_val.border = double_bottom_border
    t_val.fill = total_fill

    t_rec = ws.cell(row=current_row, column=8, value="")
    t_rec.border = double_bottom_border
    t_rec.fill = total_fill

    for col_idx, (_, width, _) in enumerate(headers, start=1):
        col_letter = get_column_letter(col_idx)
        ws.column_dimensions[col_letter].width = width

    # -------------------------------------------------------------
    # SHEET 3: CARGO & VEHICLE RUNNING COSTS DETAIL (FUEL, TRANSPORT, ETC.)
    # -------------------------------------------------------------
    running_jobs_qs = JobShipment.objects.filter(
        created_at__date__gte=range_start, created_at__date__lte=range_end
    ).filter(
        Q(cost_fuel__gt=0) |
        Q(cost_transport__gt=0) |
        Q(cost_facilitation__gt=0) |
        Q(cost_ferry_charges__gt=0) |
        Q(cost_running_other__gt=0)
    ).select_related('customer').order_by('-created_at')

    if query:
        running_jobs_qs = running_jobs_qs.filter(
            Q(job_number__icontains=query) |
            Q(bl_number__icontains=query) |
            Q(chassis_number__icontains=query) |
            Q(cargo_description__icontains=query) |
            Q(vehicle_make__icontains=query) |
            Q(vehicle_model__icontains=query) |
            Q(customer__company_name__icontains=query) |
            Q(cost_running_other_description__icontains=query)
        )

    ws2 = wb.create_sheet(title="Cargo Running Costs")
    ws2.views.sheetView[0].showGridLines = True

    ws2.merge_cells("A1:L1")
    t2_cell = ws2["A1"]
    t2_cell.value = "MALKIA CARGO WAVES - CARGO & VEHICLE RUNNING COSTS"
    t2_cell.font = title_font
    t2_cell.fill = navy_fill
    t2_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws2.row_dimensions[1].height = 28

    ws2.merge_cells("A2:L2")
    sub2_cell = ws2["A2"]
    sub2_cell.value = f"Period: {range_label}  |  Exported on: {today.strftime('%d %b %Y')}  |  Jobs: {running_jobs_qs.count()}"
    sub2_cell.font = subtitle_font
    sub2_cell.fill = navy_fill
    sub2_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws2.row_dimensions[2].height = 18
    ws2.row_dimensions[3].height = 10

    headers2 = [
        ("S/N", 6, Alignment(horizontal="center", vertical="center")),
        ("Date", 12, Alignment(horizontal="center", vertical="center")),
        ("Job No", 16, Alignment(horizontal="center", vertical="center")),
        ("BL / Chassis", 18, Alignment(horizontal="left", vertical="center")),
        ("Vehicle / Cargo", 24, Alignment(horizontal="left", vertical="center")),
        ("Client", 24, Alignment(horizontal="left", vertical="center")),
        ("Fuel (TSh)", 15, Alignment(horizontal="right", vertical="center")),
        ("Transport (TSh)", 16, Alignment(horizontal="right", vertical="center")),
        ("Facilitation (TSh)", 16, Alignment(horizontal="right", vertical="center")),
        ("Ferry / Toll (TSh)", 16, Alignment(horizontal="right", vertical="center")),
        ("Other Running (TSh)", 18, Alignment(horizontal="right", vertical="center")),
        ("Total Running (TSh)", 18, Alignment(horizontal="right", vertical="center")),
    ]

    header_row2 = 4
    ws2.row_dimensions[header_row2].height = 24
    amber_header_fill = PatternFill(start_color="B45309", end_color="B45309", fill_type="solid")
    for col_idx, (col_name, width, align) in enumerate(headers2, start=1):
        cell = ws2.cell(row=header_row2, column=col_idx, value=col_name)
        cell.font = header_font
        cell.fill = amber_header_fill
        cell.alignment = align
        cell.border = thin_border

    current_row2 = 5
    tot_fuel = Decimal('0.00')
    tot_trans = Decimal('0.00')
    tot_facil = Decimal('0.00')
    tot_ferry = Decimal('0.00')
    tot_other = Decimal('0.00')
    tot_running = Decimal('0.00')

    for idx, j in enumerate(running_jobs_qs, start=1):
        ws2.row_dimensions[current_row2].height = 20
        fuel = j.cost_fuel or Decimal('0.00')
        trans = j.cost_transport or Decimal('0.00')
        facil = j.cost_facilitation or Decimal('0.00')
        ferry = j.cost_ferry_charges or Decimal('0.00')
        other = j.cost_running_other or Decimal('0.00')
        row_tot = fuel + trans + facil + ferry + other

        tot_fuel += fuel
        tot_trans += trans
        tot_facil += facil
        tot_ferry += ferry
        tot_other += other
        tot_running += row_tot

        veh_desc = (f"{j.vehicle_make} {j.vehicle_model}".strip() or j.cargo_description or "Cargo")
        bl_chassis = j.bl_number or j.chassis_number or "-"
        client_name = j.customer.company_name if j.customer else "-"

        row2_data = [
            (idx, Alignment(horizontal="center", vertical="center"), regular_font, None),
            (j.created_at.strftime("%d/%m/%Y") if j.created_at else "-", Alignment(horizontal="center", vertical="center"), regular_font, None),
            (j.job_number, Alignment(horizontal="center", vertical="center"), bold_font, None),
            (bl_chassis, Alignment(horizontal="left", vertical="center"), regular_font, None),
            (veh_desc, Alignment(horizontal="left", vertical="center"), regular_font, None),
            (client_name, Alignment(horizontal="left", vertical="center"), regular_font, None),
            (float(fuel), Alignment(horizontal="right", vertical="center"), regular_font, "#,##0"),
            (float(trans), Alignment(horizontal="right", vertical="center"), regular_font, "#,##0"),
            (float(facil), Alignment(horizontal="right", vertical="center"), regular_font, "#,##0"),
            (float(ferry), Alignment(horizontal="right", vertical="center"), regular_font, "#,##0"),
            (float(other), Alignment(horizontal="right", vertical="center"), regular_font, "#,##0"),
            (float(row_tot), Alignment(horizontal="right", vertical="center"), money_font, "#,##0"),
        ]

        for col_idx, (val, align, font, num_fmt) in enumerate(row2_data, start=1):
            cell = ws2.cell(row=current_row2, column=col_idx, value=val)
            cell.alignment = align
            cell.font = font
            cell.border = thin_border
            if num_fmt:
                cell.number_format = num_fmt

        current_row2 += 1

    # Total row ws2
    ws2.row_dimensions[current_row2].height = 24
    ws2.merge_cells(start_row=current_row2, start_column=1, end_row=current_row2, end_column=6)
    t2_label = ws2.cell(row=current_row2, column=1, value="TOTAL CARGO RUNNING COSTS (TSH)")
    t2_label.font = bold_font
    t2_label.alignment = Alignment(horizontal="right", vertical="center")
    t2_label.fill = total_fill

    for c in range(1, 7):
        ws2.cell(row=current_row2, column=c).border = double_bottom_border
        ws2.cell(row=current_row2, column=c).fill = total_fill

    subtotals2 = [
        (7, float(tot_fuel)),
        (8, float(tot_trans)),
        (9, float(tot_facil)),
        (10, float(tot_ferry)),
        (11, float(tot_other)),
        (12, float(tot_running)),
    ]
    for c_idx, val in subtotals2:
        cell = ws2.cell(row=current_row2, column=c_idx, value=val)
        cell.font = bold_font if c_idx != 12 else Font(name="Calibri", size=10, bold=True, color="B91C1C")
        cell.alignment = Alignment(horizontal="right", vertical="center")
        cell.number_format = "#,##0"
        cell.border = double_bottom_border
        cell.fill = total_fill

    for col_idx, (_, width, _) in enumerate(headers2, start=1):
        col_letter = get_column_letter(col_idx)
        ws2.column_dimensions[col_letter].width = width

    log_audit(request, "OPERATING_EXPENSES_EXCEL_EXPORTED", f"Exported {expenses.count()} expenses & {running_jobs_qs.count()} running jobs for period {range_label}")

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    filename = f"Malkia_Operating_Expenses_{filename_dates}.xlsx"
    response = HttpResponse(
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
@role_required(OPERATING_EXPENSE_ROLES)
def operating_expense_category_create_action(request):
    month = request.POST.get('return_month', '').strip()
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('category_description', '').strip()
        if not name:
            messages.error(request, "Please enter a category name.")
        elif OperatingExpenseCategory.objects.filter(name__iexact=name).exists():
            messages.error(request, f"Category '{name}' already exists.")
        else:
            OperatingExpenseCategory.objects.create(name=name, description=description, created_by=request.user)
            log_audit(request, "OPERATING_EXPENSE_CATEGORY_CREATED", f"Expense category '{name}' created.")
            messages.success(request, f"Category '{name}' added. You can now record expenses under it.")
    return _operating_expenses_redirect(month)


@login_required
@role_required(OPERATING_EXPENSE_ROLES)
def operating_expense_category_toggle_action(request, category_id):
    category = get_object_or_404(OperatingExpenseCategory, id=category_id)
    if request.method == 'POST':
        category.is_active = not category.is_active
        category.save(update_fields=['is_active'])
        state = "activated" if category.is_active else "deactivated"
        log_audit(request, "OPERATING_EXPENSE_CATEGORY_TOGGLED", f"Expense category '{category.name}' {state}.")
        messages.success(request, f"Category '{category.name}' {state}.")
    return _operating_expenses_redirect(request.POST.get('return_month', '').strip())


def _other_revenues_redirect(month_param=''):
    if month_param:
        return redirect(f"{reverse('other_revenues')}?month={month_param}")
    return redirect('other_revenues')


def _parse_other_revenue_form(request, is_update=False):
    date_str = request.POST.get('date', '').strip()
    inflow_type = request.POST.get('inflow_type', 'OTHER_REVENUE').strip()
    amount_raw = request.POST.get('amount', '0').replace(',', '').strip()
    deposit_status = request.POST.get('deposit_status', 'PENDING').strip()
    returned_raw = request.POST.get('returned_amount', '0').replace(',', '').strip()
    source = request.POST.get('source', '').strip()
    job_id = request.POST.get('job_id', '').strip()
    payment_method = request.POST.get('payment_method', 'BANK').strip()
    payment_reference = request.POST.get('payment_reference', '').strip()
    description = request.POST.get('description', '').strip()
    receipt_file = request.FILES.get('receipt_file')

    if inflow_type not in dict(OtherRevenue.INFLOW_TYPE_CHOICES):
        inflow_type = 'OTHER_REVENUE'
    if deposit_status not in dict(OtherRevenue.DEPOSIT_STATUS_CHOICES):
        deposit_status = 'PENDING'
    if payment_method not in dict(OperatingExpense.PAYMENT_METHOD_CHOICES):
        payment_method = 'BANK'

    try:
        amount = Decimal(amount_raw)
    except Exception:
        return None, "Please enter a valid numeric amount."
    if amount <= 0:
        return None, "Amount must be greater than zero."

    returned_amount = Decimal('0')
    if inflow_type == 'CONTAINER_REFUND':
        if not is_update and 'deposit_status' not in request.POST:
            deposit_status = 'PENDING'
            returned_amount = Decimal('0')
        elif deposit_status == 'RETURNED_FULL':
            returned_amount = amount
        elif deposit_status == 'PARTIAL':
            try:
                returned_amount = Decimal(returned_raw)
            except Exception:
                return None, "Please enter a valid returned amount."
            if returned_amount <= 0 or returned_amount >= amount:
                return None, "For Partial refund, returned amount must be greater than 0 and less than the deposit."
        else:
            returned_amount = Decimal('0')
    else:
        deposit_status = 'RETURNED_FULL'
        returned_amount = amount

    if not source:
        if inflow_type == 'CONTAINER_REFUND':
            source = 'Shipping Line'
        elif inflow_type == 'CAPITAL_INJECTION':
            source = 'Boss / Director'
        else:
            source = 'Other Source'

    try:
        rev_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else timezone.localdate()
    except ValueError:
        return None, "Invalid date format."

    job_obj = None
    if job_id.isdigit():
        job_obj = JobShipment.objects.filter(id=int(job_id)).first()

    return {
        'date': rev_date,
        'inflow_type': inflow_type,
        'amount': amount,
        'deposit_status': deposit_status,
        'returned_amount': returned_amount,
        'source': source,
        'job': job_obj,
        'payment_method': payment_method,
        'payment_reference': payment_reference,
        'description': description,
        'receipt_file': receipt_file,
    }, None


@login_required
@role_required(OPERATING_EXPENSE_ROLES)
def other_revenues_view(request):
    month_param = request.GET.get('month', '').strip()
    inflow_type_filter = request.GET.get('inflow_type', '').strip()
    q = request.GET.get('q', '').strip()

    today = timezone.localdate()
    if month_param == 'all':
        selected_month = None
        month_label = 'All Time'
    else:
        try:
            selected_month = datetime.strptime(month_param, '%Y-%m').date().replace(day=1) if month_param else today.replace(day=1)
        except ValueError:
            selected_month = today.replace(day=1)
        month_label = selected_month.strftime('%B %Y')

    revenues = OtherRevenue.objects.select_related('job', 'recorded_by')
    if selected_month:
        revenues = revenues.filter(date__year=selected_month.year, date__month=selected_month.month)
    if inflow_type_filter in dict(OtherRevenue.INFLOW_TYPE_CHOICES):
        revenues = revenues.filter(inflow_type=inflow_type_filter)
    if q:
        revenues = revenues.filter(
            Q(source__icontains=q) |
            Q(payment_reference__icontains=q) |
            Q(description__icontains=q) |
            Q(job__bl_number__icontains=q) |
            Q(job__job_number__icontains=q)
        )

    totals = revenues.aggregate(
        total_all=Sum('returned_amount', filter=Q(inflow_type='OTHER_REVENUE') | Q(inflow_type='CAPITAL_INJECTION') | Q(inflow_type='CONTAINER_REFUND', deposit_status__in=['RETURNED_FULL', 'PARTIAL'])),
        total_business=Sum('amount', filter=Q(inflow_type='OTHER_REVENUE')),
        total_refunds=Sum('returned_amount', filter=Q(inflow_type='CONTAINER_REFUND', deposit_status__in=['RETURNED_FULL', 'PARTIAL'])),
        total_capital=Sum('amount', filter=Q(inflow_type='CAPITAL_INJECTION')),
    )

    context = {
        'revenues': revenues,
        'selected_month': selected_month,
        'month_param': 'all' if month_param == 'all' else (selected_month.strftime('%Y-%m') if selected_month else ''),
        'month_label': month_label,
        'inflow_type_filter': inflow_type_filter,
        'search_q': q,
        'inflow_choices': OtherRevenue.INFLOW_TYPE_CHOICES,
        'payment_methods': OperatingExpense.PAYMENT_METHOD_CHOICES,
        'total_inflows': totals['total_all'] or Decimal('0'),
        'total_business_revenue': totals['total_business'] or Decimal('0'),
        'total_container_refunds': totals['total_refunds'] or Decimal('0'),
        'total_capital_injections': totals['total_capital'] or Decimal('0'),
        'recent_jobs': JobShipment.objects.exclude(container_size_type='RORO').select_related('customer').order_by('-created_at')[:300],
        'today_str': today.strftime('%Y-%m-%d'),
    }
    return render(request, 'core/finance_other_revenues.html', context)


@login_required
@role_required(OPERATING_EXPENSE_ROLES)
def other_revenue_create_action(request):
    if request.method != 'POST':
        return redirect('other_revenues')

    data, error = _parse_other_revenue_form(request)
    if error:
        messages.error(request, error)
        return _other_revenues_redirect(request.POST.get('return_month', '').strip())

    rev = OtherRevenue.objects.create(recorded_by=request.user, **data)
    if rev.inflow_type == 'CONTAINER_REFUND' and rev.job and (rev.job.cost_container_deposit or 0) == 0:
        rev.job.cost_container_deposit = rev.amount
        rev.job.save(update_fields=['cost_container_deposit', 'updated_at'])
    log_audit(
        request,
        "OTHER_REVENUE_CREATED",
        f"{rev.get_inflow_type_display()}: TSh {rev.amount:,.2f} from {rev.source} on {rev.date}",
        job=rev.job,
    )
    messages.success(request, f"Recorded TSh {rev.amount:,.2f} ({rev.get_inflow_type_display()}) successfully.")
    next_url = request.POST.get('next_url', '').strip()
    if next_url and next_url.startswith('/'):
        return redirect(next_url)
    return _other_revenues_redirect(rev.date.strftime('%Y-%m'))


@login_required
@role_required(OPERATING_EXPENSE_ROLES)
def other_revenue_update_action(request, revenue_id):
    rev = get_object_or_404(OtherRevenue, id=revenue_id)
    if request.method != 'POST':
        return redirect('other_revenues')

    data, error = _parse_other_revenue_form(request, is_update=True)
    if error:
        messages.error(request, error)
        return _other_revenues_redirect(request.POST.get('return_month', '').strip())

    for field, value in data.items():
        if field == 'receipt_file' and value is None:
            continue
        setattr(rev, field, value)
    rev.save()
    if rev.inflow_type == 'CONTAINER_REFUND' and rev.job and (rev.job.cost_container_deposit or 0) == 0:
        rev.job.cost_container_deposit = rev.amount
        rev.job.save(update_fields=['cost_container_deposit', 'updated_at'])
    log_audit(
        request,
        "OTHER_REVENUE_UPDATED",
        f"{rev.get_inflow_type_display()}: TSh {rev.amount:,.2f} from {rev.source} on {rev.date}",
        job=rev.job,
    )
    messages.success(request, "Inflow / revenue record updated.")
    return _other_revenues_redirect(rev.date.strftime('%Y-%m'))


@login_required
@role_required(OPERATING_EXPENSE_ROLES)
def other_revenue_delete_action(request, revenue_id):
    rev = get_object_or_404(OtherRevenue, id=revenue_id)
    if request.method == 'POST':
        month = rev.date.strftime('%Y-%m')
        details = f"{rev.get_inflow_type_display()}: TSh {rev.amount:,.2f} from {rev.source} on {rev.date}"
        rev.delete()
        log_audit(request, "OTHER_REVENUE_DELETED", details)
        messages.success(request, "Inflow / revenue record deleted.")
        return _other_revenues_redirect(month)
    return redirect('other_revenues')


# =========================================================================
# EMPLOYEE REGISTRY & SALARY PAYROLL
# =========================================================================

PAYROLL_EXPENSE_CATEGORY_NAME = 'Salaries & Wages'


def _parse_month_param(raw):
    today = timezone.now().date()
    try:
        return datetime.strptime((raw or '').strip(), '%Y-%m').date().replace(day=1)
    except (ValueError, TypeError):
        return today.replace(day=1)


def _month_bounds(month_start):
    if month_start.month == 12:
        month_end = date(month_start.year + 1, 1, 1) - timedelta(days=1)
    else:
        month_end = date(month_start.year, month_start.month + 1, 1) - timedelta(days=1)
    return month_start, month_end


def _payroll_redirect(month=None):
    url = reverse('payroll')
    if month:
        return redirect(f"{url}?month={month}")
    return redirect(url)


def _decimal_field(raw, label, errors):
    try:
        value = Decimal((raw or '0').strip() or '0')
    except (InvalidOperation, ValueError):
        errors.append(f"{label} must be a valid number.")
        return Decimal('0.00')
    if value < 0:
        errors.append(f"{label} cannot be negative.")
        return Decimal('0.00')
    return value


def _parse_employee_form(request):
    errors = []
    full_name = request.POST.get('full_name', '').strip()
    position = request.POST.get('position', '').strip()
    if not full_name:
        errors.append("Employee full name is required.")
    if not position:
        errors.append("Job title / position is required.")

    linked_user_id = request.POST.get('linked_user_id', '').strip()
    linked_user = User.objects.filter(id=int(linked_user_id)).first() if linked_user_id.isdigit() else None

    data = {
        'full_name': full_name,
        'position': position,
        'phone': request.POST.get('phone', '').strip(),
        'nssf_number': request.POST.get('nssf_number', '').strip(),
        'basic_salary': _decimal_field(request.POST.get('basic_salary'), "Basic salary", errors),
        'allowances': _decimal_field(request.POST.get('allowances'), "Allowances", errors),
        'bank_name': request.POST.get('bank_name', '').strip(),
        'bank_account_number': request.POST.get('bank_account_number', '').strip(),
        'status': 'ACTIVE' if 'on_payroll' in request.POST else 'TERMINATED',
        'no_deductions': 'no_deductions' in request.POST,
        'user': linked_user,
    }
    return data, errors


@login_required
@role_required(OPERATING_EXPENSE_ROLES)
def employees_view(request):
    query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '').strip()
    employees = Employee.objects.all()
    if query:
        employees = employees.filter(
            Q(full_name__icontains=query) | Q(employee_number__icontains=query) |
            Q(position__icontains=query) | Q(phone__icontains=query)
        )
    if status_filter == 'ACTIVE':
        employees = employees.filter(status__in=('ACTIVE', 'ON_LEAVE'))
    elif status_filter:
        employees = employees.filter(status=status_filter)
    employees = employees.order_by('full_name')

    payroll_staff = Employee.objects.filter(status__in=('ACTIVE', 'ON_LEAVE'))
    totals = payroll_staff.aggregate(b=Sum('basic_salary'), a=Sum('allowances'))
    monthly_payroll = (totals['b'] or Decimal('0.00')) + (totals['a'] or Decimal('0.00'))
    started = timezone.now().date().replace(month=1, day=1)
    ytd_paid = sum(
        (p.net_pay for p in SalaryPayment.objects.filter(status='PAID', payment_date__gte=started)),
        Decimal('0.00'),
    )

    editing = None
    edit_id = request.GET.get('edit', '').strip()
    if edit_id.isdigit():
        editing = Employee.objects.filter(id=int(edit_id)).first()

    return render(request, 'core/finance_employees.html', {
        'employees': employees,
        'total_employees': Employee.objects.count(),
        'active_employees': Employee.objects.filter(status='ACTIVE').count(),
        'payroll_staff_count': payroll_staff.count(),
        'monthly_payroll': monthly_payroll,
        'average_gross': (monthly_payroll / payroll_staff.count()) if payroll_staff.count() else Decimal('0.00'),
        'ytd_salary_paid': ytd_paid,
        'status_filter': status_filter,
        'search_query': query,
        'editing': editing,
        'system_users': User.objects.filter(is_active=True).select_related('profile').order_by('first_name', 'username'),
        'today': timezone.now().date(),
    })


@login_required
@role_required(OPERATING_EXPENSE_ROLES)
def employee_create_action(request):
    if request.method != 'POST':
        return redirect('employees')
    data, errors = _parse_employee_form(request)
    if errors:
        for error in errors:
            messages.error(request, error)
        return redirect('employees')
    employee = Employee.objects.create(created_by=request.user, **data)
    log_audit(request, "EMPLOYEE_CREATED", f"Employee {employee.full_name} ({employee.employee_number}) added — {employee.position}, basic salary TSh {employee.basic_salary:,.2f}.")
    messages.success(request, f"Employee {employee.full_name} added successfully ({employee.employee_number}).")
    return redirect('employees')


@login_required
@role_required(OPERATING_EXPENSE_ROLES)
def employee_update_action(request, employee_id):
    employee = get_object_or_404(Employee, id=employee_id)
    if request.method != 'POST':
        return redirect('employee_detail', employee_id=employee.id)
    data, errors = _parse_employee_form(request)
    if errors:
        for error in errors:
            messages.error(request, error)
        return redirect(f"{reverse('employees')}?edit={employee.id}")
    for field, value in data.items():
        setattr(employee, field, value)
    employee.save()
    log_audit(request, "EMPLOYEE_UPDATED", f"Employee {employee.full_name} ({employee.employee_number}) record updated — {employee.position}, basic salary TSh {employee.basic_salary:,.2f}.")
    messages.success(request, f"Employee {employee.full_name} updated successfully.")
    return redirect('employee_detail', employee_id=employee.id)


@login_required
@role_required(OPERATING_EXPENSE_ROLES)
def employee_detail_view(request, employee_id):
    employee = get_object_or_404(Employee, id=employee_id)
    payments = employee.salary_payments.all().order_by('-period')
    paid = [p for p in payments if p.status == 'PAID']
    today = timezone.now().date()
    service_days = (today - employee.date_joined).days if employee.date_joined else 0
    return render(request, 'core/finance_employee_detail.html', {
        'employee': employee,
        'payments': payments,
        'total_paid': sum((p.net_pay for p in paid), Decimal('0.00')),
        'total_gross_paid': sum((p.gross_pay for p in paid), Decimal('0.00')),
        'payments_count': len(paid),
        'service_years': max(service_days, 0) // 365,
        'service_months': (max(service_days, 0) % 365) // 30,
        'today': today,
    })


@login_required
@role_required(OPERATING_EXPENSE_ROLES)
def payroll_view(request):
    selected_month = _parse_month_param(request.GET.get('month'))
    month_start, month_end = _month_bounds(selected_month)
    salaries = SalaryPayment.objects.select_related('employee', 'operating_expense').filter(period=selected_month).order_by('employee__full_name')

    excluded = salaries.values_list('employee_id', flat=True)
    pending_employees = Employee.objects.filter(status__in=('ACTIVE', 'ON_LEAVE')).exclude(id__in=excluded).order_by('full_name')

    totals = {
        'basic': Decimal('0.00'), 'allowances': Decimal('0.00'), 'gross': Decimal('0.00'),
        'nssf': Decimal('0.00'), 'taxable': Decimal('0.00'), 'paye': Decimal('0.00'),
        'wcf': Decimal('0.00'), 'sdl': Decimal('0.00'), 'pay': Decimal('0.00'),
        'advance': Decimal('0.00'), 'loan': Decimal('0.00'), 'other': Decimal('0.00'),
        'deductions': Decimal('0.00'), 'net': Decimal('0.00'),
        'paid': Decimal('0.00'), 'pending': Decimal('0.00')
    }
    for salary in salaries:
        if salary.status == 'CANCELLED':
            continue
        totals['basic'] += salary.basic_salary or Decimal('0.00')
        totals['allowances'] += salary.allowances or Decimal('0.00')
        totals['gross'] += salary.gross_pay
        totals['nssf'] += salary.nssf or Decimal('0.00')
        totals['taxable'] += salary.taxable_amount
        totals['paye'] += salary.paye or Decimal('0.00')
        totals['wcf'] += salary.wcf or Decimal('0.00')
        totals['sdl'] += salary.sdl or Decimal('0.00')
        totals['pay'] += salary.pay_before_personal_deductions
        totals['advance'] += salary.salary_advance or Decimal('0.00')
        totals['loan'] += salary.loan_deduction or Decimal('0.00')
        totals['other'] += salary.other_deductions or Decimal('0.00')
        totals['deductions'] += salary.total_deductions
        totals['net'] += salary.net_pay
        if salary.status == 'PAID':
            totals['paid'] += salary.net_pay
        else:
            totals['pending'] += salary.net_pay

    editing = None
    edit_id = request.GET.get('edit', '').strip()
    if edit_id.isdigit():
        editing = SalaryPayment.objects.filter(id=int(edit_id)).first()

    return render(request, 'core/finance_payroll.html', {
        'selected_month': selected_month,
        'selected_month_label': selected_month.strftime('%B %Y'),
        'month_key': selected_month.strftime('%Y-%m'),
        'salaries': salaries,
        'pending_employees': pending_employees,
        'totals': totals,
        'payment_methods': OperatingExpense.PAYMENT_METHOD_CHOICES,
        'status_choices': SalaryPayment.STATUS_CHOICES,
        'editing': editing,
        'system_users': User.objects.filter(is_active=True).select_related('profile').order_by('first_name', 'username'),
        'today': timezone.now().date(),
        'payment_default_date': month_end,
    })


@login_required
@role_required(OPERATING_EXPENSE_ROLES)
def payroll_generate_action(request):
    month = request.POST.get('month', '').strip()
    if request.method != 'POST':
        return _payroll_redirect(month)
    selected_month = _parse_month_param(month)
    existing = SalaryPayment.objects.filter(period=selected_month).values_list('employee_id', flat=True)
    staff = Employee.objects.filter(status__in=('ACTIVE', 'ON_LEAVE')).exclude(id__in=existing)
    created = 0
    for employee in staff:
        if employee.no_deductions:
            paye = nssf = wcf = sdl = Decimal('0.00')
        else:
            paye, nssf, wcf, sdl = compute_statutory(employee.monthly_gross)
        SalaryPayment.objects.create(
            employee=employee,
            period=selected_month,
            basic_salary=employee.basic_salary,
            allowances=employee.allowances,
            paye=paye,
            nssf=nssf,
            wcf=wcf,
            sdl=sdl,
            recorded_by=request.user,
        )
        created += 1
    if created:
        log_audit(request, "PAYROLL_GENERATED", f"Payroll drafts generated for {created} employee(s) — {selected_month:%B %Y}.")
        messages.success(request, f"{created} salary row(s) generated for {selected_month:%B %Y}. Review deductions, then mark each as paid.")
    else:
        messages.info(request, f"Payroll for {selected_month:%B %Y} is already generated for all staff on payroll.")
    return _payroll_redirect(selected_month.strftime('%Y-%m'))


def _salary_expense_category(request):
    """Reuse the accountant's own salary category if it exists, otherwise create one."""
    existing = OperatingExpenseCategory.objects.filter(
        Q(name__icontains='salary') | Q(name__icontains='salaries') |
        Q(name__icontains='wage') | Q(name__icontains='mishahara') | Q(name__icontains='payroll')
    ).order_by('-is_active', 'id').first()
    if existing:
        return existing
    category, _ = OperatingExpenseCategory.objects.get_or_create(
        name=PAYROLL_EXPENSE_CATEGORY_NAME,
        defaults={'description': 'Auto-generated from the salary payroll', 'created_by': request.user},
    )
    return category


def _sync_salary_expense(request, salary):
    """Create/update the matching operating expense for a paid salary."""
    category = _salary_expense_category(request)
    if not category.is_active:
        category.is_active = True
        category.save(update_fields=['is_active'])

    description = (
        f"Salary {salary.period:%B %Y} — {salary.employee.position} ({salary.employee.employee_number}). "
        f"Gross TSh {salary.gross_pay:,.2f}; deductions TSh {salary.total_deductions:,.2f}."
    )
    expense_date = salary.payment_date or salary.period
    if salary.operating_expense_id:
        expense = salary.operating_expense
        expense.date = expense_date
        expense.category = category
        expense.amount = salary.net_pay
        expense.payee = salary.employee.full_name
        expense.payment_method = salary.payment_method
        expense.payment_reference = salary.payment_reference
        expense.description = description
        expense.recorded_by = request.user
        expense.save()
    else:
        expense = OperatingExpense.objects.create(
            date=expense_date,
            category=category,
            amount=salary.net_pay,
            payee=salary.employee.full_name,
            payment_method=salary.payment_method,
            payment_reference=salary.payment_reference,
            description=description,
            recorded_by=request.user,
        )
        salary.operating_expense = expense
        salary.save(update_fields=['operating_expense'])
    return expense


@login_required
@role_required(OPERATING_EXPENSE_ROLES)
def payroll_update_action(request, salary_id):
    salary = get_object_or_404(SalaryPayment.objects.select_related('employee'), id=salary_id)
    if request.method != 'POST':
        return _payroll_redirect(salary.period.strftime('%Y-%m'))

    errors = []
    basic = _decimal_field(request.POST.get('basic_salary'), "Basic salary", errors)
    allowances = _decimal_field(request.POST.get('allowances'), "Allowances", errors)
    paye = _decimal_field(request.POST.get('paye'), "PAYE", errors)
    nssf = _decimal_field(request.POST.get('nssf'), "NSSF", errors)
    wcf = _decimal_field(request.POST.get('wcf'), "WCF", errors)
    sdl = _decimal_field(request.POST.get('sdl'), "SDL", errors)
    advance = _decimal_field(request.POST.get('salary_advance'), "Salary advance", errors)
    loan = _decimal_field(request.POST.get('loan_deduction'), "Loan deduction", errors)
    other = _decimal_field(request.POST.get('other_deductions'), "Other deductions", errors)
    status = request.POST.get('status', 'DRAFT')
    if status not in dict(SalaryPayment.STATUS_CHOICES):
        status = 'DRAFT'
    method = request.POST.get('payment_method', 'BANK')
    if method not in dict(OperatingExpense.PAYMENT_METHOD_CHOICES):
        method = 'BANK'

    payment_date = None
    payment_date_raw = request.POST.get('payment_date', '').strip()
    if payment_date_raw:
        try:
            payment_date = datetime.strptime(payment_date_raw, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            errors.append("Payment date is not a valid date.")
    elif status == 'PAID':
        errors.append("Please provide the date the salary was paid.")

    if errors:
        for error in errors:
            messages.error(request, error)
        return _payroll_redirect(salary.period.strftime('%Y-%m'))

    gross = basic + allowances
    deductions = paye + nssf + advance + loan + other
    if deductions > gross:
        messages.error(request, "Total deductions cannot exceed gross pay.")
        return _payroll_redirect(salary.period.strftime('%Y-%m'))

    salary.basic_salary = basic
    salary.allowances = allowances
    salary.paye = paye
    salary.nssf = nssf
    salary.wcf = wcf
    salary.sdl = sdl
    salary.salary_advance = advance
    salary.loan_deduction = loan
    salary.other_deductions = other
    salary.deduction_notes = request.POST.get('deduction_notes', '').strip()
    salary.status = status
    salary.payment_date = payment_date
    salary.payment_method = method
    salary.payment_reference = request.POST.get('payment_reference', '').strip()
    salary.notes = request.POST.get('notes', '').strip()
    new_receipt = request.FILES.get('receipt_file')
    if new_receipt:
        salary.receipt_file = new_receipt
    salary.recorded_by = request.user
    salary.save()

    if status == 'PAID':
        _sync_salary_expense(request, salary)
        log_audit(request, "SALARY_PAID", f"{salary.employee.full_name} — {salary.period:%B %Y}: net TSh {salary.net_pay:,.2f} via {salary.get_payment_method_display()} (ref {salary.payment_reference or 'N/A'}).")
        messages.success(request, f"Salary for {salary.employee.full_name} ({salary.period:%B %Y}) marked paid — TSh {salary.net_pay:,.2f} recorded in operating expenses.")
    else:
        if salary.operating_expense_id:
            linked = salary.operating_expense
            salary.operating_expense = None
            salary.save(update_fields=['operating_expense'])
            linked.delete()
            log_audit(request, "SALARY_EXPENSE_REVERSED", f"{salary.employee.full_name} — {salary.period:%B %Y}: linked operating expense removed because status changed to {salary.get_status_display()}.")
        log_audit(request, "SALARY_UPDATED", f"{salary.employee.full_name} — {salary.period:%B %Y}: gross TSh {salary.gross_pay:,.2f}, net TSh {salary.net_pay:,.2f}, status {salary.get_status_display()}.")
        messages.success(request, f"Salary record for {salary.employee.full_name} updated.")
    return _payroll_redirect(salary.period.strftime('%Y-%m'))


@login_required
@role_required(OPERATING_EXPENSE_ROLES)
def payroll_delete_action(request, salary_id):
    salary = get_object_or_404(SalaryPayment.objects.select_related('employee'), id=salary_id)
    month = salary.period.strftime('%Y-%m')
    if request.method == 'POST':
        details = f"{salary.employee.full_name} — {salary.period:%B %Y}: net TSh {salary.net_pay:,.2f} ({salary.get_status_display()})"
        if salary.operating_expense_id:
            salary.operating_expense.delete()
        salary.delete()
        log_audit(request, "SALARY_DELETED", details)
        messages.success(request, "Salary record deleted.")
        return _payroll_redirect(month)
    return _payroll_redirect(month)


@login_required
@role_required(OPERATING_EXPENSE_ROLES)
def payroll_export_excel(request):
    import io
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    selected_month = _parse_month_param(request.GET.get('month'))
    month_start, month_end = _month_bounds(selected_month)
    salaries = SalaryPayment.objects.select_related('employee').filter(period=selected_month).order_by('employee__full_name')

    wb = Workbook()
    ws = wb.active
    ws.title = "Payroll"
    ws.views.sheetView[0].showGridLines = True

    font_family = "Calibri"
    header_fill = PatternFill(start_color="D9A5B3", end_color="D9A5B3", fill_type="solid")
    green_fill = PatternFill(start_color="D9EAD3", end_color="D9EAD3", fill_type="solid")
    yellow_fill = PatternFill(start_color="FFFF00", end_color="FFFF00", fill_type="solid")
    blue_fill = PatternFill(start_color="8EA9DB", end_color="8EA9DB", fill_type="solid")

    thin_border = Border(
        left=Side(style='thin', color='7F7F7F'),
        right=Side(style='thin', color='7F7F7F'),
        top=Side(style='thin', color='7F7F7F'),
        bottom=Side(style='thin', color='7F7F7F')
    )
    header_font = Font(name=font_family, size=9, bold=True, color="000000")
    bold_font = Font(name=font_family, size=9, bold=True, color="000000")
    regular_font = Font(name=font_family, size=9, color="000000")

    day = month_end.day
    suffix = "TH" if 11 <= day <= 13 else {1: "ST", 2: "ND", 3: "RD"}.get(day % 10, "TH")
    title_text = f"{day}{suffix} {month_end.strftime('%B %Y').upper()} PAYROLL"

    ws.merge_cells("A1:P1")
    title_cell = ws["A1"]
    title_cell.value = title_text
    title_cell.font = Font(name=font_family, size=11, bold=True, color="000000")
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    title_cell.fill = header_fill
    for col in range(1, 17):
        ws.cell(row=1, column=col).border = thin_border
    ws.row_dimensions[1].height = 24

    headers = [
        "S/N", "NAME OF EMPLOYEE", "ACCOUNT NO", "BASE SALARY", "ALLOWANCE",
        "NSSF NO.", "GROSS SALARY", "NSSF AMOUNT", "TAXABLE AMOUNT", "PAYEE",
        "WCF", "SDL", "PAY", "ADVANCE", "LOAN", "NET PAY"
    ]
    ws.append(headers)
    ws.row_dimensions[2].height = 22
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=2, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = thin_border

    row_idx = 3
    valid_count = 0
    for idx, s in enumerate(salaries, start=1):
        if s.status == 'CANCELLED':
            continue
        valid_count += 1
        emp = s.employee
        acc_no = f"AC/ {emp.bank_account_number}" if emp.bank_account_number else ""
        nssf_no = emp.nssf_number or ""
        allowance_val = float(s.allowances) if (s.allowances and s.allowances > 0) else "-"

        row_data = [
            valid_count,
            emp.full_name.upper(),
            acc_no,
            float(s.basic_salary or 0),
            allowance_val,
            nssf_no,
            float(s.gross_pay or 0),
            float(s.nssf or 0),
            float(s.taxable_amount or 0),
            float(s.paye or 0),
            float(s.wcf or 0),
            float(s.sdl or 0),
            float(s.pay_before_personal_deductions or 0),
            float(s.salary_advance or 0),
            float(s.loan_deduction or 0),
            float(s.net_pay or 0),
        ]
        ws.append(row_data)
        ws.row_dimensions[row_idx].height = 20

        for col_idx in range(1, 17):
            c = ws.cell(row=row_idx, column=col_idx)
            c.font = regular_font
            c.border = thin_border

            if col_idx == 1:
                c.alignment = Alignment(horizontal="center", vertical="center")
            elif col_idx in (2, 3, 6):
                c.alignment = Alignment(horizontal="left", vertical="center")
            elif col_idx == 5 and allowance_val == "-":
                c.alignment = Alignment(horizontal="center", vertical="center")
            else:
                c.alignment = Alignment(horizontal="right", vertical="center")
                if isinstance(c.value, (int, float)):
                    c.number_format = '#,##0.00'

            # Green tint for PAYEE (10), WCF (11), SDL (12), NET PAY (16)
            if col_idx in (10, 11, 12, 16):
                c.fill = green_fill

        row_idx += 1

    # TOTAL ROW
    total_row_idx = row_idx
    ws.cell(row=total_row_idx, column=1, value="")
    ws.cell(row=total_row_idx, column=2, value="TOTAL")

    if valid_count > 0:
        first_r = 3
        last_r = row_idx - 1
        ws.cell(row=total_row_idx, column=4, value=f"=SUM(D{first_r}:D{last_r})")
        ws.cell(row=total_row_idx, column=7, value=f"=SUM(G{first_r}:G{last_r})")
        ws.cell(row=total_row_idx, column=8, value=f"=SUM(H{first_r}:H{last_r})")
        ws.cell(row=total_row_idx, column=9, value=f"=SUM(I{first_r}:I{last_r})")
        ws.cell(row=total_row_idx, column=10, value=f"=SUM(J{first_r}:J{last_r})")
        ws.cell(row=total_row_idx, column=11, value=f"=SUM(K{first_r}:K{last_r})")
        ws.cell(row=total_row_idx, column=12, value=f"=SUM(L{first_r}:L{last_r})")
        ws.cell(row=total_row_idx, column=13, value=f"=SUM(M{first_r}:M{last_r})")
        ws.cell(row=total_row_idx, column=14, value=f"=SUM(N{first_r}:N{last_r})")
        ws.cell(row=total_row_idx, column=15, value=f"=SUM(O{first_r}:O{last_r})")
        ws.cell(row=total_row_idx, column=16, value=f"=SUM(P{first_r}:P{last_r})")

    ws.row_dimensions[total_row_idx].height = 22
    for col_idx in range(1, 17):
        c = ws.cell(row=total_row_idx, column=col_idx)
        c.font = bold_font
        c.fill = yellow_fill
        c.border = thin_border
        if col_idx in (4, 5, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16):
            c.number_format = '#,##0.00'
            c.alignment = Alignment(horizontal="right", vertical="center")
        elif col_idx == 2:
            c.alignment = Alignment(horizontal="left", vertical="center")

    # Statutory rates box in column D (BASE SALARY column below totals)
    notes_start = total_row_idx + 2
    notes = [("NSSF 10%", notes_start), ("WCF 0.5%", notes_start + 1), ("SDL 3.5%", notes_start + 2)]
    for note, r in notes:
        nc = ws.cell(row=r, column=4, value=note)
        nc.font = bold_font
        nc.fill = blue_fill
        nc.alignment = Alignment(horizontal="center", vertical="center")
        nc.border = thin_border

    col_widths = {
        'A': 6,   'B': 28,  'C': 22,  'D': 15,
        'E': 14,  'F': 14,  'G': 15,  'H': 14,
        'I': 16,  'J': 13,  'K': 12,  'L': 12,
        'M': 15,  'N': 13,  'O': 12,  'P': 16,
    }
    for col_letter, width in col_widths.items():
        ws.column_dimensions[col_letter].width = width

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    filename = f"Payroll_{month_end.strftime('%B_%Y')}.xlsx"
    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def my_salary_view(request):
    """Self-service salary & payslip view for the logged-in employee."""
    employee = Employee.objects.filter(user=request.user).first()
    if not employee and request.user.email:
        employee = Employee.objects.filter(email__iexact=request.user.email.strip(), user__isnull=True).first()
        if employee:
            employee.user = request.user
            employee.save(update_fields=['user'])
    if not employee:
        full_name = (request.user.get_full_name() or '').strip()
        if full_name:
            employee = Employee.objects.filter(full_name__iexact=full_name, user__isnull=True).first()
            if employee:
                employee.user = request.user
                employee.save(update_fields=['user'])

    if not employee:
        return render(request, 'core/finance_employee_detail.html', {
            'employee': None,
            'payments': [],
            'total_paid': Decimal('0.00'),
            'total_gross_paid': Decimal('0.00'),
            'payments_count': 0,
            'service_years': 0,
            'service_months': 0,
            'today': timezone.now().date(),
            'is_self_salary_view': True,
        })

    payments = employee.salary_payments.all().order_by('-period')
    paid = [p for p in payments if p.status == 'PAID']
    today = timezone.now().date()
    service_days = (today - employee.date_joined).days if employee.date_joined else 0
    return render(request, 'core/finance_employee_detail.html', {
        'employee': employee,
        'payments': payments,
        'total_paid': sum((p.net_pay for p in paid), Decimal('0.00')),
        'total_gross_paid': sum((p.gross_pay for p in paid), Decimal('0.00')),
        'payments_count': len(paid),
        'service_years': max(service_days, 0) // 365,
        'service_months': (max(service_days, 0) % 365) // 30,
        'today': today,
        'is_self_salary_view': True,
    })


@login_required
def payslip_view(request, salary_id):
    salary = get_object_or_404(SalaryPayment.objects.select_related('employee'), id=salary_id)
    role = get_user_role(request.user)
    is_allowed_staff = (salary.employee.user_id == request.user.id)
    is_finance_or_exec = (role in OPERATING_EXPENSE_ROLES or request.user.is_superuser)
    if not (is_allowed_staff or is_finance_or_exec):
        messages.error(request, "Permission denied: You can only view your own payslip.")
        return redirect('my_profile')
    return render(request, 'core/print_payslip.html', {
        'salary': salary,
        'employee': salary.employee,
        'month_label': salary.period.strftime('%B %Y'),
        'today': timezone.now().date(),
    })


@login_required



@role_required([UserRole.FINANCE, UserRole.CEO, UserRole.ADMIN])



def finance_billing_view(request):
    role = get_user_role(request.user)
    is_ceo = (role in [UserRole.CEO, UserRole.ADMIN] or request.user.is_superuser)
    is_finance = (role == UserRole.FINANCE or request.user.is_superuser)

    query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '').strip()
    create_for_job = request.GET.get('create_for_job', '').strip()

    invoices = ClientInvoice.objects.all().select_related('job', 'customer').prefetch_related('payments').order_by('-issue_date')

    if query:
        invoices = invoices.filter(
            Q(invoice_number__icontains=query) |
            Q(customer__company_name__icontains=query) |
            Q(job__job_number__icontains=query) |
            Q(job__bl_number__icontains=query) |
            Q(job__chassis_number__icontains=query)
        )

    if status_filter:
        if status_filter == 'outstanding':
            invoices = invoices.filter(status__in=['ISSUED', 'PARTIALLY_PAID', 'OVERDUE'])
        else:
            invoices = invoices.filter(status=status_filter)

    all_invoices = list(ClientInvoice.objects.all())
    total_billed = sum((i.total_amount or Decimal('0.00')) for i in all_invoices)
    total_collected = sum((i.amount_paid or Decimal('0.00')) for i in all_invoices)
    total_outstanding = sum(i.balance_due for i in all_invoices)
    overdue_count = ClientInvoice.objects.filter(status='OVERDUE').count()

    page_obj, extra_querystring = paginate_queryset(request, invoices, default_per_page=10)

    jobs = JobShipment.objects.all().select_related('customer').order_by('-created_at')

    context = {
        'invoices': page_obj.object_list,
        'page_obj': page_obj,
        'extra_querystring': extra_querystring,
        'search_query': query,
        'status_filter': status_filter,
        'total_billed': total_billed,
        'total_collected': total_collected,
        'total_outstanding': total_outstanding,
        'overdue_count': overdue_count,
        'jobs': jobs,
        'create_for_job': create_for_job,
        'payment_methods': ClientPayment.PAYMENT_METHODS,
        'is_ceo': is_ceo,
        'is_finance': is_finance,
    }
    return render(request, 'core/finance_billing.html', context)


@login_required
def expense_create_action(request):



    if request.method == 'POST':



        if get_user_role(request.user) == UserRole.CEO:



            messages.error(request, "Akaunti ya Boss ina mamlaka ya ukaguzi tu (Read-Only) na haina ruhusa ya kuomba vocha ya matumizi.")



            return redirect(request.META.get('HTTP_REFERER') or 'finance_billing')







        job_id = request.POST.get('job_id')



        category = request.POST.get('category')



        amount_str = request.POST.get('amount', '0')



        description = request.POST.get('description', '').strip()



        payment_method = request.POST.get('payment_method', 'BANK')



        



        job = get_object_or_404(JobShipment, id=job_id)



        amount = Decimal(amount_str)



        required_role = ExpenseVoucher.determine_required_role(amount)



        voucher_number = ExpenseVoucher.generate_next_voucher_number()







        voucher = ExpenseVoucher.objects.create(



            voucher_number=voucher_number,



            job=job,



            category=category,



            amount=amount,



            description=description,



            payment_method=payment_method,



            requester=request.user,



            required_role=required_role,



            approval_status='REQUESTED',



        )







        if 'receipt_file' in request.FILES:



            voucher.supporting_document = request.FILES['receipt_file']



            voucher.save()







        log_audit(request, "REQUEST_EXPENSE", f"Requested Expense {voucher_number} of TSh {amount:,.2f} ({voucher.get_payment_method_display()}) for {category} on {job.job_number}", job=job)



        messages.success(request, f"Expense Voucher {voucher_number} (TSh {amount:,.2f} - {voucher.get_payment_method_display()}) submitted. Required Authority: {voucher.get_required_role_display()}!")



        



        next_url = request.POST.get('next', 'finance')



        if next_url == 'job_detail':



            return redirect('job_detail', job_id=job.id)



        return redirect(request.META.get('HTTP_REFERER') or 'finance_billing')



    return redirect(request.META.get('HTTP_REFERER') or 'finance_billing')











def _sync_operational_voucher_to_job(voucher, request):

    job = voucher.job

    if not job:

        return

    now = timezone.now()



    if voucher.category == ExpenseCategory.CUSTOMS_DUTY:

        job.duty_paid = True

        job.duty_payment_date = now.date()

        job.duty_payment_reference = voucher.payment_reference or voucher.control_number or f"TRA-{voucher.voucher_number}"

        st3 = job.stages.filter(stage_number=3).first()

        if st3:

            st3.status = 'COMPLETED'

            st3.completed_at = now

            st3.remarks = f"Customs Duty TSh {voucher.amount:,.2f} settled via {job.duty_payment_reference} by Finance."

            st3.save()

        if job.current_stage_number <= 3:

            job.current_stage_number = 4

            st4 = job.stages.filter(stage_number=4).first()

            if st4:

                st4.status = 'IN_PROGRESS'

                st4.started_at = now

                st4.save()

        job.save()



    elif voucher.category == ExpenseCategory.SHIPPING_LINE:

        # Delivery Order (D/O) is STAGE 4

        ref_do = voucher.control_number or voucher.payment_reference or f"DO-{job.job_number}"

        job.delivery_order_number = ref_do

        st4 = job.stages.filter(stage_number=4).first()

        if st4:

            st4.status = 'COMPLETED'

            st4.completed_at = now

            st4.responsible_officer = request.user

            st4.remarks = f"Shipping Line D/O fee TSh {voucher.amount:,.2f} paid & approved by Finance (Ref: {ref_do})."

            st4.save()



        # Advance to Stage 5: Physical Verification

        if job.current_stage_number <= 4:

            job.current_stage_number = 5

            st5 = job.stages.filter(stage_number=5).first()

            if st5:

                st5.status = 'IN_PROGRESS'

                st5.started_at = now

                st5.save()

        job.save()



        log_audit(

            request, 

            "DELIVERY_ORDER_RECORDED", 

            f"Shipping Line D/O fee settled (Ref: {ref_do}). Consignment advanced to Stage 5 (Physical Verification).", 

            job=job

        )



    elif voucher.category == ExpenseCategory.PORT_CHARGES:

        # Port & ICD Charges is STAGE 6

        ref_port = voucher.control_number or voucher.payment_reference or f"PORT-{job.job_number}"

        job.port_invoice_number = ref_port

        st6 = job.stages.filter(stage_number=6).first()

        if st6:

            st6.status = 'COMPLETED'

            st6.completed_at = now

            st6.responsible_officer = request.user

            st6.remarks = f"Port & ICD wharfage charges TSh {voucher.amount:,.2f} paid & approved by Finance (Ref: {ref_port})."

            st6.save()



        # Advance to Stage 7: Gate Exit & Inspection

        if job.current_stage_number <= 6:

            job.current_stage_number = 7

            st7 = job.stages.filter(stage_number=7).first()

            if st7:

                st7.status = 'IN_PROGRESS'

                st7.started_at = now

                st7.save()

        job.save()



        log_audit(

            request, 

            "PORT_INVOICE_PAID", 

            f"Port & ICD charges settled (Ref: {ref_port}). Consignment advanced to Stage 7 (Gate Exit).", 

            job=job

        )



    # Always re-sync client invoice if one exists or vehicle is at/on way to yard

    if job.invoices.exists() or job.vehicle_dispatched_to_office or job.vehicle_arrived_at_office:

        auto_compile_customer_final_bill(job)





@login_required



def expense_approval_action(request, voucher_id):

    if request.method == 'POST':

        voucher = get_object_or_404(ExpenseVoucher, id=voucher_id)

        decision = request.POST.get('decision') # 'VERIFY', 'APPROVE', 'PAY', 'REJECT'

        remarks = request.POST.get('remarks', '').strip()

        user_role = get_user_role(request.user)

        user_disp = request.user.get_full_name() or request.user.username

        now = timezone.now()

        next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or 'finance'



        # 1. DARAJA LA MHASIBU: Hakiki & Tuma kwa CEO (Audit & Forward to CEO)

        if decision in ['VERIFY', 'FORWARD_TO_CEO']:

            can_audit = (user_role in [UserRole.FINANCE, UserRole.OPERATIONS_MGR, UserRole.ADMIN, UserRole.CEO] or request.user.is_superuser)

            if not can_audit:

                messages.error(request, "Unauthorized to audit and submit payment requests to CEO.")

                return redirect(next_url)



            voucher.approval_status = 'VERIFIED'

            voucher.audited_by = request.user

            voucher.audited_at = now

            if remarks:

                voucher.approval_remarks = remarks

            else:

                voucher.approval_remarks = f"Audited by Finance ({user_disp}) and submitted to CEO for payout."

            voucher.save()



            log_audit(

                request,

                "VERIFY_EXPENSE",

                f"Finance Officer {user_disp} audited voucher {voucher.voucher_number} (TSh {voucher.amount:,.2f}) and forwarded to CEO for payout.",

                job=voucher.job

            )

            messages.success(

                request,

                f"Voucher {voucher.voucher_number} ({voucher.get_category_display()} - TSh {voucher.amount:,.2f}) verified and forwarded to CEO for payout."

            )

            return redirect(next_url)



        # 2. MAMLAKA YA CEO: Idhinisha & Toa Fedha kutoka Akaunti ya Ofisi / Cash

        elif decision in ['APPROVE', 'PAY']:

            if voucher.approval_status != 'VERIFIED':

                messages.error(request, "This voucher must be verified by Finance before it can be approved.")

                return redirect(next_url)

            is_authorized = (user_role in [UserRole.CEO, UserRole.ADMIN] or request.user.is_superuser)

            if not is_authorized:

                messages.error(

                    request,

                    f"Only the CEO / Managing Director is authorized to disburse office funds."

                )

                return redirect(next_url)



            pay_method = request.POST.get('payment_method') or voucher.payment_method or 'BANK'

            pay_ref = request.POST.get('payment_reference', '').strip()



            voucher.approval_status = 'APPROVED'

            voucher.approval_date = now

            voucher.approver = request.user

            if remarks:

                voucher.approval_remarks = remarks

            voucher.payment_method = pay_method

            voucher.is_paid = True

            voucher.paid_at = now

            voucher.payment_reference = pay_ref or voucher.control_number or f"PAY-{voucher.voucher_number}"

            voucher.save()



            # Automatic synchronization with shipment workflow for payments

            _sync_operational_voucher_to_job(voucher, request)



            log_audit(

                request,

                "CEO_DISBURSE_EXPENSE",

                f"CEO {user_disp} approved & disbursed voucher {voucher.voucher_number} (TSh {voucher.amount:,.2f}) via {voucher.get_payment_method_display()} (Ref: {voucher.payment_reference}).",

                job=voucher.job

            )

            messages.success(

                request,

                f"Payment of TSh {voucher.amount:,.2f} ({voucher.get_category_display()}) approved and disbursed by CEO."

            )

            return redirect(next_url)



        # 3. KATAA: Kataa vocha

        elif decision == 'REJECT':

            can_reject = (user_role in [UserRole.FINANCE, UserRole.CEO, UserRole.ADMIN, UserRole.OPERATIONS_MGR] or request.user.is_superuser)

            if not can_reject:

                messages.error(request, "Unauthorized to reject expense voucher.")

                return redirect(next_url)



            voucher.approval_status = 'REJECTED'

            voucher.approval_date = now

            voucher.approver = request.user

            voucher.approval_remarks = remarks or f"Rejected by {user_disp}"

            voucher.save()



            log_audit(request, "REJECT_EXPENSE", f"Voucher {voucher.voucher_number} rejected: {remarks}", job=voucher.job)

            messages.warning(request, f"Voucher {voucher.voucher_number} has been rejected.")

            return redirect(next_url)



    return redirect(request.META.get('HTTP_REFERER') or 'finance_billing')







@login_required



@role_required([UserRole.FINANCE])



def invoice_create_action(request):
    if request.method == 'POST':
        job_id = request.POST.get('job_id')
        job = get_object_or_404(JobShipment, id=job_id)
        customer = job.customer

        agency_fee = Decimal(request.POST.get('agency_fee', '0') or '0')
        duty_reimb = Decimal(request.POST.get('duty_reimb', '0') or '0')
        port_charges = Decimal(request.POST.get('port_charges', '0') or '0')
        terminal_handling = Decimal(request.POST.get('terminal_handling', '0') or request.POST.get('amount_terminal_handling', '0') or '0')
        shipping_line = Decimal(request.POST.get('shipping_line', '0') or '0')
        transport = Decimal(request.POST.get('transport', '0') or '0')
        sundry = Decimal(request.POST.get('sundry', '0') or '0')

        total = agency_fee + duty_reimb + port_charges + terminal_handling + shipping_line + transport + sundry
        inv_number = ClientInvoice.generate_next_invoice_number()
        due_date = timezone.now().date() + timedelta(days=14)

        invoice = ClientInvoice.objects.create(
            invoice_number=inv_number,
            job=job,
            customer=customer,
            due_date=due_date,
            amount_clearing_agency_fee=agency_fee,
            amount_duty_reimbursement=duty_reimb,
            amount_port_charges=port_charges,
            amount_terminal_handling=terminal_handling,
            amount_shipping_line_do=shipping_line,
            amount_transport=transport,
            amount_sundry_charges=sundry,
            total_amount=total,
            status='ISSUED',
            notes=request.POST.get('notes', '')
        )

        # Sync agent fee to job if not set
        if agency_fee > 0 and (not job.cost_agent_fee or job.cost_agent_fee == 0):
            job.cost_agent_fee = agency_fee
            job.save(update_fields=['cost_agent_fee'])

        log_audit(request, 'CREATE_INVOICE', f'Issued Invoice {inv_number} of TSh {total:,.2f} for {customer.company_name} on {job.job_number}', job=job)
        messages.success(request, f'Client Invoice {inv_number} for TSh {total:,.2f} generated successfully!')

        next_url = request.POST.get('next')
        if next_url == 'job_detail':
            return redirect('job_detail', job_id=job.id)
        return redirect('finance_billing')

    return redirect('finance_billing')


@login_required
@role_required([UserRole.FINANCE])
def payment_record_action(request):



    if request.method == 'POST':



        invoice_id = request.POST.get('invoice_id')



        invoice = get_object_or_404(ClientInvoice, id=invoice_id)



        amount = Decimal(request.POST.get('amount', '0') or '0')



        method = request.POST.get('payment_method', 'BANK_TRANSFER')



        ref = request.POST.get('payment_reference', '').strip()



        notes = request.POST.get('notes', '').strip()







        payment = ClientPayment.objects.create(



            invoice=invoice,



            amount=amount,



            payment_date=timezone.now().date(),



            payment_method=method,



            payment_reference=ref,



            notes=notes,



            recorded_by=request.user



        )







        invoice.amount_paid += amount



        if invoice.amount_paid >= invoice.total_amount:



            invoice.status = 'PAID'



        else:



            invoice.status = 'PARTIALLY_PAID'



        invoice.save()







        log_audit(request, "RECORD_PAYMENT", f"Recorded payment of TSh {amount:,.2f} for invoice {invoice.invoice_number} (Ref: {ref})", job=invoice.job)



        messages.success(request, f"Payment of TSh {amount:,.2f} recorded for {invoice.invoice_number}!")







    return redirect(request.META.get('HTTP_REFERER') or 'finance_billing')











DOCUMENT_UPLOAD_EXTENSIONS = {'.pdf', '.jpg', '.jpeg', '.png', '.webp'}
DOCUMENT_UPLOAD_MAX_BYTES = 60 * 1024 * 1024
DOCUMENT_UPLOAD_MAX_FILES = 20
DOCUMENT_UPLOAD_TOKEN_SALT = 'malkia-document-upload-v1'
DOCUMENT_UPLOAD_TOKEN_MAX_AGE = 1800


def _document_upload_content_type(filename):
    content_type, _ = mimetypes.guess_type(filename)
    return content_type or 'application/octet-stream'


def _document_upload_object_key(job, filename):
    valid_name = get_valid_filename(os.path.basename(filename)) or 'document'
    stem, extension = os.path.splitext(valid_name)
    unique_name = f"{uuid.uuid4().hex}_{stem[:80]}{extension.lower()}"
    document = JobDocument(job=job)
    return job_document_upload_path(document, unique_name).replace('\\', '/')


def _store_dossier_documents(request, job, documents):
    doc_type_dict = dict(JobDocument.DOC_TYPES)
    doc_flag_map = {
        'BILL_OF_LADING': 'doc_bl_received',
        'COMMERCIAL_INVOICE': 'doc_invoice_received',
        'PACKING_LIST': 'doc_packing_list_received',
        'TBS_CERT': 'doc_tbs_cert_received',
        'EXPORT_CERT': 'doc_export_cert_received',
    }
    single_slot_types = {
        'TRA_AUTH_SIGNED', 'TBS_SIGNED', 'FORM_C41',
        'BILL_OF_LADING', 'COMMERCIAL_INVOICE', 'PACKING_LIST',
    }
    update_fields = {
        'doc_intake_finalized': True,
        'doc_received_at': timezone.now(),
    }
    if not job.documentation_officer_id:
        update_fields['documentation_officer'] = request.user

    uploaded_count = 0
    with transaction.atomic():
        for item in documents:
            raw_type = item['document_type']
            if raw_type not in doc_type_dict:
                raw_type = 'OTHER'
            raw_title = item['title']
            if not raw_title:
                raw_title = (
                    f"{doc_type_dict[raw_type]} ({item['filename']})"
                    if raw_type != 'OTHER' and raw_type in doc_type_dict
                    else item['filename']
                )

            if raw_type in single_slot_types:
                JobDocument.objects.filter(job=job, document_type=raw_type).delete()

            file_value = item.get('file')
            if file_value is None:
                file_value = item['object_key']
            else:
                file_value = _compress_image_if_needed(file_value)

            JobDocument.objects.create(
                job=job,
                document_type=raw_type,
                title=raw_title,
                file=file_value,
                uploaded_by=request.user,
            )
            uploaded_count += 1
            if raw_type in doc_flag_map:
                update_fields[doc_flag_map[raw_type]] = True

        if uploaded_count == 0:
            raise ValueError('Faili zilizochaguliwa ni tupu (0 KB). Tafadhali chagua faili sahihi.')

        JobShipment.objects.filter(id=job.id).update(**update_fields)

    try:
        log_audit(request, "UPLOAD_DOCUMENT", f"Uploaded {uploaded_count} document(s) to Job {job.job_number}", job=job)
    except Exception:
        pass
    return uploaded_count


def _compress_pdf_if_needed(uploaded_file):
    """Return PDF as-is without CPU-heavy PyMuPDF image rewriting."""
    return uploaded_file


def _compress_image_if_needed(uploaded_file, max_dim=1800, quality=80):
    """
    Compresses oversized image (JPG/PNG/WEBP) or PDF uploads before saving
    to Cloudflare R2 to reduce storage size and speed up viewing.
    """
    if not uploaded_file:
        return uploaded_file
    ext = os.path.splitext(getattr(uploaded_file, 'name', ''))[1].lower()
    if ext == '.pdf':
        return _compress_pdf_if_needed(uploaded_file)
    if ext not in ('.jpg', '.jpeg', '.png', '.webp'):
        return uploaded_file
    if getattr(uploaded_file, 'size', 0) <= 300 * 1024:
        return uploaded_file

    try:
        from io import BytesIO
        from PIL import Image, ImageOps
        from django.core.files.uploadedfile import InMemoryUploadedFile

        uploaded_file.seek(0)
        img = Image.open(uploaded_file)
        img = ImageOps.exif_transpose(img)
        if img.mode in ('RGBA', 'LA', 'P'):
            bg = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            bg.paste(img, mask=img.split()[-1] if 'A' in img.mode else None)
            img = bg
        elif img.mode != 'RGB':
            img = img.convert('RGB')

        img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
        buf = BytesIO()
        img.save(buf, format='JPEG', quality=quality, optimize=True)
        new_size = buf.tell()
        if new_size < uploaded_file.size:
            buf.seek(0)
            base_name = os.path.splitext(uploaded_file.name)[0]
            return InMemoryUploadedFile(
                buf, 'ImageField', f"{base_name}.jpg", 'image/jpeg', new_size, None
            )
    except Exception:
        pass
    try:
        uploaded_file.seek(0)
    except Exception:
        pass
    return uploaded_file


@login_required
def upload_document_action(request, job_id):
    if request.method == 'POST':
        job = get_object_or_404(JobShipment, id=job_id)
        if not user_can_manage_docs(request.user, job):
            messages.error(request, "Ruksa imezuiwa: Ni Afisa Nyaraka (Documentation Officer) au Admin pekee anayeweza kupakia nyaraka.")
            return redirect(f"/jobs/{job_id}/#documentCenter")

        doc_type = request.POST.get('document_type', 'OTHER').strip()
        custom_type_name = request.POST.get('custom_type_name', '').strip()
        title = request.POST.get('title', '').strip()
        notes = request.POST.get('notes', '').strip()

        files = request.FILES.getlist('file')
        if not files and 'file' in request.FILES:
            files = [request.FILES['file']]

        if not files:
            messages.error(request, "No file was selected for upload.")
            return redirect('job_detail', job_id=job_id)

        uploaded_count = 0
        doc_type_dict = dict(JobDocument.DOC_TYPES)

        updated_flags = set()
        for f in files:
            lower_name = f.name.lower()
            effective_doc_type = doc_type

            if effective_doc_type == 'OTHER':
                if 'c41' in lower_name:
                    effective_doc_type = 'FORM_C41'
                elif 'tra' in lower_name and ('auth' in lower_name or 'letter' in lower_name or 'sign' in lower_name):
                    effective_doc_type = 'TRA_AUTH_SIGNED'
                elif 'tbs' in lower_name and ('sign' in lower_name or 'auth' in lower_name or 'letter' in lower_name):
                    effective_doc_type = 'TBS_SIGNED'
                elif 'bl' in lower_name or 'lading' in lower_name:
                    effective_doc_type = 'BILL_OF_LADING'
                elif 'inv' in lower_name:
                    effective_doc_type = 'COMMERCIAL_INVOICE'
                elif 'pack' in lower_name:
                    effective_doc_type = 'PACKING_LIST'
                elif 'tbs' in lower_name and 'cert' in lower_name:
                    effective_doc_type = 'TBS_CERT'
                elif 'export' in lower_name or 'origin' in lower_name:
                    effective_doc_type = 'EXPORT_CERT'

            doc_title = title
            if not doc_title:
                if custom_type_name:
                    doc_title = custom_type_name
                elif effective_doc_type in doc_type_dict and effective_doc_type != 'OTHER':
                    doc_title = f"{doc_type_dict[effective_doc_type]} ({f.name})"
                else:
                    doc_title = f.name
            elif len(files) > 1:
                doc_title = f"{title} - {f.name}"

            f = _compress_image_if_needed(f)
            JobDocument.objects.create(
                job=job,
                document_type=effective_doc_type,
                title=doc_title,
                file=f,
                uploaded_by=request.user,
                notes=notes
            )
            uploaded_count += 1

            doc_flag_map = {
                'BILL_OF_LADING': 'doc_bl_received',
                'COMMERCIAL_INVOICE': 'doc_invoice_received',
                'PACKING_LIST': 'doc_packing_list_received',
                'TBS_CERT': 'doc_tbs_cert_received',
                'EXPORT_CERT': 'doc_export_cert_received',
            }
            if effective_doc_type in doc_flag_map:
                flag = doc_flag_map[effective_doc_type]
                setattr(job, flag, True)
                updated_flags.add(flag)

        if updated_flags:
            job.save(update_fields=list(updated_flags))

        log_audit(request, "UPLOAD_DOCUMENT", f"Uploaded {uploaded_count} document(s) to Job {job.job_number}", job=job)
        messages.success(request, f"{uploaded_count} document(s) uploaded successfully.")

    redirect_url = request.META.get('HTTP_REFERER') or f'/jobs/{job_id}/'
    return redirect(redirect_url)


@login_required
def create_document_upload_urls(request, job_id):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)

    job = get_object_or_404(JobShipment, id=job_id)
    if not user_can_manage_docs(request.user, job):
        return JsonResponse({
            'status': 'error',
            'message': 'Ruksa imezuiwa: Ni Afisa Nyaraka (Documentation Officer) au Admin pekee anayeweza kupakia nyaraka.',
        }, status=403)

    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({'status': 'error', 'message': 'Ombi la upload si sahihi.'}, status=400)

    files = payload.get('files') if isinstance(payload, dict) else None
    if not isinstance(files, list) or not files:
        return JsonResponse({'status': 'error', 'message': 'Hakuna faili zilizochaguliwa.'}, status=400)
    if len(files) > DOCUMENT_UPLOAD_MAX_FILES:
        return JsonResponse({
            'status': 'error',
            'message': f'Unaweza kupakia hadi faili {DOCUMENT_UPLOAD_MAX_FILES} kwa wakati mmoja.',
        }, status=400)

    doc_type_dict = dict(JobDocument.DOC_TYPES)
    prepared = []
    total_size = 0
    for item in files:
        if not isinstance(item, dict):
            return JsonResponse({'status': 'error', 'message': 'Taarifa ya faili si sahihi.'}, status=400)

        filename = str(item.get('name', '')).strip()
        extension = os.path.splitext(filename)[1].lower()
        if not filename or len(filename) > 255 or extension not in DOCUMENT_UPLOAD_EXTENSIONS:
            return JsonResponse({
                'status': 'error',
                'message': 'Chagua faili la PDF, JPG, PNG au WEBP.',
            }, status=400)
        try:
            size = int(item.get('size', 0))
        except (TypeError, ValueError):
            size = 0
        if size <= 0:
            return JsonResponse({'status': 'error', 'message': f'Faili "{filename}" ni tupu (0 B).'}, status=400)

        total_size += size
        if total_size > DOCUMENT_UPLOAD_MAX_BYTES:
            return JsonResponse({
                'status': 'error',
                'message': 'Jumla ya faili ni kubwa kuliko uwezo wa 60 MB.',
            }, status=400)

        raw_type = str(item.get('document_type', 'OTHER')).strip()
        if raw_type not in doc_type_dict:
            raw_type = 'OTHER'
        title = str(item.get('title', '')).strip()[:200]
        if not title:
            title = f"{doc_type_dict[raw_type]} ({filename})" if raw_type != 'OTHER' else filename

        object_key = _document_upload_object_key(job, filename)
        completion_token = signing.dumps({
            'job_id': job.id,
            'object_key': object_key,
            'document_type': raw_type,
            'title': title,
            'filename': filename,
            'size': size,
        }, salt=DOCUMENT_UPLOAD_TOKEN_SALT)
        prepared.append({
            'object_key': object_key,
            'content_type': _document_upload_content_type(filename),
            'completion_token': completion_token,
        })

    from .storage_backends import get_r2_config, generate_presigned_upload_url
    if not get_r2_config().get('is_configured'):
        return JsonResponse({'status': 'fallback', 'message': 'Cloudflare R2 is not configured.'})

    uploads = []
    for item in prepared:
        upload_url = generate_presigned_upload_url(item['object_key'], item['content_type'], DOCUMENT_UPLOAD_TOKEN_MAX_AGE)
        if not upload_url:
            return JsonResponse({'status': 'fallback', 'message': 'Cloudflare R2 is not configured.'})
        uploads.append({
            'upload_url': upload_url,
            'object_key': item['object_key'],
            'content_type': item['content_type'],
            'completion_token': item['completion_token'],
        })

    return JsonResponse({'status': 'ok', 'uploads': uploads})


@login_required
def upload_documents_batch_action(request, job_id):
    """Uploads staged documents through R2 or the VPS, then finalizes the dossier."""
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', '')

    if request.method != 'POST':
        if is_ajax:
            return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)
        return redirect('job_detail', job_id=job_id)

    job = get_object_or_404(JobShipment, id=job_id)
    if not user_can_manage_docs(request.user, job):
        msg = 'Ruksa imezuiwa: Ni Afisa Nyaraka (Documentation Officer) au Admin pekee anayeweza kupakia nyaraka.'
        if is_ajax:
            return JsonResponse({'status': 'error', 'message': msg}, status=403)
        messages.error(request, msg)
        return redirect('job_detail', job_id=job.id)

    if request.content_type == 'application/json':
        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        except (UnicodeDecodeError, json.JSONDecodeError):
            return JsonResponse({'status': 'error', 'message': 'Ombi la kuhifadhi nyaraka si sahihi.'}, status=400)

        entries = payload.get('documents') if isinstance(payload, dict) else None
        if not isinstance(entries, list) or not entries or len(entries) > DOCUMENT_UPLOAD_MAX_FILES:
            return JsonResponse({'status': 'error', 'message': 'Hakuna nyaraka sahihi za kuhifadhi.'}, status=400)

        documents = []
        for entry in entries:
            if not isinstance(entry, dict):
                return JsonResponse({'status': 'error', 'message': 'Taarifa ya nyaraka si sahihi.'}, status=400)
            object_key = str(entry.get('object_key', '')).strip()
            token = str(entry.get('completion_token', '')).strip()
            if not object_key or not token:
                return JsonResponse({'status': 'error', 'message': 'Uthibitisho wa upload haukamilika.'}, status=400)
            try:
                data = signing.loads(token, salt=DOCUMENT_UPLOAD_TOKEN_SALT, max_age=DOCUMENT_UPLOAD_TOKEN_MAX_AGE)
            except signing.BadSignature:
                return JsonResponse({'status': 'error', 'message': 'Muda wa upload umeisha au link si halali.'}, status=400)
            if not isinstance(data, dict) or data.get('job_id') != job.id or data.get('object_key') != object_key:
                return JsonResponse({'status': 'error', 'message': 'Nyaraka hii si ya faili hili.'}, status=400)
            documents.append({
                'object_key': object_key,
                'document_type': data.get('document_type', 'OTHER'),
                'title': data.get('title', ''),
                'filename': data.get('filename', ''),
            })
    else:
        files = request.FILES.getlist('files')
        doc_types = request.POST.getlist('document_types')
        titles = request.POST.getlist('titles')
        if not files:
            msg = 'Hakuna faili zilizochaguliwa.'
            if is_ajax:
                return JsonResponse({'status': 'error', 'message': msg}, status=400)
            messages.warning(request, msg)
            return redirect(f"/jobs/{job.id}/#documentCenter")

        doc_type_dict = dict(JobDocument.DOC_TYPES)
        documents = []
        for idx, uploaded_file in enumerate(files):
            if getattr(uploaded_file, 'size', 0) == 0:
                continue
            raw_type = doc_types[idx].strip() if idx < len(doc_types) else 'OTHER'
            if raw_type not in doc_type_dict:
                raw_type = 'OTHER'
            raw_title = titles[idx].strip() if idx < len(titles) else ''
            documents.append({
                'file': uploaded_file,
                'document_type': raw_type,
                'title': raw_title,
                'filename': uploaded_file.name,
            })

    try:
        uploaded_count = _store_dossier_documents(request, job, documents)
    except ValueError as exc:
        if is_ajax:
            return JsonResponse({'status': 'error', 'message': str(exc)}, status=400)
        messages.warning(request, str(exc))
        return redirect(f"/jobs/{job.id}/#documentCenter")
    except Exception:
        msg = 'Hitilafu ya server wakati wa kuhifadhi faili.'
        if is_ajax:
            return JsonResponse({'status': 'error', 'message': msg}, status=500)
        messages.error(request, msg)
        return redirect(f"/jobs/{job.id}/#documentCenter")

    if is_ajax:
        return JsonResponse({
            'status': 'ok',
            'uploaded': uploaded_count,
            'message': f"Nyaraka {uploaded_count} zimepakiwa na kuhifadhiwa kikamilifu!",
        })

    messages.success(request, f"Nyaraka {uploaded_count} zimepakiwa na kuhifadhiwa kikamilifu!")
    return redirect(f"/jobs/{job.id}/#documentCenter")


















@login_required

def view_job_document_view(request, document_id):

    doc = get_object_or_404(JobDocument.objects.select_related('job'), id=document_id)

    try:

        f = doc.file.open('rb')

        content_type, _ = mimetypes.guess_type(doc.file.name)

        if not content_type:

            content_type = 'application/pdf' if doc.file.name.lower().endswith('.pdf') else 'application/octet-stream'

        filename = os.path.basename(doc.file.name)

        response = FileResponse(f, content_type=content_type)

        response['Content-Disposition'] = f'inline; filename="{filename}"'

        return response

    except Exception as e:

        messages.error(request, f"Error opening document: {str(e)}")

        return redirect('job_detail', job_id=doc.job_id)





TANCIS_DOC_CODES = {
    'COMMERCIAL_INVOICE': '100',
    'BILL_OF_LADING': '101',
    'PACKING_LIST': '102',
    'FORM_C41': '115',
    'TRA_AUTH_SIGNED': '137',
    'TBS_SIGNED': '147',
}


def _get_tancis_filename(doc):
    ext = os.path.splitext(doc.file.name)[1] or '.pdf'
    code = TANCIS_DOC_CODES.get(doc.document_type)
    if code:
        return f"{code}{ext}"
    raw_title = (getattr(doc, 'title', '') or '').strip()
    if raw_title:
        import re
        clean_title = re.sub(r'[\\/:*?"<>|]+', '_', raw_title)
        clean_title = re.sub(r'\s+', '_', clean_title).strip('_')
        if clean_title:
            if clean_title.lower().endswith(ext.lower()):
                return clean_title
            return f"{clean_title}{ext}"
    doc_type_clean = (
        doc.get_document_type_display()
        .replace(' ', '_')
        .replace('/', '_')
        .replace('(', '')
        .replace(')', '')
    )
    return f"{doc_type_clean}{ext}"


@login_required
def download_job_document_view(request, document_id):

    doc = get_object_or_404(JobDocument.objects.select_related('job'), id=document_id)

    try:

        f = doc.file.open('rb')

        content_type, _ = mimetypes.guess_type(doc.file.name)

        if not content_type:

            content_type = 'application/octet-stream'

        clean_filename = _get_tancis_filename(doc)

        response = FileResponse(f, content_type=content_type)

        response['Content-Disposition'] = f'attachment; filename="{clean_filename}"'

        return response

    except Exception as e:

        messages.error(request, f"Error downloading document: {str(e)}")

        return redirect('job_detail', job_id=doc.job_id)





@login_required

def download_all_job_documents_zip_view(request, job_id):

    job = get_object_or_404(JobShipment, id=job_id)

    docs = job.documents.all()

    if not docs.exists():

        messages.warning(request, "Hapana nyaraka zilizopakiwa kwenye file hili bado.")

        return redirect('job_detail', job_id=job.id)



    zip_buffer = io.BytesIO()
    bl_slug = (job.bl_number or job.job_number).replace('/', '_').replace(' ', '')
    seen_names = {}

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for doc in docs:
            try:
                base_name = _get_tancis_filename(doc)
                if base_name in seen_names:
                    seen_names[base_name] += 1
                    stem, ext = os.path.splitext(base_name)
                    arc_name = f"BL_{bl_slug}/{stem}_{seen_names[base_name]}{ext}"
                else:
                    seen_names[base_name] = 1
                    arc_name = f"BL_{bl_slug}/{base_name}"

                with doc.file.open('rb') as f:
                    file_content = f.read()

                zip_file.writestr(arc_name, file_content)
            except Exception as e:
                print(f"[ZIP Pack Error on doc {doc.id}] {e}")

    zip_buffer.seek(0)
    zip_filename = f"TANCIS_Documents_BL_{bl_slug}.zip"



    response = HttpResponse(zip_buffer.getvalue(), content_type='application/zip')

    response['Content-Disposition'] = f'attachment; filename="{zip_filename}"'

    return response





def customers_list_view(request):



    from django.db.models import Q



    q = request.GET.get('q', '').strip()



    customers = Customer.objects.all().prefetch_related('shipments', 'invoices').order_by('company_name')



    if q:



        customers = customers.filter(



            Q(company_name__icontains=q) |



            Q(contact_person__icontains=q) |



            Q(phone__icontains=q) |



            Q(email__icontains=q) |



            Q(tin_number__icontains=q) |



            Q(id_number__icontains=q)



        )



    context = {



        'customers': customers,



        'search_q': q,



        'total_clients_count': Customer.objects.count(),



    }



    return render(request, 'core/customers_list.html', context)











@login_required



@role_required([UserRole.DOC_OFFICER, UserRole.OPERATIONS_MGR, UserRole.FINANCE, UserRole.ADMIN])



def customer_create_action(request):



    if request.method == 'POST':



        name = request.POST.get('company_name', '').strip()



        contact = request.POST.get('contact_person', '').strip() or name



        phone = request.POST.get('phone', '').strip()



        email = request.POST.get('email', '').strip()



        tin = request.POST.get('tin_number', '').strip()



        id_num = request.POST.get('id_number', '').strip()



        vrn = request.POST.get('vrn_number', '').strip()



        addr = request.POST.get('physical_address', '').strip()



        cred = Decimal(request.POST.get('credit_limit', '0') or '0')



        terms = request.POST.get('payment_terms', 'IMMEDIATE')







        cust = Customer.objects.create(



            company_name=name,



            contact_person=contact,



            phone=phone,



            email=email,



            tin_number=tin,



            id_number=id_num,



            vrn_number=vrn,



            physical_address=addr,



            credit_limit=cred,



            payment_terms=terms



        )



        log_audit(request, "CREATE_CUSTOMER", f"Created client {cust.company_name} (TIN: {tin}, ID: {id_num})")



        messages.success(request, f"Client '{cust.company_name}' registered successfully!")



    return redirect('customers_list')











# ==============================================================================



# 7. FIELD AGENT / WHARFINGER MODULE (PORT OFFICER)



# ==============================================================================







@login_required



@role_required([UserRole.PORT_OFFICER, UserRole.DRIVER, UserRole.OPERATIONS_MGR, UserRole.CEO, UserRole.ADMIN])



def field_today_jobs_view(request):



    role = get_user_role(request.user)



    



    # Base query: Active & Delayed shipments



    jobs_qs = JobShipment.objects.filter(



        status__in=['ACTIVE', 'DELAYED']



    ).select_related('customer', 'port_officer', 'driver').order_by('-updated_at')







    # Tabs: 'my' (assigned to this officer), 'port_stages' (stages 5, 8, 10), 'delayed', 'all'



    filter_tab = request.GET.get('tab', 'my' if role in [UserRole.PORT_OFFICER, UserRole.DRIVER] else 'all')



    search_q = request.GET.get('q', '').strip()







    if filter_tab == 'my':



        if role == UserRole.DRIVER:



            jobs = jobs_qs.filter(driver=request.user)



        else:



            jobs = jobs_qs.filter(Q(port_officer=request.user) | Q(port_officer__isnull=True))



    elif filter_tab == 'port_stages':



        jobs = jobs_qs.filter(current_stage_number__in=[4, 5, 6, 7, 8])



    elif filter_tab == 'delayed':



        jobs = jobs_qs.filter(status='DELAYED')



    else:



        jobs = jobs_qs







    if search_q:



        jobs = jobs.filter(



            Q(job_number__icontains=search_q) |



            Q(container_numbers__icontains=search_q) |



            Q(bl_number__icontains=search_q) |



            Q(customer__company_name__icontains=search_q) |



            Q(vessel_name__icontains=search_q)



        )







    # KPI counts for today



    if role == UserRole.DRIVER:



        my_jobs_count = jobs_qs.filter(driver=request.user).count()



    else:



        my_jobs_count = jobs_qs.filter(Q(port_officer=request.user) | Q(port_officer__isnull=True)).count()



        



    verification_count = jobs_qs.filter(current_stage_number=5).count()



    gate_loading_count = jobs_qs.filter(current_stage_number__in=[6, 7, 8]).count()



    open_issues_count = FieldIssue.objects.filter(status='OPEN').count()







    context = {



        'jobs': jobs,



        'filter_tab': filter_tab,



        'search_q': search_q,



        'my_jobs_count': my_jobs_count,



        'verification_count': verification_count,



        'gate_loading_count': gate_loading_count,



        'open_issues_count': open_issues_count,



        'today': timezone.now().date(),



    }



    return render(request, 'core/field_today_jobs.html', context)











@login_required



@role_required([UserRole.PORT_OFFICER, UserRole.DRIVER, UserRole.OPERATIONS_MGR, UserRole.CEO, UserRole.ADMIN])



def field_updates_view(request):



    role = get_user_role(request.user)



    



    if role == UserRole.DRIVER:



        jobs = JobShipment.objects.filter(



            status__in=['ACTIVE', 'DELAYED'],



            driver=request.user



        ).select_related('customer', 'port_officer', 'driver').order_by('-updated_at')



    else:



        jobs = JobShipment.objects.filter(



            status__in=['ACTIVE', 'DELAYED']



        ).select_related('customer', 'port_officer', 'driver').order_by('-updated_at')







    selected_job_id = request.GET.get('job_id')



    selected_job = None



    if selected_job_id:



        selected_job = jobs.filter(id=selected_job_id).first()



    if not selected_job and jobs.exists():



        selected_job = jobs.first()







    recent_logs = []

    job_docs = []

    port_vouchers = []

    verification_done = False

    unpaid_port_bills = []

    gate_exit_allowed = True

    gate_exit_block_reason = ""



    if selected_job:

        recent_logs = selected_job.audit_logs.all().select_related('user').order_by('-timestamp')[:8]

        job_docs = selected_job.documents.all().order_by('-uploaded_at')[:6]

        port_vouchers = selected_job.expenses.exclude(category=ExpenseCategory.CUSTOMS_DUTY).order_by('-requested_at')



        verification_done = bool(

            selected_job.current_stage_number > 5 or

            selected_job.stages.filter(stage_number=5, status='COMPLETED').exists() or

            selected_job.vehicle_inspection_done

        )



        unpaid_port_bills = list(selected_job.expenses.filter(

            category__in=[ExpenseCategory.SHIPPING_LINE, ExpenseCategory.PORT_CHARGES],

            is_paid=False

        ).exclude(approval_status='REJECTED'))



        if not verification_done:

            gate_exit_allowed = False

            gate_exit_block_reason = "Physical Verification must be completed first."

        elif unpaid_port_bills:

            gate_exit_allowed = False

            gate_exit_block_reason = "Port bills (D/O or Port Charges) are awaiting Finance review and CEO payout."



    context = {

        'jobs': jobs,

        'selected_job': selected_job,

        'recent_logs': recent_logs,

        'job_docs': job_docs,

        'port_vouchers': port_vouchers,

        'verification_done': verification_done,

        'unpaid_port_bills': unpaid_port_bills,

        'gate_exit_allowed': gate_exit_allowed,

        'gate_exit_block_reason': gate_exit_block_reason,

    }

    return render(request, 'core/field_updates.html', context)











@login_required



@role_required([UserRole.PORT_OFFICER, UserRole.DRIVER, UserRole.OPERATIONS_MGR, UserRole.ADMIN, UserRole.CEO])



def field_update_action(request, job_id):



    if request.method == 'POST':



        job = get_object_or_404(JobShipment, id=job_id)



        update_type = request.POST.get('update_type')



        remarks = request.POST.get('remarks', '').strip()



        evidence_file = request.FILES.get('evidence_file')







        current_stage = job.stages.filter(stage_number=job.current_stage_number).first()







        # 0. SEND CONTROL NUMBER OR FIELD EXPENSE TO FINANCE (D/O, Port Charges, Fuel/Mafuta, Transport, Other)

        if update_type == 'SEND_CONTROL_NUMBER':

            category = request.POST.get('payment_category', 'SHIPPING_LINE')

            control_num = request.POST.get('control_number', '').strip()

            beneficiary = request.POST.get('beneficiary_name', '').strip()

            amount_raw = request.POST.get('amount', '0').replace(',', '').strip()

            slip_file = request.FILES.get('slip_photo') or evidence_file



            try:

                amt = Decimal(amount_raw)

            except Exception:

                amt = Decimal('0.00')



            v_num = ExpenseVoucher.generate_next_voucher_number()

            req_role = ExpenseVoucher.determine_required_role(amt)

            cat_labels = {

                'SHIPPING_LINE': 'Shipping Line D/O',

                'PORT_CHARGES': 'ICD Port Charges & Wharfage',

                'FUEL': 'Vehicle Fuel / Mafuta ya Gari',

                'TRANSPORT': 'Driver / Transport Allowance',

                'PORT_HANDLING': 'Port Handling & Tally',

                'OTHER': 'Other Field Expense',

            }

            cat_label = cat_labels.get(category, 'Operational Field Expense')

            ref_info = f" | Control/Ref: {control_num}" if control_num else ""



            voucher = ExpenseVoucher.objects.create(

                voucher_number=v_num,

                job=job,

                category=category,

                amount=amt,

                control_number=control_num,

                beneficiary_name=beneficiary,

                description=f"{cat_label} for {job.cargo_description or job.job_number} ({job.chassis_number}). Payee/Purpose: {beneficiary}{ref_info}",

                supporting_document=slip_file,

                requester=request.user,

                required_role=req_role,

                approval_status='REQUESTED',

            )



            if slip_file:

                doc_type_map = {

                    'PORT_CHARGES': 'PORT_INVOICE',

                    'SHIPPING_LINE': 'DELIVERY_ORDER',

                }

                JobDocument.objects.create(

                    job=job,

                    stage=current_stage,

                    document_type=doc_type_map.get(category, 'OTHER'),

                    title=f"{cat_label} Slip - {control_num or v_num}",

                    file=slip_file,

                    uploaded_by=request.user,

                    notes=f"Category: {cat_label} | Ref: {control_num or v_num} | Amount: TSh {amt:,.2f}"

                )



            log_audit(request, "PORT_EXPENSE_DISPATCH", f"Sent {cat_label} request (TSh {amt:,.2f}) to Finance. Ref: {control_num or v_num}. Voucher: {v_num}", job=job)

            messages.success(request, f"Payment request for {cat_label} (TSh {amt:,.2f}) has been submitted to Finance.")

            return redirect(f"/field/updates/?job_id={job.id}")







        # 1. TRA PHYSICAL VERIFICATION

        elif update_type in ['VERIFICATION', 'TRA_VERIFICATION']:

            verification_outcome = request.POST.get('verification_outcome', 'PASSED')

            findings = request.POST.get('findings', '').strip()

            is_passed = 'PASS' in verification_outcome.upper() or verification_outcome == 'PASSED'



            if is_passed:

                now = timezone.now()

                note = f"TRA Physical Verification: PASSED / Verified. {findings} {remarks}".strip()

                if evidence_file:

                    JobDocument.objects.create(

                        job=job,

                        stage=current_stage,

                        document_type='OTHER',

                        title=f"TRA Verification Stamp/Slip - {job.chassis_number or job.job_number}",

                        file=evidence_file,

                        uploaded_by=request.user,

                        notes=note

                    )



                for st in job.stages.filter(stage_number__lte=5):

                    if st.status != 'COMPLETED':

                        st.status = 'COMPLETED'

                        st.completed_at = now

                        st.completed_by = request.user

                        st.remarks = note

                        st.save()



                if job.current_stage_number <= 5:

                    job.current_stage_number = 6

                if job.tra_status != 'ACCEPTED':

                    job.tra_status = 'ACCEPTED'

                job.status = 'ACTIVE'

                job.save()



                next_stage = job.stages.filter(stage_number=6).first()

                if next_stage and next_stage.status != 'COMPLETED':

                    next_stage.status = 'IN_PROGRESS'

                    next_stage.started_at = now

                    next_stage.save()



                try:

                    from .email_service import send_stage_update_email

                    send_stage_update_email(job, 6, extra_note=note)

                except Exception as e:

                    print(f"[Email Notification Error] {e}")



                log_audit(request, "PHYSICAL_VERIFICATION_PASSED", note, job=job)

                log_audit(request, "FIELD_VERIFICATION", note, job=job)

                messages.success(request, f"✅ TRA Verification imekamilika kwa {job.chassis_number or job.job_number}! Sasa unaweza ku-verify Gate Pass & Dispatch.")



            else:



                note = f"TRA Physical Verification: OBJECTION / QUERY. Sababu: {findings} {remarks}".strip()



                job.tra_status = 'OBJECTION'



                job.tra_objection_notes = note



                job.tra_objection_at = timezone.now()



                job.status = 'DELAYED'



                job.save()



                log_audit(request, "TRA_OBJECTION", note, job=job)



                messages.warning(request, f"⚠️ Customs objection recorded for vehicle {job.chassis_number or job.job_number}. Office team notified.")







        # 2. VEHICLE CONDITION INSPECTION & GATE EXIT (STAGE 7)

        elif update_type == 'VEHICLE_INSPECTION':

            has_scratches = request.POST.get('has_scratches') == 'YES'

            radio_present = request.POST.get('radio_present', 'YES') == 'YES'

            spare_wheel_present = request.POST.get('spare_wheel_present', 'YES') == 'YES'

            jack_tools_present = request.POST.get('jack_tools_present', 'YES') == 'YES'

            mirrors_ok = request.POST.get('mirrors_ok', 'YES') == 'YES'

            battery_ok = request.POST.get('battery_ok', 'YES') == 'YES'

            notes = request.POST.get('condition_notes', '').strip()

            gate_pass_num = request.POST.get('gate_pass_number', '').strip()

            driver_name = request.POST.get('driver_name', '').strip() or job.vehicle_driver_name or (request.user.get_full_name() or request.user.username)



            now = timezone.now()

            job.vehicle_inspection_done = True

            job.vehicle_has_scratches = has_scratches

            job.vehicle_radio_present = radio_present

            job.vehicle_spare_wheel_present = spare_wheel_present

            job.vehicle_jack_tools_present = jack_tools_present

            job.vehicle_mirrors_ok = mirrors_ok

            job.vehicle_battery_ok = battery_ok

            job.vehicle_inspection_notes = notes

            job.vehicle_inspection_at = now

            job.vehicle_inspection_by = request.user



            if gate_pass_num:

                job.gate_pass_number = gate_pass_num

            elif not job.gate_pass_number:

                job.gate_pass_number = f"GP-{job.port_invoice_number}" if job.port_invoice_number else f"GP-{job.id:04d}"



            job.vehicle_driver_name = driver_name

            job.vehicle_dispatched_to_office = True

            job.vehicle_dispatched_at = now



            # Complete Stages <= 7 (Gate Exit & Simple Verify) and advance to Stage 8 (Malkia Yard Arrival)

            for st in job.stages.filter(stage_number__lte=7):

                if st.status != 'COMPLETED':

                    st.status = 'COMPLETED'

                    st.completed_at = now

                    st.completed_by = request.user

                    st.responsible_officer = request.user

                    st.remarks = f"Gate Pass #{job.gate_pass_number} | Driver: {driver_name} | Verified. {notes}".strip()

                    st.save()

            st7 = job.stages.filter(stage_number=7).first()



            if job.current_stage_number <= 7:

                job.current_stage_number = 8

                job.status = 'ACTIVE'

                st8 = job.stages.filter(stage_number=8).first()

                if st8:

                    st8.status = 'IN_PROGRESS'

                    st8.started_at = now

                    st8.save()



            job.save()

            try:

                auto_compile_customer_final_bill(job)

            except Exception:

                pass



            photos = request.FILES.getlist('photos')

            if evidence_file and evidence_file not in photos:

                photos.append(evidence_file)



            for p in photos:

                JobDocument.objects.create(

                    job=job,

                    stage=st7 or current_stage,

                    document_type='GATE_PASS',

                    title=f"Vehicle Gate Exit & Inspection Photo - {job.chassis_number or job.job_number}",

                    file=p,

                    uploaded_by=request.user,

                    notes=f"Gate Pass: {job.gate_pass_number} | Scratches: {has_scratches}, Radio: {radio_present}, Spare: {spare_wheel_present}, Jack: {jack_tools_present}, Mirrors: {mirrors_ok}"

                )



            summary = f"Gate Exit & Simple Vehicle Verify imekamilika (Gate Pass #{job.gate_pass_number}, Dereva: {driver_name}). {notes}".strip()

            log_audit(request, "VEHICLE_INSPECTION", summary, job=job)

            log_audit(request, "GATE_EXIT_RECORDED", summary, job=job)

            messages.success(request, f"✅ Gate Exit & Vehicle Inspection completed for {job.chassis_number or job.job_number} (Gate Pass #{job.gate_pass_number})! Vehicle is now en route to Malkia Yard (Stage 8).")



        # 3. DISPATCH FROM PORT / ICD TO OFFICE YARD (STAGE 7 -> STAGE 8)

        elif update_type in ['DISPATCH_OFFICE', 'PORT_EXIT', 'GATE', 'LOADING']:

            now = timezone.now()

            driver_name = request.POST.get('driver_name', '').strip() or job.vehicle_driver_name or (request.user.get_full_name() or request.user.username)

            gate_pass_num = request.POST.get('gate_pass_number', '').strip()



            job.vehicle_inspection_done = True

            job.vehicle_dispatched_to_office = True

            job.vehicle_dispatched_at = now

            job.vehicle_driver_name = driver_name

            if gate_pass_num:

                job.gate_pass_number = gate_pass_num

            elif not job.gate_pass_number:

                job.gate_pass_number = f"GP-{job.port_invoice_number}" if job.port_invoice_number else f"GP-{job.id:04d}"



            st7 = job.stages.filter(stage_number=7).first()

            if st7:

                st7.status = 'COMPLETED'

                st7.completed_at = now

                st7.completed_by = request.user

                st7.responsible_officer = request.user

                st7.remarks = f"Gari limetoka bandarini/ICD (Gate Pass #{job.gate_pass_number}) kwa dereva: {driver_name} {remarks}".strip()

                st7.save()



            if job.current_stage_number <= 7 or job.current_stage_number in [9, 10]:

                job.current_stage_number = 8

                job.status = 'ACTIVE'

                st8 = job.stages.filter(stage_number=8).first()

                if st8:

                    st8.status = 'IN_PROGRESS'

                    st8.started_at = now

                    st8.save()



            job.save()

            try:

                auto_compile_customer_final_bill(job)

            except Exception:

                pass



            note = f"Gari {job.chassis_number or job.job_number} limetoka bandarini/ICD (Gate Pass #{job.gate_pass_number}). Dereva wa ofisi: {driver_name}. Liko njiani kuelekea Yard ya Malkia."

            log_audit(request, "GATE_EXIT_RECORDED", note, job=job)

            log_audit(request, "VEHICLE_DISPATCH", note, job=job)

            messages.success(request, f"🚗 Vehicle {job.chassis_number or job.job_number} (Gate Pass #{job.gate_pass_number}) exited port/ICD and is en route to Malkia Yard (Stage 8).")



        # 4. ARRIVED AT OFFICE YARD (STAGE 8 -> STAGE 9)

        elif update_type == 'ARRIVED_OFFICE':

            now = timezone.now()

            job.vehicle_arrived_at_office = True

            job.vehicle_arrived_at = now



            st8 = job.stages.filter(stage_number=8).first()

            if st8:

                st8.status = 'COMPLETED'

                st8.completed_at = now

                st8.completed_by = request.user

                st8.responsible_officer = request.user

                st8.remarks = f"Vehicle arrived safely at Malkia Central Yard."

                st8.save()



            if job.current_stage_number <= 8 or job.current_stage_number == 10:

                job.current_stage_number = 9

                st9 = job.stages.filter(stage_number=9).first()

                if st9:

                    st9.status = 'IN_PROGRESS'

                    st9.started_at = now

                    st9.save()



            job.status = 'ACTIVE'

            job.save()

            try:

                auto_compile_customer_final_bill(job)

            except Exception:

                pass



            # Send Dual Notification #3 (Email via Resend + SMS via NextSMS) to customer immediately upon Yard Arrival!

            notif_res = {'email_ok': False, 'sms_ok': False}

            try:

                from .email_service import notify_client_milestone

                notif_res = notify_client_milestone(

                    job,

                    'PORT_EXIT_YARD_ARRIVAL',

                    extra_note=f"Mzigo/Gari lako limetoka bandarini (Gate Pass: {job.gate_pass_number or 'Issued'}) na kuwasili salama Malkia Central Yard."

                )

            except Exception as e:

                print(f"[Yard Arrival Notification Error] {e}")



            if job.clearance_mode == 'BOND':

                note = f"Gari {job.chassis_number or job.job_number} limepokelewa Yard ya Malkia kama IN-BOND. Ujumbe (Email & SMS) umetumwa kwa mteja."

                log_audit(request, "YARD_ARRIVAL_RECORDED", note, job=job)

                log_audit(request, "VEHICLE_ARRIVED_BOND", note, job=job)

                messages.info(request, f"📍 Vehicle arrived at Malkia Yard (IN-BOND)! Customer notified via Email & SMS.")

            else:

                note = f"Gari {job.chassis_number or job.job_number} limefika Yard ya Malkia. Ujumbe (Email & SMS) umetumwa kwa mteja kuja kukabidhiwa gari."

                log_audit(request, "YARD_ARRIVAL_RECORDED", note, job=job)

                log_audit(request, "VEHICLE_ARRIVED_YARD", note, job=job)

                messages.success(request, f"📍 Vehicle arrived safely at Malkia Yard! Mteja ametumiwa ujumbe wa Email na SMS moja kwa moja.")



        # 5. HANDOVER / DELIVERY TO CUSTOMER (STAGE 9 COMPLETED)

        elif update_type == 'DELIVERY':

            now = timezone.now()

            received_by = request.POST.get('received_by_name', '').strip()

            pod_file = request.FILES.get('pod_file')

            note = f"Delivery Complete. Consignee: {received_by}. {remarks}"



            st9 = job.stages.filter(stage_number=9).first()

            if pod_file:

                job.proof_of_delivery_image = pod_file

                JobDocument.objects.create(

                    job=job,

                    stage=st9 or current_stage,

                    document_type='OTHER',

                    title=f"Signed Handover Note - {job.job_number}",

                    file=pod_file,

                    uploaded_by=request.user,

                    notes=f"Handover to {received_by}"

                )



            for s_num in [8, 9]:

                st_obj = job.stages.filter(stage_number=s_num).first()

                if st_obj and st_obj.status != 'COMPLETED':

                    st_obj.status = 'COMPLETED'

                    st_obj.completed_at = now

                    st_obj.completed_by = request.user

                    st_obj.responsible_officer = request.user

                    st_obj.remarks = note

                    st_obj.save()



            job.current_stage_number = 9

            job.status = 'COMPLETED'

            job.delivered_date = now

            job.received_by_name = received_by

            job.save()



            try:

                from .email_service import send_stage_update_email

                send_stage_update_email(job, 9, extra_note=f"Gari limekabidhiwa salama kwa {received_by}.")

            except Exception as e:

                print(f"[Email Notification Error] {e}")



            log_audit(request, "FIELD_DELIVERY", note, job=job)

            messages.success(request, f"Vehicle {job.job_number} officially handed over to client ({received_by})!")



        return redirect(f"/field/updates/?job_id={job.id}")



    return redirect('field_updates')











@login_required



@role_required([UserRole.PORT_OFFICER, UserRole.OPERATIONS_MGR, UserRole.CEO, UserRole.ADMIN])



def field_issues_view(request):



    status_filter = request.GET.get('status', 'ALL')



    job_filter = request.GET.get('job_id')







    issues = FieldIssue.objects.all().select_related('job', 'reported_by').order_by('-created_at')







    if status_filter in ['OPEN', 'ACTION_TAKEN', 'RESOLVED']:



        issues = issues.filter(status=status_filter)



    



    if job_filter:



        issues = issues.filter(job_id=job_filter)







    active_jobs = JobShipment.objects.filter(status__in=['ACTIVE', 'DELAYED']).order_by('-created_at')







    open_count = FieldIssue.objects.filter(status='OPEN').count()



    action_taken_count = FieldIssue.objects.filter(status='ACTION_TAKEN').count()



    resolved_count = FieldIssue.objects.filter(status='RESOLVED').count()







    context = {



        'issues': issues,



        'active_jobs': active_jobs,



        'status_filter': status_filter,



        'selected_job_id': int(job_filter) if job_filter else None,



        'open_count': open_count,



        'action_taken_count': action_taken_count,



        'resolved_count': resolved_count,



    }



    return render(request, 'core/field_issues.html', context)











@login_required



@role_required([UserRole.PORT_OFFICER, UserRole.OPERATIONS_MGR])



def field_issue_create_action(request):



    if request.method == 'POST':



        job_id = request.POST.get('job_id')



        issue_type = request.POST.get('issue_type', 'PORT_DELAY')



        description = request.POST.get('description', '').strip()



        action_taken = request.POST.get('action_taken', '').strip()



        photo = request.FILES.get('evidence_photo')







        job = get_object_or_404(JobShipment, id=job_id)







        issue = FieldIssue.objects.create(



            job=job,



            issue_type=issue_type,



            description=description,



            action_taken=action_taken,



            evidence_photo=photo,



            reported_by=request.user,



            status='OPEN'



        )







        job.status = 'DELAYED'



        job.save()







        log_audit(



            request,



            "REPORT_FIELD_ISSUE",



            f"Field Issue logged on {job.job_number}: {issue.get_issue_type_display()} - {description[:100]}",



            job=job



        )



        messages.warning(request, f"Port challenge logged for {job.job_number}. Operations team alerted!")



        return redirect('field_issues')



    return redirect('field_issues')











@login_required



@role_required([UserRole.PORT_OFFICER, UserRole.OPERATIONS_MGR])



def field_issue_resolve_action(request, issue_id):



    if request.method == 'POST':



        issue = get_object_or_404(FieldIssue, id=issue_id)



        new_status = request.POST.get('status', 'RESOLVED')



        action_note = request.POST.get('action_taken', '').strip()







        if action_note:



            ts = timezone.now().strftime('%d/%m %H:%M')



            if issue.action_taken:



                issue.action_taken += f"\n[{ts}] {action_note}"



            else:



                issue.action_taken = f"[{ts}] {action_note}"







        issue.status = new_status



        if new_status == 'RESOLVED':



            issue.resolved_at = timezone.now()



            # If no other open issues on this job, restore status to ACTIVE



            job = issue.job



            other_open = FieldIssue.objects.filter(job=job, status='OPEN').exclude(id=issue.id).exists()



            if not other_open and job.status == 'DELAYED':



                job.status = 'ACTIVE'



                job.save()







        issue.save()







        log_audit(



            request,



            "RESOLVE_FIELD_ISSUE",



            f"Field Issue #{issue.id} on {issue.job.job_number} updated to {issue.get_status_display()}.",



            job=issue.job



        )



        messages.success(request, f"Issue #{issue.id} updated to {issue.get_status_display()} successfully!")



        return redirect('field_issues')



    return redirect('field_issues')











# Backwards compatibility alias



field_mobile_view = field_today_jobs_view











# ==============================================================================



# 8. LOGISTICS / DISPATCH OFFICER MODULE (EXACTLY 4 BUTTONS ACCORDING TO SPEC)



# ==============================================================================







@login_required



@role_required([UserRole.DISPATCH_OFFICER, UserRole.OPERATIONS_MGR, UserRole.CEO, UserRole.ADMIN])



def logistics_dashboard_view(request):



    """



    1. Dispatch Dashboard



    - Jobs ready for dispatch



    - Vehicles available



    - Vehicles in transit



    - Deliveries today



    - Delayed deliveries



    """



    jobs_ready_for_dispatch = JobShipment.objects.filter(



        status__in=['ACTIVE', 'DELAYED'],



        current_stage_number__in=[9, 10]



    ).count()







    vehicles_available = FleetVehicle.objects.filter(current_status='AVAILABLE').count()



    vehicles_in_transit = FleetVehicle.objects.filter(current_status='IN_TRANSIT').count()







    today_date = timezone.now().date()



    deliveries_today = JobShipment.objects.filter(



        delivered_date__date=today_date



    ).count()







    delayed_deliveries = JobShipment.objects.filter(



        status='DELAYED'



    ).count()







    active_dispatches = JobShipment.objects.filter(



        status__in=['ACTIVE', 'DELAYED'],



        current_stage_number__gte=9



    ).select_related('customer', 'driver', 'port_officer').order_by('-updated_at')[:10]







    fleet_summary = FleetVehicle.objects.all().select_related('assigned_driver')[:6]







    context = {



        'jobs_ready_for_dispatch': jobs_ready_for_dispatch,



        'vehicles_available': vehicles_available,



        'vehicles_in_transit': vehicles_in_transit,



        'deliveries_today': deliveries_today,



        'delayed_deliveries': delayed_deliveries,



        'active_dispatches': active_dispatches,



        'fleet_summary': fleet_summary,



        'today': today_date,



    }



    return render(request, 'core/logistics_dashboard.html', context)











@login_required



@role_required([UserRole.DISPATCH_OFFICER, UserRole.OPERATIONS_MGR, UserRole.CEO, UserRole.ADMIN])



def logistics_jobs_view(request):



    """



    2. Dispatch Jobs



    - Assign vehicle per job or per individual container



    - Assign driver



    - Destination



    - Multi-container haulage allocation



    """



    tab = request.GET.get('tab', 'all')



    search_q = request.GET.get('q', '').strip()







    jobs_qs = JobShipment.objects.filter(



        status__in=['ACTIVE', 'DELAYED']



    ).select_related('customer', 'driver', 'port_officer').prefetch_related('containers', 'containers__assigned_driver').order_by('-updated_at')







    if tab == 'ready':



        jobs = jobs_qs.filter(Q(truck_number='') | Q(truck_number__isnull=True))



    elif tab == 'assigned':



        jobs = jobs_qs.filter(~Q(truck_number='') & Q(current_stage_number__lte=10))



    elif tab == 'in_transit':



        jobs = jobs_qs.filter(current_stage_number=11)



    else:



        jobs = jobs_qs







    if search_q:



        jobs = jobs.filter(



            Q(job_number__icontains=search_q) |



            Q(container_numbers__icontains=search_q) |



            Q(truck_number__icontains=search_q) |



            Q(final_destination__icontains=search_q) |



            Q(customer__company_name__icontains=search_q)



        )







    available_vehicles = FleetVehicle.objects.filter(current_status='AVAILABLE')



    drivers = User.objects.filter(profile__role=UserRole.DRIVER).select_related('profile')







    context = {



        'jobs': jobs,



        'tab': tab,



        'search_q': search_q,



        'available_vehicles': available_vehicles,



        'drivers': drivers,



        'ready_count': jobs_qs.filter(Q(truck_number='') | Q(truck_number__isnull=True)).count(),



        'assigned_count': jobs_qs.filter(~Q(truck_number='') & Q(current_stage_number__lte=10)).count(),



        'transit_count': jobs_qs.filter(current_stage_number=11).count(),



    }



    return render(request, 'core/logistics_jobs.html', context)











@login_required



@role_required([UserRole.DISPATCH_OFFICER, UserRole.OPERATIONS_MGR])



def logistics_assign_vehicle_action(request, job_id):



    if request.method == 'POST':



        job = get_object_or_404(JobShipment, id=job_id)



        truck_number = request.POST.get('truck_number', '').strip()



        trailer_number = request.POST.get('trailer_number', '').strip()



        driver_id = request.POST.get('driver_id')



        seal_number = request.POST.get('seal_number', '').strip()



        destination = request.POST.get('destination', '').strip()



        container_id = request.POST.get('container_id')







        job.truck_number = truck_number



        if trailer_number:



            job.trailer_number = trailer_number



        if seal_number:



            job.seal_number = seal_number



        if destination:



            job.final_destination = destination







        driver_user = None



        if driver_id:



            driver_user = User.objects.filter(id=driver_id).first()



            job.driver = driver_user







        v = FleetVehicle.objects.filter(plate_number__iexact=truck_number).first()



        if v:



            v.current_status = 'IN_TRANSIT'



            if driver_user:



                v.assigned_driver = driver_user



            v.current_location = f"Assigned to {job.job_number} (Dest: {job.final_destination})"



            v.save()







        # Update specific container or all containers under this job



        if container_id and container_id != 'ALL':



            target_container = job.containers.filter(id=container_id).first()



            if target_container:



                target_container.assigned_truck = truck_number



                if trailer_number:



                    target_container.assigned_trailer = trailer_number



                if seal_number:



                    target_container.seal_number = seal_number



                if driver_user:



                    target_container.assigned_driver = driver_user



                if target_container.status == 'AT_PORT':



                    target_container.status = 'LOADED'



                    target_container.loaded_at = timezone.now()



                target_container.save()



        else:



            for c in job.containers.all():



                if not c.assigned_truck or container_id == 'ALL':



                    c.assigned_truck = truck_number



                    if trailer_number:



                        c.assigned_trailer = trailer_number



                    if seal_number and not c.seal_number:



                        c.seal_number = seal_number



                    if driver_user:



                        c.assigned_driver = driver_user



                    if c.status == 'AT_PORT':



                        c.status = 'LOADED'



                        c.loaded_at = timezone.now()



                    c.save()







        # Only advance to Stage 10 if cargo has cleared statutory payment stages (Stage 9)



        if job.current_stage_number == 9:



            st9 = job.stages.filter(stage_number=9).first()



            if st9 and st9.status != 'COMPLETED':



                st9.status = 'COMPLETED'



                st9.completed_at = timezone.now()



                st9.save()



            job.current_stage_number = 10



            st10 = job.stages.filter(stage_number=10).first()



            if st10:



                st10.status = 'IN_PROGRESS'



                st10.started_at = timezone.now()



                st10.save()



            job.save()



            try:



                from .email_service import send_stage_update_email



                send_stage_update_email(job, 10, extra_note=f"Lori {truck_number} limepangiwa tayari kupakia mzigo.")



            except Exception as e:



                print(f"[Email Notification Error] {e}")



        else:



            job.save()







        log_audit(



            request,



            "ASSIGN_DISPATCH",



            f"Assigned Truck {truck_number} (Trailer {trailer_number}) & Driver {driver_user.get_full_name() if driver_user else 'None'} to {job.job_number} (Dest: {job.final_destination})",



            job=job



        )



        messages.success(request, f"Truck {truck_number} and driver assigned to Job {job.job_number}!")



        return redirect('logistics_jobs')



    return redirect('logistics_jobs')











@login_required



@role_required([UserRole.DISPATCH_OFFICER, UserRole.OPERATIONS_MGR, UserRole.CEO, UserRole.ADMIN])



def logistics_fleet_view(request):



    """



    3. Vehicles & Drivers



    - Vehicle list



    - Driver list



    - Vehicle assignment



    - Driver assignment



    """



    vehicles = FleetVehicle.objects.all().select_related('assigned_driver').order_by('plate_number')



    drivers = User.objects.filter(profile__role=UserRole.DRIVER).select_related('profile')







    status_filter = request.GET.get('status', 'ALL')



    if status_filter in ['AVAILABLE', 'IN_TRANSIT', 'MAINTENANCE', 'OFF_DUTY']:



        vehicles = vehicles.filter(current_status=status_filter)







    available_count = FleetVehicle.objects.filter(current_status='AVAILABLE').count()



    transit_count = FleetVehicle.objects.filter(current_status='IN_TRANSIT').count()



    maintenance_count = FleetVehicle.objects.filter(current_status='MAINTENANCE').count()







    context = {



        'vehicles': vehicles,



        'drivers': drivers,



        'status_filter': status_filter,



        'available_count': available_count,



        'transit_count': transit_count,



        'maintenance_count': maintenance_count,



    }



    return render(request, 'core/logistics_fleet.html', context)











@login_required



@role_required([UserRole.DISPATCH_OFFICER, UserRole.OPERATIONS_MGR])



def logistics_vehicle_create_action(request):



    if request.method == 'POST':



        plate_number = request.POST.get('plate_number', '').strip().upper()



        trailer_plate = request.POST.get('trailer_plate', '').strip().upper()



        vehicle_type = request.POST.get('vehicle_type', 'PRIME_MOVER')



        make_model = request.POST.get('make_model', '').strip()



        capacity = request.POST.get('capacity', '30.0')



        location = request.POST.get('location', 'Dar Central Yard').strip()



        driver_id = request.POST.get('driver_id')







        driver_user = User.objects.filter(id=driver_id).first() if driver_id else None







        v, created = FleetVehicle.objects.get_or_create(



            plate_number=plate_number,



            defaults={



                'trailer_plate': trailer_plate,



                'vehicle_type': vehicle_type,



                'make_model': make_model or 'Scania / Mercedes Hauler',



                'carrying_capacity_tons': Decimal(capacity) if capacity else Decimal('30.0'),



                'current_location': location,



                'assigned_driver': driver_user,



                'current_status': 'AVAILABLE',



            }



        )



        if created:



            log_audit(request, "CREATE_VEHICLE", f"Added vehicle {v.plate_number} ({v.make_model}) to fleet.")



            messages.success(request, f"Vehicle {v.plate_number} added to fleet successfully!")



        else:



            messages.warning(request, f"Vehicle with plate {plate_number} already exists.")



        return redirect('logistics_fleet')



    return redirect('logistics_fleet')











@login_required



@role_required([UserRole.DISPATCH_OFFICER, UserRole.OPERATIONS_MGR])



def logistics_vehicle_status_action(request, vehicle_id):



    if request.method == 'POST':



        vehicle = get_object_or_404(FleetVehicle, id=vehicle_id)



        new_status = request.POST.get('status')



        location = request.POST.get('location', '').strip()







        if new_status in ['AVAILABLE', 'IN_TRANSIT', 'MAINTENANCE', 'OFF_DUTY']:



            vehicle.current_status = new_status



        if location:



            vehicle.current_location = location



        vehicle.save()







        log_audit(request, "UPDATE_VEHICLE_STATUS", f"Vehicle {vehicle.plate_number} status set to {vehicle.get_current_status_display()}")



        messages.success(request, f"Vehicle {vehicle.plate_number} status updated to {vehicle.get_current_status_display()}!")



        return redirect('logistics_fleet')



    return redirect('logistics_fleet')











@login_required



@role_required([UserRole.DISPATCH_OFFICER, UserRole.OPERATIONS_MGR, UserRole.CEO, UserRole.ADMIN])



def logistics_deliveries_view(request):



    """



    4. Delivery Records



    - Delivered jobs



    - Pending deliveries



    - Proof of Delivery



    - Signed Delivery Note



    """



    tab = request.GET.get('tab', 'all')



    search_q = request.GET.get('q', '').strip()







    deliveries_qs = JobShipment.objects.filter(



        Q(status='COMPLETED') | Q(current_stage_number__gte=10)



    ).select_related('customer', 'driver').order_by('-delivered_date', '-updated_at')







    if tab == 'delivered':



        deliveries = deliveries_qs.filter(status='COMPLETED')



    elif tab == 'pending':



        deliveries = deliveries_qs.filter(status__in=['ACTIVE', 'DELAYED'])



    elif tab == 'missing_pod':



        deliveries = deliveries_qs.filter(Q(proof_of_delivery_image='') | Q(proof_of_delivery_image__isnull=True))



    else:



        deliveries = deliveries_qs







    if search_q:



        deliveries = deliveries.filter(



            Q(job_number__icontains=search_q) |



            Q(container_numbers__icontains=search_q) |



            Q(truck_number__icontains=search_q) |



            Q(received_by_name__icontains=search_q) |



            Q(customer__company_name__icontains=search_q)



        )







    pending_delivery_jobs = JobShipment.objects.filter(



        status__in=['ACTIVE', 'DELAYED'],



        current_stage_number__gte=10



    ).order_by('-updated_at')







    delivered_count = deliveries_qs.filter(status='COMPLETED').count()



    pending_count = deliveries_qs.filter(status__in=['ACTIVE', 'DELAYED']).count()



    missing_pod_count = deliveries_qs.filter(Q(proof_of_delivery_image='') | Q(proof_of_delivery_image__isnull=True)).count()







    context = {



        'deliveries': deliveries,



        'tab': tab,



        'search_q': search_q,



        'pending_delivery_jobs': pending_delivery_jobs,



        'delivered_count': delivered_count,



        'pending_count': pending_count,



        'missing_pod_count': missing_pod_count,



    }



    return render(request, 'core/logistics_deliveries.html', context)











@login_required



@role_required([UserRole.DISPATCH_OFFICER, UserRole.OPERATIONS_MGR])



def logistics_record_pod_action(request, job_id):



    if request.method == 'POST':



        job = get_object_or_404(JobShipment, id=job_id)



        received_by = request.POST.get('received_by_name', '').strip()



        pod_file = request.FILES.get('pod_file')



        remarks = request.POST.get('remarks', '').strip()







        job.received_by_name = received_by



        job.delivered_date = timezone.now()



        job.status = 'COMPLETED'



        job.current_stage_number = 11







        if pod_file:



            job.proof_of_delivery_image = pod_file



            stage11 = job.stages.filter(stage_number=11).first()



            JobDocument.objects.create(



                job=job,



                stage=stage11,



                document_type='OTHER',



                title=f"Signed Proof of Delivery (POD) - {job.job_number}",



                file=pod_file,



                uploaded_by=request.user,



                notes=f"Delivered to {received_by}. {remarks}"



            )







        stage11 = job.stages.filter(stage_number=11).first()



        if stage11:



            stage11.status = 'COMPLETED'



            stage11.completed_at = timezone.now()



            stage11.completed_by = request.user



            stage11.remarks = f"Received by {received_by}. {remarks}"



            stage11.save()







        if job.truck_number:



            v = FleetVehicle.objects.filter(plate_number__iexact=job.truck_number).first()



            if v:



                v.current_status = 'AVAILABLE'



                v.current_location = f"Delivered to {job.final_destination} (Standby)"



                v.save()







        job.save()







        log_audit(request, "RECORD_POD", f"Cargo Delivery & Signed POD confirmed for {job.job_number} (Received by {received_by})", job=job)



        messages.success(request, f"Delivery confirmed & Proof of Delivery saved for Job {job.job_number}!")



        return redirect('logistics_deliveries')



    return redirect('logistics_deliveries')











# ==============================================================================



# 9. DRIVER MODULE (EXACTLY 3 MODULES: MY DELIVERY, DELIVERY UPDATE, PROOF OF DELIVERY)



# Minimal, secure, mobile-first interface.



# Privacy rule: Driver asione taarifa za fedha, TANCIS, clients wote au documents za kampuni.



# ==============================================================================







@login_required



@role_required([UserRole.DRIVER, UserRole.DISPATCH_OFFICER, UserRole.OPERATIONS_MGR, UserRole.CEO, UserRole.ADMIN])



def driver_delivery_view(request):



    """



    9. DRIVER - 1. My Delivery



    - Job assigned



    - Vehicle



    - Destination



    - Client



    - Cargo information



    """



    role = get_user_role(request.user)







    if role == UserRole.DRIVER:



        user_driver = request.user



    else:



        # Supervisors previewing driver interface



        driver_id = request.GET.get('driver_id')



        if driver_id:



            user_driver = User.objects.filter(id=driver_id).first() or request.user



        else:



            user_driver = User.objects.filter(profile__role=UserRole.DRIVER).first() or request.user







    # Check container assigned directly to this driver



    driver_containers = JobContainer.objects.filter(



        assigned_driver=user_driver,



        status__in=['LOADED', 'IN_TRANSIT', 'DELIVERED', 'AT_PORT']



    ).select_related('job', 'job__customer')







    assigned_container = driver_containers.first()



    if assigned_container:



        active_delivery = assigned_container.job



    else:



        active_delivery = JobShipment.objects.filter(



            driver=user_driver,



            status__in=['ACTIVE', 'DELAYED']



        ).select_related('customer').prefetch_related('containers').order_by('-current_stage_number', '-updated_at').first()







    # Associated vehicle



    assigned_vehicle = None



    if assigned_container and assigned_container.assigned_truck:



        assigned_vehicle = FleetVehicle.objects.filter(plate_number__iexact=assigned_container.assigned_truck).first()



    elif active_delivery and active_delivery.truck_number:



        assigned_vehicle = FleetVehicle.objects.filter(plate_number__iexact=active_delivery.truck_number).first()



    if not assigned_vehicle and user_driver:



        assigned_vehicle = FleetVehicle.objects.filter(assigned_driver=user_driver).first()







    # Recent completed trips for history



    completed_deliveries = JobShipment.objects.filter(



        driver=user_driver,



        status='COMPLETED'



    ).select_related('customer').order_by('-delivered_date', '-updated_at')[:8]







    # Recent updates/milestones for this active job



    recent_logs = []



    if active_delivery:



        recent_logs = AuditLog.objects.filter(



            job=active_delivery,



            action__in=['DRIVER_UPDATE', 'ASSIGN_VEHICLE', 'RECORD_POD', 'FIELD_UPDATE']



        ).order_by('-timestamp')[:6]







    all_drivers = None



    if role != UserRole.DRIVER:



        all_drivers = User.objects.filter(profile__role=UserRole.DRIVER).select_related('profile')







    context = {



        'active_delivery': active_delivery,



        'assigned_container': assigned_container,



        'assigned_vehicle': assigned_vehicle,



        'completed_deliveries': completed_deliveries,



        'recent_logs': recent_logs,



        'user_driver': user_driver,



        'all_drivers': all_drivers,



        'is_preview_mode': (role != UserRole.DRIVER),



    }



    return render(request, 'core/driver_delivery.html', context)











@login_required



@role_required([UserRole.DRIVER, UserRole.DISPATCH_OFFICER, UserRole.OPERATIONS_MGR, UserRole.CEO, UserRole.ADMIN])



def driver_update_view(request):



    """



    9. DRIVER - 2. Delivery Update



    Milestones: Started, At Port, In Transit, Arrived, Delivered



    """



    role = get_user_role(request.user)







    if role == UserRole.DRIVER:



        user_driver = request.user



    else:



        driver_id = request.GET.get('driver_id')



        if driver_id:



            user_driver = User.objects.filter(id=driver_id).first() or request.user



        else:



            user_driver = User.objects.filter(profile__role=UserRole.DRIVER).first() or request.user







    driver_containers = JobContainer.objects.filter(



        assigned_driver=user_driver,



        status__in=['LOADED', 'IN_TRANSIT', 'DELIVERED', 'AT_PORT']



    ).select_related('job', 'job__customer')







    assigned_container = driver_containers.first()



    if assigned_container:



        active_delivery = assigned_container.job



    else:



        active_delivery = JobShipment.objects.filter(



            driver=user_driver,



            status__in=['ACTIVE', 'DELAYED']



        ).select_related('customer').prefetch_related('containers').order_by('-current_stage_number', '-updated_at').first()







    assigned_vehicle = None



    if assigned_container and assigned_container.assigned_truck:



        assigned_vehicle = FleetVehicle.objects.filter(plate_number__iexact=assigned_container.assigned_truck).first()



    elif active_delivery and active_delivery.truck_number:



        assigned_vehicle = FleetVehicle.objects.filter(plate_number__iexact=active_delivery.truck_number).first()



    if not assigned_vehicle and user_driver:



        assigned_vehicle = FleetVehicle.objects.filter(assigned_driver=user_driver).first()







    recent_updates = []



    if active_delivery:



        recent_updates = AuditLog.objects.filter(



            job=active_delivery,



            action__in=['DRIVER_UPDATE', 'ASSIGN_VEHICLE', 'RECORD_POD', 'FIELD_UPDATE']



        ).order_by('-timestamp')[:8]







    context = {



        'active_delivery': active_delivery,



        'assigned_container': assigned_container,



        'assigned_vehicle': assigned_vehicle,



        'recent_updates': recent_updates,



        'user_driver': user_driver,



        'is_preview_mode': (role != UserRole.DRIVER),



    }



    return render(request, 'core/driver_update.html', context)











@login_required



@role_required([UserRole.DRIVER, UserRole.DISPATCH_OFFICER, UserRole.OPERATIONS_MGR])



def driver_update_action(request, job_id):



    if request.method == 'POST':



        role = get_user_role(request.user)



        job = get_object_or_404(JobShipment, id=job_id)







        # Driver security check: only update own job



        if role == UserRole.DRIVER and job.driver_id != request.user.id:



            # Check if assigned to any container in this job



            has_cnt = job.containers.filter(assigned_driver=request.user).exists()



            if not has_cnt:



                messages.error(request, "You are not authorized to update trips assigned to another driver.")



                return redirect('driver_delivery')







        milestone = request.POST.get('milestone', 'IN_TRANSIT')



        location = request.POST.get('location', '').strip()



        remarks = request.POST.get('remarks', '').strip()



        photo = request.FILES.get('update_photo')







        milestone_labels = {



            'STARTED': 'Trip Started',



            'AT_PORT': 'At Port / ICD',



            'IN_TRANSIT': 'In Transit',



            'ARRIVED': 'Arrived at Destination',



            'DELIVERED': 'Offloading in Progress',



        }



        milestone_label = milestone_labels.get(milestone, milestone)







        now = timezone.now()







        # Update container status directly



        target_containers = job.containers.filter(Q(assigned_driver=request.user) | Q(assigned_truck=job.truck_number))



        if not target_containers.exists():



            target_containers = job.containers.all()







        for c in target_containers:



            if milestone == 'DELIVERED':



                c.status = 'DELIVERED'



                if not c.delivered_at:



                    c.delivered_at = now



            elif milestone in ['STARTED', 'IN_TRANSIT']:



                if c.status in ['AT_PORT', 'VERIFIED', 'LOADED']:



                    c.status = 'IN_TRANSIT'



                    if not c.gate_out_at:



                        c.gate_out_at = now



            elif milestone == 'AT_PORT':



                if c.status == 'AT_PORT':



                    c.status = 'LOADED'



            c.save()







        # Update FleetVehicle if exists



        if job.truck_number:



            v = FleetVehicle.objects.filter(plate_number__iexact=job.truck_number).first()



            if v:



                if milestone in ['STARTED', 'IN_TRANSIT']:



                    v.current_status = 'IN_TRANSIT'



                if location:



                    v.current_location = location



                v.save()







        # Update stage status



        stage10 = job.stages.filter(stage_number=10).first()



        if stage10 and stage10.status != 'COMPLETED':



            stage10.status = 'IN_PROGRESS'



            stage10.save()







        # Optional photo



        if photo:



            JobDocument.objects.create(



                job=job,



                stage=stage10,



                document_type='OTHER',



                title=f"Transit Milestone [{milestone}] - {job.job_number}",



                file=photo,



                uploaded_by=request.user,



                notes=f"Location: {location or 'En route'}. {remarks}"



            )







        log_msg = f"Driver Milestone [{milestone_label}]: Location: {location or 'Not specified'}. Remarks: {remarks or 'None'}."



        log_audit(request, "DRIVER_UPDATE", log_msg, job=job)



        messages.success(request, f"Trip status updated successfully: {milestone_label}!")



        return redirect('driver_delivery')



    return redirect('driver_delivery')



    return redirect('driver_delivery')











@login_required



@role_required([UserRole.DRIVER, UserRole.DISPATCH_OFFICER, UserRole.OPERATIONS_MGR, UserRole.CEO, UserRole.ADMIN])



def driver_pod_view(request):



    """



    9. DRIVER - 3. Proof of Delivery



    - Upload signed Delivery Note



    - Delivery confirmation



    """



    role = get_user_role(request.user)







    if role == UserRole.DRIVER:



        user_driver = request.user



    else:



        driver_id = request.GET.get('driver_id')



        if driver_id:



            user_driver = User.objects.filter(id=driver_id).first() or request.user



        else:



            user_driver = User.objects.filter(profile__role=UserRole.DRIVER).first() or request.user







    active_delivery = JobShipment.objects.filter(



        driver=user_driver,



        status__in=['ACTIVE', 'DELAYED']



    ).select_related('customer').order_by('-current_stage_number', '-updated_at').first()







    recent_pods = JobShipment.objects.filter(



        driver=user_driver,



        status='COMPLETED'



    ).select_related('customer').order_by('-delivered_date', '-updated_at')[:6]







    context = {



        'active_delivery': active_delivery,



        'recent_pods': recent_pods,



        'user_driver': user_driver,



        'is_preview_mode': (role != UserRole.DRIVER),



    }



    return render(request, 'core/driver_pod.html', context)











@login_required



@role_required([UserRole.DRIVER, UserRole.DISPATCH_OFFICER, UserRole.OPERATIONS_MGR])



def driver_pod_action(request, job_id):



    if request.method == 'POST':



        role = get_user_role(request.user)



        job = get_object_or_404(JobShipment, id=job_id)







        # Driver security check: only submit POD for own job



        if role == UserRole.DRIVER and job.driver_id != request.user.id:



            messages.error(request, "You are not authorized to upload POD for an unassigned shipment.")



            return redirect('driver_delivery')







        received_by = request.POST.get('received_by_name', '').strip()



        recipient_phone = request.POST.get('recipient_phone', '').strip()



        pod_file = request.FILES.get('pod_file')



        remarks = request.POST.get('remarks', '').strip()







        if not received_by:



            messages.error(request, "Please enter the full name of the recipient.")



            return redirect('driver_pod')







        job.received_by_name = received_by



        job.delivered_date = timezone.now()



        job.status = 'COMPLETED'



        job.current_stage_number = 11







        full_notes = f"Delivered to {received_by} (Phone: {recipient_phone or 'N/A'}). {remarks}".strip()







        if pod_file:



            job.proof_of_delivery_image = pod_file



            stage11 = job.stages.filter(stage_number=11).first()



            JobDocument.objects.create(



                job=job,



                stage=stage11,



                document_type='OTHER',



                title=f"Driver Signed Proof of Delivery (POD) - {job.job_number}",



                file=pod_file,



                uploaded_by=request.user,



                notes=full_notes



            )







        stage10 = job.stages.filter(stage_number=10).first()



        if stage10:



            stage10.status = 'COMPLETED'



            stage10.completed_at = timezone.now()



            stage10.save()







        stage11 = job.stages.filter(stage_number=11).first()



        if stage11:



            stage11.status = 'COMPLETED'



            stage11.completed_at = timezone.now()



            stage11.completed_by = request.user



            stage11.remarks = full_notes



            stage11.save()







        # Free up assigned truck



        if job.truck_number:



            v = FleetVehicle.objects.filter(plate_number__iexact=job.truck_number).first()



            if v:



                v.current_status = 'AVAILABLE'



                v.current_location = f"Delivered to {job.final_destination} (Standby)"



                v.save()







        job.save()







        log_audit(request, "RECORD_POD", f"Driver {request.user.get_full_name() or request.user.username} submitted signed POD for {job.job_number} (Received by {received_by})", job=job)



        messages.success(request, f"Proof of Delivery (POD) submitted successfully! Trip for {job.job_number} is completed.")



        return redirect('driver_delivery')



    return redirect('driver_pod')











# ==============================================================================



# 10. SUPER ADMIN / DIRECTOR MODULE (EXACTLY 7 BUTTONS)



# 1. Dashboard, 2. Jobs, 3. Operations, 4. Finance, 5. Documents, 6. Staff & Attendance, 7. Settings



# ==============================================================================







@login_required



@role_required([UserRole.CEO, UserRole.ADMIN, UserRole.OPERATIONS_MGR])



def admin_operations_view(request):



    """



    10. SUPER ADMIN / DIRECTOR - 3. Operations



    - Pending Intakes



    - Active Operations



    - Port Activities



    - Completed Operations



    """



    tab = request.GET.get('tab', 'active')



    search_q = request.GET.get('q', '').strip()







    all_jobs_qs = JobShipment.objects.all().select_related(



        'customer', 'documentation_officer', 'clearing_officer', 'port_officer', 'driver'



    ).order_by('-updated_at')







    if tab == 'intakes':



        jobs = all_jobs_qs.filter(current_stage_number__in=[1, 2], status__in=['ACTIVE', 'DELAYED'])



    elif tab == 'port':



        jobs = all_jobs_qs.filter(current_stage_number__in=[5, 6, 7, 8, 10], status__in=['ACTIVE', 'DELAYED'])



    elif tab == 'completed':



        jobs = all_jobs_qs.filter(Q(status='COMPLETED') | Q(current_stage_number=11)).order_by('-delivered_date', '-updated_at')



    else:  # active operations across pipeline



        jobs = all_jobs_qs.filter(status__in=['ACTIVE', 'DELAYED'])







    if search_q:



        jobs = jobs.filter(



            Q(job_number__icontains=search_q) |



            Q(bl_number__icontains=search_q) |



            Q(container_numbers__icontains=search_q) |



            Q(customer__company_name__icontains=search_q) |



            Q(vessel_name__icontains=search_q)



        )







    pipeline_total = all_jobs_qs.filter(status__in=['ACTIVE', 'DELAYED']).count()



    intakes_count = all_jobs_qs.filter(current_stage_number__in=[1, 2], status__in=['ACTIVE', 'DELAYED']).count()



    port_count = all_jobs_qs.filter(current_stage_number__in=[5, 6, 7, 8, 10], status__in=['ACTIVE', 'DELAYED']).count()



    completed_count = all_jobs_qs.filter(Q(status='COMPLETED') | Q(current_stage_number=11)).count()



    delayed_count = all_jobs_qs.filter(status='DELAYED').count()



    active_fleet_in_transit = FleetVehicle.objects.filter(current_status='IN_TRANSIT').count()







    context = {



        'jobs': jobs,



        'tab': tab,



        'search_q': search_q,



        'pipeline_total': pipeline_total,



        'intakes_count': intakes_count,



        'port_count': port_count,



        'completed_count': completed_count,



        'delayed_count': delayed_count,



        'active_fleet_in_transit': active_fleet_in_transit,



    }



    return render(request, 'core/admin_operations.html', context)











@login_required



@role_required([UserRole.CEO, UserRole.ADMIN, UserRole.OPERATIONS_MGR, UserRole.FINANCE])



def staff_attendance_view(request):



    """



    10. SUPER ADMIN / DIRECTOR - 6. Staff & Attendance



    - Employees



    - Attendance



    - Clock In/Out



    - Late employees



    - Field attendance



    - Office attendance



    """



    filter_date_str = request.GET.get('date', '')



    if filter_date_str:



        try:



            view_date = timezone.datetime.strptime(filter_date_str, '%Y-%m-%d').date()



        except ValueError:



            view_date = timezone.now().date()



    else:



        view_date = timezone.now().date()







    tab = request.GET.get('tab', 'attendance')



    search_q = request.GET.get('q', '').strip()







    all_staff = User.objects.filter(is_active=True).select_related('profile').order_by('first_name', 'username')



    attendances_qs = StaffAttendance.objects.filter(date=view_date).select_related('user', 'user__profile').order_by('clock_in_time')







    if search_q:



        all_staff = all_staff.filter(



            Q(first_name__icontains=search_q) |



            Q(last_name__icontains=search_q) |



            Q(username__icontains=search_q) |



            Q(profile__role__icontains=search_q)



        )



        attendances_qs = attendances_qs.filter(



            Q(user__first_name__icontains=search_q) |



            Q(user__last_name__icontains=search_q) |



            Q(user__username__icontains=search_q) |



            Q(location_name__icontains=search_q)



        )







    total_staff = User.objects.filter(is_active=True).exclude(username='admin').count() or User.objects.filter(is_active=True).count()



    present_count = attendances_qs.filter(status__in=['PRESENT', 'LATE']).count()



    on_time_count = attendances_qs.filter(status='PRESENT').count()



    late_count = attendances_qs.filter(status='LATE').count()



    office_count = attendances_qs.filter(attendance_type='OFFICE').count()



    field_count = attendances_qs.filter(attendance_type='FIELD').count()







    today_user_att = StaffAttendance.objects.filter(user=request.user, date=timezone.now().date()).first()







    context = {



        'all_staff': all_staff,



        'attendances': attendances_qs,



        'view_date': view_date,



        'today': timezone.now().date(),



        'tab': tab,



        'search_q': search_q,



        'total_staff': total_staff,



        'present_count': present_count,



        'on_time_count': on_time_count,



        'late_count': late_count,



        'office_count': office_count,



        'field_count': field_count,



        'today_user_att': today_user_att,



    }



    return render(request, 'core/staff_attendance.html', context)











@login_required



def staff_clock_in_action(request):



    if request.method == 'POST':



        today = timezone.now().date()



        now = timezone.now()



        att_type = request.POST.get('attendance_type', 'OFFICE')



        location = request.POST.get('location_name', '').strip()



        notes = request.POST.get('notes', '').strip()







        # Late threshold: 08:15 local time



        threshold_time = timezone.make_aware(timezone.datetime.combine(today, time(8, 15)))



        status = 'LATE' if now > threshold_time else 'PRESENT'







        if not location:



            location = 'Malkia HQ - Posta Dar es Salaam' if att_type == 'OFFICE' else 'Dar Port (TPA / ICD Station)'







        ip = get_client_ip(request)







        att, created = StaffAttendance.objects.update_or_create(



            user=request.user,



            date=today,



            defaults={



                'clock_in_time': now,



                'attendance_type': att_type,



                'location_name': location,



                'ip_address': ip,



                'status': status,



                'notes': notes,



            }



        )







        log_audit(request, "CLOCK_IN", f"Staff {request.user.get_full_name() or request.user.username} clocked in ({status}) at {location} [{att_type}]")



        messages.success(request, f"Clocked in successfully at {now.strftime('%H:%M')} ({status}) - {location}!")



        next_url = request.META.get('HTTP_REFERER', '/staff/attendance/')



        return redirect(next_url)



    return redirect('staff_attendance')











@login_required



def staff_clock_out_action(request):



    if request.method == 'POST':



        today = timezone.now().date()



        now = timezone.now()



        att = StaffAttendance.objects.filter(user=request.user, date=today).first()



        if att:



            att.clock_out_time = now



            att.save()



            log_audit(request, "CLOCK_OUT", f"Staff {request.user.get_full_name() or request.user.username} clocked out at {now.strftime('%H:%M')}")



            messages.success(request, f"Umefanikiwa ku-Clock Out saa {now.strftime('%H:%M')}! Asante kwa kazi ya leo.")



        else:



            messages.warning(request, "Hukuwa ume-Clock In leo.")



        next_url = request.META.get('HTTP_REFERER', '/staff/attendance/')



        return redirect(next_url)



    return redirect('staff_attendance')











@login_required



@role_required([UserRole.ADMIN])



def system_settings_view(request):



    """



    10. SUPER ADMIN / DIRECTOR - 7. Settings



    - Users



    - Roles & Permissions



    - Office IP



    - Port/ICD locations



    - Workflow settings



    - System settings



    """



    tab = request.GET.get('tab', 'users')



    search_q = request.GET.get('q', '').strip()







    users = User.objects.all().select_related('profile').order_by('username')



    if search_q and tab == 'users':



        users = users.filter(



            Q(username__icontains=search_q) |



            Q(first_name__icontains=search_q) |



            Q(last_name__icontains=search_q) |



            Q(email__icontains=search_q)



        )







    roles = UserRole.choices



    stage_definitions = WorkflowStageDefinition.objects.all().order_by('stage_number')



    system_configs = SystemConfig.objects.all().order_by('category', 'key')



    config_dict = {cfg.key: cfg.value for cfg in system_configs}







    from .storage_backends import get_r2_config



    r2_status = get_r2_config()



    total_stored_docs = JobDocument.objects.count()







    context = {



        'tab': tab,



        'search_q': search_q,



        'users': users,



        'roles': roles,



        'stage_definitions': stage_definitions,



        'system_configs': system_configs,



        'config': config_dict,



        'r2_status': r2_status,



        'total_stored_docs': total_stored_docs,



    }



    return render(request, 'core/system_settings.html', context)











@login_required



@role_required([UserRole.CEO, UserRole.ADMIN])



def save_cloudflare_r2_action(request):



    if request.method == 'POST':



        account_id = request.POST.get('r2_account_id', '').strip()



        bucket_name = request.POST.get('r2_bucket_name', '').strip() or 'malkia-files'



        access_key = request.POST.get('r2_access_key_id', '').strip()



        secret_key = request.POST.get('r2_secret_access_key', '').strip()



        public_domain = request.POST.get('r2_public_domain', '').strip()







        SystemConfig.set_value('R2_ACCOUNT_ID', account_id, category='STORAGE', description='Cloudflare R2 Account ID')



        SystemConfig.set_value('R2_BUCKET_NAME', bucket_name, category='STORAGE', description='Cloudflare R2 Bucket Name')



        SystemConfig.set_value('R2_ACCESS_KEY_ID', access_key, category='STORAGE', description='Cloudflare R2 S3 Access Key ID')



        if secret_key:



            SystemConfig.set_value('R2_SECRET_ACCESS_KEY', secret_key, category='STORAGE', description='Cloudflare R2 S3 Secret Access Key')



        SystemConfig.set_value('R2_PUBLIC_DOMAIN', public_domain, category='STORAGE', description='Cloudflare R2 Public Custom Domain / r2.dev URL')







        log_audit(request, "UPDATE_R2_STORAGE", f"Updated Cloudflare R2 storage settings (Bucket: {bucket_name})")







        if request.POST.get('action_mode') == 'test':



            from .storage_backends import test_r2_connection



            ok, msg = test_r2_connection()



            if ok:



                messages.success(request, f"Cloudflare R2 Connected Successfully! {msg}")



            else:



                messages.warning(request, f"Settings saved, but R2 connection test reported: {msg}")



        else:



            messages.success(request, f"Cloudflare R2 Cloud Storage settings saved for bucket '{bucket_name}'!")







        return redirect('/settings/?tab=r2_storage')



    return redirect('system_settings')











@login_required



@role_required([UserRole.ADMIN])



def system_settings_update_action(request):



    if request.method == 'POST':



        category = request.POST.get('category', 'GENERAL')



        for key in request.POST:



            if key not in ['csrfmiddlewaretoken', 'category', 'redirect_tab']:



                val = request.POST.get(key, '').strip()



                SystemConfig.set_value(key, val, category=category)







        log_audit(request, "UPDATE_SETTINGS", f"System settings ({category}) updated by {request.user.username}")



        messages.success(request, f"{category} settings updated successfully!")



        return redirect(f"/settings/?tab={request.POST.get('redirect_tab', 'network')}")



    return redirect('system_settings')











@login_required



@role_required([UserRole.ADMIN])



def admin_update_user_role_action(request, user_id):



    if request.method == 'POST':



        target_user = get_object_or_404(User, id=user_id)



        new_role = request.POST.get('role')



        new_phone = request.POST.get('phone_number', '').strip()



        is_active = request.POST.get('is_active') == 'on'







        if new_role in [c[0] for c in UserRole.choices]:



            profile = getattr(target_user, 'profile', None)



            if profile:



                profile.role = new_role



                if new_phone:



                    profile.phone_number = new_phone



                profile.save()



            target_user.is_active = is_active



            target_user.save()







            log_audit(request, "UPDATE_USER_ROLE", f"Updated user {target_user.username} role to {new_role}")



            messages.success(request, f"User details for {target_user.get_full_name() or target_user.username} updated ({new_role})!")



        return redirect('system_settings')



    return redirect('system_settings')











@login_required

@role_required([UserRole.CEO, UserRole.ADMIN])

def test_resend_email_action(request):

    if request.method == 'POST':

        action_mode = request.POST.get('action_mode', 'test')

        to_email = request.POST.get('to_email', '').strip()

        custom_key = request.POST.get('resend_api_key', '').strip()

        sender_name = request.POST.get('sender_name', '').strip()

        from_email = request.POST.get('from_email', '').strip()



        if custom_key:

            SystemConfig.set_value('RESEND_API_KEY', custom_key, category='EMAIL', description='Resend API Key')

        if sender_name:

            SystemConfig.set_value('RESEND_SENDER_NAME', sender_name, category='EMAIL', description='Resend Sender Display Name')

        if from_email:

            SystemConfig.set_value('RESEND_FROM_EMAIL', from_email, category='EMAIL', description='Resend Sender Email Address')



        log_audit(request, "UPDATE_RESEND_EMAIL", f"Updated Resend Email settings (Sender: {sender_name} <{from_email}>)")



        if action_mode == 'save' or not to_email:

            messages.success(request, "✅ Credentials za Resend Email zimehifadhiwa kikamilifu!")

            return redirect('/settings/?tab=email')



        from .email_service import send_resend_email

        active_sender = sender_name or SystemConfig.get_value('RESEND_SENDER_NAME', 'Malkia Cargo Wave Limited')

        active_from = from_email or SystemConfig.get_value('RESEND_FROM_EMAIL', 'onboarding@resend.dev')



        subject = f"Uthibitisho wa Mfumo wa Barua Pepe (Resend) - {active_sender}"

        html_body = f"""

        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; border: 1px solid #E2E8F0; border-radius: 12px; overflow: hidden; background: #FFFFFF;">

            <div style="background: linear-gradient(135deg, #0F766E 0%, #0F172A 100%); padding: 24px; color: #FFFFFF; text-align: center;">

                <h1 style="margin: 0; font-size: 21px; font-weight: 800;">MALKIA CARGO WAVE LIMITED</h1>

                <p style="margin: 6px 0 0 0; font-size: 13px; color: #99F6E4;">Mfumo Rasmi wa Taarifa kwa Wateja (Email &amp; SMS)</p>

            </div>

            <div style="padding: 24px; color: #1E293B; line-height: 1.6;">

                <h3 style="color: #0F172A; margin-top: 0;">Jaribio la Barua Pepe Limefanikiwa!</h3>

                <p>Habari,</p>

                <p>Barua pepe hii ya majaribio imetumwa kwa mafanikio kutoka <strong>{active_sender}</strong> kupitia injini ya <strong>Resend</strong>.</p>

                <div style="background: #F0FDFA; border-left: 4px solid #0F766E; padding: 12px 16px; border-radius: 6px; margin: 20px 0;">

                    <div style="font-size: 13px; color: #64748B;">Jina la Mtumaji:</div>

                    <div style="font-weight: 700; color: #0F172A; font-size: 15px;">{active_sender}</div>

                    <div style="font-size: 13px; color: #64748B; margin-top: 8px;">Anwani ya Barua Pepe:</div>

                    <div style="font-family: monospace; color: #0F766E;">{active_from}</div>

                </div>

                <p style="font-size: 14px; color: #475569;">

                    Mfumo wako sasa uko tayari kutuma taarifa 3 muhimu kwa wateja moja kwa moja:

                    <strong>1. Kupokea Document za Mteja</strong>,

                    <strong>2. Kodi ya TRA &amp; GePG Control Number Ikitoka</strong>, na

                    <strong>3. Mzigo Kutoka Bandarini na Kuwasili Malkia Yard</strong>.

                </p>

            </div>

        </div>

        """



        ok, result = send_resend_email(

            to_email=to_email,

            subject=subject,

            html_content=html_body,

            text_content=f"Jaribio la Resend Email kutoka {active_sender} ({active_from}) limefanikiwa!",

        )



        if ok:

            messages.success(request, f"✅ Resend Email imehifadhiwa na barua pepe ya majaribio imetumwa kwenda {to_email}! ({result})")

        else:

            messages.error(request, f"❌ Mipangilio imehifadhiwa, lakini jaribio la kutuma barua pepe limeshindikana: {result}")



        return redirect('/settings/?tab=email')



    return redirect('system_settings')





@login_required

@role_required([UserRole.CEO, UserRole.ADMIN])

def test_nextsms_action(request):

    if request.method == 'POST':

        action_mode = request.POST.get('action_mode', 'test')

        server_url = request.POST.get('smsgate_server_url', '').strip() or 'https://api.sms-gate.app'

        smsgate_user = request.POST.get('smsgate_username', '').strip()

        smsgate_pass = request.POST.get('smsgate_password', '').strip()

        smsgate_device = request.POST.get('smsgate_device_id', '').strip()

        smsgate_sim = request.POST.get('smsgate_sim_number', '1').strip() or '1'

        smsgate_order_phone = request.POST.get('smsgate_order_phone', '').strip()



        api_key = request.POST.get('nextsms_api_key', '').strip()

        username = request.POST.get('nextsms_username', '').strip()

        password = request.POST.get('nextsms_password', '').strip()

        sender_id = request.POST.get('nextsms_sender_id', '').strip() or 'N-SMS'

        api_url = request.POST.get('nextsms_api_url', '').strip() or 'https://messaging-service.co.tz/api/sms/v1/text/single'

        to_phone = request.POST.get('to_phone', '').strip()



        if server_url:

            SystemConfig.set_value('SMS_GATE_SERVER_URL', server_url, category='SMS', description='SMS Gate Server URL')

        if smsgate_user:

            SystemConfig.set_value('SMS_GATE_USERNAME', smsgate_user, category='SMS', description='SMS Gate Username')

        if smsgate_pass:

            SystemConfig.set_value('SMS_GATE_PASSWORD', smsgate_pass, category='SMS', description='SMS Gate Password')

        if smsgate_device:

            SystemConfig.set_value('SMS_GATE_DEVICE_ID', smsgate_device, category='SMS', description='SMS Gate Device ID')

        if smsgate_sim:

            SystemConfig.set_value('SMS_GATE_SIM_NUMBER', smsgate_sim, category='SMS', description='SMS Gate SIM Number')

        if smsgate_order_phone:

            SystemConfig.set_value('SMS_GATE_ORDER_PHONE', smsgate_order_phone, category='SMS', description='SMS Gate Order Phone')



        if api_key:

            SystemConfig.set_value('NEXTSMS_API_KEY', api_key, category='SMS', description='NextSMS API Token / Base64 Key')

        if username:

            SystemConfig.set_value('NEXTSMS_USERNAME', username, category='SMS', description='NextSMS Username')

        if password:

            SystemConfig.set_value('NEXTSMS_PASSWORD', password, category='SMS', description='NextSMS Password')

        if request.POST.get('nextsms_sender_id'):

            SystemConfig.set_value('NEXTSMS_SENDER_ID', sender_id, category='SMS', description='NextSMS Sender ID')

        if request.POST.get('nextsms_api_url'):

            SystemConfig.set_value('NEXTSMS_API_URL', api_url, category='SMS', description='NextSMS API Endpoint URL')



        log_audit(request, "UPDATE_SMS_CONFIG", f"Updated SMS Gateway settings (SMS Gate User: {smsgate_user or 'N/A'})")



        if action_mode == 'save' or not to_phone:

            messages.success(request, "✅ Mipangilio ya SMS imehifadhiwa kikamilifu!")

            return redirect('/settings/?tab=email')



        from .email_service import send_nextsms_sms

        test_msg = (

            "Malkia Cargo Wave Limited: Uthibitisho wa mfumo wa SMS umekamilika! "

            "Wateja sasa watapokea SMS za: 1. Kupokea Nyaraka, 2. Kodi ya TRA Ikitoka, na 3. Mzigo Kufika Yard."

        )

        ok, info = send_nextsms_sms(to_phone, test_msg)

        if ok:

            messages.success(request, f"✅ Mipangilio ya SMS imehifadhiwa na SMS ya majaribio imetumwa kwenda {to_phone}! ({info})")

        else:

            messages.error(request, f"❌ Mipangilio imehifadhiwa, lakini jaribio la kutuma SMS limeshindikana: {info}")



        return redirect('/settings/?tab=email')



    return redirect('system_settings')











@login_required



@role_required([UserRole.CEO, UserRole.OPERATIONS_MGR, UserRole.FINANCE, UserRole.ADMIN])



def audit_trail_view(request):



    logs = AuditLog.objects.all().select_related('user', 'job').order_by('-timestamp')[:100]



    context = {



        'logs': logs,



    }



    return render(request, 'core/audit_trail.html', context)











def switch_role_action(request, role_name):



    # Quick switch for testing and presentation



    if role_name in [UserRole.DISPATCH_OFFICER, UserRole.DRIVER]:



        messages.warning(request, "Logistics/Fleet haulage module has been deactivated.")



        return redirect('dashboard')







    user = User.objects.filter(profile__role=role_name).first()



    if user:



        login(request, user)



        log_audit(request, "SWITCH_ROLE", f"Session switched to {user.profile.get_role_display()} ({user.username})")



        messages.info(request, f"Switched view to {user.profile.get_role_display()} ({user.get_full_name() or user.username})")



        if role_name == UserRole.PORT_OFFICER:



            return redirect('field_today_jobs')



        if role_name == UserRole.OPERATIONS_MGR:



            return redirect('yard_operations')



        return redirect('dashboard')



    else:



        messages.warning(request, f"No user found with role {role_name}")



    



    return redirect('dashboard')











# ==============================================================================



# 11. EXPORT DAILY MANAGEMENT REPORT (EXCEL - 3 SHEETS SPEC)



# ==============================================================================







@login_required



@role_required([UserRole.CEO, UserRole.ADMIN, UserRole.FINANCE, UserRole.OPERATIONS_MGR])



def export_daily_report_excel(request):



    """



    Exports the exact 3-sheet Daily Management Report as specified in Makia Cargo Wave Reporting System:



    1. Daily Finance Report (Date, Job No, Client Name, Container/Ref No, Particulars, Expense, Income, Cash, Bank, Approved By, Remarks)



    2. Daily Operations (Date, Client, Job No, Container No, Type of Cargo, Vehicle No, Driver, Status, Destination, Challenges, Action Taken)



    3. CEO Dashboard (Total Daily Income, Total Daily Expenses, Net Position, Total Jobs Today, Completed Jobs, Pending Jobs)



    """



    date_str = request.GET.get('date', '')



    if date_str:



        try:



            filter_date = timezone.datetime.strptime(date_str, '%Y-%m-%d').date()



        except ValueError:



            filter_date = timezone.now().date()



    else:



        filter_date = timezone.now().date()







    wb = openpyxl.Workbook()



    wb.remove(wb.active)  # Remove default blank sheet







    # Design styles matching professional executive spreadsheets



    navy_header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")



    navy_header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")



    totals_font = Font(name="Calibri", size=11, bold=True, color="000000")



    totals_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")







    # ==========================================



    # SHEET 1: Daily Finance Report



    # ==========================================



    ws1 = wb.create_sheet(title="Daily Finance Report")



    ws1_headers = ['Date', 'Job No', 'Client Name', 'Container/Ref No', 'Particulars', 'Expense (TZS)', 'Income (TZS)', 'Cash', 'Bank', 'Approved By', 'Remarks']



    ws1.append(ws1_headers)



    for col_num in range(1, len(ws1_headers) + 1):



        cell = ws1.cell(row=1, column=col_num)



        cell.font = navy_header_font



        cell.fill = navy_header_fill



        cell.alignment = Alignment(horizontal="center", vertical="center")







    expenses_qs = ExpenseVoucher.objects.select_related('job', 'job__customer', 'approver', 'requester').order_by('-requested_at')



    payments_qs = ClientPayment.objects.select_related('invoice', 'invoice__job', 'invoice__customer', 'recorded_by').order_by('-payment_date')







    # If specific date filtering yields records, filter by it; else include all recent active records



    exp_today = expenses_qs.filter(Q(paid_at__date=filter_date) | Q(requested_at__date=filter_date))



    pay_today = payments_qs.filter(payment_date=filter_date)







    if exp_today.exists() or pay_today.exists():



        exp_list = exp_today



        pay_list = pay_today



    else:



        exp_list = expenses_qs[:60]



        pay_list = payments_qs[:60]







    total_expense = Decimal('0.00')



    total_income = Decimal('0.00')







    # Add Expenses



    for exp in exp_list:



        is_cash = exp.payment_method == 'CASH' or 'CASH' in (exp.payment_reference or '').upper()



        r_date = (exp.paid_at.date() if exp.paid_at else exp.requested_at.date()).strftime('%d.%m.%Y')



        approver_name = exp.approver.get_full_name() or exp.approver.username if exp.approver else (exp.requester.first_name if exp.requester else 'Pending')



        particulars = exp.description or exp.get_category_display()



        row = [



            r_date,



            exp.job.job_number,



            exp.job.customer.company_name,



            exp.job.container_numbers[:35],



            particulars,



            float(exp.amount),



            0,



            'Cash' if is_cash else '',



            '' if is_cash else 'Bank',



            approver_name,



            exp.get_approval_status_display()



        ]



        ws1.append(row)



        total_expense += exp.amount







    # Add Income Payments



    for pay in pay_list:



        is_cash = pay.payment_method == 'CASH'



        p_date = pay.payment_date.strftime('%d.%m.%Y')



        collector_name = pay.recorded_by.get_full_name() or pay.recorded_by.username if pay.recorded_by else 'Accounts'



        row = [



            p_date,



            pay.invoice.job.job_number,



            pay.invoice.customer.company_name,



            pay.invoice.job.container_numbers[:35],



            f"Client Payment ({pay.invoice.invoice_number})",



            0,



            float(pay.amount),



            'Cash' if is_cash else '',



            '' if is_cash else 'Bank',



            collector_name,



            f"Received ({pay.payment_reference})"



        ]



        ws1.append(row)



        total_income += pay.amount







    # Totals Row



    ws1.append(['', '', '', '', 'TOTALS', float(total_expense), float(total_income), '', '', '', ''])



    last_r = ws1.max_row



    for c_idx in range(1, len(ws1_headers) + 1):



        cell = ws1.cell(row=last_r, column=c_idx)



        cell.font = totals_font



        cell.fill = totals_fill







    # ==========================================



    # SHEET 2: Daily Operations



    # ==========================================



    ws2 = wb.create_sheet(title="Daily Operations")



    ws2_headers = ['Date', 'Client', 'Job No', 'Container No', 'Type of Cargo', 'Vehicle No', 'Driver', 'Status', 'Destination', 'Challenges', 'Action Taken']



    ws2.append(ws2_headers)



    for col_num in range(1, len(ws2_headers) + 1):



        cell = ws2.cell(row=1, column=col_num)



        cell.font = navy_header_font



        cell.fill = navy_header_fill



        cell.alignment = Alignment(horizontal="center", vertical="center")







    jobs_qs = JobShipment.objects.select_related('customer', 'driver').prefetch_related('field_issues', 'containers', 'containers__assigned_driver').order_by('-updated_at')



    for job in jobs_qs:



        open_issue = job.field_issues.filter(status__in=['OPEN', 'ACTION_TAKEN']).first()



        challenges = open_issue.description if open_issue else "None"



        action_taken = open_issue.action_taken if open_issue else ("Delivered & POD Signed" if job.status == 'COMPLETED' else "In Progress")







        job_containers = list(job.containers.all())



        if job_containers:



            for cnt in job_containers:



                vehicle_no = cnt.assigned_truck or job.truck_number or "MCW 101"



                driver_name = cnt.assigned_driver.get_full_name() if cnt.assigned_driver else (job.driver.get_full_name() if job.driver else "Assigned Ops")



                row = [



                    job.updated_at.strftime('%d.%m.%Y'),



                    job.customer.company_name,



                    job.job_number,



                    f"{cnt.container_number} ({cnt.get_size_type_display()})",



                    job.cargo_description[:40],



                    vehicle_no,



                    driver_name,



                    cnt.get_status_display(),



                    job.final_destination,



                    challenges,



                    action_taken



                ]



                ws2.append(row)



        else:



            vehicle_no = job.truck_number or "MCW 101"



            driver_name = job.driver.get_full_name() or job.driver.username if job.driver else "Assigned Ops"



            row = [



                job.updated_at.strftime('%d.%m.%Y'),



                job.customer.company_name,



                job.job_number,



                job.container_numbers,



                job.cargo_description[:40],



                vehicle_no,



                driver_name,



                job.get_status_display(),



                job.final_destination,



                challenges,



                action_taken



            ]



            ws2.append(row)







    # ==========================================



    # SHEET 3: CEO Dashboard



    # ==========================================



    ws3 = wb.create_sheet(title="CEO Dashboard")



    ws3_headers = ['Metric', 'Value']



    ws3.append(ws3_headers)



    for col_num in range(1, len(ws3_headers) + 1):



        cell = ws3.cell(row=1, column=col_num)



        cell.font = navy_header_font



        cell.fill = navy_header_fill







    net_position = total_income - total_expense



    completed_jobs_count = jobs_qs.filter(status='COMPLETED').count()



    pending_jobs_count = jobs_qs.exclude(status='COMPLETED').count()







    metrics = [



        ('Total Daily Income', float(total_income)),



        ('Total Daily Expenses', float(total_expense)),



        ('Net Position', float(net_position)),



        ('Total Jobs Today', jobs_qs.count()),



        ('Completed Jobs', completed_jobs_count),



        ('Pending Jobs', pending_jobs_count),



    ]



    for metric_name, metric_val in metrics:



        ws3.append([metric_name, metric_val])







    # Auto-adjust column widths



    for sheet in [ws1, ws2, ws3]:



        for col in sheet.columns:



            max_len = max(len(str(c.value or '')) for c in col)



            col_letter = get_column_letter(col[0].column)



            sheet.column_dimensions[col_letter].width = max(max_len + 3, 13)







    log_audit(request, "EXPORT_EXCEL_REPORT", f"Exported Daily Excel Management Report for {filter_date}")







    buffer = io.BytesIO()



    wb.save(buffer)



    buffer.seek(0)







    filename = f"Malkia_Cargo_Wave_Daily_Report_{filter_date.strftime('%Y_%m_%d')}.xlsx"



    response = HttpResponse(



        buffer.getvalue(),



        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'



    )



    response['Content-Disposition'] = f'attachment; filename="{filename}"'



    return response











# ==============================================================================



# 12. USER & STAFF MANAGEMENT CONSOLE (EXECUTIVE & ADMIN GOVERNANCE)



# ==============================================================================







@login_required



@role_required([UserRole.CEO, UserRole.ADMIN, UserRole.OPERATIONS_MGR])



def users_list_view(request):



    """



    Staff Directory & Employee Management Console.



    Allows Boss (CEO) and Admin to supervise all employees, view active status,



    roles, departments, contact info, attendance, and register new staff.



    """



    query = request.GET.get('q', '').strip()



    dept_filter = request.GET.get('department', 'ALL')



    role_filter = request.GET.get('role', 'ALL')



    status_filter = request.GET.get('status', 'ALL')







    users_qs = User.objects.select_related('profile').prefetch_related('attendances').all()







    # Search filter



    if query:



        users_qs = users_qs.filter(



            Q(first_name__icontains=query) |



            Q(last_name__icontains=query) |



            Q(username__icontains=query) |



            Q(email__icontains=query) |



            Q(profile__employee_id__icontains=query) |



            Q(profile__phone_number__icontains=query) |



            Q(profile__national_id__icontains=query)



        )







    # Department filter



    if dept_filter != 'ALL':



        users_qs = users_qs.filter(profile__department=dept_filter)







    # Role filter



    if role_filter != 'ALL':



        users_qs = users_qs.filter(profile__role=role_filter)







    # Status filter



    if status_filter != 'ALL':



        users_qs = users_qs.filter(profile__employment_status=status_filter)







    today = timezone.now().date()



    today_present_user_ids = set(StaffAttendance.objects.filter(



        date=today, status__in=['PRESENT', 'LATE']



    ).values_list('user_id', flat=True))







    total_staff = UserProfile.objects.count()



    active_staff = UserProfile.objects.filter(employment_status='ACTIVE').count()



    on_leave_staff = UserProfile.objects.filter(employment_status='ON_LEAVE').count()



    today_present_count = len(today_present_user_ids)







    # Auto next employee ID suggestion



    next_emp_id = UserProfile.generate_next_employee_id()







    context = {



        'staff_list': users_qs.order_by('profile__employee_id', 'first_name'),



        'search_query': query,



        'dept_filter': dept_filter,



        'role_filter': role_filter,



        'status_filter': status_filter,



        'departments': UserProfile.DEPARTMENT_CHOICES,



        'roles': UserRole.primary_choices(),



        'statuses': UserProfile.EMPLOYMENT_STATUS_CHOICES,



        'employment_types': UserProfile.EMPLOYMENT_TYPE_CHOICES,



        'total_staff': total_staff,



        'active_staff': active_staff,



        'on_leave_staff': on_leave_staff,



        'today_present_count': today_present_count,



        'today_present_user_ids': today_present_user_ids,



        'next_emp_id': next_emp_id,



    }



    return render(request, 'core/users_list.html', context)











@login_required



def user_profile_view(request, user_id):



    """



    Detailed dossier and management view for a single employee.



    Shows personal details, official documents (NIDA, TIN, Driving License),



    Next of Kin, assigned operations, attendance history, and audit log.



    """



    current_role = get_user_role(request.user)



    is_management = current_role in [UserRole.CEO, UserRole.ADMIN, UserRole.OPERATIONS_MGR]



    



    # Permission check: users can view own profile, or management can view any profile



    if request.user.id != user_id and not is_management:



        messages.error(request, "You do not have permission to view another employee's dossier.")



        return redirect('dashboard')







    target_user = get_object_or_404(User.objects.select_related('profile'), id=user_id)



    profile, _ = UserProfile.objects.get_or_create(user=target_user)







    # Load assigned operations based on role



    assigned_jobs = []



    r = profile.role



    if r == UserRole.DRIVER:



        assigned_jobs = JobShipment.objects.filter(driver=target_user).select_related('customer').order_by('-created_at')[:20]



    elif r == UserRole.PORT_OFFICER:



        assigned_jobs = JobShipment.objects.filter(port_officer=target_user).select_related('customer').order_by('-created_at')[:20]



    elif r == UserRole.CLEARING_OFFICER:



        assigned_jobs = JobShipment.objects.filter(clearing_officer=target_user).select_related('customer').order_by('-created_at')[:20]



    elif r == UserRole.DOC_OFFICER:



        assigned_jobs = JobShipment.objects.filter(documentation_officer=target_user).select_related('customer').order_by('-created_at')[:20]



    elif r == UserRole.DISPATCH_OFFICER:



        assigned_jobs = JobShipment.objects.filter(current_stage_number__in=[9, 10, 11]).select_related('customer').order_by('-created_at')[:20]







    # Assigned fleet vehicle if any



    assigned_vehicle = FleetVehicle.objects.filter(assigned_driver=target_user).first()







    # Attendance history (last 30 records)



    attendance_records = StaffAttendance.objects.filter(user=target_user).order_by('-date')[:30]







    # Audit / Action history



    audit_logs = AuditLog.objects.filter(user=target_user).select_related('job').order_by('-timestamp')[:30]







    active_tab = request.GET.get('tab', 'dossier')



    qr_code_b64 = generate_staff_qr_code(profile, target_user)







    context = {



        'target_user': target_user,



        'profile': profile,



        'qr_code_b64': qr_code_b64,



        'is_self': (request.user.id == target_user.id),



        'is_management': is_management,



        'can_edit_profile': (current_role in [UserRole.CEO, UserRole.ADMIN] or request.user.id == target_user.id),



        'assigned_jobs': assigned_jobs,



        'assigned_vehicle': assigned_vehicle,



        'attendance_records': attendance_records,



        'audit_logs': audit_logs,



        'active_tab': active_tab,



        'departments': UserProfile.DEPARTMENT_CHOICES,



        'roles': UserRole.primary_choices(),



        'statuses': UserProfile.EMPLOYMENT_STATUS_CHOICES,
        'employment_types': UserProfile.EMPLOYMENT_TYPE_CHOICES,
        'linked_employee': Employee.objects.filter(user=target_user).first() if request.user.id == target_user.id else None,
    }



    return render(request, 'core/user_profile.html', context)











def generate_staff_qr_code(profile, user):



    """Generates an authentic scannable QR code PNG base64 string for a staff profile."""



    try:



        import qrcode



        import io



        import base64



        



        emp_id = profile.employee_id or 'MC-STAFF'



        full_name = user.get_full_name() or user.username



        role = profile.get_role_display()



        dept = profile.get_department_display()



        station = profile.work_station or 'Dar HQ'



        status = profile.get_employment_status_display()



        



        payload = (



            f"MALKIA CARGO WAVE | OFFICIAL ID\n"



            f"Staff ID: {emp_id}\n"



            f"Name: {full_name}\n"



            f"Role: {role}\n"



            f"Dept: {dept}\n"



            f"Station: {station}\n"



            f"Status: {status}\n"



            f"Auth: Malkia Cargo Wave Co. Ltd."



        )



        



        qr = qrcode.QRCode(



            version=1,



            error_correction=qrcode.constants.ERROR_CORRECT_M,



            box_size=8,



            border=1,



        )



        qr.add_data(payload)



        qr.make(fit=True)



        img = qr.make_image(fill_color='#0F172A', back_color='white')



        



        buffer = io.BytesIO()



        img.save(buffer, format='PNG')



        return base64.b64encode(buffer.getvalue()).decode('utf-8')



    except Exception:



        return ''











@login_required



def user_id_card_view(request, user_id):



    """



    Dedicated printable and digital ID card badge view for an employee.



    Formatted to ISO CR80 standard dimensions with 3D flip and print layout.



    """



    current_role = get_user_role(request.user)



    is_management = current_role in [UserRole.CEO, UserRole.ADMIN, UserRole.OPERATIONS_MGR]



    



    # Permission: own ID or management



    if request.user.id != user_id and not is_management:



        messages.error(request, "You do not have permission to view another employee's ID card.")



        return redirect('dashboard')







    target_user = get_object_or_404(User.objects.select_related('profile'), id=user_id)



    profile, _ = UserProfile.objects.get_or_create(user=target_user)



    qr_code_b64 = generate_staff_qr_code(profile, target_user)

    target_role = get_user_role(target_user)
    if target_role == UserRole.CEO or target_user.is_superuser:
        id_card_title = "CEO"
        id_card_department = "Executive"
    elif target_role == UserRole.FINANCE:
        id_card_title = "ACCOUNTANT"
        id_card_department = "Finance & Accounts"
    else:
        id_card_title = "OPERATION OFFICER"
        id_card_department = "Operations"

    context = {
        'target_user': target_user,
        'profile': profile,
        'qr_code_b64': qr_code_b64,
        'id_card_title': id_card_title,
        'id_card_department': id_card_department,
        'id_card_station': profile.work_station or "Dar es Salaam HQ",
        'is_self': (request.user.id == target_user.id),
        'is_management': is_management,
    }



    return render(request, 'core/user_id_card.html', context)











@login_required



def my_profile_view(request):



    """Shortcut redirect to the logged-in user's own profile page."""



    return redirect('user_profile', user_id=request.user.id)















@login_required



@role_required([UserRole.CEO, UserRole.ADMIN])



def user_create_action(request):



    """



    Registers a new employee account and associated UserProfile dossier.



    Only accessible by Director (CEO) and System Administrator.



    """



    if request.method == 'POST':



        username = request.POST.get('username', '').strip().lower()



        first_name = request.POST.get('first_name', '').strip()



        last_name = request.POST.get('last_name', '').strip()



        email = request.POST.get('email', '').strip()



        password = request.POST.get('password', '').strip() or 'Malkia@2026'







        employee_id = request.POST.get('employee_id', '').strip().upper()



        role = request.POST.get('role', UserRole.DOC_OFFICER)



        department = request.POST.get('department', 'OPERATIONS')



        title = request.POST.get('title', '').strip()



        phone_number = request.POST.get('phone_number', '').strip()



        secondary_phone = request.POST.get('secondary_phone', '').strip()







        national_id = request.POST.get('national_id', '').strip()



        tin_number = request.POST.get('tin_number', '').strip()



        driving_license_number = request.POST.get('driving_license_number', '').strip()



        license_class = request.POST.get('license_class', '').strip()



        license_expiry = request.POST.get('license_expiry') or None







        employment_type = request.POST.get('employment_type', 'PERMANENT')



        employment_status = request.POST.get('employment_status', 'ACTIVE')



        date_joined = request.POST.get('date_joined') or timezone.now().date()



        work_station = request.POST.get('work_station', 'Dar HQ (Posta)').strip()







        emergency_contact_name = request.POST.get('emergency_contact_name', '').strip()



        emergency_contact_phone = request.POST.get('emergency_contact_phone', '').strip()



        emergency_contact_relation = request.POST.get('emergency_contact_relation', '').strip()



        residential_address = request.POST.get('residential_address', '').strip()



        bio = request.POST.get('bio', '').strip()







        if not username:



            messages.error(request, "Please enter a username.")



            return redirect('users_list')







        if User.objects.filter(username=username).exists():



            messages.error(request, f"Username '{username}' is already in use. Please choose another.")



            return redirect('users_list')







        if not employee_id:



            employee_id = UserProfile.generate_next_employee_id()







        # Check unique employee_id



        if UserProfile.objects.filter(employee_id=employee_id).exists():



            employee_id = UserProfile.generate_next_employee_id()







        new_user = User.objects.create_user(



            username=username,



            email=email,



            password=password,



            first_name=first_name,



            last_name=last_name,



            is_active=(employment_status == 'ACTIVE')



        )







        profile, _ = UserProfile.objects.get_or_create(user=new_user)



        profile.employee_id = employee_id



        profile.role = role



        profile.department = department



        profile.title = title or f"{profile.get_role_display()}"



        profile.phone_number = phone_number



        profile.secondary_phone = secondary_phone



        profile.national_id = national_id



        profile.tin_number = tin_number



        profile.driving_license_number = driving_license_number



        profile.license_class = license_class



        if license_expiry:



            profile.license_expiry = license_expiry



        profile.employment_type = employment_type



        profile.employment_status = employment_status



        if date_joined:



            profile.date_joined = date_joined



        profile.work_station = work_station



        profile.emergency_contact_name = emergency_contact_name



        profile.emergency_contact_phone = emergency_contact_phone



        profile.emergency_contact_relation = emergency_contact_relation



        profile.residential_address = residential_address



        profile.bio = bio







        if 'avatar' in request.FILES:



            profile.avatar = request.FILES['avatar']







        profile.save()







        log_audit(



            request,



            "CREATE_EMPLOYEE",



            f"Registered employee {new_user.get_full_name() or new_user.username} ({employee_id}) as {profile.get_role_display()} [{department}]"



        )



        messages.success(request, f"New staff member {new_user.get_full_name() or new_user.username} ({employee_id}) registered successfully!")



        return redirect('user_profile', user_id=new_user.id)







    return redirect('users_list')











@login_required



def user_update_action(request, user_id):



    """



    Updates an employee's personal dossier, contact details, or job role.



    Boss and Admin can update everything. Staff can update their own contact and avatar.



    """



    current_role = get_user_role(request.user)



    is_management = current_role in [UserRole.CEO, UserRole.ADMIN]







    if request.user.id != user_id and not is_management:



        messages.error(request, "You do not have permission to modify this employee's profile.")



        return redirect('dashboard')







    target_user = get_object_or_404(User.objects.select_related('profile'), id=user_id)



    profile = target_user.profile







    if request.method == 'POST':



        # Basic user info



        target_user.first_name = request.POST.get('first_name', target_user.first_name).strip()



        target_user.last_name = request.POST.get('last_name', target_user.last_name).strip()



        target_user.email = request.POST.get('email', target_user.email).strip()



        target_user.save()







        # Contact & Profile



        profile.phone_number = request.POST.get('phone_number', profile.phone_number).strip()



        profile.secondary_phone = request.POST.get('secondary_phone', profile.secondary_phone).strip()



        profile.residential_address = request.POST.get('residential_address', profile.residential_address).strip()



        profile.emergency_contact_name = request.POST.get('emergency_contact_name', profile.emergency_contact_name).strip()



        profile.emergency_contact_phone = request.POST.get('emergency_contact_phone', profile.emergency_contact_phone).strip()



        profile.emergency_contact_relation = request.POST.get('emergency_contact_relation', profile.emergency_contact_relation).strip()



        profile.national_id = request.POST.get('national_id', profile.national_id).strip()



        profile.tin_number = request.POST.get('tin_number', profile.tin_number).strip()



        profile.driving_license_number = request.POST.get('driving_license_number', profile.driving_license_number).strip()



        profile.license_class = request.POST.get('license_class', profile.license_class).strip()



        



        lic_exp = request.POST.get('license_expiry')



        if lic_exp:



            profile.license_expiry = lic_exp







        profile.bio = request.POST.get('bio', profile.bio).strip()







        # Management-only fields (Role, Department, Station, Status, Type, Employee ID)



        if is_management:



            new_role = request.POST.get('role')



            if new_role in [c[0] for c in UserRole.choices]:



                profile.role = new_role







            new_dept = request.POST.get('department')



            if new_dept:



                profile.department = new_dept







            profile.title = request.POST.get('title', profile.title).strip()



            profile.work_station = request.POST.get('work_station', profile.work_station).strip()



            profile.employment_type = request.POST.get('employment_type', profile.employment_type)



            



            new_status = request.POST.get('employment_status', profile.employment_status)



            profile.employment_status = new_status



            target_user.is_active = (new_status == 'ACTIVE')



            target_user.save()







            custom_emp_id = request.POST.get('employee_id', '').strip().upper()



            if custom_emp_id:



                profile.employee_id = custom_emp_id







            date_j = request.POST.get('date_joined')



            if date_j:



                profile.date_joined = date_j







        if 'avatar' in request.FILES:



            profile.avatar = request.FILES['avatar']







        profile.save()







        log_audit(



            request,



            "UPDATE_STAFF_PROFILE",



            f"Updated profile dossier for {target_user.get_full_name() or target_user.username} ({profile.employee_id})"



        )



        messages.success(request, f"Staff details for {target_user.get_full_name() or target_user.username} updated successfully!")



        return redirect('user_profile', user_id=target_user.id)







    return redirect('user_profile', user_id=target_user.id)











@login_required



@role_required([UserRole.CEO, UserRole.ADMIN])



def user_password_reset_action(request, user_id):



    """



    Administrative password reset for employees.



    """



    if request.method == 'POST':



        target_user = get_object_or_404(User, id=user_id)



        new_pwd = request.POST.get('new_password', '').strip()



        confirm_pwd = request.POST.get('confirm_password', '').strip()







        if not new_pwd:



            messages.error(request, "Please enter a new password.")



            return redirect('user_profile', user_id=target_user.id)







        if new_pwd != confirm_pwd:



            messages.error(request, "New password and confirmation do not match.")



            return redirect('user_profile', user_id=target_user.id)







        target_user.set_password(new_pwd)



        target_user.save()







        log_audit(request, "RESET_PASSWORD", f"Administrative password reset for user {target_user.username}")



        messages.success(request, f"Password for {target_user.get_full_name() or target_user.username} changed successfully!")



        return redirect('user_profile', user_id=target_user.id)







    return redirect('user_profile', user_id=user_id)











@login_required



@role_required([UserRole.CEO, UserRole.ADMIN])



def user_status_toggle_action(request, user_id):



    """



    Quick status toggle (Active / On Leave / Suspended) for staff management.



    """



    if request.method == 'POST':



        target_user = get_object_or_404(User.objects.select_related('profile'), id=user_id)



        profile = target_user.profile



        new_status = request.POST.get('status')







        if new_status in ['ACTIVE', 'ON_LEAVE', 'SUSPENDED', 'TERMINATED']:



            profile.employment_status = new_status



            profile.save()



            target_user.is_active = (new_status == 'ACTIVE')



            target_user.save()







            log_audit(request, "TOGGLE_USER_STATUS", f"Changed status of {target_user.username} to {new_status}")



            messages.success(request, f"Employment status for {target_user.get_full_name() or target_user.username} changed to '{profile.get_employment_status_display()}'!")







        return redirect('user_profile', user_id=target_user.id)







    return redirect('users_list')











# ==============================================================================



# CLIENT PORTAL & AI CARGO ASSISTANT ("MALKIA AI")



# ==============================================================================







def client_portal_view(request):



    """



    State-of-the-art interactive Client Portal for Importers, Clearing Clients & Cargo Owners.



    Provides live cargo tracking, container radar, free days & demurrage countdown,



    verified document repository, billing summaries, and integrated Malkia AI Cargo Assistant.



    """



    customers = Customer.objects.all().order_by('company_name')



    



    # Active selected customer



    customer_id = request.GET.get('customer_id')



    selected_customer = None



    if customer_id:



        selected_customer = Customer.objects.filter(id=customer_id).first()



    if not selected_customer and customers.exists():



        selected_customer = customers.first()







    # Search query for BL / Container / Job #



    query = request.GET.get('q', '').strip()



    



    shipments = []



    containers = []



    documents = []



    invoices = []



    



    if selected_customer:



        shipments_qs = JobShipment.objects.filter(customer=selected_customer).select_related('customer', 'documentation_officer', 'clearing_officer', 'port_officer', 'driver').order_by('-created_at')



        if query:



            shipments_qs = shipments_qs.filter(



                Q(job_number__icontains=query) |



                Q(bl_number__icontains=query) |



                Q(container_numbers__icontains=query) |



                Q(vessel_name__icontains=query)



            )



        shipments = list(shipments_qs)



        containers = list(JobContainer.objects.filter(job__customer=selected_customer).select_related('job', 'assigned_driver').order_by('-created_at')[:25])



        documents = list(JobDocument.objects.filter(job__customer=selected_customer).select_related('job').order_by('-uploaded_at')[:20])



        invoices = list(selected_customer.invoices.all().order_by('-created_at')[:15])







    stages = list(WorkflowStageDefinition.objects.all().order_by('stage_number'))







    # Calculate high-level KPIs for selected customer



    active_shipments_count = len([s for s in shipments if s.status in ['ACTIVE', 'DELAYED']])



    total_containers_count = sum(s.total_containers_count for s in shipments)



    



    # Demurrage & Detention risk count



    demurrage_risk_count = sum(1 for c in containers if (c.is_detention_expiring_soon or c.is_detention_overdue))







    total_billed = selected_customer.total_revenue if selected_customer else Decimal('0.00')



    total_paid = selected_customer.total_paid if selected_customer else Decimal('0.00')



    outstanding = selected_customer.outstanding_balance if selected_customer else Decimal('0.00')







    context = {



        'customers': customers,



        'selected_customer': selected_customer,



        'shipments': shipments,



        'containers': containers,



        'documents': documents,



        'invoices': invoices,



        'stages': stages,



        'query': query,



        'active_shipments_count': active_shipments_count,



        'total_containers_count': total_containers_count,



        'demurrage_risk_count': demurrage_risk_count,



        'total_billed': total_billed,



        'total_paid': total_paid,



        'outstanding': outstanding,



    }



    return render(request, 'core/client_portal.html', context)











def client_track_api(request):



    """



    AJAX Live tracking search API for public / client portal.



    Finds shipments by BL Number, Container Number, or Job File Number.



    """



    q = request.GET.get('q', '').strip()



    if not q or len(q) < 2:



        return JsonResponse({'status': 'error', 'message': 'Please enter a valid B/L, Container, or Job File number.'})







    jobs = JobShipment.objects.filter(



        Q(job_number__icontains=q) |



        Q(bl_number__icontains=q) |



        Q(container_numbers__icontains=q)



    ).select_related('customer').order_by('-created_at')[:10]







    results = []



    for j in jobs:



        curr = j.current_stage_obj



        results.append({



            'id': j.id,



            'job_number': j.job_number,



            'bl_number': j.bl_number,



            'customer': j.customer.company_name,



            'vessel_name': j.vessel_name,



            'port_of_origin': j.port_of_origin,



            'eta': j.eta_arrival_date.strftime('%d %b %Y') if j.eta_arrival_date else '--',



            'stage_number': j.current_stage_number,



            'stage_name': curr.name_en if curr else 'Initial Processing',



            'status': j.get_status_display(),



            'containers_count': j.total_containers_count,



            'duty_paid': j.duty_paid,



            'created_at': j.created_at.strftime('%d %b %Y'),



        })







    return JsonResponse({'status': 'success', 'results': results, 'count': len(results)})















def get_vehicle_tracking_milestones(job):
    """
    Computes all 5 real-world clearing & forwarding milestones for this job.
    Uses REAL user data (who actually completed the step) and exact time taken
    (duration the job stayed in each stage).
    """
    import datetime
    from django.utils import timezone

    is_bond = (job.clearance_mode == 'BOND')
    is_completed = (job.status == 'COMPLETED')

    def _to_dt(val):
        if not val:
            return None
        if isinstance(val, datetime.datetime):
            return val
        if isinstance(val, datetime.date):
            dt = datetime.datetime.combine(val, datetime.time.min)
            return timezone.make_aware(dt) if timezone.is_aware(timezone.now()) else dt
        return None

    def _fmt_duration_en(td):
        if not td:
            return '< 1 hour'
        sec = max(0, int(td.total_seconds()))
        if sec < 60:
            return f'{sec}s'
        mins = sec // 60
        if mins < 60:
            return f'{mins}m'
        hrs = mins // 60
        rem_m = mins % 60
        if hrs < 24:
            return f'{hrs}h {rem_m}m' if rem_m else f'{hrs} hours'
        days = hrs // 24
        rem_h = hrs % 24
        return f'{days}d {rem_h}h' if rem_h else f'{days} days'

    STAGE_SPECS = [
        (1, 'File Opening & Doc Intake', 'Document Intake & File Opening', 'Same Day', 'fa-folder-open'),
        (2, 'Customs Declaration', 'TRA TANSAD Declaration', '24 Hours', 'fa-file-invoice'),
        (3, 'TBS Inspection & Clearance', 'TBS Portal & Standards Approval', '1-2 Days', 'fa-shield-halved'),
        (4, 'Port Clearance & Gate Exit', 'D/O, Inspection, Port Fees & Gate Pass', '1-2 Days', 'fa-truck-moving'),
        (5, 'Vehicle Arrival', 'Arrived at Yard / Office', 'Same Day', 'fa-warehouse'),
        (6, 'Customer Handover', 'Customer Handover & POD Signed', 'Upon Request', 'fa-handshake'),
    ]

    stages_map = {si.stage_number: si for si in job.stages.all().select_related('responsible_officer')}
    audit_logs = list(job.audit_logs.all().order_by('timestamp'))
    log_users_by_action = {}
    for l in audit_logs:
        u_name = l.user.get_full_name() or l.user.username if l.user else ''
        if u_name:
            log_users_by_action[l.action] = u_name

    milestones = []
    prev_finish_time = job.created_at

    for step_num, title, default_sub, sla, icon in STAGE_SPECS:
        si = stages_map.get(step_num)
        is_done = False
        if is_completed:
            is_done = True
        elif (job.current_stage_number or 1) > step_num:
            is_done = True
        elif si and si.status == 'COMPLETED':
            is_done = True

        is_current = (job.current_stage_number == step_num and not is_done and not is_completed)

        officer = None
        if si and si.responsible_officer:
            officer = si.responsible_officer.get_full_name() or si.responsible_officer.username

        if not officer:
            if step_num == 1 and job.documentation_officer:
                officer = job.documentation_officer.get_full_name() or job.documentation_officer.username
            elif step_num == 2 and job.clearing_officer:
                officer = job.clearing_officer.get_full_name() or job.clearing_officer.username
            elif step_num == 3 and getattr(job, 'tbs_officer', None):
                officer = job.tbs_officer.get_full_name() or job.tbs_officer.username
            elif step_num == 4 and (job.vehicle_inspection_by or getattr(job, 'port_officer', None)):
                officer = (job.vehicle_inspection_by.get_full_name() or job.vehicle_inspection_by.username) if job.vehicle_inspection_by else (job.port_officer.get_full_name() or job.port_officer.username)
            elif step_num == 5 and job.vehicle_driver_name:
                officer = job.vehicle_driver_name
            elif step_num == 6 and job.received_by_name:
                officer = job.received_by_name

        if not officer:
            if is_done:
                officer = log_users_by_action.get('ADVANCE_STAGE') or 'Malkia Operations Team'
            elif is_current:
                officer = 'In Progress'
            else:
                officer = 'Pending'

        comp_time = si.completed_at if (si and si.completed_at) else None
        if not comp_time and is_done:
            if step_num == 1: comp_time = getattr(job, 'file_opened_at', None) or job.created_at
            elif step_num == 2: comp_time = getattr(job, 'tanesw_lodged_at', None)
            elif step_num == 3: comp_time = getattr(job, 'vehicle_dispatched_at', None) or getattr(job, 'vehicle_inspection_at', None)
            elif step_num == 4: comp_time = getattr(job, 'vehicle_arrived_at', None)
            elif step_num == 5: comp_time = getattr(job, 'delivered_date', None)
        comp_time = _to_dt(comp_time)

        sub = default_sub
        if step_num == 1 and getattr(job, 'declaration_number', None):
            sub = f'Dec #{job.declaration_number}'
        elif step_num == 2 and getattr(job, 'declaration_number', None):
            sub = f'Dec #{job.declaration_number}'
        elif step_num == 3:
            if getattr(job, 'gate_pass_number', None):
                sub = f'Gate Pass #{job.gate_pass_number}'
            elif getattr(job, 'vehicle_dispatched_to_office', False):
                sub = 'Exited Port Gate & Cleared'
            elif is_done:
                sub = 'Port Clearance Complete'
            elif is_current:
                sub = 'Clearing at Port & ICD'
        elif step_num == 4:
            sub = 'Arrived at Malkia Yard' if is_done else 'En Route to Yard / Office'
        elif step_num == 5 and getattr(job, 'received_by_name', None):
            sub = f'Received by: {job.received_by_name}'

        time_taken = None
        if si and si.started_at and si.completed_at:
            time_taken = _fmt_duration_en(si.completed_at - si.started_at)
        elif comp_time and prev_finish_time and comp_time >= prev_finish_time:
            time_taken = _fmt_duration_en(comp_time - prev_finish_time)
        elif is_done:
            time_taken = '< 1 hour'
        elif is_current:
            s_time = (si.started_at if (si and si.started_at) else prev_finish_time)
            if s_time:
                time_taken = f'Elapsed: {_fmt_duration_en(timezone.now() - s_time)}'
        if comp_time:
            prev_finish_time = comp_time

        milestones.append({
            'id': step_num,
            'name': title,
            'subtitle': sub,
            'done': is_done,
            'current': is_current,
            'assigned_officer': officer,
            'completed_at': comp_time,
            'time_taken': time_taken,
            'target_sla': sla,
            'icon': icon,
        })

    return milestones


def client_shipment_detail_view(request, job_id):



    """



    Detailed client tracking page for a single shipment with full 11-stage progress trail.



    """



    job = get_object_or_404(JobShipment.objects.select_related('customer', 'documentation_officer', 'clearing_officer', 'port_officer', 'driver'), id=job_id)



    stages = list(WorkflowStageDefinition.objects.all().order_by('stage_number'))



    stage_instances = {si.stage_number: si for si in job.stages.all()}



    documents = job.documents.all()



    milestones = get_vehicle_tracking_milestones(job)



    completed_milestones_count = sum(1 for m in milestones if m['done'])







    context = {



        'job': job,



        'milestones': milestones,



        'completed_milestones_count': completed_milestones_count,



        'stages': stages,



        'stage_instances': stage_instances,



        'documents': documents,



    }



    return render(request, 'core/client_shipment_detail.html', context)























def client_ai_chat_api(request):



    """



    Intelligent Conversational Logistics AI ("Malkia AI") for Clients & Cargo Owners.



    Performs real-time context analysis on client's active shipments, free-days, customs duties,



    truck assignments, and invoices, giving rich, accurate answers in Swahili & English.



    """



    if request.method != 'POST':



        return JsonResponse({'status': 'error', 'message': 'Only POST method is allowed.'}, status=405)







    try:



        data = json.loads(request.body.decode('utf-8'))



    except Exception:



        data = request.POST







    user_message = data.get('message', '').strip()



    customer_id = data.get('customer_id')







    if not user_message:



        return JsonResponse({'status': 'error', 'message': 'Message cannot be empty.'})







    customer = None



    if customer_id:



        customer = Customer.objects.filter(id=customer_id).first()



    if not customer:



        customer = Customer.objects.first()







    from core.executive_ai import query_client_ai



    



    # We don't have chat_history from the frontend currently, so we pass None or extract it if provided



    chat_history = data.get('chat_history', [])



    



    ai_response = query_client_ai(user_message=user_message, customer=customer, chat_history=chat_history)



    



    if ai_response.get("status") == "error":



        return JsonResponse({'status': 'error', 'message': ai_response.get("reply", "A temporary service error occurred. Please try again.")})



        



    reply = ai_response.get("reply", "")



    suggestions = ai_response.get("suggestions", ["Track Cargo", "Upload Payment Receipt", "Clearance Inquiries"])







    return JsonResponse({



        'status': 'success',



        'reply': reply,



        'timestamp': timezone.now().strftime('%H:%M'),



        'suggestions': suggestions,



        'target_job_id': ai_response.get('target_job_id'),



        'target_job_number': ai_response.get('target_job_number'),



        'intent': ai_response.get('intent', 'general'),



    })











@csrf_exempt



def client_upload_receipt_api(request):



    """



    API endpoint for clients uploading TRA / Bank payment receipts via Malkia AI Chat Portal.



    Attaches file to JobDocument as DUTY_PAYMENT_RECEIPT, records reference, logs audit trail,



    and returns rich confirmation data for the interactive chat stream.



    """



    if request.method != 'POST':



        return JsonResponse({'status': 'error', 'message': 'Only POST method is allowed.'}, status=405)







    receipt_file = request.FILES.get('receipt_file')



    if not receipt_file:



        return JsonResponse({'status': 'error', 'message': 'Please attach a valid receipt file (Image or PDF).'}, status=400)







    # Allowed extensions



    allowed_exts = ['.jpg', '.jpeg', '.png', '.webp', '.pdf']



    filename = receipt_file.name.lower()



    if not any(filename.endswith(ext) for ext in allowed_exts):



        return JsonResponse({'status': 'error', 'message': 'Invalid file format. Please upload JPG, PNG, or PDF.'}, status=400)







    job_id = request.POST.get('job_id')



    job_number_input = request.POST.get('job_number', '').strip()



    receipt_reference = request.POST.get('receipt_reference', '').strip()



    notes = request.POST.get('notes', '').strip()







    job = None



    if job_id and str(job_id).isdigit():



        job = JobShipment.objects.filter(id=int(job_id)).first()



    



    if not job and job_number_input:



        job = JobShipment.objects.filter(Q(job_number__iexact=job_number_input) | Q(bl_number__iexact=job_number_input)).first()



        if not job:



            job = JobShipment.objects.filter(job_number__icontains=job_number_input).first()







    if not job:



        # Fallback to the latest active job if single customer



        job = JobShipment.objects.filter(status='ACTIVE').order_by('-created_at').first()







    if not job:



        return JsonResponse({



            'status': 'error',



            'message': 'Shipment not found. Please provide a valid Job Number (e.g. CF/2026/0008) or B/L number.'



        }, status=404)







    # Create JobDocument



    doc_title = f"TRA Duty Receipt - {receipt_reference}" if receipt_reference else f"TRA Duty Receipt (Client Portal)"



    stage4 = job.stages.filter(stage_number=4).first()







    doc = JobDocument.objects.create(



        job=job,



        stage=stage4,



        document_type='DUTY_PAYMENT_RECEIPT',



        title=doc_title,



        file=receipt_file,



        uploaded_by=None,



        notes=f"Uploaded by client via Malkia AI Portal. Reference: {receipt_reference or 'N/A'}. {notes}".strip()



    )







    if receipt_reference and not job.duty_payment_reference:



        job.duty_payment_reference = receipt_reference



        job.save(update_fields=['duty_payment_reference'])







    # Audit Trail



    log_audit(



        request,



        action='CLIENT_RECEIPT_UPLOADED',



        details=f"Client uploaded payment receipt '{doc.title}' via Malkia AI Portal. Reference: {receipt_reference or 'N/A'}. Awaiting internal verification.",



        job=job



    )







    clean_filename = doc.file.name.split('/')[-1]



    ai_reply = (



        f"✅ **Payment Receipt Successfully Received!**\n\n"



        f"• **Shipment Dossier:** `{job.job_number}` (B/L: `{job.bl_number}`)\n"



        f"• **Attached File:** `{clean_filename}`\n"



        f"{f'• **TRA Receipt / Bank Ref:** `{receipt_reference}`' if receipt_reference else ''}\n"



        f"• **Verification Status:** ⏳ Pending Finance & Customs Officer Approval\n\n"



        f"Our operations team has received an automated alert. Once verified, this shipment will advance to Delivery Order (DO) processing immediately."



    )







    return JsonResponse({



        'status': 'success',



        'message': 'Payment receipt uploaded successfully.',



        'job_id': job.id,



        'job_number': job.job_number,



        'bl_number': job.bl_number,



        'doc_id': doc.id,



        'doc_title': doc.title,



        'doc_url': doc.file.url if doc.file else '',



        'filename': clean_filename,



        'receipt_reference': receipt_reference,



        'ai_reply': ai_reply,



        'timestamp': timezone.now().strftime('%H:%M')



    })















@login_required



@role_required([UserRole.CEO])



def executive_ai_chat_api(request):



    """



    Executive AI (Boss Mode) — Real Hive AI (DeepSeek V4.1 Flash) Intelligence Engine.



    Queries the live database in real-time and uses DeepSeek to answer management,



    financial, container tracking, and operational questions.



    """



    if request.method != 'POST':



        return JsonResponse({'status': 'error', 'message': 'POST only.'}, status=405)







    try:



        data = json.loads(request.body.decode('utf-8'))



    except Exception:



        data = request.POST







    # Clear chat history action



    if data.get('action') == 'clear':



        request.session['exec_ai_chat_history'] = []



        request.session.modified = True



        return JsonResponse({'status': 'success', 'message': 'Conversation cleared.'})







    user_message = data.get('message', '').strip()



    if not user_message:



        return JsonResponse({'status': 'error', 'message': 'Message cannot be empty.'})







    # Retrieve and sanitize conversation history (strictly valid user-assistant pairs)



    raw_history = request.session.get('exec_ai_chat_history', [])



    valid_pairs = []



    i = 0



    while i < len(raw_history) - 1:



        u = raw_history[i]



        a = raw_history[i + 1]



        if (



            isinstance(u, dict) and u.get('role') == 'user' and



            isinstance(a, dict) and a.get('role') == 'assistant' and



            'mtandao' not in a.get('content', '').lower() and



            'samahani' not in a.get('content', '').lower()



        ):



            valid_pairs.append(u)



            valid_pairs.append(a)



            i += 2



        else:



            i += 1







    # Only pass the last 1 pair (last user turn + last answer) for immediate context



    chat_history = valid_pairs[-2:]







    # Query the real Hive AI engine with live database context



    from core.executive_ai import query_executive_ai



    result = query_executive_ai(user_message, user=request.user, chat_history=chat_history)







    if result.get('status') == 'success':



        valid_pairs.append({'role': 'user', 'content': user_message})



        valid_pairs.append({'role': 'assistant', 'content': result['reply']})



        request.session['exec_ai_chat_history'] = valid_pairs[-6:]



        request.session.modified = True







    return JsonResponse({



        'status': result.get('status', 'success'),



        'reply': result['reply'],



        'timestamp': timezone.now().strftime('%H:%M'),



        'suggestions': result.get('suggestions', [])



    })















# ============================================================================# ==============================================================================



# AUTOMATED VEHICLE COST ROLLUP & YARD HANDOVER MODULE



# ==============================================================================







def auto_compile_customer_final_bill(job):
    """
    Automatically compiles vehicle clearance direct costing (or approved port expenses)
    into a clean, up-to-date ClientInvoice.
    """
    from datetime import date, timedelta
    from decimal import Decimal

    existing_invoice = job.invoices.first()

    has_direct_costing = bool(
        (job.cost_agent_fee and job.cost_agent_fee > Decimal('0')) or 
        (job.total_direct_costs and job.total_direct_costs > Decimal('0'))
    )

    if has_direct_costing:
        agency_fee = job.cost_agent_fee or (job.contracted_revenue if job.contracted_revenue and job.contracted_revenue > Decimal('0') else Decimal('350000.00'))
        shipping_line_amt = job.cost_do or Decimal('0.00')
        port_charges_amt = (job.cost_wharfage or Decimal('0.00')) + (job.cost_tiss_wharfage or Decimal('0.00'))
        terminal_handling_amt = job.cost_handling or Decimal('0.00')
        transport_amt = job.cost_transport or Decimal('0.00')
        sundry_amt = (
            (job.cost_facilitation or Decimal('0.00')) +
            (job.cost_fuel or Decimal('0.00')) +
            (job.cost_ferry_charges or Decimal('0.00')) +
            (job.cost_other or Decimal('0.00'))
        )
    else:
        # 1. Agency / Clearing fee:
        if job.contracted_revenue and job.contracted_revenue > 0:
            agency_fee = job.contracted_revenue
        elif existing_invoice and existing_invoice.amount_clearing_agency_fee > 0:
            agency_fee = existing_invoice.amount_clearing_agency_fee
        else:
            agency_fee = Decimal('350000.00')

        # 2. Strictly PAID / APPROVED vouchers only
        vouchers = job.expenses.filter(
            Q(is_paid=True) | Q(approval_status__in=['APPROVED', 'PAID'])
        )

        shipping_vouchers = vouchers.filter(category=ExpenseCategory.SHIPPING_LINE)
        shipping_line_amt = shipping_vouchers.aggregate(tot=Sum('amount'))['tot'] or Decimal('0.00')

        port_vouchers = vouchers.filter(category=ExpenseCategory.PORT_CHARGES)
        port_charges_amt = port_vouchers.aggregate(tot=Sum('amount'))['tot'] or Decimal('0.00')

        handling_vouchers = vouchers.filter(category=ExpenseCategory.PORT_HANDLING)
        terminal_handling_amt = handling_vouchers.aggregate(tot=Sum('amount'))['tot'] or Decimal('0.00')

        transport_vouchers = vouchers.filter(category=ExpenseCategory.TRANSPORT)
        transport_amt = transport_vouchers.aggregate(tot=Sum('amount'))['tot'] or Decimal('0.00')

        sundry_vouchers = vouchers.filter(
            category__in=[
                ExpenseCategory.FUEL,
                ExpenseCategory.DOCUMENTATION,
                ExpenseCategory.OTHER,
            ]
        )
        sundry_amt = sundry_vouchers.aggregate(tot=Sum('amount'))['tot'] or Decimal('0.00')

    duty_reimb = Decimal('0.00')
    total_bill = agency_fee + shipping_line_amt + port_charges_amt + terminal_handling_amt + transport_amt + sundry_amt + duty_reimb

    invoice = existing_invoice
    today = date.today()
    if not invoice:
        inv_no = ClientInvoice.generate_next_invoice_number()

        vehicle_name = f"{job.vehicle_make or ''} {job.vehicle_model or ''}".strip() or (job.cargo_description or job.chassis_number or 'Shipment')
        invoice = ClientInvoice.objects.create(
            invoice_number=inv_no,
            job=job,
            customer=job.customer,
            issue_date=today,
            due_date=today + timedelta(days=14),
            amount_clearing_agency_fee=agency_fee,
            amount_shipping_line_do=shipping_line_amt,
            amount_port_charges=port_charges_amt,
            amount_terminal_handling=terminal_handling_amt,
            amount_transport=transport_amt,
            amount_sundry_charges=sundry_amt,
            amount_duty_reimbursement=duty_reimb,
            total_amount=total_bill,
            amount_paid=Decimal('0.00'),
            status='ISSUED',
            notes=f"Customs Clearance, Port Disbursements & Logistics for {vehicle_name} | Chassis: {job.chassis_number or '—'} | B/L: {job.bl_number}."
        )
    else:
        invoice.amount_clearing_agency_fee = agency_fee
        invoice.amount_shipping_line_do = shipping_line_amt
        invoice.amount_port_charges = port_charges_amt
        invoice.amount_terminal_handling = terminal_handling_amt
        invoice.amount_transport = transport_amt
        invoice.amount_sundry_charges = sundry_amt
        invoice.amount_duty_reimbursement = duty_reimb
        invoice.total_amount = total_bill
        if invoice.amount_paid >= total_bill and total_bill > 0:
            invoice.status = 'PAID'
        elif invoice.amount_paid > 0:
            invoice.status = 'PARTIALLY_PAID'
        else:
            invoice.status = 'ISSUED'
        invoice.save()

    return invoice











@login_required



@role_required([UserRole.OPERATIONS_MGR, UserRole.CEO, UserRole.ADMIN, UserRole.PORT_OFFICER, UserRole.FINANCE])



def yard_operations_view(request):



    tab = request.GET.get('tab', 'ready')



    search_q = request.GET.get('q', '').strip()







    base_qs = JobShipment.objects.select_related('customer', 'port_officer').prefetch_related('invoices', 'expenses')







    # Automatically ensure final bill is compiled for any active job



    for j in base_qs.filter(Q(vehicle_dispatched_to_office=True) | Q(vehicle_arrived_at_office=True)):



        if not j.invoices.exists():



            auto_compile_customer_final_bill(j)







    ready_count = base_qs.filter(vehicle_arrived_at_office=True, status__in=['ACTIVE', 'DELAYED']).count()







    bond_count = base_qs.filter(



        vehicle_arrived_at_office=True,



        clearance_mode='BOND',



        status__in=['ACTIVE', 'DELAYED']



    ).count()







    en_route_count = base_qs.filter(



        vehicle_dispatched_to_office=True,



        vehicle_arrived_at_office=False,



        status__in=['ACTIVE', 'DELAYED']



    ).count()







    delivered_count = base_qs.filter(status='COMPLETED').count()







    if tab == 'en_route':



        vehicles = base_qs.filter(



            vehicle_dispatched_to_office=True,



            vehicle_arrived_at_office=False,



            status__in=['ACTIVE', 'DELAYED']



        ).order_by('-vehicle_dispatched_at', '-updated_at')



    elif tab == 'delivered':



        vehicles = base_qs.filter(status='COMPLETED').order_by('-delivered_date', '-updated_at')



    else:

        vehicles = base_qs.filter(vehicle_arrived_at_office=True, status__in=['ACTIVE', 'DELAYED']).order_by('-vehicle_arrived_at', '-updated_at')







    if search_q:



        vehicles = vehicles.filter(



            Q(job_number__icontains=search_q) |



            Q(chassis_number__icontains=search_q) |



            Q(bl_number__icontains=search_q) |



            Q(customer__company_name__icontains=search_q) |



            Q(cargo_description__icontains=search_q) |



            Q(box_number__icontains=search_q) |



            Q(received_by_name__icontains=search_q)



        )







    context = {



        'tab': tab,



        'vehicles': vehicles,



        'ready_count': ready_count,



        'bond_count': bond_count,



        'en_route_count': en_route_count,



        'delivered_count': delivered_count,



        'search_q': search_q,



    }



    return render(request, 'core/yard_operations.html', context)











@login_required



@role_required([UserRole.OPERATIONS_MGR, UserRole.CEO, UserRole.ADMIN, UserRole.FINANCE, UserRole.PORT_OFFICER])



def yard_receive_payment_action(request, job_id):



    if request.method == 'POST':



        job = get_object_or_404(JobShipment, id=job_id)



        invoice = auto_compile_customer_final_bill(job)







        amount_str = request.POST.get('amount', '').strip()



        method = request.POST.get('payment_method', 'CASH')



        reference = request.POST.get('payment_reference', '').strip() or f"RCPT-{timezone.now().strftime('%d%m%H%M')}"



        notes = request.POST.get('notes', '').strip() or "Customer settlement at Malkia Yard"







        remaining = max(Decimal('0.00'), invoice.total_amount - invoice.amount_paid)



        try:



            amount = Decimal(amount_str) if amount_str else remaining



        except Exception:



            amount = remaining







        if amount > 0:



            ClientPayment.objects.create(



                invoice=invoice,



                amount=amount,



                payment_date=timezone.now().date(),



                payment_method=method,



                payment_reference=reference,



                notes=notes,



                recorded_by=request.user



            )







            invoice.amount_paid += amount



            if invoice.amount_paid >= invoice.total_amount:



                invoice.status = 'PAID'



            else:



                invoice.status = 'PARTIALLY_PAID'



            invoice.save()







            log_audit(request, "RECORD_PAYMENT", f"Received TSh {amount:,.2f} ({method} - Ref: {reference}) from customer for {job.chassis_number or job.job_number}", job=job)



            messages.success(request, f"💵 TSh {amount:,.0f} ({method}) imepokelewa na kurekodiwa! Bakaa iliyobaki: TSh {max(Decimal('0'), invoice.total_amount - invoice.amount_paid):,.0f}.")



        else:



            messages.info(request, "Bili hii tayari imelipwa kamili.")







        return redirect('yard_operations')



    return redirect('yard_operations')











@login_required



@role_required([UserRole.OPERATIONS_MGR, UserRole.CEO, UserRole.ADMIN, UserRole.PORT_OFFICER])



def yard_handover_action(request, job_id):

    if request.method == 'POST':

        job = get_object_or_404(JobShipment, id=job_id)

        action_type = request.POST.get('action_type', 'HANDOVER')



        if action_type == 'CONFIRM_ARRIVAL':

            now = timezone.now()

            job.vehicle_arrived_at_office = True

            job.vehicle_arrived_at = now

            st8 = job.stages.filter(stage_number=8).first()

            if st8:

                st8.status = 'COMPLETED'

                st8.completed_at = now

                st8.completed_by = request.user

                st8.responsible_officer = request.user

                st8.remarks = "Confirmed vehicle arrived safely at Malkia Yard."

                st8.save()

            if job.current_stage_number <= 8:

                job.current_stage_number = 9

                st9 = job.stages.filter(stage_number=9).first()

                if st9:

                    st9.status = 'IN_PROGRESS'

                    st9.started_at = now

                    st9.save()

            job.save()

            auto_compile_customer_final_bill(job)

            log_audit(request, "YARD_ARRIVAL_RECORDED", f"Confirmed vehicle {job.chassis_number or job.job_number} arrived safely at Malkia Yard", job=job)

            log_audit(request, "YARD_ARRIVAL", f"Confirmed vehicle {job.chassis_number or job.job_number} arrived safely at Malkia Yard", job=job)

            messages.success(request, f"Vehicle {job.chassis_number or job.job_number} marked as arrived at Malkia Yard (Stage 8 Completed)! Cost breakdown compiled.")

            return redirect('yard_operations')



        received_by = request.POST.get('received_by_name', '').strip()

        id_number = request.POST.get('id_number', '').strip()

        phone_number = request.POST.get('phone_number', '').strip()

        pod_file = request.FILES.get('pod_file')

        notes = request.POST.get('notes', '').strip()

        settle_payment_now = request.POST.get('settle_payment_now') == 'YES'



        if not received_by:

            messages.error(request, "Receiver name is required for customer handover.")

            return redirect('yard_operations')



        invoice = auto_compile_customer_final_bill(job)

        if settle_payment_now:

            remaining = max(Decimal('0.00'), invoice.total_amount - invoice.amount_paid)

            if remaining > 0:

                pay_method = request.POST.get('handover_payment_method', 'CASH')

                ClientPayment.objects.create(

                    invoice=invoice,

                    amount=remaining,

                    payment_date=timezone.now().date(),

                    payment_method=pay_method,

                    payment_reference=f"HANDOVER-PAY-{timezone.now().strftime('%d%m%H%M')}",

                    notes="Paid full settlement to Yard Officer upon vehicle key collection",

                    recorded_by=request.user

                )

                invoice.amount_paid += remaining

                invoice.status = 'PAID'

                invoice.save()



        box_number = request.POST.get('box_number', '').strip()

        if box_number:

            job.box_number = box_number



        full_note = f"Received by: {received_by} | ID: {id_number} | Phone: {phone_number} | Storage: {box_number}. Notes: {notes}".strip()



        now = timezone.now()

        job.received_by_name = received_by

        job.delivered_date = now

        job.status = 'COMPLETED'

        job.current_stage_number = 9



        st9 = job.stages.filter(stage_number=9).first()

        if pod_file:

            job.proof_of_delivery_image = pod_file

            JobDocument.objects.create(

                job=job,

                stage=st9,

                document_type='OTHER',

                title=f"Signed POD / Handover Photo - {job.chassis_number or job.job_number}",

                file=pod_file,

                uploaded_by=request.user,

                notes=full_note

            )



        for s_num in [8, 9]:

            st_obj = job.stages.filter(stage_number=s_num).first()

            if st_obj:

                st_obj.status = 'COMPLETED'

                st_obj.completed_at = now

                st_obj.completed_by = request.user

                st_obj.responsible_officer = request.user

                st_obj.remarks = full_note

                st_obj.save()



        job.closure_notes = full_note

        job.save()



        try:

            from .email_service import send_stage_update_email

            send_stage_update_email(job, 9, extra_note=f"Gari lako ({job.cargo_description or job.chassis_number}) limekabidhiwa kwa mafanikio kwa {received_by}. Asante kwa kuchagua Malkia C&F.")

        except Exception as e:

            print(f"[Email Notification Error] {e}")



        log_audit(request, "VEHICLE_HANDOVER", f"Vehicle {job.job_number} ({job.chassis_number}) handed over to customer {received_by} (ID: {id_number})", job=job)

        messages.success(request, f"🎉 Gari {job.chassis_number or job.job_number} limekabidhiwa rasmi kwa {received_by}! Faili limefungwa kikamilifu.")

        return redirect('yard_operations')



    return redirect('yard_operations')







@login_required



@role_required([UserRole.OPERATIONS_MGR, UserRole.CEO, UserRole.ADMIN, UserRole.FINANCE, UserRole.PORT_OFFICER])



def yard_update_agency_fee_action(request, job_id):



    if request.method == 'POST':



        from decimal import Decimal



        job = get_object_or_404(JobShipment, id=job_id)



        fee_str = request.POST.get('agency_fee', '0').strip()



        try:



            fee = Decimal(fee_str)



        except Exception:



            fee = Decimal('350000.00')







        job.contracted_revenue = fee



        job.save()







        auto_compile_customer_final_bill(job)







        log_audit(request, "UPDATE_AGENCY_FEE", f"Updated Agency Fee to TSh {fee:,.2f} for {job.chassis_number or job.job_number}", job=job)



        messages.success(request, f"✅ Ada ya Kampuni (Agency Fee) imesasishwa kuwa TSh {fee:,.0f}!")



        return redirect('yard_operations')



    return redirect('yard_operations')







@login_required



@role_required([UserRole.OPERATIONS_MGR, UserRole.CEO, UserRole.ADMIN, UserRole.PORT_OFFICER, UserRole.DOC_OFFICER])



def yard_update_box_action(request, job_id):



    if request.method == 'POST':



        job = get_object_or_404(JobShipment, id=job_id)



        box = request.POST.get('box_number', '').strip()



        job.box_number = box



        job.save()



        log_audit(request, "UPDATE_BOX_LOCATION", f"Updated physical file storage location to '{box}' for {job.chassis_number or job.job_number}", job=job)



        messages.success(request, f"📁 Eneo la kuhifadhia jalada (Kabati / Rafu) limesasishwa: {box}")



        return redirect('yard_operations')



    return redirect('yard_operations')







@login_required



@role_required([UserRole.OPERATIONS_MGR, UserRole.CEO, UserRole.ADMIN, UserRole.FINANCE, UserRole.PORT_OFFICER, UserRole.DOC_OFFICER, UserRole.CLEARING_OFFICER])



def print_invoice_view(request, invoice_id):



    from decimal import Decimal



    invoice = get_object_or_404(ClientInvoice, id=invoice_id)



    job = invoice.job



    customer = invoice.customer



    payments = invoice.payments.all().order_by('-payment_date')



    balance_due = max(Decimal('0.00'), invoice.total_amount - invoice.amount_paid)







    context = {



        'invoice': invoice,



        'job': job,



        'customer': customer,



        'payments': payments,



        'balance_due': balance_due,



    }



    return render(request, 'core/print_client_invoice.html', context)











@login_required



@role_required([UserRole.OPERATIONS_MGR, UserRole.CEO, UserRole.ADMIN, UserRole.FINANCE, UserRole.PORT_OFFICER, UserRole.DOC_OFFICER, UserRole.CLEARING_OFFICER])



def print_job_invoice_view(request, job_id):



    job = get_object_or_404(JobShipment, id=job_id)



    invoice = auto_compile_customer_final_bill(job)



    return redirect('print_invoice', invoice_id=invoice.id)











def root_entry_view(request):



    """



    Smart Domain Router for Unified Malkia System:



    - If accessed via 'portal.malkiacargowave.com' -> Directs to Staff Portal (Dashboard if logged in, else Login)



    - If accessed via 'malkiacargowave.com' (or other domain/IP) -> Serves Corporate Website



    """



    host = request.get_host().lower()



    if 'portal' in host:



        if request.user.is_authenticated:



            return dashboard_view(request)

        return redirect('login')

    return public_website_view(request)











def public_website_view(request):

    """

    Serves the standalone official corporate website for Malkia Cargo Wave Limited

    with dynamic Google Search Console & Bing Webmaster verification tags injected.

    """

    import os

    from django.conf import settings

    website_path = os.path.join(settings.BASE_DIR, 'website', 'index.html')

    if os.path.exists(website_path):

        with open(website_path, 'r', encoding='utf-8') as f:

            content = f.read()



        google_verify = SystemConfig.get_value('GOOGLE_SITE_VERIFICATION', '').strip()

        bing_verify = SystemConfig.get_value('BING_SITE_VERIFICATION', '').strip()

        indexnow_key = SystemConfig.get_value('INDEXNOW_KEY', 'malkia2026seokey8899').strip()



        dynamic_tags = []

        if google_verify:

            clean_g = google_verify.replace('<meta name="google-site-verification" content="', '').replace('">', '').replace('"', '').strip()

            dynamic_tags.append(f'<meta name="google-site-verification" content="{clean_g}">')

        if bing_verify:

            clean_b = bing_verify.replace('<meta name="msvalidate.01" content="', '').replace('">', '').replace('"', '').strip()

            dynamic_tags.append(f'<meta name="msvalidate.01" content="{clean_b}">')

        if indexnow_key:

            dynamic_tags.append(f'<link rel="indexnow" href="/{indexnow_key}.txt">')



        if dynamic_tags:

            content = content.replace('<!-- SEO_DYNAMIC_VERIFICATION_TAGS -->', '\n    '.join(dynamic_tags))



        response = HttpResponse(content, content_type='text/html; charset=utf-8')

        response['X-Robots-Tag'] = 'index, follow, max-image-preview:large, max-snippet:-1'

        return response

    return redirect('dashboard')





def robots_txt_view(request):

    """

    Serves /robots.txt for Googlebot, Bingbot, and all search engine crawlers.

    """

    canonical_domain = SystemConfig.get_value('SEO_CANONICAL_DOMAIN', 'https://malkiacargowave.com').rstrip('/')

    lines = [

        "# Malkia Cargo Wave Limited - Official Robots.txt",

        "User-agent: *",

        "Allow: /",

        "Allow: /website/",

        "Allow: /portal/",

        "Allow: /sitemap.xml",

        "Allow: /manifest.json",

        "Disallow: /dashboard/",

        "Disallow: /jobs/",

        "Disallow: /finance/",

        "Disallow: /customs/",

        "Disallow: /field/",

        "Disallow: /yard/",

        "Disallow: /staff/",

        "Disallow: /settings/",

        "Disallow: /audit/",

        "Disallow: /admin-operations/",

        "Disallow: /switch-role/",

        "",

        "User-agent: Googlebot",

        "Allow: /",

        "Allow: /website/",

        "Allow: /portal/",

        "",

        "User-agent: Bingbot",

        "Allow: /",

        "Allow: /website/",

        "Allow: /portal/",

        "",

        f"Sitemap: {canonical_domain}/sitemap.xml",

    ]

    return HttpResponse("\n".join(lines), content_type="text/plain; charset=utf-8")





def sitemap_xml_view(request):

    """

    Serves /sitemap.xml and /sitemap-main.xml with strict Sitemaps 0.9 schema

    (matching the exact domain host so Google Search Console URL-prefix properties validate 100%).

    """

    host = request.get_host().lower()

    if 'portal.malkiacargowave.com' in host:

        base_domain = 'https://portal.malkiacargowave.com'

    else:

        base_domain = SystemConfig.get_value('SEO_CANONICAL_DOMAIN', 'https://malkiacargowave.com').rstrip('/')



    today_iso = timezone.now().strftime('%Y-%m-%d')



    xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>

<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">

  <url>

    <loc>{base_domain}/</loc>

    <lastmod>{today_iso}</lastmod>

    <changefreq>daily</changefreq>

    <priority>1.0</priority>

  </url>

  <url>

    <loc>{base_domain}/website/</loc>

    <lastmod>{today_iso}</lastmod>

    <changefreq>weekly</changefreq>

    <priority>0.9</priority>

  </url>

  <url>

    <loc>{base_domain}/portal/</loc>

    <lastmod>{today_iso}</lastmod>

    <changefreq>daily</changefreq>

    <priority>0.8</priority>

  </url>

</urlset>"""

    resp = HttpResponse(xml_content.strip(), content_type="application/xml; charset=utf-8")

    resp["Cache-Control"] = "no-cache, no-store, must-revalidate"

    resp["X-Robots-Tag"] = "noindex"

    return resp





def bing_site_auth_xml_view(request):

    """

    Serves /BingSiteAuth.xml for Bing Webmaster Tools XML file verification.

    """

    bing_code = SystemConfig.get_value('BING_SITE_VERIFICATION', 'BING_VERIFICATION_CODE').strip()

    xml_content = f"""<?xml version="1.0"?>

<users>

    <user>{bing_code}</user>

</users>"""

    return HttpResponse(xml_content, content_type="application/xml; charset=utf-8")





def google_verification_file_view(request, token):

    """

    Serves /google<token>.html ONLY for the exact authorized Google Search Console token.

    Returns 404 for any other random probe (required by Google Search Console security check).

    """

    configured_token = SystemConfig.get_value('GOOGLE_SITE_VERIFICATION', '').replace('google', '').replace('.html', '').strip()

    allowed_tokens = {'45f3f04c3ca65559'}

    if configured_token:

        allowed_tokens.add(configured_token)



    if token not in allowed_tokens:

        return HttpResponse("404 Not Found", status=404, content_type="text/plain; charset=utf-8")



    filename = f"google{token}.html"

    return HttpResponse(f"google-site-verification: {filename}", content_type="text/html; charset=utf-8")





def indexnow_key_txt_view(request):

    """

    Serves /indexnow-key.txt for instant Bing & Yandex IndexNow verification.

    """

    key = SystemConfig.get_value('INDEXNOW_KEY', 'malkia2026seokey8899').strip()

    return HttpResponse(key, content_type="text/plain; charset=utf-8")





def web_manifest_json_view(request):

    """

    Serves /manifest.json for Mobile SEO, Google Search, Bing, and Progressive Web App metadata.

    """

    manifest = {

        "name": "Malkia Cargo Waves Ltd",

        "short_name": "Malkia Cargo",

        "description": "Malkia Cargo Waves Ltd, Crossing borders with no limit — Utoaji wa Magari Bandari ya Dar es Salaam, Yadi ya In-Bond, na Usafirishaji Salama.",

        "start_url": "/",

        "display": "standalone",

        "background_color": "#FFFFFF",

        "theme_color": "#1E3A8A",

        "lang": "sw-TZ",

        "icons": [

            {

                "src": "/static/images/favicon-48.png",

                "sizes": "48x48",

                "type": "image/png"

            },

            {

                "src": "/static/images/favicon-96.png",

                "sizes": "96x96",

                "type": "image/png"

            },

            {

                "src": "/static/images/favicon-192.png",

                "sizes": "192x192",

                "type": "image/png",

                "purpose": "any maskable"

            },

            {

                "src": "/static/images/favicon-512.png",

                "sizes": "512x512",

                "type": "image/png",

                "purpose": "any maskable"

            }

        ]

    }

    return JsonResponse(manifest)





def favicon_ico_view(request):

    """

    Serves /favicon.ico directly from root domain for Google Search Console, Bing Webmaster & Browsers.

    """

    ico_path = os.path.join(settings.BASE_DIR, 'static', 'images', 'favicon.ico')

    if os.path.exists(ico_path):

        with open(ico_path, 'rb') as f:

            resp = HttpResponse(f.read(), content_type="image/x-icon")

            resp["Cache-Control"] = "public, max-age=86400"

            return resp

    return HttpResponse(status=404)





def apple_touch_icon_view(request):

    """

    Serves /apple-touch-icon.png directly from root domain.

    """

    png_path = os.path.join(settings.BASE_DIR, 'static', 'images', 'apple-touch-icon.png')

    if os.path.exists(png_path):

        with open(png_path, 'rb') as f:

            resp = HttpResponse(f.read(), content_type="image/png")

            resp["Cache-Control"] = "public, max-age=86400"

            return resp

    return HttpResponse(status=404)





def official_logo_png_view(request):

    """

    Serves /logo.png directly from root domain for Schema.org Organization logo & Search Engines.

    """

    png_path = os.path.join(settings.BASE_DIR, 'static', 'images', 'malkia_logo_square.png')

    if os.path.exists(png_path):

        with open(png_path, 'rb') as f:

            resp = HttpResponse(f.read(), content_type="image/png")

            resp["Cache-Control"] = "public, max-age=86400"

            return resp

    return HttpResponse(status=404)





@login_required

@role_required([UserRole.CEO, UserRole.ADMIN])

def save_seo_settings_action(request):

    """

    Saves Google Search Console, Bing Webmaster Tools, Canonical Domain, and triggers IndexNow ping.

    """

    if request.method == 'POST':

        action_mode = request.POST.get('action_mode', 'save')

        canonical_domain = request.POST.get('seo_canonical_domain', 'https://malkiacargowave.com').strip().rstrip('/')

        portal_domain = request.POST.get('seo_portal_domain', 'https://portal.malkiacargowave.com').strip().rstrip('/')

        google_verify = request.POST.get('google_site_verification', '').strip()

        bing_verify = request.POST.get('bing_site_verification', '').strip()

        indexnow_key = request.POST.get('indexnow_key', 'malkia2026seokey8899').strip() or 'malkia2026seokey8899'



        # Clean if user pasted full <meta ...> tag instead of just the token

        if 'content="' in google_verify:

            google_verify = google_verify.split('content="')[1].split('"')[0].strip()

        if 'content="' in bing_verify:

            bing_verify = bing_verify.split('content="')[1].split('"')[0].strip()



        SystemConfig.set_value('SEO_CANONICAL_DOMAIN', canonical_domain, category='SEO', description='Primary Website Domain')

        SystemConfig.set_value('SEO_PORTAL_DOMAIN', portal_domain, category='SEO', description='Portal Subdomain')

        SystemConfig.set_value('GOOGLE_SITE_VERIFICATION', google_verify, category='SEO', description='Google Search Console Verification Code')

        SystemConfig.set_value('BING_SITE_VERIFICATION', bing_verify, category='SEO', description='Bing Webmaster Tools Verification Code')

        SystemConfig.set_value('INDEXNOW_KEY', indexnow_key, category='SEO', description='Bing IndexNow API Key')



        log_audit(request, "UPDATE_SEO_SETTINGS", f"Updated SEO & Search Console settings for {canonical_domain}")



        if action_mode == 'ping':

            import requests as req_lib

            host_only = canonical_domain.replace('https://', '').replace('http://', '').split('/')[0]

            ping_payload = {

                "host": host_only,

                "key": indexnow_key,

                "keyLocation": f"{canonical_domain}/indexnow-key.txt",

                "urlList": [

                    f"{canonical_domain}/",

                    f"{canonical_domain}/website/",

                    f"{canonical_domain}/portal/",

                ]

            }

            try:

                resp = req_lib.post("https://api.indexnow.org/indexnow", json=ping_payload, timeout=10)

                if resp.status_code in [200, 202]:

                    messages.success(request, f"✅ Mipangilio ya SEO imehifadhiwa na Bing/IndexNow imepokea Sitemap ya {canonical_domain} papo hapo!")

                else:

                    messages.info(request, f"✅ Mipangilio ya SEO imehifadhiwa! (IndexNow Status: HTTP {resp.status_code} - hakikisha domain {host_only} iko live).")

            except Exception as e:

                messages.warning(request, f"✅ Mipangilio ya SEO imehifadhiwa, lakini IndexNow ping ilishindwa kuunganishwa: {e}")

        else:

            messages.success(request, "✅ Mipangilio ya SEO (Google Search Console & Bing Webmaster) imehifadhiwa kikamilifu!")



        return redirect('/settings/?tab=seo')



    return redirect('system_settings')











@csrf_exempt



def public_website_ai_chat_api(request):



    """



    Public Customer AI Assistant for Malkia Cargo Wave Limited website.



    Answers public customer questions regarding motor vehicle port clearance,



    TRA duty calculation, private in-bond yard storage, shipment tracking,



    office location, contact numbers, and security against theft.



    """



    if request.method != 'POST':



        return JsonResponse({'status': 'error', 'message': 'POST only.'}, status=405)







    try:



        data = json.loads(request.body.decode('utf-8'))



    except Exception:



        data = request.POST







    user_message = data.get('message', '').strip()



    if not user_message:



        return JsonResponse({'status': 'error', 'message': 'Message cannot be empty.'})







    # 1. Check if user is asking to track a vehicle / shipment (B/L, chassis, or file number)



    words = [w.strip(".,;:?!'\"()[]{}") for w in user_message.split()]



    found_job = None



    for w in words:



        if len(w) >= 5:



            match = JobShipment.objects.filter(



                Q(bl_number__iexact=w) |



                Q(chassis_number__iexact=w) |



                Q(job_number__iexact=w) |



                Q(containers__container_number__iexact=w)



            ).distinct().first()



            if match:



                found_job = match



                break







    if found_job:



        chassis = found_job.chassis_number or 'N/A'



        cargo = found_job.cargo_description or 'Motor Vehicle'



        status_text = found_job.get_operational_status_display() if hasattr(found_job, 'get_operational_status_display') else found_job.status



        stage_name = getattr(found_job, 'current_stage_name', 'In Progress')



        reply = (



            f"Taarifa za Usafirishaji zimepatikana! 🚗\n\n"



            f"• Gari: **{cargo}**\n"



            f"• Namba ya B/L: **{found_job.bl_number}**\n"



            f"• Chassis No: **{chassis}**\n"



            f"• Hatua ya Sasa: **{stage_name}**\n"



            f"• Hali: **{status_text}**\n\n"



            f"Gari lako lipo chini ya uangalizi salama wa Malkia Cargo Wave. "



            f"Kama unahitaji msaada zaidi au ratiba ya kulichukua, tupigie simu au WhatsApp kwa **+255 787 367 474**."



        )



        return JsonResponse({'status': 'success', 'reply': reply})







    # 2. Use Hive DeepSeek AI if available



    from django.conf import settings



    api_key = getattr(settings, 'HIVE_API_KEY', '')



    base_url = getattr(settings, 'HIVE_BASE_URL', 'https://api-cdn.thehive.ai/api/v3')



    model = getattr(settings, 'HIVE_MODEL', 'deepseek-ai/deepseek-v4.1-flash')







    system_prompt = """You are Malkia AI, the customer service assistant for Malkia Cargo Wave Limited (malkiacargowave.com).

Malkia Cargo Wave Limited is a licensed Clearing & Forwarding agency and customs broker in Dar es Salaam, Tanzania.

KEY FACTS ABOUT MALKIA CARGO WAVE LIMITED:
1. Core Service: Customs clearance (TRA & TBS) and port logistics for cargo, containers, and vehicles (mizigo na magari) at Dar es Salaam Port.
2. Transparent Process: Free TRA tax estimation and official GePG control numbers with no hidden fees.
3. Delivery: Safe delivery across Tanzania and neighboring countries.
4. Contact & Office: Bandari Road, Port Area, Dar es Salaam, Tanzania. Phone/WhatsApp: +255 787 367 474, Email: info@malkiacargowave.com.
5. Client Portal: portal.malkiacargowave.com.

STRICT RULES:
- Answer ONLY what the user asked. Do NOT write long bullet-point lists or unnecessary explanations.
- If the user just greets you (e.g. "mambo", "habari", "hi", "hello"), simply greet them back warmly in 1 short sentence and welcome them (e.g. "Poa sana! Karibu Malkia Cargo Wave Limited, tukuhudumie vipi leo?").
- NEVER mention "RORO", "in-bond yard", "bonded warehouse", or vehicle repair ("ukarabati"). Say "mizigo" or "mizigo na magari" instead.
- Match the user's language (natural Swahili or clear English).
- Keep every reply short, direct, and polite."""







    reply = None



    if api_key:



        try:



            import requests



            endpoint = f"{base_url.rstrip('/')}/chat/completions"



            headers = {



                "Authorization": f"Bearer {api_key}",



                "Content-Type": "application/json"



            }



            messages = [



                {"role": "system", "content": system_prompt},



                {"role": "user", "content": user_message}



            ]



            resp = requests.post(



                endpoint,



                headers=headers,



                json={"model": model, "messages": messages, "max_tokens": 800, "temperature": 0.4},



                timeout=25



            )



            if resp.status_code == 200:



                res_data = resp.json()



                reply = res_data.get('choices', [{}])[0].get('message', {}).get('content', '')



        except Exception as e:



            logger.warning(f"Hive AI error on website chat: {e}")







    # 3. Fallback smart response if AI call failed or timed out



    if not reply:



        msg_lower = user_message.lower().strip()

        if msg_lower in ['mambo', 'habari', 'vipi', 'salama', 'hi', 'hello', 'hey', 'hujambo', 'shikamoo', 'mambo vipi', 'habari gani']:
            reply = "Poa sana! Karibu Malkia Cargo Wave Limited, tukuhudumie vipi leo kuhusu utoaji wa mizigo?"
        elif any(w in msg_lower for w in ['gharama', 'cost', 'bei', 'price', 'duty', 'kodi', 'tra', 'quote', 'hesabu', 'calculate']):



            reply = (



                "Kuhusu **Gharama na Kodi ya TRA**:\n\n"



                "Kodi ya gari inategemea vigezo vinne vikuu vya TRA:\n"



                "1. Aina ya gari na modeli (mfano: IST, Harrier, Prado, Canter)\n"



                "2. Mwaka wa utengenezaji (Magari ya zaidi ya miaka 8 hulipiwa uchakavu/dumping fee)\n"



                "3. Ukubwa wa injini (CC za gari)\n"



                "4. Thamani ya gari (FOB / CIF value).\n\n"



                "👉 **Ushauri:** Tutumie nyaraka zako (Export Certificate au Invoice) kupitia WhatsApp **+255 787 367 474** au ujaze fomu hapo chini ili wataalamu wetu wakupigie na kukupa mchanganuo kamili na Control Number ya TRA bila malipo yoyote!"



            )



        elif any(w in msg_lower for w in ['usalama', 'safety', 'betri', 'battery', 'radio', 'redio', 'wizi', 'theft', 'taili', 'spare']):
            reply = (
                "Katika **Malkia Cargo Wave Limited**, tunakagua na kutunza mizigo na magari yote kwa umakini wa hali ya juu kuanzia bandarini hadi kukabidhiwa mikononi mwako."
            )



        elif any(w in msg_lower for w in ['wapi', 'location', 'ofisi', 'office', 'mahali', 'namba', 'simu', 'contact', 'phone', 'whatsapp', 'email']):



            reply = (



                "Ofisi na Mawasiliano ya **Malkia Cargo Wave Limited**:\n\n"



                "📍 **Ofisi:** Bandari Road, Karibu na Lango la Bandari ya Dar es Salaam, Tanzania.\n"



                "📞 **Simu & WhatsApp:** +255 787 367 474\n"



                "✉️ **Barua Pepe:** info@malkiacargowave.com\n"



                "🌐 **Tovuti:** malkiacargowave.com\n\n"



                "Milango yetu ipo wazi Jumatatu hadi Jumamosi, kuanzia saa 2:00 Asubuhi hadi 11:30 Jioni."



            )



        elif any(w in msg_lower for w in ['track', 'fuatilia', 'wapi gari', 'status']):



            reply = (



                "Ili kufuatilia gari lako, tafadhali andika namba ya **Bill of Lading (B/L)** au namba ya **Chassis** hapa kwenye chat, au tumia sehemu ya 'Track Your Vehicle' hapo juu kwenye ukurasa wetu.\n\n"



                "Mfano wa namba: `JILI-KEI` au `GDJ150-0082914`.\n"



                "Mfumo wetu utakuonyesha moja kwa moja hatua ya gari lako!"



            )



        else:
            reply = (
                "Karibu **Malkia Cargo Wave Limited**! Tunashughulikia utoaji wa mizigo na magari bandarini Dar es Salaam. "
                "Tuambie unahitaji msaada gani leo au wasiliana nasi kwa WhatsApp **+255 787 367 474**."
            )







    return JsonResponse({'status': 'success', 'reply': reply})







_PULSE_CACHE = {'ts': 0.0, 'version': None, 'payload': None}


def api_realtime_pulse(request):
    """
    Ultra-lightweight real-time synchronization pulse endpoint for connected staff & client consoles.
    Caches version state briefly (2s) so polling bursts do not hammer the database.
    """
    client_version = request.GET.get('v', '').strip()
    now_ts = time_module.monotonic()

    if _PULSE_CACHE['version'] is not None and (now_ts - _PULSE_CACHE['ts']) < 2.0:
        current_version = _PULSE_CACHE['version']
        if client_version and client_version == current_version:
            return JsonResponse({'has_change': False, 'version': current_version})
        if _PULSE_CACHE['payload'] is not None:
            return JsonResponse(_PULSE_CACHE['payload'])

    latest_audit_row = AuditLog.objects.order_by('-id').values_list('id', 'timestamp').first()
    latest_exp_id = ExpenseVoucher.objects.order_by('-id').values_list('id', flat=True).first()
    latest_job_ts = JobShipment.objects.order_by('-updated_at').values_list('updated_at', flat=True).first()

    audit_ts = int(latest_audit_row[1].timestamp()) if latest_audit_row else 0
    audit_id = latest_audit_row[0] if latest_audit_row else 0
    exp_id = latest_exp_id or 0
    job_ts = int(latest_job_ts.timestamp()) if latest_job_ts else 0

    current_version = f"{audit_ts}_{audit_id}_{exp_id}_{job_ts}"

    if client_version and client_version == current_version:
        _PULSE_CACHE['ts'] = now_ts
        _PULSE_CACHE['version'] = current_version
        return JsonResponse({'has_change': False, 'version': current_version})

    latest_audit = AuditLog.objects.filter(id=audit_id).select_related('user', 'job').first() if audit_id else None

    event_info = None
    if latest_audit:
        actor_name = ""
        if latest_audit.user:
            fn = latest_audit.user.get_full_name().strip()
            actor_name = fn if fn and fn not in ['Super Administrator', 'IT Administrator'] else latest_audit.user.username
        if not actor_name:
            actor_name = "Operations Team"

        clean_details = latest_audit.details or latest_audit.action
        event_info = {
            'id': latest_audit.id,
            'action': latest_audit.action,
            'actor': actor_name,
            'job_id': latest_audit.job_id,
            'job_number': latest_audit.job.job_number if latest_audit.job else "",
            'details': clean_details,
            'timestamp': latest_audit.timestamp.isoformat(),
        }

    requested_vouchers = ExpenseVoucher.objects.filter(approval_status='REQUESTED').count()
    verified_vouchers = ExpenseVoucher.objects.filter(approval_status='VERIFIED', is_paid=False).count()
    active_jobs = JobShipment.objects.filter(status__in=['ACTIVE', 'DELAYED']).count()

    payload = {
        'has_change': True,
        'version': current_version,
        'latest_event': event_info,
        'counts': {
            'pending_finance': requested_vouchers,
            'pending_ceo': verified_vouchers,
            'active_jobs': active_jobs,
        }
    }
    _PULSE_CACHE['ts'] = now_ts
    _PULSE_CACHE['version'] = current_version
    _PULSE_CACHE['payload'] = payload

    return JsonResponse(payload)



# ==============================================================================
# DEDICATED 5-STAGE OPERATIONAL PIPELINE CONSOLES
# Each stage has its own dedicated queue with 1-click Finish button
# ==============================================================================

def _ensure_stage_definition_exists(stage_number):
    stage_def = WorkflowStageDefinition.objects.filter(stage_number=stage_number).first()
    if stage_def:
        return stage_def

    stage_defaults = {
        1: ("File Opening & Doc Intake", "Upokeaji Nyaraka & Kufungua Jalada", 1, "folder-plus", UserRole.DOC_OFFICER, "Client document intake, file opening, and digital dossier registration.", False),
        2: ("Customs Declaration (TANSAD)", "Declaration ya TANSAD", 2, "file-invoice", UserRole.CLEARING_OFFICER, "Customs declaration lodge (TANSAD) and tax assessment verification.", False),
        3: ("TBS Inspection & Clearance", "Ukaguzi na Kibali cha TBS", 1, "shield-halved", UserRole.PORT_OFFICER, "TBS portal clearance, standards inspection, and approval before port exit.", False),
        4: ("Port Clearance & Gate Exit", "Bandarini & Kutoka Geti (D/O, Ukaguzi, Malipo & Gate Pass)", 1, "anchor", UserRole.PORT_OFFICER, "D/O collection, wharfage clearance, physical verification, and gate pass exit.", True),
        5: ("Vehicle Arrival (Yard / Office)", "Gari Kufika Yadi / Ofisini", 1, "warehouse", UserRole.OPERATIONS_MGR, "Vehicle intake at Malkia yard with condition inspection.", False),
        6: ("Customer Handover", "Kukabidhi Gari kwa Mteja & POD", 1, "handshake", UserRole.OPERATIONS_MGR, "Final handover to customer, POD signing, and file closing.", True),
    }

    vals = stage_defaults.get(stage_number, (f"Stage {stage_number}", f"Hatua {stage_number}", 1, "layer-group", UserRole.OPERATIONS, "", False))
    stage_def, _ = WorkflowStageDefinition.objects.get_or_create(
        stage_number=stage_number,
        defaults={
            'name_en': vals[0],
            'name_sw': vals[1],
            'target_days': vals[2],
            'icon': vals[3],
            'required_role': vals[4],
            'description': vals[5],
            'is_controlled_gate': vals[6],
        }
    )
    return stage_def


@login_required
@role_required([UserRole.OPERATIONS, UserRole.CEO, UserRole.ADMIN])
def stage_pipeline_view(request, stage_number):
    stage_def = _ensure_stage_definition_exists(stage_number)
    q = request.GET.get('q', '').strip()

    from django.db.models import Case, When, BooleanField, Value

    jobs = JobShipment.objects.filter(
        current_stage_number__gte=stage_number,
        status__in=['ACTIVE', 'DELAYED', 'COMPLETED'],
    ).select_related('customer', 'documentation_officer', 'clearing_officer', 'port_officer')

    if q:
        jobs = jobs.filter(
            Q(job_number__icontains=q) |
            Q(bl_number__icontains=q) |
            Q(chassis_number__icontains=q) |
            Q(customer__company_name__icontains=q) |
            Q(cargo_description__icontains=q)
        )

    jobs = jobs.annotate(
        stage_completed=Case(
            When(Q(current_stage_number__gt=stage_number) | Q(status='COMPLETED'), then=Value(True)),
            default=Value(False),
            output_field=BooleanField(),
        )
    ).order_by('stage_completed', '-updated_at', '-created_at')

    has_assignment_stage = stage_number in (2, 3, 4)
    can_assign_declarer = has_assignment_stage and _can_assign_stage(request.user, stage_number)
    show_all_stage2_workload = has_assignment_stage
    selected_declarer = (request.GET.get('declarer') or '').strip()
    declarers = []
    declarer_stats = []
    unassigned_count = 0
    my_pending_count = 0

    if has_assignment_stage:
        from django.db.models import Count
        officer_field = 'clearing_officer' if stage_number == 2 else ('tbs_officer' if stage_number == 3 else 'port_officer')
        officer_id_field = f'{officer_field}_id'
        all_stage_jobs = jobs
        unassigned_count = all_stage_jobs.filter(stage_completed=False, **{f'{officer_field}__isnull': True}).count()
        my_pending_count = all_stage_jobs.filter(stage_completed=False, **{officer_field: request.user}).count()

        ops_roles = [
            UserRole.OPERATIONS, UserRole.CLEARING_OFFICER, UserRole.OPERATIONS_MGR,
            UserRole.DOC_OFFICER, UserRole.PORT_OFFICER, UserRole.DISPATCH_OFFICER,
        ]
        declarers = list(
            User.objects.filter(
                is_active=True,
                profile__role__in=ops_roles,
            ).exclude(username__startswith='test_').order_by('first_name', 'username')
        )

        counts_qs = (
            all_stage_jobs.filter(**{f'{officer_field}__isnull': False})
            .values(officer_id_field, 'stage_completed')
            .annotate(cnt=Count('id'))
        )
        counts_map = {}
        for row in counts_qs:
            uid = row[officer_id_field]
            bucket = counts_map.setdefault(uid, {'pending': 0, 'completed': 0})
            if row['stage_completed']:
                bucket['completed'] += row['cnt']
            else:
                bucket['pending'] += row['cnt']

        for u in declarers:
            st = counts_map.get(u.id, {'pending': 0, 'completed': 0})
            declarer_stats.append({
                'id': u.id,
                'name': u.get_full_name() or u.username,
                'pending': st['pending'],
                'completed': st['completed'],
            })

        if selected_declarer == 'mine':
            jobs = jobs.filter(**{officer_field: request.user})
        elif selected_declarer == 'unassigned':
            jobs = jobs.filter(**{f'{officer_field}__isnull': True})
        elif selected_declarer.isdigit():
            jobs = jobs.filter(**{officer_id_field: int(selected_declarer)})

    stage_specs = {
        1: {
            'title': "1. Documentation & Intake (File Opening)",
            'desc': "Client document intake and digital dossier registration.",
            'icon': "fa-folder-open",
            'badge_bg': "#F59E0B",
            'finish_label': "✓ Complete Intake",
            'confirm_msg': "Confirm: Complete document intake and advance to Customs?",
        },
        2: {
            'title': "2. Customs Declaration (TANSAD)",
            'desc': "Customs declaration lodge and tax assessment verification.",
            'icon': "fa-stamp",
            'badge_bg': "#8B5CF6",
            'finish_label': "✓ Complete TANSAD",
            'confirm_msg': "Confirm: Complete TANSAD declaration for this consignment?",
        },
        3: {
            'title': "3. TBS Inspection & Clearance",
            'desc': "TBS portal clearance, standards inspection, and approval before port exit.",
            'icon': "fa-shield-halved",
            'badge_bg': "#0EA5E9",
            'finish_label': "✓ Approve TBS",
            'confirm_msg': "Confirm: Approve TBS clearance and advance to Port Clearance?",
        },
        4: {
            'title': "4. Port Clearance & Gate Exit",
            'desc': "D/O collection, wharfage clearance, physical verification, and gate pass exit.",
            'icon': "fa-anchor",
            'badge_bg': "#0284C7",
            'finish_label': "✓ Complete Port Clearance",
            'confirm_msg': "Confirm: Cargo has cleared gate exit and departed port?",
        },
        5: {
            'title': "5. Yard Arrivals & Inspection",
            'desc': "Vehicle intake at Malkia yard with condition inspection.",
            'icon': "fa-warehouse",
            'badge_bg': "#0D9488",
            'finish_label': "✓ Confirm Yard Arrival",
            'confirm_msg': "Confirm: Vehicle safely received at Malkia yard?",
        },
        6: {
            'title': "6. Customer Handover & Delivery",
            'desc': "Final handover to customer, POD signing, and file closing.",
            'icon': "fa-handshake",
            'badge_bg': "#16A34A",
            'finish_label': "✓ Complete Handover",
            'confirm_msg': "Confirm: Hand over vehicle to customer and close file?",
        },
    }

    spec = stage_specs.get(stage_number, {
        'title': f"Stage {stage_number}",
        'desc': "",
        'icon': "fa-layer-group",
        'badge_bg': "#2563EB",
        'finish_label': "✓ Complete Stage",
        'confirm_msg': "Confirm completion of this stage?",
    })

    context = {
        'stage_number': stage_number,
        'stage_def': stage_def,
        'stage_title': spec['title'],
        'stage_desc': spec['desc'],
        'stage_icon': spec['icon'],
        'badge_bg': spec['badge_bg'],
        'finish_label': spec['finish_label'],
        'confirm_msg': spec['confirm_msg'],
        'jobs': jobs,
        'search_q': q,
        'active_count': jobs.filter(stage_completed=False).count(),
        'total_count': jobs.count(),
        'has_assignment_stage': has_assignment_stage,
        'assign_url_name': 'assign_declarer' if stage_number == 2 else ('assign_tbs_officer' if stage_number == 3 else 'assign_port_officer'),
        'can_assign_declarer': can_assign_declarer,
        'show_all_stage2_workload': show_all_stage2_workload,
        'declarers': declarers,
        'declarer_stats': declarer_stats,
        'unassigned_count': unassigned_count,
        'my_pending_count': my_pending_count,
        'selected_declarer': selected_declarer,
    }
    return render(request, 'core/stage_operation_list.html', context)


def stage_customs_view(request):
    return stage_pipeline_view(request, stage_number=2)

def stage_tbs_view(request):
    return stage_pipeline_view(request, stage_number=3)

def stage_port_view(request):
    return stage_pipeline_view(request, stage_number=4)

def stage_yard_view(request):
    return stage_pipeline_view(request, stage_number=5)

def stage_handover_view(request):
    return stage_pipeline_view(request, stage_number=6)



# ==============================================================================
# 5. ACCOUNTANT'S "VEHICLES OUT" DIRECT COSTING LEDGER & EXCEL EXPORT
# ==============================================================================

@role_required([UserRole.FINANCE, UserRole.CEO, UserRole.ADMIN])
def finance_vehicles_out_view(request):
    """
    Dedicated Ledger for the Accountant and CEO matching the 'VEHICLES OUT' spreadsheet.
    Displays all vehicles with commercial intake data and direct payment costs.
    """
    year_param = request.GET.get('year', '2026').strip()
    ledger_tab = request.GET.get('tab', 'vehicles').strip().lower()
    if ledger_tab not in ('vehicles', 'containers'):
        ledger_tab = 'vehicles'
    q = request.GET.get('q', '').strip()
    date_from_str = request.GET.get('date_from', '').strip()
    date_to_str = request.GET.get('date_to', '').strip()

    parsed_date_from = None
    parsed_date_to = None
    if date_from_str:
        try:
            parsed_date_from = datetime.strptime(date_from_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            parsed_date_from = None
    if date_to_str:
        try:
            parsed_date_to = datetime.strptime(date_to_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            parsed_date_to = None

    jobs = JobShipment.objects.all().select_related('customer').prefetch_related('documents', 'invoices').order_by('-created_at')
    if ledger_tab == 'containers':
        jobs = jobs.exclude(container_size_type='RORO')
    else:
        jobs = jobs.filter(container_size_type='RORO')

    if parsed_date_from or parsed_date_to:
        if parsed_date_from and parsed_date_to:
            jobs = jobs.filter(created_at__date__gte=parsed_date_from, created_at__date__lte=parsed_date_to)
        elif parsed_date_from:
            jobs = jobs.filter(created_at__date__gte=parsed_date_from)
        else:
            jobs = jobs.filter(created_at__date__lte=parsed_date_to)
    else:
        if year_param != 'all' and year_param.isdigit():
            jobs = jobs.filter(created_at__year=int(year_param))

    if q:
        jobs = jobs.filter(
            Q(bl_number__icontains=q) |
            Q(chassis_number__icontains=q) |
            Q(container_numbers__icontains=q) |
            Q(cargo_description__icontains=q) |
            Q(vehicle_make__icontains=q) |
            Q(vehicle_model__icontains=q) |
            Q(customer__company_name__icontains=q) |
            Q(job_number__icontains=q)
        )

    # Calculate Ledger Totals (preload container deposit refunds first so net_container_deposit doesn't trigger N+1)
    job_list = list(jobs)
    total_vehicles = len(job_list)

    if job_list:
        refund_rows = OtherRevenue.objects.filter(
            job_id__in=[j.id for j in job_list],
            inflow_type='CONTAINER_REFUND',
        ).values('job_id').annotate(
            total=Sum('returned_amount', filter=Q(deposit_status__in=['RETURNED_FULL', 'PARTIAL'])),
            resolved_cnt=Count('id', filter=Q(deposit_status__in=['RETURNED_FULL', 'PARTIAL', 'FORFEITED'])),
        )
        refund_totals = {r['job_id']: (r['total'] or Decimal('0')) for r in refund_rows}
        refund_counts = {r['job_id']: r['resolved_cnt'] for r in refund_rows}
    else:
        refund_totals = {}
        refund_counts = {}

    for j in job_list:
        j.deposit_refunded_total = refund_totals.get(j.id, Decimal('0'))
        j._deposit_refunded_cache = j.deposit_refunded_total
        j.deposit_refund_logged = refund_counts.get(j.id, 0) > 0
        bl_doc = j.bl_doc
        inv_doc = j.invoice_doc
        j.bl_doc_url = bl_doc.file.url if bl_doc and bl_doc.file else None
        j.inv_doc_url = inv_doc.file.url if inv_doc and inv_doc.file else None
        j.unrecovered_deposit_for_invoice = (
            (j.cost_other or Decimal('0')) + j.net_container_deposit
            if j.deposit_refund_logged and j.net_container_deposit > 0
            else (j.cost_other or Decimal('0'))
        )

    sum_cif_usd = sum(j.cif_usd or Decimal('0') for j in job_list)
    sum_duty = sum(j.cost_duty or Decimal('0') for j in job_list)
    sum_do = sum(j.cost_do or Decimal('0') for j in job_list)
    sum_wharfage = sum(j.cost_wharfage or Decimal('0') for j in job_list)
    sum_tiss_wharfage = sum(j.cost_tiss_wharfage or Decimal('0') for j in job_list)
    sum_handling = sum(j.cost_handling or Decimal('0') for j in job_list)
    sum_facilitation = sum(j.cost_facilitation or Decimal('0') for j in job_list)
    sum_transport = sum(j.cost_transport or Decimal('0') for j in job_list)
    sum_agent_fee = sum(j.cost_agent_fee or Decimal('0') for j in job_list)
    sum_fuel = sum(j.cost_fuel or Decimal('0') for j in job_list)
    sum_ferry_charges = sum(j.cost_ferry_charges or Decimal('0') for j in job_list)
    sum_total_direct_costs = sum(j.total_direct_costs for j in job_list)
    sum_total_with_fee = sum(j.total_disbursement_with_agent_fee for j in job_list)

    # Status counts
    costed_count = len([j for j in job_list if j.costing_status == 'FULLY_COSTED'])
    in_progress_count = len([j for j in job_list if j.costing_status == 'IN_PROGRESS'])
    pending_count = len([j for j in job_list if j.costing_status == 'PENDING'])

    # Status filtering
    status_param = request.GET.get('status', 'all').strip().lower()
    if status_param == 'costed':
        displayed_jobs = [j for j in job_list if j.costing_status == 'FULLY_COSTED']
    elif status_param == 'in_progress':
        displayed_jobs = [j for j in job_list if j.costing_status == 'IN_PROGRESS']
    elif status_param == 'pending':
        displayed_jobs = [j for j in job_list if j.costing_status == 'PENDING']
    else:
        status_param = 'all'
        displayed_jobs = job_list

    context = {
        'jobs': displayed_jobs,
        'ledger_tab': ledger_tab,
        'total_vehicles': total_vehicles,
        'selected_year': year_param,
        'date_from': date_from_str,
        'date_to': date_to_str,
        'selected_status': status_param,
        'costed_count': costed_count,
        'in_progress_count': in_progress_count,
        'pending_count': pending_count,
        'search_q': q,
        'sum_cif_usd': sum_cif_usd,
        'sum_duty': sum_duty,
        'sum_do': sum_do,
        'sum_wharfage': sum_wharfage,
        'sum_tiss_wharfage': sum_tiss_wharfage,
        'sum_handling': sum_handling,
        'sum_facilitation': sum_facilitation,
        'sum_transport': sum_transport,
        'sum_agent_fee': sum_agent_fee,
        'sum_fuel': sum_fuel,
        'sum_ferry_charges': sum_ferry_charges,
        'sum_total_direct_costs': sum_total_direct_costs,
        'sum_total_with_fee': sum_total_with_fee,
    }
    return render(request, 'finance/vehicles_out_ledger.html', context)


@role_required([UserRole.FINANCE, UserRole.CEO, UserRole.ADMIN])
def finance_vehicles_out_update_cost_action(request, job_id):
    """
    Updates direct costs disbursed for a specific vehicle.
    Synchronizes duty and agent fee with the rest of the operational system.
    """
    job = get_object_or_404(JobShipment, id=job_id)

    if request.method == 'POST':
        def parse_dec(val):
            if not val:
                return Decimal('0')
            try:
                cleaned = str(val).replace(',', '').replace('$', '').replace('TSh', '').strip()
                return Decimal(cleaned) if cleaned else Decimal('0')
            except Exception:
                return Decimal('0')

        job.cost_duty = parse_dec(request.POST.get('cost_duty'))
        job.cost_do = parse_dec(request.POST.get('cost_do'))
        job.cost_wharfage = parse_dec(request.POST.get('cost_wharfage'))
        job.cost_tiss_wharfage = parse_dec(request.POST.get('cost_tiss_wharfage'))
        job.cost_handling = parse_dec(request.POST.get('cost_handling'))
        job.cost_facilitation = parse_dec(request.POST.get('cost_facilitation'))
        job.cost_transport = parse_dec(request.POST.get('cost_transport'))
        job.cost_agent_fee = parse_dec(request.POST.get('cost_agent_fee'))
        job.cost_fuel = parse_dec(request.POST.get('cost_fuel'))
        job.cost_ferry_charges = parse_dec(request.POST.get('cost_ferry_charges'))
        job.cost_container_deposit = parse_dec(request.POST.get('cost_container_deposit'))
        job.cost_shipping_fee = parse_dec(request.POST.get('cost_shipping_fee'))
        job.cost_demurrage = parse_dec(request.POST.get('cost_demurrage'))
        job.cost_storage = parse_dec(request.POST.get('cost_storage'))

        # Parse extra costs if provided via dynamic list
        extra_names = request.POST.getlist('extra_cost_names[]')
        extra_amounts = request.POST.getlist('extra_cost_amounts[]')
        if extra_names and extra_amounts:
            extra_list = []
            total_extra = Decimal('0')
            for name, amt in zip(extra_names, extra_amounts):
                name = name.strip()
                amt_dec = parse_dec(amt)
                if name or amt_dec > 0:
                    extra_list.append({'name': name or 'Additional Cost', 'amount': float(amt_dec)})
                    total_extra += amt_dec
            job.cost_other = total_extra
            import json
            job.cost_other_description = json.dumps(extra_list) if extra_list else ''
        else:
            job.cost_other = parse_dec(request.POST.get('cost_other'))
            job.cost_other_description = request.POST.get('cost_other_description', '').strip()

        # Parse running extra costs (Group 2: Malkia Running Costs - Driver posho, car wash, repair, escort...)
        running_names = request.POST.getlist('running_extra_cost_names[]')
        running_amounts = request.POST.getlist('running_extra_cost_amounts[]')
        if running_names and running_amounts:
            running_list = []
            total_running = Decimal('0')
            for name, amt in zip(running_names, running_amounts):
                name = name.strip()
                amt_dec = parse_dec(amt)
                if name or amt_dec > 0:
                    running_list.append({'name': name or 'Additional Running Cost', 'amount': float(amt_dec)})
                    total_running += amt_dec
            job.cost_running_other = total_running
            import json
            job.cost_running_other_description = json.dumps(running_list) if running_list else ''
        else:
            job.cost_running_other = parse_dec(request.POST.get('cost_running_other'))
            job.cost_running_other_description = request.POST.get('cost_running_other_description', '').strip()

        # Also update commercial invoice price if modified
        if request.POST.get('cif_usd'):
            job.cif_usd = parse_dec(request.POST.get('cif_usd'))

        # Harmonize with operational fields
        if job.cost_duty > 0:
            job.assessed_duty_amount = job.cost_duty
            job.duty_paid = True
        if job.cost_agent_fee > 0:
            job.contracted_revenue = job.cost_agent_fee

        job.save()

        log_audit(request, "UPDATE_VEHICLE_COSTS", f"Updated direct costs for vehicle {job.job_number} (BL: {job.bl_number})")
        messages.success(request, f"Direct costs for {job.vehicle_make} {job.vehicle_model} ({job.bl_number}) saved successfully.")

    redirect_url = request.META.get('HTTP_REFERER') or 'finance_vehicles_out'
    return redirect(redirect_url)


@role_required([UserRole.FINANCE, UserRole.CEO, UserRole.ADMIN])
def finance_invoice_generate_action(request, job_id):
    """
    Dedicated action for Accountant to manually compose or customize a Client Invoice.
    The accountant explicitly chooses which items to bill the client.
    """
    job = get_object_or_404(JobShipment, id=job_id)

    if request.method == 'POST':
        def parse_dec(val):
            if not val:
                return Decimal('0')
            try:
                cleaned = str(val).replace(',', '').replace('$', '').replace('TSh', '').strip()
                return Decimal(cleaned) if cleaned else Decimal('0')
            except Exception:
                return Decimal('0')

        # Line items from accountant
        agency_fee = parse_dec(request.POST.get('amount_clearing_agency_fee'))
        shipping_line = parse_dec(request.POST.get('amount_shipping_line_do'))
        port_charges = parse_dec(request.POST.get('amount_port_charges'))
        terminal_handling = parse_dec(request.POST.get('amount_terminal_handling'))
        transport = parse_dec(request.POST.get('amount_transport'))
        duty_reimb = parse_dec(request.POST.get('amount_duty_reimbursement'))
        sundry = parse_dec(request.POST.get('amount_sundry_charges'))

        # Dynamic extra cargo items (TBS, Demurrage, Storage, Escort, etc.)
        inv_extra_names = request.POST.getlist('inv_extra_names[]')
        inv_extra_amounts = request.POST.getlist('inv_extra_amounts[]')
        extra_line_items_list = []
        extra_line_items_total = Decimal('0')
        if inv_extra_names and inv_extra_amounts:
            for name, amt in zip(inv_extra_names, inv_extra_amounts):
                name = name.strip()
                amt_dec = parse_dec(amt)
                if name and amt_dec > 0:
                    extra_line_items_list.append({'name': name, 'amount': float(amt_dec)})
                    extra_line_items_total += amt_dec

        # Container deposit loss (if client is being billed for forfeited/unreturned deposit)
        container_deposit_loss = parse_dec(request.POST.get('amount_container_deposit_loss'))
        if container_deposit_loss > 0:
            extra_line_items_list.append({
                'name': 'Container Deposit Loss (Forfeited by Shipping Line)',
                'amount': float(container_deposit_loss)
            })
            extra_line_items_total += container_deposit_loss

        import json
        extra_line_items_json = json.dumps(extra_line_items_list) if extra_line_items_list else ''

        total_bill = agency_fee + shipping_line + port_charges + terminal_handling + transport + duty_reimb + sundry + extra_line_items_total
        notes = request.POST.get('notes', '').strip()

        issue_date_str = request.POST.get('issue_date', '').strip()
        due_date_str = request.POST.get('due_date', '').strip()

        today = timezone.localdate()
        try:
            issue_date = datetime.strptime(issue_date_str, '%Y-%m-%d').date() if issue_date_str else today
        except Exception:
            issue_date = today

        try:
            due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date() if due_date_str else (issue_date + timedelta(days=14))
        except Exception:
            due_date = issue_date + timedelta(days=14)

        invoice = job.latest_invoice
        if not invoice:
            inv_no = ClientInvoice.generate_next_invoice_number()
            vehicle_name = f"{job.vehicle_make or ''} {job.vehicle_model or ''}".strip() or (job.cargo_description or job.chassis_number or 'Shipment')
            if not notes:
                notes = f"Customs Clearance & Port Disbursements for {vehicle_name} | Chassis: {job.chassis_number or '—'} | B/L: {job.bl_number}."
            invoice = ClientInvoice.objects.create(
                invoice_number=inv_no,
                job=job,
                customer=job.customer,
                issue_date=issue_date,
                due_date=due_date,
                amount_clearing_agency_fee=agency_fee,
                amount_shipping_line_do=shipping_line,
                amount_port_charges=port_charges,
                amount_terminal_handling=terminal_handling,
                amount_transport=transport,
                amount_sundry_charges=sundry,
                amount_duty_reimbursement=duty_reimb,
                extra_line_items=extra_line_items_json,
                total_amount=total_bill,
                amount_paid=Decimal('0.00'),
                status='ISSUED',
                notes=notes
            )
            log_audit(request, "CREATE_INVOICE", f"Generated custom invoice {inv_no} for vehicle {job.job_number}", job=job)
            messages.success(request, f"Invoice {inv_no} for {job.vehicle_make} {job.vehicle_model} generated successfully.")
        else:
            invoice.amount_clearing_agency_fee = agency_fee
            invoice.amount_shipping_line_do = shipping_line
            invoice.amount_port_charges = port_charges
            invoice.amount_terminal_handling = terminal_handling
            invoice.amount_transport = transport
            invoice.amount_sundry_charges = sundry
            invoice.amount_duty_reimbursement = duty_reimb
            invoice.extra_line_items = extra_line_items_json
            invoice.total_amount = total_bill
            invoice.issue_date = issue_date
            invoice.due_date = due_date
            if notes:
                invoice.notes = notes
            if invoice.amount_paid >= total_bill and total_bill > 0:
                invoice.status = 'PAID'
            elif invoice.amount_paid > 0:
                invoice.status = 'PARTIALLY_PAID'
            else:
                invoice.status = 'ISSUED'
            invoice.save()
            log_audit(request, "UPDATE_INVOICE", f"Updated custom invoice {invoice.invoice_number} for vehicle {job.job_number}", job=job)
            messages.success(request, f"Invoice {invoice.invoice_number} updated successfully.")

        action_type = request.POST.get('action_type', 'save').strip()
        if action_type == 'save_and_print':
            return redirect('print_invoice', invoice_id=invoice.id)

    redirect_url = request.META.get('HTTP_REFERER') or 'finance_vehicles_out'
    return redirect(redirect_url)


@role_required([UserRole.FINANCE, UserRole.CEO, UserRole.ADMIN])
def finance_vehicles_out_export_excel(request):
    """
    Generates a genuine .xlsx Excel spreadsheet matching 100% the layout
    of the accountant's 'VEHICLES OUT 2026' ledger.
    """
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    year_param = request.GET.get('year', '2026').strip()
    ledger_tab = request.GET.get('tab', 'vehicles').strip().lower()
    if ledger_tab not in ('vehicles', 'containers'):
        ledger_tab = 'vehicles'
    q = request.GET.get('q', '').strip()
    date_from_str = request.GET.get('date_from', '').strip()
    date_to_str = request.GET.get('date_to', '').strip()
    status_param = request.GET.get('status', 'all').strip().lower()

    parsed_date_from = None
    parsed_date_to = None
    if date_from_str:
        try:
            parsed_date_from = datetime.strptime(date_from_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            parsed_date_from = None
    if date_to_str:
        try:
            parsed_date_to = datetime.strptime(date_to_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            parsed_date_to = None

    jobs = JobShipment.objects.all().select_related('customer').order_by('created_at')
    if ledger_tab == 'containers':
        jobs = jobs.exclude(container_size_type='RORO')
    else:
        jobs = jobs.filter(container_size_type='RORO')

    if parsed_date_from or parsed_date_to:
        if parsed_date_from and parsed_date_to:
            jobs = jobs.filter(created_at__date__gte=parsed_date_from, created_at__date__lte=parsed_date_to)
        elif parsed_date_from:
            jobs = jobs.filter(created_at__date__gte=parsed_date_from)
        else:
            jobs = jobs.filter(created_at__date__lte=parsed_date_to)
    else:
        if year_param != 'all' and year_param.isdigit():
            jobs = jobs.filter(created_at__year=int(year_param))

    if q:
        jobs = jobs.filter(
            Q(bl_number__icontains=q) |
            Q(chassis_number__icontains=q) |
            Q(container_numbers__icontains=q) |
            Q(cargo_description__icontains=q) |
            Q(vehicle_make__icontains=q) |
            Q(vehicle_model__icontains=q) |
            Q(customer__company_name__icontains=q)
        )

    job_list = list(jobs)
    if status_param == 'costed':
        jobs = [j for j in job_list if j.costing_status == 'FULLY_COSTED']
    elif status_param == 'in_progress':
        jobs = [j for j in job_list if j.costing_status == 'IN_PROGRESS']
    elif status_param == 'pending':
        jobs = [j for j in job_list if j.costing_status == 'PENDING']
    else:
        jobs = job_list

    wb = openpyxl.Workbook()
    ws = wb.active
    is_containers = (ledger_tab == 'containers')
    ws.title = f"{'CONTAINERS' if is_containers else 'VEHICLES'} OUT {year_param.upper()}"
    ws.views.sheetView[0].showGridLines = True

    if is_containers:
        ws.merge_cells('A1:O1')
        title_cell = ws['A1']
        title_cell.value = f"CONTAINERS OUT {year_param.upper()}"
        title_cell.font = Font(name='Segoe UI', size=14, bold=True, color='0F172A')
        title_cell.fill = PatternFill(start_color='B45309', end_color='B45309', fill_type='solid')
        title_cell.font = Font(name='Segoe UI', size=14, bold=True, color='FFFFFF')
        title_cell.alignment = Alignment(horizontal='center', vertical='center')
        ws.row_dimensions[1].height = 36

        headers = [
            "S/N",
            "DATE IN",
            "CONTAINER NO",
            "ITEM",
            "QTY (CONTAINERS)",
            "INVOICE",
            "CONTAINER DEPOSIT",
            "D/O",
            "SHIPPING FEE",
            "DEMURRAGE CHARGES",
            "STORAGE CHARGES",
            "WHARFAGE",
            "HANDLING",
            "FACILITATION",
            "AGENCY FEE",
        ]
        header_fill = PatternFill(start_color='FDE68A', end_color='FDE68A', fill_type='solid')
        header_font = Font(name='Segoe UI', size=10, bold=True, color='0F172A')
        thin_border_side = Side(style='thin', color='CBD5E1')
        cell_border = Border(left=thin_border_side, right=thin_border_side, top=thin_border_side, bottom=thin_border_side)

        ws.row_dimensions[2].height = 28
        for col_idx, header_text in enumerate(headers, 1):
            cell = ws.cell(row=2, column=col_idx, value=header_text)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
            cell.border = cell_border

        row_idx = 3
        currency_fmt = '#,##0.00'
        for sn, job in enumerate(jobs, 1):
            ws.row_dimensions[row_idx].height = 22
            date_str = job.created_at.strftime('%d.%m.%Y') if job.created_at else ''
            row_values = [
                (sn, 'center', None),
                (date_str, 'center', None),
                (job.container_numbers or job.bl_number or job.job_number, 'center', None),
                (job.cargo_description or '', 'left', None),
                (int(job.container_qty or 1), 'center', '0'),
                (float(job.cif_usd or 0), 'right', currency_fmt),
                (float(job.cost_container_deposit or 0), 'right', currency_fmt),
                (float(job.cost_do or 0), 'right', currency_fmt),
                (float(job.cost_shipping_fee or 0), 'right', currency_fmt),
                (float(job.cost_demurrage or 0), 'right', currency_fmt),
                (float(job.cost_storage or 0), 'right', currency_fmt),
                (float(job.cost_wharfage or 0), 'right', currency_fmt),
                (float(job.cost_handling or 0), 'right', currency_fmt),
                (float(job.cost_facilitation or 0), 'right', currency_fmt),
                (float(job.cost_agent_fee or 0), 'right', currency_fmt),
            ]
            row_fill = PatternFill(start_color='F8FAFC' if row_idx % 2 == 0 else 'FFFFFF', end_color='F8FAFC' if row_idx % 2 == 0 else 'FFFFFF', fill_type='solid')
            for col_idx, (val, align, num_fmt) in enumerate(row_values, 1):
                cell = ws.cell(row=row_idx, column=col_idx, value=val)
                cell.font = Font(name='Segoe UI', size=9.5)
                cell.fill = row_fill
                cell.border = cell_border
                cell.alignment = Alignment(horizontal=align, vertical='center')
                if num_fmt and isinstance(val, (int, float)):
                    cell.number_format = num_fmt
            row_idx += 1

        ws.row_dimensions[row_idx].height = 26
        total_fill = PatternFill(start_color='DCFCE7', end_color='DCFCE7', fill_type='solid')
        double_bottom_border = Border(
            left=thin_border_side, right=thin_border_side,
            top=Side(style='thin', color='0F172A'),
            bottom=Side(style='double', color='0F172A')
        )
        for col in range(1, len(headers) + 1):
            c = ws.cell(row=row_idx, column=col)
            c.fill = total_fill
            c.border = double_bottom_border
            c.font = Font(name='Segoe UI', size=10, bold=True)
        ws.cell(row=row_idx, column=1, value="TOTAL").alignment = Alignment(horizontal='center', vertical='center')
        if row_idx > 3:
            for col_letter in ['F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O']:
                c = ws[f"{col_letter}{row_idx}"]
                c.value = f"=SUM({col_letter}3:{col_letter}{row_idx-1})"
                c.number_format = currency_fmt
                c.alignment = Alignment(horizontal='right', vertical='center')
    else:
        # 1. Top Super Header (Title banner)
        ws.merge_cells('A1:R1')
        title_cell = ws['A1']
        title_cell.value = f"MALKIA CARGO WAVES LTD — VEHICLES OUT {year_param.upper()}"
        title_cell.font = Font(name='Segoe UI', size=14, bold=True, color='FFFFFF')
        title_cell.fill = PatternFill(start_color='0F172A', end_color='0F172A', fill_type='solid')
        title_cell.alignment = Alignment(horizontal='center', vertical='center')
        ws.row_dimensions[1].height = 36

        # 2. Column Headers (Row 2) - Matching User's Spreadsheet Exactly
        headers = [
            "DATE IN",
            "REFERANCE NO",
            "Registration Year",
            "Make",
            "Model",
            "Chassis No.",
            "CIF BUYING Price(USD)",
            "INVOICE $",
            "Duty",
            "D/O",
            "Wharfage",
            "Tiss Wharfage",
            "Handling",
            "Facilitation",
            "Transport",
            "Agent Fee",
            "FUEL",
            "FERRY CHARGES",
            "TOTAL EXPENSES (TSh)"
        ]

        header_font = Font(name='Segoe UI', size=10, bold=True, color='0F172A')
        header_fill = PatternFill(start_color='E2E8F0', end_color='E2E8F0', fill_type='solid')
        thin_border_side = Side(style='thin', color='CBD5E1')
        cell_border = Border(left=thin_border_side, right=thin_border_side, top=thin_border_side, bottom=thin_border_side)

        ws.row_dimensions[2].height = 28
        for col_idx, header_text in enumerate(headers, 1):
            cell = ws.cell(row=2, column=col_idx, value=header_text)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
            cell.border = cell_border

        # 3. Data Rows
        row_idx = 3
        currency_fmt = '#,##0.00'
        usd_fmt = '$#,##0.00'

        for job in jobs:
            ws.row_dimensions[row_idx].height = 22
            
            date_str = job.created_at.strftime('%d.%m.%Y') if job.created_at else ''
            ref_no = job.bl_number or job.job_number
            reg_year = str(job.registration_year or '')
            make = job.vehicle_make or ''
            model = job.vehicle_model or ''
            chassis = job.chassis_number or ''
            cif_price = float(job.cif_usd or 0)
            invoice_usd = float(job.cif_usd or 0)
            duty = float(job.cost_duty or 0)
            do_cost = float(job.cost_do or 0)
            wharfage = float(job.cost_wharfage or 0)
            tiss = float(job.cost_tiss_wharfage or 0)
            handling = float(job.cost_handling or 0)
            facil = float(job.cost_facilitation or 0)
            trans = float(job.cost_transport or 0)
            agent_fee = float(job.cost_agent_fee or 0)
            fuel = float(job.cost_fuel or 0)
            ferry = float(job.cost_ferry_charges or 0)
            total_costs = float(job.total_disbursement_with_agent_fee)

            row_values = [
                (date_str, 'center', None),
                (ref_no, 'center', None),
                (reg_year, 'center', None),
                (make, 'left', None),
                (model, 'left', None),
                (chassis, 'center', None),
                (cif_price if cif_price > 0 else '', 'right', usd_fmt),
                (invoice_usd if invoice_usd > 0 else '', 'right', usd_fmt),
                (duty, 'right', currency_fmt),
                (do_cost, 'right', currency_fmt),
                (wharfage, 'right', currency_fmt),
                (tiss, 'right', currency_fmt),
                (handling, 'right', currency_fmt),
                (facil, 'right', currency_fmt),
                (trans, 'right', currency_fmt),
                (agent_fee, 'right', currency_fmt),
                (fuel, 'right', currency_fmt),
                (ferry, 'right', currency_fmt),
                (total_costs, 'right', currency_fmt),
            ]

            # Zebra coloring for alternating rows
            row_fill = PatternFill(start_color='F8FAFC' if row_idx % 2 == 0 else 'FFFFFF', end_color='F8FAFC' if row_idx % 2 == 0 else 'FFFFFF', fill_type='solid')

            for col_idx, (val, align, num_fmt) in enumerate(row_values, 1):
                cell = ws.cell(row=row_idx, column=col_idx, value=val)
                cell.font = Font(name='Segoe UI', size=9.5)
                cell.fill = row_fill
                cell.border = cell_border
                cell.alignment = Alignment(horizontal=align, vertical='center')
                if num_fmt and isinstance(val, (int, float)):
                    cell.number_format = num_fmt

            row_idx += 1

        # 4. Totals Row
        ws.row_dimensions[row_idx].height = 26
        total_cell = ws.cell(row=row_idx, column=1, value="TOTAL")
        total_cell.font = Font(name='Segoe UI', size=10, bold=True, color='0F172A')
        total_cell.alignment = Alignment(horizontal='center', vertical='center')
        
        total_fill = PatternFill(start_color='FEF3C7', end_color='FEF3C7', fill_type='solid')
        double_bottom_border = Border(
            left=thin_border_side, right=thin_border_side,
            top=Side(style='thin', color='0F172A'),
            bottom=Side(style='double', color='0F172A')
        )

        for col in range(1, len(headers) + 1):
            c = ws.cell(row=row_idx, column=col)
            c.fill = total_fill
            c.border = double_bottom_border
            c.font = Font(name='Segoe UI', size=10, bold=True)

        if row_idx > 3:
            # Excel SUM formulas for numeric columns
            for col_letter, num_fmt in [
                ('G', usd_fmt), ('H', usd_fmt),
                ('I', currency_fmt), ('J', currency_fmt), ('K', currency_fmt),
                ('L', currency_fmt), ('M', currency_fmt), ('N', currency_fmt),
                ('O', currency_fmt), ('P', currency_fmt), ('Q', currency_fmt),
                ('R', currency_fmt), ('S', currency_fmt)
            ]:
                c = ws[f"{col_letter}{row_idx}"]
                c.value = f"=SUM({col_letter}3:{col_letter}{row_idx-1})"
                c.number_format = num_fmt
                c.alignment = Alignment(horizontal='right', vertical='center')

    # Auto-adjust column widths
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            val_str = str(cell.value or '')
            if len(val_str) > max_len and not cell.coordinate in ['A1']:
                max_len = len(val_str)
        ws.column_dimensions[col_letter].width = max(max_len + 4, 12)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f"{'CONTAINERS' if is_containers else 'VEHICLES'}_OUT_{year_param.upper()}.xlsx"
    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def rename_document_action(request, doc_id):
    doc = get_object_or_404(JobDocument.objects.select_related('job'), id=doc_id)
    job_id = doc.job.id

    if not user_can_manage_docs(request.user, doc.job):
        messages.error(request, "Ruksa imezuiwa: Ni Afisa Nyaraka (Documentation Officer) au Admin pekee anayeweza kurekebisha nyaraka.")
        return redirect(f"/jobs/{job_id}/#documentCenter")

    if request.method == 'POST':
        new_title = request.POST.get('title', '').strip()
        new_doc_type = request.POST.get('document_type', '').strip()

        if new_title:
            doc.title = new_title
        if new_doc_type and new_doc_type in dict(JobDocument.DOC_TYPES):
            doc.document_type = new_doc_type

        # Support replacing the physical file
        new_file = request.FILES.get('file')
        file_replaced = False
        if new_file:
            if doc.file:
                try:
                    doc.file.delete(save=False)
                except Exception:
                    pass
            doc.file = _compress_image_if_needed(new_file)
            doc.uploaded_at = timezone.now()
            doc.uploaded_by = request.user
            file_replaced = True

        doc.save()
        
        # Update job document flags if applicable
        job = doc.job
        doc_flag_map = {
            'BILL_OF_LADING': 'doc_bl_received',
            'COMMERCIAL_INVOICE': 'doc_invoice_received',
            'PACKING_LIST': 'doc_packing_list_received',
            'TBS_CERT': 'doc_tbs_cert_received',
            'EXPORT_CERT': 'doc_export_cert_received',
        }
        if doc.document_type in doc_flag_map:
            setattr(job, doc_flag_map[doc.document_type], True)
            job.save(update_fields=[doc_flag_map[doc.document_type]])

        if file_replaced:
            log_audit(request, "REPLACE_DOCUMENT", f"Replaced file & updated document '{doc.title}' ({doc.document_type}) for Job {doc.job.job_number}", job=doc.job)
            messages.success(request, f"Faili la '{doc.title}' limesasishwa kikamilifu na kubadilika mfumo mzima (Document updated successfully).")
        else:
            log_audit(request, "RENAME_DOCUMENT", f"Renamed document to '{doc.title}' ({doc.document_type}) for Job {doc.job.job_number}", job=doc.job)
            messages.success(request, f"Jina la '{doc.title}' limesasishwa kikamilifu.")

    redirect_url = request.META.get('HTTP_REFERER') or f'/jobs/{job_id}/#documentCenter'
    return redirect(redirect_url)


@login_required
def delete_document_action(request, doc_id):
    doc = get_object_or_404(JobDocument.objects.select_related('job'), id=doc_id)
    job_id = doc.job.id

    if not user_can_manage_docs(request.user, doc.job):
        messages.error(request, "Ruksa imezuiwa: Ni Afisa Nyaraka (Documentation Officer) au Admin pekee anayeweza kufuta nyaraka.")
        return redirect(f"/jobs/{job_id}/#documentCenter")

    if request.method == 'POST':
        doc_title = doc.title
        job_number = doc.job.job_number
        if doc.file:
            try:
                doc.file.delete(save=False)
            except Exception:
                pass
        doc.delete()
        doc_flag_map = {
            'BILL_OF_LADING': 'doc_bl_received',
            'COMMERCIAL_INVOICE': 'doc_invoice_received',
            'PACKING_LIST': 'doc_packing_list_received',
            'TBS_CERT': 'doc_tbs_cert_received',
            'EXPORT_CERT': 'doc_export_cert_received',
        }
        if doc.document_type in doc_flag_map:
            flag = doc_flag_map[doc.document_type]
            has_other = doc.job.documents.filter(document_type=doc.document_type).exists()
            setattr(doc.job, flag, has_other)
            doc.job.save(update_fields=[flag])
        log_audit(request, "DELETE_DOCUMENT", f"Deleted document '{doc_title}' from Job {job_number}", job=doc.job)
        messages.success(request, f"Document '{doc_title}' deleted successfully.")

    redirect_url = request.META.get('HTTP_REFERER') or f'/jobs/{job_id}/'
    return redirect(redirect_url)


@login_required
def finalize_document_dossier_view(request, job_id):
    job = get_object_or_404(JobShipment, id=job_id)

    if not user_can_manage_docs(request.user, job):
        messages.error(request, "Permission denied: Ni Afisa Nyaraka au Admin pekee anayeweza kuhifadhi faili hili.")
        return redirect(f"/jobs/{job_id}/#documentCenter")

    if request.method == 'POST':
        job.doc_intake_finalized = True
        job.doc_received_at = timezone.now()
        if not job.documentation_officer:
            job.documentation_officer = request.user

        # Auto sync checklist flags based on uploaded documents
        job.doc_bl_received = bool(job.bl_doc)
        job.doc_invoice_received = bool(job.invoice_doc)
        job.doc_packing_list_received = bool(job.packing_list_doc)
        job.doc_tbs_cert_received = bool(job.tbs_cert_doc)
        job.doc_export_cert_received = bool(job.export_cert_doc)

        job.save()
        log_audit(request, "SAVE_DOCUMENT_DOSSIER", f"Document dossier officially saved and finalized for Job {job.job_number}", job=job)
        messages.success(request, f"Nyaraka zote za jalada zimehifadhiwa kikamilifu (Document dossier for {job.bl_number or job.job_number} saved successfully).")

    return redirect(f"/jobs/{job_id}/#documentCenter")
