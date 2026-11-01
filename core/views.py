import os

import io

import json

from decimal import Decimal

from django.shortcuts import render, redirect, get_object_or_404

from django.http import HttpResponse, JsonResponse, FileResponse
import mimetypes, zipfile

from django.contrib import messages

from django.contrib.auth.models import User

from django.contrib.auth import login, logout, authenticate

from django.contrib.auth.decorators import login_required

from django.views.decorators.csrf import csrf_exempt

from django.utils import timezone

from django.db.models import Sum, Q

from datetime import time, timedelta, datetime, date



import openpyxl

from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

from openpyxl.utils import get_column_letter



from .models import (

    UserRole, UserProfile, Customer, WorkflowStageDefinition,

    JobShipment, JobStageInstance, JobDocument, JobContainer, ExpenseVoucher,

    ExpenseCategory, ClientInvoice, ClientPayment, AuditLog, FieldIssue, FleetVehicle,

    StaffAttendance, SystemConfig

)

from .permissions import (

    get_user_role, role_required, can_approve_expense, can_advance_stage

)





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



        # Standard Credentials Login

        username = request.POST.get('username', '').strip()

        password = request.POST.get('password', '').strip()

        user = authenticate(request, username=username, password=password)



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





# ==============================================================================

# CORE VIEWS (PROTECTED BY RBAC)

# ==============================================================================



@login_required

def dashboard_view(request):

    role = get_user_role(request.user)

    # Drivers and Port Officers have specialized operational field consoles

    if role == UserRole.PORT_OFFICER:

        return redirect('field_today_jobs')

    if role == UserRole.OPERATIONS_MGR:

        return redirect('yard_operations')

    if role in [UserRole.DRIVER, UserRole.DISPATCH_OFFICER]:

        return redirect('dashboard')



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

        preset = 'today'

        date_from = today_date

        date_to = today_date



    # Human-readable filter label

    if preset == 'today':

        filter_label = f"Today ({today_date.strftime('%d %b %Y')})"

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

        completed_jobs = all_jobs_raw.filter(status='COMPLETED', delivered_date__date__range=(date_from, date_to))

        active_jobs = all_jobs_raw.filter(status__in=['ACTIVE', 'DELAYED'], created_at__date__lte=date_to)

        delayed_jobs = all_jobs_raw.filter(status='DELAYED', created_at__date__lte=date_to)

        jobs = all_jobs_raw.filter(Q(status__in=['ACTIVE', 'DELAYED'], created_at__date__lte=date_to) | Q(status='COMPLETED', delivered_date__date__range=(date_from, date_to)))

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

    pending_expenses = ExpenseVoucher.objects.filter(approval_status='REQUESTED').select_related('job', 'requester')



    # Stage distribution for visual health card and chart

    all_stage_defs = WorkflowStageDefinition.objects.all().order_by('stage_number')

    if not can_view_all_stages:

        allowed_stage_numbers = ROLE_STAGE_MAPPING.get(role, [])

        role_stage_defs = all_stage_defs.filter(stage_number__in=allowed_stage_numbers)

        stage_section_title, stage_section_desc = ROLE_STAGE_TITLES.get(

            role,

            ("Operational Workflow Stages", "Active shipments count across your designated workflow stages")

        )

        role_display_name = request.user.profile.get_role_display() if hasattr(request.user, 'profile') else 'Operational'

        pipeline_title = f"{role_display_name} Pipeline Distribution"

        pipeline_desc = f"Shipment volume across your {len(allowed_stage_numbers)} assigned workflow stages"

    else:

        role_stage_defs = all_stage_defs

        stage_section_title = "Workflow Operational Health"

        stage_section_desc = "Active files count and progression"

        pipeline_title = "Pipeline Distribution"

        pipeline_desc = "Files volume across active workflow stages"



    stage_counts = []

    for sdef in role_stage_defs:

        cnt = jobs.filter(current_stage_number=sdef.stage_number, status__in=['ACTIVE', 'DELAYED']).count()

        stage_counts.append({

            'num': sdef.stage_number,

            'name': sdef.name_en,

            'count': cnt

        })



    # Visible jobs in dashboard table (Role-Based Scope Filter: strictly their stages)

    if can_view_all_stages:

        visible_jobs = jobs.filter(status__in=['ACTIVE', 'DELAYED'])

    else:

        if role == UserRole.CLEARING_OFFICER:

            # Customs Declarer sees jobs currently in customs/clearance stages (2 through 7)

            visible_jobs = jobs.filter(

                current_stage_number__in=[2, 3, 4, 5, 6, 7],

                status__in=['ACTIVE', 'DELAYED']

            )

        elif role == UserRole.DOC_OFFICER:

            # Documentation Officer sees jobs currently in doc intake / file opening (1, 2)

            visible_jobs = jobs.filter(

                current_stage_number__in=[1, 2],

                status__in=['ACTIVE', 'DELAYED']

            )

        elif role == UserRole.FINANCE:

            visible_jobs = jobs.filter(

                Q(current_stage_number__in=[4, 9]) |

                Q(duty_paid=True) |

                Q(assessed_duty_amount__gt=0) |

                Q(invoices__status__in=['ISSUED', 'PARTIALLY_PAID', 'OVERDUE']) |

                Q(expenses__approval_status='REQUESTED')

            ).distinct()

        elif role == UserRole.PORT_OFFICER:

            visible_jobs = jobs.filter(

                current_stage_number__in=[4, 5, 6, 7, 8],

                status__in=['ACTIVE', 'DELAYED']

            )

        elif role in [UserRole.DISPATCH_OFFICER, UserRole.DRIVER]:

            visible_jobs = jobs.filter(

                current_stage_number__in=[10, 11],

                status__in=['ACTIVE', 'DELAYED']

            )

        else:

            visible_jobs = jobs.filter(status__in=['ACTIVE', 'DELAYED'])



    stage_1_count = jobs.filter(current_stage_number=1, status__in=['ACTIVE', 'DELAYED']).count()

    stage_2_count = jobs.filter(current_stage_number=2, status__in=['ACTIVE', 'DELAYED']).count()

    my_assigned_jobs_count = jobs.filter(documentation_officer=request.user, status__in=['ACTIVE', 'DELAYED']).count() if request.user.is_authenticated else 0



    docs_received_today = JobDocument.objects.filter(uploaded_at__date=today_date).count()

    pending_file_opening = stage_2_count

    completed_documents_count = JobDocument.objects.count()

    recent_doc_activities = JobDocument.objects.all().select_related('job', 'job__customer', 'uploaded_by').order_by('-uploaded_at')[:6]



    jobs_at_tra = jobs.filter(current_stage_number__in=[3, 4], status__in=['ACTIVE', 'DELAYED']).count()

    jobs_at_port = jobs.filter(current_stage_number__in=[5, 6, 7, 8, 9, 10], status__in=['ACTIVE', 'DELAYED']).count()

    in_bond_count = jobs.filter(clearance_mode='BOND', status__in=['ACTIVE', 'DELAYED']).count()

    new_files_count = stage_1_count

    pending_files_count = stage_2_count



    # Customs Declarer metrics

    pending_declarations_count = jobs.filter(current_stage_number__in=[2, 3], status__in=['ACTIVE', 'DELAYED'], declaration_number='').count()

    awaiting_assessment_count = jobs.filter(current_stage_number=3, status__in=['ACTIVE', 'DELAYED']).exclude(declaration_number='').filter(assessed_duty_amount=0).count()

    assessed_declarations_count = jobs.filter(assessed_duty_amount__gt=0).count()

    customs_attention_count = jobs.filter(current_stage_number__in=[3, 4], status='DELAYED').count()

    customs_pending_queue = jobs.filter(current_stage_number__in=[2, 3], status__in=['ACTIVE', 'DELAYED'], declaration_number='').select_related('customer', 'documentation_officer')[:6]

    recent_assessed_jobs = jobs.filter(assessed_duty_amount__gt=0).select_related('customer', 'clearing_officer').order_by('-updated_at')[:6]



    # Staff Attendance metrics for Executive Dashboard Spec

    staff_present_today = StaffAttendance.objects.filter(date=today_date, status__in=['PRESENT', 'LATE']).count()

    staff_total_count = User.objects.filter(is_active=True).exclude(username='admin').count() or User.objects.filter(is_active=True).count()

    staff_late_today = StaffAttendance.objects.filter(date=today_date, status='LATE').count()



    context = {

        'can_view_all_stages': can_view_all_stages,

        'stage_section_title': stage_section_title,

        'stage_section_desc': stage_section_desc,

        'pipeline_title': pipeline_title,

        'pipeline_desc': pipeline_desc,

        'jobs': visible_jobs[:8],

        'visible_jobs_count': visible_jobs.count(),

        'active_jobs_count': active_jobs.count(),

        'completed_jobs_count': completed_jobs.count(),

        'delayed_jobs_count': len(flagged_delayed_list),

        'preset': preset,

        'date_from': date_from.strftime('%Y-%m-%d') if date_from else '',

        'date_to': date_to.strftime('%Y-%m-%d') if date_to else '',

        'filter_label': filter_label,

        'today_str': today_date.strftime('%Y-%m-%d'),

        'staff_present_today': staff_present_today,

        'staff_total_count': staff_total_count,

        'staff_late_today': staff_late_today,

        'total_revenue': total_revenue,

        'total_expenses': total_expenses,

        'gross_margin': gross_margin,

        'gross_margin_pct': gross_margin_pct,

        'outstanding_receivables': outstanding_receivables,

        'daily_income': daily_income,

        'daily_expenses': daily_expenses,

        'containers_at_port': containers_at_port,

        'in_transit_count': in_transit_count,

        'under_verification_count': under_verification_count,

        'stage_1_count': stage_1_count,

        'stage_2_count': stage_2_count,

        'my_assigned_jobs_count': my_assigned_jobs_count,

        'docs_received_today': docs_received_today,

        'pending_file_opening': pending_file_opening,

        'completed_documents_count': completed_documents_count,

        'recent_doc_activities': recent_doc_activities,

        'jobs_at_tra': jobs_at_tra,

        'jobs_at_port': jobs_at_port,

        'in_bond_count': in_bond_count,

        'new_files_count': new_files_count,

        'pending_files_count': pending_files_count,

        'pending_declarations_count': pending_declarations_count,

        'awaiting_assessment_count': awaiting_assessment_count,

        'assessed_declarations_count': assessed_declarations_count,

        'customs_attention_count': customs_attention_count,

        'customs_pending_queue': customs_pending_queue,

        'recent_assessed_jobs': recent_assessed_jobs,

        'flagged_delayed_list': flagged_delayed_list[:5],

        'pending_expenses': pending_expenses[:5],

        'stage_counts': stage_counts,

    }

    return render(request, 'core/dashboard.html', context)





@login_required

@role_required([UserRole.CEO, UserRole.OPERATIONS_MGR, UserRole.DOC_OFFICER, UserRole.CLEARING_OFFICER, UserRole.PORT_OFFICER, UserRole.FINANCE, UserRole.ADMIN])

def jobs_list_view(request):

    role = get_user_role(request.user)

    can_view_all_stages = (role in [UserRole.CEO, UserRole.OPERATIONS_MGR, UserRole.ADMIN] or request.user.is_superuser)



    status_filter = request.GET.get('status', '')

    customer_id = request.GET.get('customer', '')

    query = request.GET.get('q', '').strip()



    jobs = JobShipment.objects.all().select_related('customer', 'documentation_officer', 'clearing_officer', 'port_officer').order_by('-created_at', '-id')



    if not can_view_all_stages:

        if role == UserRole.CLEARING_OFFICER:

            jobs = jobs.filter(current_stage_number__in=[1, 2, 3, 4, 5, 6, 7])

        elif role == UserRole.DOC_OFFICER:

            jobs = jobs.filter(current_stage_number__in=[1, 2])

        elif role == UserRole.PORT_OFFICER:

            jobs = jobs.filter(current_stage_number__in=[4, 5, 6, 7, 8])

        elif role == UserRole.FINANCE:

            jobs = jobs.filter(Q(current_stage_number__in=[4, 9]) | Q(duty_paid=True) | Q(assessed_duty_amount__gt=0) | Q(invoices__isnull=False) | Q(expenses__isnull=False)).distinct()

        elif role in [UserRole.DISPATCH_OFFICER, UserRole.DRIVER]:

            jobs = jobs.filter(current_stage_number__in=[10, 11])



    if status_filter:

        jobs = jobs.filter(status=status_filter)

    if customer_id:

        jobs = jobs.filter(customer_id=customer_id)

    if query:

        jobs = jobs.filter(

            Q(job_number__icontains=query) |

            Q(bl_number__icontains=query) |

            Q(chassis_number__icontains=query) |

            Q(container_numbers__icontains=query) |

            Q(customer__company_name__icontains=query) |

            Q(box_number__icontains=query) |

            Q(vessel_name__icontains=query)

        )



    jobs = jobs.order_by('-created_at', '-id')

    customers = Customer.objects.all()

    context = {

        'can_view_all_stages': can_view_all_stages,

        'jobs': jobs,

        'customers': customers,

        'selected_status': status_filter,

        'selected_customer': customer_id,

        'search_query': query,

    }

    return render(request, 'core/jobs_list.html', context)





@login_required

def job_detail_view(request, job_id):

    job = get_object_or_404(JobShipment.objects.select_related('customer'), id=job_id)

    role = get_user_role(request.user)



    # Driver role check: if driver, only allow viewing if assigned to this shipment

    if role == UserRole.DRIVER:

        if job.driver_id != request.user.id:

            messages.error(request, "Access Restricted: You can only view jobs assigned directly to your vehicle.")

            return redirect('field_mobile')



    stages = job.stages.all().select_related('stage_definition', 'responsible_officer').order_by('stage_number')

    containers = job.containers.all().select_related('assigned_driver').order_by('container_number')

    documents = job.documents.all().select_related('uploaded_by', 'stage')

    expenses = job.expenses.all().select_related('requester', 'approver')

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
            'subtitle': 'Malkia C&F service & clearance fee',
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

        'next_stage_num': min(9, job.current_stage_number + 1),

        'user_can_advance_current': user_can_advance_current,

        'can_track_containers': can_track_containers,

        'client_duty_receipt': job.documents.filter(document_type='DUTY_PAYMENT_RECEIPT').order_by('-uploaded_at').first(),

        'costing_items': costing_items,

        'total_itemized_billed': total_itemized_billed,

        'total_itemized_actual': total_itemized_actual,

        'total_itemized_margin': total_itemized_margin,

        'primary_invoice': primary_invoice,

    }

    return render(request, 'core/job_detail.html', context)





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

        cargo_description = request.POST.get('cargo_description', '').strip() or '1 Unit Motor Vehicle'

        clearance_mode = request.POST.get('clearance_mode', 'DIRECT')

        if clearance_mode not in ['DIRECT', 'BOND', 'EX_BOND']:

            clearance_mode = 'DIRECT'



        doc_receive_method = request.POST.get('doc_receive_method', 'PHYSICAL')
        doc_bl_received = (request.POST.get('doc_bl_received') == '1') or bool(request.FILES.get('file_bl'))
        doc_invoice_received = (request.POST.get('doc_invoice_received') == '1') or bool(request.FILES.get('file_invoice'))
        doc_packing_list_received = (request.POST.get('doc_packing_list_received') == '1') or bool(request.FILES.get('file_packing_list'))
        doc_tbs_cert_received = (request.POST.get('doc_tbs_cert_received') == '1') or bool(request.FILES.get('file_tbs_cert'))
        doc_export_cert_received = (request.POST.get('doc_export_cert_received') == '1') or bool(request.FILES.get('file_export_cert'))
        doc_packing_list_received = request.POST.get('doc_packing_list_received') == '1'

        doc_tbs_cert_received = request.POST.get('doc_tbs_cert_received') == '1'

        doc_export_cert_received = request.POST.get('doc_export_cert_received') == '1'



        job_number = JobShipment.generate_next_job_number()

        now = timezone.now()

        c41_ref = f"TRA-C41/{job_number}"

        tbs_ref = f"MALKIA/TBS/{job_number}"



        # Direct handover: Documentation Officer → Customs Declarer (no Operations approval step)

        declarer = User.objects.filter(

            profile__role=UserRole.CLEARING_OFFICER, is_active=True

        ).order_by('id').first()



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

            container_numbers=chassis_number or bl_number,

            container_size_type='RORO',

            cargo_description=cargo_description,

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

            clearing_officer=declarer,

            current_stage_number=2,

            status='ACTIVE'

        )



        # Initialize active workflow stage definitions

        first_stage_instance = None

        stage_defs = WorkflowStageDefinition.objects.all().order_by('stage_number')

        for sdef in stage_defs:

            is_first = (sdef.stage_number == 1)

            is_declaration = (sdef.stage_number == 2)

            st_obj = JobStageInstance.objects.create(

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

                remarks=f"Client documents received & scanned ({job.get_doc_receive_method_display()}), Clearance Mode: {job.get_clearance_mode_display()}, and File opened with auto-generated C41 & TBS Letter." if is_first else (

                    "File handed over directly to Customs Declarer for TRA TANESW & TBS declaration." if is_declaration else ""

                )

            )

            if is_first:

                first_stage_instance = st_obj



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



        # Automated Client Notification: 1. Documents Received

        try:

            from .email_service import send_stage_update_email

            send_stage_update_email(job, 1, extra_note=f"Your documents have been received ({job.get_doc_receive_method_display()}): {rec_str} and your File (BL: {bl_number or job.job_number}) has been officially opened.")

        except Exception as e:

            print(f"[Email Notification Error] {e}")



        # Direct notification to the Customs Declarer (TANESW/TBS queue)

        try:

            from .email_service import send_declarer_intake_notification

            send_declarer_intake_notification(job, declarer)

        except Exception as e:

            print(f"[Declarer Notification Error] {e}")



        messages.success(

            request,

            f"File {job.job_number} (BL: {bl_number or job.job_number}) imefunguliwa na kupelekwa moja kwa moja kwa Customs Declarer kwa TANESW/TBS declaration. C41 & TBS Letter zimeunganishwa pamoja na nyaraka {len(scanned_files)}."

        )

        return redirect('jobs_list')



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

def print_c41_document_view(request, job_id):

    job = get_object_or_404(JobShipment.objects.select_related('customer', 'documentation_officer'), id=job_id)

    if not job.c41_reference_no:

        job.c41_reference_no = f"TRA-C41/{job.job_number}"

        job.doc_c41_generated = True

        job.save(update_fields=['c41_reference_no', 'doc_c41_generated'])

    return render(request, 'core/print_c41.html', {'job': job, 'today': timezone.now()})





@login_required

def print_tbs_letter_view(request, job_id):

    job = get_object_or_404(JobShipment.objects.select_related('customer', 'documentation_officer'), id=job_id)

    if not job.tbs_letter_reference_no:

        job.tbs_letter_reference_no = f"MALKIA/TBS/{job.job_number}"

        job.doc_tbs_letter_generated = True

        job.save(update_fields=['tbs_letter_reference_no', 'doc_tbs_letter_generated'])

    return render(request, 'core/print_tbs_letter.html', {'job': job, 'today': timezone.now()})





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





@login_required

def advance_stage_action(request, job_id):

    if request.method == 'POST':

        job = get_object_or_404(JobShipment, id=job_id)

        current_stage = job.stages.filter(stage_number=job.current_stage_number).first()



        # RBAC Check: Ensure user role is permitted to advance this stage

        if not can_advance_stage(request.user, job.current_stage_number):

            role_disp = request.user.profile.get_role_display() if hasattr(request.user, 'profile') else get_user_role(request.user)

            messages.error(

                request,

                f"RBAC Permission Denied: Your role ({role_disp}) cannot advance Stage {job.current_stage_number} ({current_stage.name_en}). Assigned authority: {current_stage.stage_definition.get_required_role_display()}."

            )

            return redirect('job_detail', job_id=job.id)



        remarks = request.POST.get('remarks', '').strip()

        customs_doc_number = request.POST.get('customs_doc_number', '').strip()

        amount_paid = request.POST.get('amount_paid', '').strip()

        payment_reference = request.POST.get('payment_reference', '').strip()



        # Gate check for Stage 3: Duty Payment
        if job.current_stage_number == 3 and job.clearance_mode != 'BOND':
            duty_status = request.POST.get('duty_paid_confirm')
            if not duty_status and not job.duty_paid:
                messages.error(request, "STAGE BLOCKED: TRA Duty Payment must be confirmed by Finance before advancing past Stage 3!")
                return redirect('job_detail', job_id=job.id)

            job.duty_paid = True

            if payment_reference:

                job.duty_payment_reference = payment_reference

                job.duty_payment_date = timezone.now().date()

            if amount_paid:

                try:

                    job.assessed_duty_amount = Decimal(amount_paid)

                except Exception:

                    pass



        # Specific stage field updates for the 9 Real-World Vehicle Clearance Stages

        if job.current_stage_number == 2 and customs_doc_number:

            job.declaration_number = customs_doc_number

        elif job.current_stage_number == 3:

            if job.clearance_mode == 'BOND':

                job.duty_payment_reference = payment_reference or 'RO-2026-BOND-APPROVED'

                job.tra_status = 'ACCEPTED'

                job.tra_accepted_at = now

            else:

                job.duty_paid = True

                job.duty_payment_reference = payment_reference

                job.duty_payment_date = now.date()

        elif job.current_stage_number == 4 and customs_doc_number:

            job.delivery_order_number = customs_doc_number

        elif job.current_stage_number == 5:

            # Physical verification passed

            pass

        elif job.current_stage_number == 6 and customs_doc_number:

            job.port_invoice_number = customs_doc_number

        elif job.current_stage_number == 7:

            if customs_doc_number:

                job.gate_pass_number = customs_doc_number

            truck = request.POST.get('truck_number')

            if truck:

                job.vehicle_driver_name = truck

            job.vehicle_inspection_done = True

            job.vehicle_dispatched_to_office = True

            job.vehicle_dispatched_at = now

        elif job.current_stage_number == 8:

            job.vehicle_arrived_at_office = True

            job.vehicle_arrived_at = now

            if customs_doc_number:

                job.box_number = customs_doc_number

        elif job.current_stage_number == 9:

            recipient = request.POST.get('received_by_name')

            if recipient:

                job.received_by_name = recipient

            job.delivered_date = now

            job.status = 'COMPLETED'

            if 'pod_file' in request.FILES:

                job.proof_of_delivery_image = request.FILES['pod_file']



        # Mark current stage completed

        now = timezone.now()

        if current_stage:

            current_stage.status = 'COMPLETED'

            current_stage.completed_at = now

            current_stage.responsible_officer = request.user

            if remarks:

                current_stage.remarks = remarks

            current_stage.save()



        # Handle file upload if attached

        if 'stage_document' in request.FILES:

            doc_file = request.FILES['stage_document']

            doc_type = request.POST.get('document_type', 'OTHER')

            JobDocument.objects.create(

                job=job,

                stage=current_stage,

                document_type=doc_type,

                title=f"Stage {job.current_stage_number} Attachment: {doc_file.name}",

                file=doc_file,

                uploaded_by=request.user,

                notes=remarks

            )



        # Move to next stage if not final (9 real stages)

        if job.current_stage_number < 9:

            next_num = job.current_stage_number + 1

            job.current_stage_number = next_num

            next_stage = job.stages.filter(stage_number=next_num).first()

            if next_stage:

                next_stage.status = 'IN_PROGRESS'

                next_stage.started_at = now

                next_stage.save()

            log_audit(request, "ADVANCE_STAGE", f"Advanced Job {job.job_number} to Stage {next_num}: {next_stage.name_en if next_stage else ''}", job=job)



            # Automated Customer Email Notification for this milestone

            try:

                from .email_service import send_stage_update_email

                send_stage_update_email(job, next_num, extra_note=remarks)

            except Exception as e:

                print(f"[Email Notification Error] {e}")



            messages.success(request, f"Hatua imekamilika! Mteja ametumiwa barua pepe ya taarifa ({next_stage.name_sw if next_stage else ''}).")

        else:

            job.status = 'COMPLETED'

            if not job.delivered_date:

                job.delivered_date = now

            job.save()

            log_audit(request, "COMPLETE_JOB", f"Job {job.job_number} successfully completed and delivered.", job=job)



            # Automated Customer Email Notification for final delivery

            try:

                from .email_service import send_stage_update_email

                send_stage_update_email(job, 9, extra_note=remarks)

            except Exception as e:

                print(f"[Email Notification Error] {e}")



            messages.success(request, f"Hongera! Job {job.job_number} imekamilika na kufikishwa, na barua pepe ya shukrani na POD imetumwa kwa mteja!")



        job.save()



    # Route back to field if from field view

    if 'field' in request.META.get('HTTP_REFERER', ''):

        return redirect('field_mobile')

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
    Manual trigger to send or re-send one of the 3 official dual-channel notifications (Email + SMS) to the client.
    """
    job = get_object_or_404(JobShipment, id=job_id)
    from .email_service import notify_client_milestone

    milestone_key = request.POST.get('milestone') or request.GET.get('milestone')
    if not milestone_key:
        if job.vehicle_arrived_at_office or job.current_stage_number >= 8:
            milestone_key = 'PORT_EXIT_YARD_ARRIVAL'
        elif job.duty_control_number or job.assessed_duty_amount > 0 or job.current_stage_number >= 3:
            milestone_key = 'TRA_DUTY_ISSUED'
        else:
            milestone_key = 'DOCS_RECEIVED'

    note = request.POST.get('note', '') or request.GET.get('note', '')
    res = notify_client_milestone(job, milestone_key, extra_note=note)

    if res['email_ok'] or res['sms_ok']:
        messages.success(
            request,
            f"✅ Taarifa ({milestone_key}) imetumwa kwa mteja! Email: {'Imetumwa' if res['email_ok'] else res['email_info']} | SMS: {'Imetumwa' if res['sms_ok'] else res['sms_info']}"
        )
    else:
        messages.warning(
            request,
            f"⚠️ Ujumbe haujatoka: Email ({res['email_info']}) | SMS ({res['sms_info']}). Hakikisha umeweka credentials za Resend na NextSMS kwenye Settings."
        )

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

@role_required([UserRole.FINANCE, UserRole.OPERATIONS_MGR, UserRole.CEO, UserRole.ADMIN])

def finance_pending_payments_view(request):

    query = request.GET.get('q', '').strip()

    category_filter = request.GET.get('category', '')

    status_filter = request.GET.get('status', 'pending')



    expenses = ExpenseVoucher.objects.all().select_related('job', 'job__customer', 'requester', 'approver').order_by('-requested_at')



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



    if status_filter == 'pending':

        expenses = expenses.filter(Q(approval_status='REQUESTED') | Q(approval_status='APPROVED', is_paid=False))

    elif status_filter == 'requested':

        expenses = expenses.filter(approval_status='REQUESTED')

    elif status_filter == 'approved':

        expenses = expenses.filter(approval_status='APPROVED', is_paid=False)

    elif status_filter == 'paid':

        expenses = expenses.filter(is_paid=True)



    # Breakdown metrics by payment type according to spec

    all_active_vouchers = ExpenseVoucher.objects.filter(Q(approval_status='REQUESTED') | Q(approval_status='APPROVED', is_paid=False))

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

@role_required([UserRole.FINANCE, UserRole.OPERATIONS_MGR, UserRole.CEO, UserRole.ADMIN])

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



    total_income = ClientPayment.objects.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    total_expenses = ExpenseVoucher.objects.filter(is_paid=True).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

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

                'notes': p.notes or "Payment received in full settlement of customs clearing and forwarding charges.",

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



    transactions.sort(key=lambda x: x['date'], reverse=True)



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





@login_required

@role_required([UserRole.FINANCE, UserRole.OPERATIONS_MGR, UserRole.CEO, UserRole.ADMIN])

def finance_billing_view(request):

    query = request.GET.get('q', '').strip()

    status_filter = request.GET.get('status', '')



    invoices = ClientInvoice.objects.all().select_related('job', 'customer').prefetch_related('payments').order_by('-issue_date')



    if query:

        invoices = invoices.filter(

            Q(invoice_number__icontains=query) |

            Q(customer__company_name__icontains=query) |

            Q(job__job_number__icontains=query) |

            Q(job__bl_number__icontains=query)

        )



    if status_filter:

        if status_filter == 'outstanding':

            invoices = invoices.filter(status__in=['ISSUED', 'PARTIALLY_PAID', 'OVERDUE'])

        else:

            invoices = invoices.filter(status=status_filter)



    total_billed = ClientInvoice.objects.aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')

    total_collected = ClientInvoice.objects.aggregate(total=Sum('amount_paid'))['total'] or Decimal('0.00')

    total_outstanding = total_billed - total_collected

    overdue_count = ClientInvoice.objects.filter(status='OVERDUE').count()



    context = {

        'invoices': invoices,

        'search_query': query,

        'status_filter': status_filter,

        'total_billed': total_billed,

        'total_collected': total_collected,

        'total_outstanding': total_outstanding,

        'overdue_count': overdue_count,

        'jobs': JobShipment.objects.filter(status__in=['ACTIVE', 'DELAYED', 'COMPLETED']).select_related('customer'),

        'payment_methods': ClientPayment.PAYMENT_METHODS,

    }

    return render(request, 'core/finance_billing.html', context)







@login_required

def expense_create_action(request):

    if request.method == 'POST':

        if get_user_role(request.user) == UserRole.CEO:

            messages.error(request, "Akaunti ya Boss ina mamlaka ya ukaguzi tu (Read-Only) na haina ruhusa ya kuomba vocha ya matumizi.")

            return redirect('finance')



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

        return redirect('finance')

    return redirect('finance')





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

        decision = request.POST.get('decision') # 'APPROVE', 'REJECT', or 'PAY'

        remarks = request.POST.get('remarks', '').strip()



        # RBAC Enforcement: Check Approval Authority

        if decision in ['APPROVE', 'REJECT']:

            if not can_approve_expense(request.user, voucher):

                role_disp = request.user.profile.get_role_display() if hasattr(request.user, 'profile') else get_user_role(request.user)

                messages.error(

                    request,

                    f"RBAC Unauthorized: Your role ({role_disp}) cannot approve expenses of TSh {voucher.amount:,.2f}. This amount strictly requires approval by {voucher.get_required_role_display()}."

                )

                return redirect('finance')



            if decision == 'APPROVE':

                voucher.approval_status = 'APPROVED'
                now = timezone.now()
                voucher.approval_date = now
                voucher.approver = request.user
                voucher.approval_remarks = remarks

                # When Finance, Admin, or Operations approves an operational voucher (D/O or Port Charges),
                # automatically disburse/settle payment and advance the shipment milestone!
                user_role = get_user_role(request.user)
                can_disburse_auto = (user_role in [UserRole.FINANCE, UserRole.ADMIN, UserRole.OPERATIONS_MGR] or request.user.is_superuser)
                if can_disburse_auto:
                    voucher.is_paid = True
                    voucher.paid_at = now
                    voucher.payment_reference = voucher.control_number or f"PAY-{voucher.voucher_number}"

                voucher.save()

                if voucher.is_paid:
                    _sync_operational_voucher_to_job(voucher, request)

                log_audit(request, "APPROVE_EXPENSE", f"Approved & settled expense {voucher.voucher_number} of TSh {voucher.amount:,.2f} ({voucher.get_category_display()}).", job=voucher.job)
                messages.success(request, f"Expense {voucher.voucher_number} ({voucher.get_category_display()}) has been APPROVED & DISBURSED by {request.user.get_full_name() or request.user.username}!")

            elif decision == 'REJECT':

                voucher.approval_status = 'REJECTED'
                voucher.approval_date = timezone.now()
                voucher.approver = request.user
                voucher.approval_remarks = remarks
                voucher.save()

                log_audit(request, "REJECT_EXPENSE", f"Rejected expense {voucher.voucher_number}: {remarks}", job=voucher.job)
                messages.warning(request, f"Expense {voucher.voucher_number} has been REJECTED.")

        elif decision == 'PAY':

            # Disbursing funds strictly requires Finance or Admin
            user_role = get_user_role(request.user)
            if user_role not in [UserRole.FINANCE, UserRole.ADMIN, UserRole.OPERATIONS_MGR] and not request.user.is_superuser:
                messages.error(request, "RBAC Unauthorized: Only Finance/Accounts staff can disburse funds and record payments.")
                return redirect('finance')

            pay_method = request.POST.get('payment_method')
            if pay_method:
                voucher.payment_method = pay_method

            voucher.is_paid = True
            now = timezone.now()
            voucher.paid_at = now
            pay_ref = request.POST.get('payment_reference', '').strip()
            voucher.payment_reference = pay_ref or voucher.control_number or f"PAY-{voucher.voucher_number}"
            voucher.save()

            # Automatic synchronization with shipment workflow for payments
            _sync_operational_voucher_to_job(voucher, request)

            log_audit(request, "DISBURSE_EXPENSE", f"Disbursed/Paid expense {voucher.voucher_number} [{voucher.get_payment_method_display()}] (Ref: {voucher.payment_reference})", job=voucher.job)

            messages.success(request, f"Expense {voucher.voucher_number} marked as PAID/DISBURSED ({voucher.get_payment_method_display()}). Shipment {job.job_number} duty payment marked as SETTLED!")



    return redirect('finance')





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

        shipping_line = Decimal(request.POST.get('shipping_line', '0') or '0')

        transport = Decimal(request.POST.get('transport', '0') or '0')

        sundry = Decimal(request.POST.get('sundry', '0') or '0')



        total = agency_fee + duty_reimb + port_charges + shipping_line + transport + sundry

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

            amount_shipping_line_do=shipping_line,

            amount_transport=transport,

            amount_sundry_charges=sundry,

            total_amount=total,

            status='ISSUED',

            notes=request.POST.get('notes', '')

        )



        log_audit(request, "CREATE_INVOICE", f"Issued Invoice {inv_number} of TSh {total:,.2f} for {customer.company_name} on {job.job_number}", job=job)

        messages.success(request, f"Client Invoice {inv_number} for TSh {total:,.2f} generated successfully!")

        

        next_url = request.POST.get('next', 'finance')

        if next_url == 'job_detail':

            return redirect('job_detail', job_id=job.id)

        return redirect('finance')

    return redirect('finance')





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



    return redirect('finance')





@login_required

def upload_document_action(request, job_id):

    if request.method == 'POST':

        if get_user_role(request.user) == UserRole.CEO:

            messages.error(request, "The Executive account has read-only audit access and cannot upload documents.")

            return redirect('job_detail', job_id=job_id)



        job = get_object_or_404(JobShipment, id=job_id)

        doc_type = request.POST.get('document_type', 'OTHER')

        title = request.POST.get('title', '').strip()

        notes = request.POST.get('notes', '').strip()



        if 'file' in request.FILES:

            uploaded_file = request.FILES['file']

            if not title:

                title = uploaded_file.name



            JobDocument.objects.create(

                job=job,

                document_type=doc_type,

                title=title,

                file=uploaded_file,

                uploaded_by=request.user,

                notes=notes

            )

            log_audit(request, "UPLOAD_DOCUMENT", f"Uploaded document '{title}' ({doc_type}) to Job {job.job_number}", job=job)

            messages.success(request, f"Document '{title}' uploaded successfully!")

        else:

            messages.error(request, "No file was selected for upload.")



    return redirect('job_detail', job_id=job_id)





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


@login_required
def download_job_document_view(request, document_id):
    doc = get_object_or_404(JobDocument.objects.select_related('job'), id=document_id)
    try:
        f = doc.file.open('rb')
        content_type, _ = mimetypes.guess_type(doc.file.name)
        if not content_type:
            content_type = 'application/octet-stream'
        
        ext = os.path.splitext(doc.file.name)[1] or '.pdf'
        doc_type_clean = doc.get_document_type_display().replace(' ', '_').replace('/', '_').replace('(', '').replace(')', '')
        bl_clean = (doc.job.bl_number or doc.job.job_number).replace('/', '_').replace(' ', '')
        clean_filename = f"{doc_type_clean}_{bl_clean}{ext}"

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
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for idx, doc in enumerate(docs, 1):
            try:
                ext = os.path.splitext(doc.file.name)[1] or '.pdf'
                doc_type_clean = doc.get_document_type_display().replace(' ', '_').replace('/', '_').replace('(', '').replace(')', '')
                bl_clean = (job.bl_number or job.job_number).replace('/', '_').replace(' ', '')
                clean_name = f"{idx:02d}_{doc_type_clean}_{bl_clean}{ext}"
                
                with doc.file.open('rb') as f:
                    file_content = f.read()
                zip_file.writestr(clean_name, file_content)
            except Exception as e:
                print(f"[ZIP Pack Error on doc {doc.id}] {e}")

    zip_buffer.seek(0)
    bl_slug = (job.bl_number or job.job_number).replace('/', '_').replace(' ', '')
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

    if selected_job:

        recent_logs = selected_job.audit_logs.all().select_related('user').order_by('-timestamp')[:8]

        job_docs = selected_job.documents.all().order_by('-uploaded_at')[:6]

        port_vouchers = selected_job.expenses.exclude(category=ExpenseCategory.CUSTOMS_DUTY).order_by('-requested_at')



    context = {

        'jobs': jobs,

        'selected_job': selected_job,

        'recent_logs': recent_logs,

        'job_docs': job_docs,

        'port_vouchers': port_vouchers,

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
            messages.success(request, f"🚀 Ombi la malipo ({cat_label} - TSh {amt:,.2f}) limetumwa Finance! Ukishalipiwa litaonekana PAID.")
            return redirect(f"/field/updates/?job_id={job.id}")



        # 1. TRA PHYSICAL VERIFICATION

        elif update_type in ['VERIFICATION', 'TRA_VERIFICATION']:

            verification_outcome = request.POST.get('verification_outcome', 'PASSED')

            findings = request.POST.get('findings', '').strip()

            is_passed = 'PASS' in verification_outcome.upper() or verification_outcome == 'PASSED'



            if is_passed:

                note = f"TRA Physical Verification: PASSED / Wameridhia. {findings} {remarks}".strip()

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

                

                if job.current_stage_number == 5:

                    if current_stage:

                        current_stage.status = 'COMPLETED'

                        current_stage.completed_at = timezone.now()

                        current_stage.completed_by = request.user

                        current_stage.remarks = note

                        current_stage.save()

                    job.current_stage_number = 6

                    job.status = 'ACTIVE'

                    job.save()

                    next_stage = job.stages.filter(stage_number=6).first()

                    if next_stage:

                        next_stage.status = 'IN_PROGRESS'

                        next_stage.started_at = timezone.now()

                        next_stage.save()

                    

                    try:

                        from .email_service import send_stage_update_email

                        send_stage_update_email(job, 6, extra_note=note)

                    except Exception as e:

                        print(f"[Email Notification Error] {e}")



                log_audit(request, "PHYSICAL_VERIFICATION_PASSED", note, job=job)
                log_audit(request, "FIELD_VERIFICATION", note, job=job)

                messages.success(request, f"✅ TRA Physical Verification approved for vehicle {job.chassis_number or job.job_number}! File advanced to Stage 6 (Port & ICD Charges).")

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
                job.gate_pass_number = f"GP-{job.port_invoice_number or job.id:04d}"

            job.vehicle_driver_name = driver_name
            job.vehicle_dispatched_to_office = True
            job.vehicle_dispatched_at = now

            # Complete Stage 7 (Gate Exit & Vehicle Inspection) and advance to Stage 8 (Malkia Yard Arrival)
            st7 = job.stages.filter(stage_number=7).first()
            if st7:
                st7.status = 'COMPLETED'
                st7.completed_at = now
                st7.completed_by = request.user
                st7.responsible_officer = request.user
                st7.remarks = f"Gate Pass #{job.gate_pass_number} | Driver: {driver_name} | Inspected Clean. {notes}".strip()
                st7.save()

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

            summary = f"Gate Exit & Ukaguzi wa gari ICD (Gate Pass #{job.gate_pass_number}, Dereva: {driver_name}): Mikwaruzo: {'IPO' if has_scratches else 'HAKUNA'}, Radio: {'IPO' if radio_present else 'KOSA'}, Spare: {'IPO' if spare_wheel_present else 'KOSA'}, Jack: {'IPO' if jack_tools_present else 'KOSA'}. {notes}".strip()
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
                job.gate_pass_number = f"GP-{job.port_invoice_number or job.id:04d}"

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
        active_sender = sender_name or SystemConfig.get_value('RESEND_SENDER_NAME', 'Malkia Freight & Logistics')
        active_from = from_email or SystemConfig.get_value('RESEND_FROM_EMAIL', 'onboarding@resend.dev')

        subject = f"Uthibitisho wa Mfumo wa Barua Pepe (Resend) - {active_sender}"
        html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; border: 1px solid #E2E8F0; border-radius: 12px; overflow: hidden; background: #FFFFFF;">
            <div style="background: linear-gradient(135deg, #0F766E 0%, #0F172A 100%); padding: 24px; color: #FFFFFF; text-align: center;">
                <h1 style="margin: 0; font-size: 21px; font-weight: 800;">MALKIA FREIGHT &amp; LOGISTICS</h1>
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

        'roles': UserRole.choices,

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

        'roles': UserRole.choices,

        'statuses': UserProfile.EMPLOYMENT_STATUS_CHOICES,

        'employment_types': UserProfile.EMPLOYMENT_TYPE_CHOICES,

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



    context = {

        'target_user': target_user,

        'profile': profile,

        'qr_code_b64': qr_code_b64,

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

    Computes the 9 simplified real-world vehicle clearing & forwarding milestones

    strictly enforcing causal forward pipeline progression:

    If a vehicle has reached Step N (e.g. Yard Arrival), all previous steps

    (1 to N-1, including Gate Exit) are logically and physically COMPLETED.

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



    def _fmt_duration(td):

        if not td:

            return None

        sec = max(0, int(td.total_seconds()))

        if sec < 60:

            return f"{sec}s"

        mins = sec // 60

        if mins < 60:

            return f"{mins} min" if mins == 1 else f"{mins} mins"

        hrs = mins // 60

        rem_m = mins % 60

        if hrs < 24:

            return f"{hrs}h {rem_m}m" if rem_m else f"{hrs} hrs"

        days = hrs // 24

        rem_h = hrs % 24

        return f"{days}d {rem_h}h" if rem_h else f"{days} days"



    def _calc_duration(end_val, start_val, default=None):

        end_dt = _to_dt(end_val)

        start_dt = _to_dt(start_val)

        if not end_dt or not start_dt:

            return default

        try:

            if timezone.is_aware(end_dt) and timezone.is_naive(start_dt):

                start_dt = timezone.make_aware(start_dt)

            elif timezone.is_naive(end_dt) and timezone.is_aware(start_dt):

                end_dt = timezone.make_aware(end_dt)

            diff = end_dt - start_dt

            if diff.total_seconds() < 0:

                return default or "Under 1h"

            return _fmt_duration(diff)

        except Exception:

            return default



    # Extract audit log records and users

    logs = list(job.audit_logs.all().order_by('timestamp'))

    log_users = {l.action: (l.user.get_full_name() or l.user.username) for l in logs}

    log_times = {l.action: l.timestamp for l in logs}



    # Determine maximum step reached based on physical milestones

    max_step_reached = 1

    if job.declaration_number or job.tanesw_lodged_at or log_times.get('TANESW_LODGED'):

        max_step_reached = max(max_step_reached, 2)

    if job.duty_paid or job.duty_payment_reference or (job.tra_status in ['ACCEPTED', 'OBJECTION']) or log_times.get('TRA_BOND_RELEASE_ACCEPTED') or log_times.get('DUTY_PAID'):

        max_step_reached = max(max_step_reached, 3)

    if job.delivery_order_number or log_times.get('DELIVERY_ORDER_RECORDED'):

        max_step_reached = max(max_step_reached, 4)

    if job.vehicle_inspection_done or job.stages.filter(stage_number=5, status='COMPLETED').exists() or log_times.get('PHYSICAL_VERIFICATION_PASSED'):

        max_step_reached = max(max_step_reached, 5)

    if job.port_invoice_number or log_times.get('PORT_INVOICE_PAID'):

        max_step_reached = max(max_step_reached, 6)

    if job.gate_pass_number or job.vehicle_dispatched_to_office or log_times.get('GATE_EXIT_RECORDED'):

        max_step_reached = max(max_step_reached, 7)

    if job.vehicle_arrived_at_office or job.box_number or log_times.get('YARD_ARRIVAL_RECORDED'):

        max_step_reached = max(max_step_reached, 8)

    if is_completed or job.delivered_date or job.proof_of_delivery_image:

        max_step_reached = max(max_step_reached, 9)



    # Effective current active stage

    # Effective current active stage
    curr_stage = job.current_stage_number or 1

    # Has Declaration / Control Number been issued?
    # Step 2 is only complete when Control Number is issued and awaiting payment (or advanced to stage 3+)
    has_declaration_done = bool(
        (job.duty_control_number and job.duty_control_number.strip()) or
        (job.declaration_number and job.assessed_duty_amount and job.assessed_duty_amount > 0) or
        (job.tra_status in ['ACCEPTED', 'OBJECTION']) or
        log_times.get('TRA_ASSESSMENT_ISSUED') or
        log_times.get('TRA_BOND_RELEASE_ACCEPTED') or
        log_times.get('DUTY_PAID') or
        curr_stage > 2 or
        max_step_reached > 2 or
        is_completed
    )

    # Has Duty Payment / In-Bond been settled?
    if is_bond:
        has_payment_done = bool(
            job.tra_status == 'ACCEPTED' or
            log_times.get('TRA_BOND_RELEASE_ACCEPTED') or
            curr_stage > 3 or
            max_step_reached > 3 or
            is_completed
        )
    else:
        # In Direct Duty: Duty must actually be paid & confirmed by Finance
        # (A control number or invoice reference is NOT payment!)
        has_payment_done = bool(
            job.duty_paid or
            log_times.get('DUTY_PAID') or
            (curr_stage > 3 and job.duty_paid) or
            (is_completed and job.duty_paid)
        )

    # Has Delivery Order (D/O) been issued?
    has_do_done = bool(
        (job.delivery_order_number and job.delivery_order_number.strip()) or
        log_times.get('DELIVERY_ORDER_RECORDED') or
        (curr_stage > 4 and has_payment_done) or
        (max_step_reached > 4 and has_payment_done) or
        (is_completed and has_payment_done)
    )

    # Has Physical Verification been completed?
    has_verification_done = bool(
        job.stages.filter(stage_number=5, status='COMPLETED').exists() or
        log_times.get('PHYSICAL_VERIFICATION_PASSED') or
        log_times.get('FIELD_VERIFICATION') or
        curr_stage > 5 or
        max_step_reached > 5 or
        is_completed
    )

    # Has Port & ICD charges been paid?
    has_port_charges_done = bool(
        (job.port_invoice_number and job.port_invoice_number.strip()) or
        log_times.get('PORT_INVOICE_PAID') or
        curr_stage > 6 or
        max_step_reached > 6 or
        is_completed
    )

    # Has Gate Exit & Vehicle Inspection been recorded?
    has_gate_exit_done = bool(
        (job.gate_pass_number and job.gate_pass_number.strip()) or
        job.vehicle_dispatched_to_office or
        (job.vehicle_inspection_done and has_port_charges_done) or
        job.stages.filter(stage_number=7, status='COMPLETED').exists() or
        log_times.get('GATE_EXIT_RECORDED') or
        log_times.get('VEHICLE_DISPATCH') or
        curr_stage > 7 or
        max_step_reached > 7 or
        is_completed
    )

    # Has Malkia Yard Arrival occurred?
    has_yard_done = bool(
        job.vehicle_arrived_at_office or
        (job.box_number and job.box_number.strip()) or
        job.stages.filter(stage_number=8, status='COMPLETED').exists() or
        log_times.get('YARD_ARRIVAL_RECORDED') or
        log_times.get('VEHICLE_ARRIVED_YARD') or
        log_times.get('VEHICLE_ARRIVED_BOND') or
        log_times.get('YARD_ARRIVAL') or
        curr_stage > 8 or
        max_step_reached > 8 or
        is_completed
    )

    # Has Customer Handover occurred?
    has_handover_done = bool(
        is_completed or
        job.delivered_date or
        job.proof_of_delivery_image
    )

    s1_done = True
    s2_done = has_declaration_done
    s3_done = has_payment_done
    s4_done = has_do_done
    s5_done = has_verification_done
    s6_done = has_port_charges_done
    s7_done = has_gate_exit_done
    s8_done = has_yard_done
    s9_done = has_handover_done

    # Subtitles
    s1_sub = f"File Opened ({job.job_number})"
    if s2_done:
        if job.duty_control_number:
            s2_sub = f"Control No: {job.duty_control_number}"
        elif job.declaration_number:
            s2_sub = f"TANSAD #{job.declaration_number}"
        else:
            s2_sub = "Lodged in TANSAD"
    else:
        s2_sub = "Pending TANSAD Lodgement & Control No"

    if is_bond:
        s3_title = "In-Bond Clearance"
        if s3_done:
            s3_sub = f"In-Bond Approved ({job.duty_payment_reference or 'RO Approved'})"
        elif s2_done:
            s3_sub = "Awaiting Bond Release Approval"
        else:
            s3_sub = "Under Customs Bond"
    else:
        s3_title = "TRA Duty Payment"
        if s3_done:
            s3_sub = f"Duty Settled ({job.duty_payment_reference or 'Paid'})"
        elif job.duty_control_number:
            s3_sub = f"Pending Payment (Ctrl #{job.duty_control_number})"
        else:
            s3_sub = "Awaiting Control Number"

    s4_sub = f"D/O #{job.delivery_order_number}" if job.delivery_order_number else ("D/O Released" if s4_done else "Awaiting D/O")

    s5_sub = "Customs Verified" if s5_done else "Awaiting Inspection"

    s6_sub = f"Invoice #{job.port_invoice_number}" if job.port_invoice_number else ("Port Charges Settled" if s6_done else "Pending Port Invoice")

    s7_sub = f"Gate Pass #{job.gate_pass_number}" if job.gate_pass_number else ("Gate Exited & Released" if s7_done else "At Port / ICD")

    s8_sub = f"At Malkia Yard ({job.box_number or 'Bay Parked'})" if s8_done else "In Transit to Yard"

    s9_sub = f"Delivered ({job.received_by_name or 'POD Signed'})" if s9_done else "Pending Handover"



    # Officers

    s1_officer = getattr(job.documentation_officer, 'get_full_name', lambda: None)() or log_users.get('OPEN_FILE_AND_SCAN_DOCS') or 'Amani Bakari (Doc Officer)'

    s2_officer = getattr(job.clearing_officer, 'get_full_name', lambda: None)() or log_users.get('TANESW_LODGED') or 'Rashid Nassor (Customs Declarer)'

    if is_bond:
        s3_officer = getattr(job.clearing_officer, 'get_full_name', lambda: None)() or log_users.get('TRA_BOND_RELEASE_ACCEPTED') or 'Rashid Nassor (Customs Declarer)'
    else:
        if s3_done:
            s3_officer = log_users.get('DUTY_PAID') or 'Subira Kilonzo (Finance Officer)'
        else:
            s3_officer = 'Subira Kilonzo (Finance Officer)'


    s4_officer = getattr(job.port_officer, 'get_full_name', lambda: None)() or 'Port Operations Officer'

    s5_officer = getattr(job.port_officer, 'get_full_name', lambda: None)() or 'Port Verification Inspector'

    s6_officer = 'Port Finance & Accounts'

    s7_officer = getattr(job.port_officer, 'get_full_name', lambda: None)() or 'Port Gate Inspector'

    s8_officer = getattr(job.driver, 'get_full_name', lambda: None)() or 'Transport Driver & Yard Master'

    s9_officer = getattr(job.documentation_officer, 'get_full_name', lambda: None)() or 'Customer Service Officer'



    # Timestamps & Durations

    s1_time = job.file_opened_at or (logs[0].timestamp if logs else job.created_at)

    s2_time = job.tanesw_lodged_at or log_times.get('TANESW_LODGED')

    s3_time = log_times.get('TRA_BOND_RELEASE_ACCEPTED') or log_times.get('DUTY_PAID') or job.duty_payment_date

    s4_time = log_times.get('DELIVERY_ORDER_RECORDED')

    s5_time = log_times.get('PHYSICAL_VERIFICATION_PASSED') or log_times.get('FIELD_VERIFICATION')

    s6_time = log_times.get('PORT_INVOICE_PAID')

    s7_time = log_times.get('GATE_EXIT_RECORDED') or log_times.get('VEHICLE_DISPATCH') or log_times.get('VEHICLE_INSPECTION') or job.vehicle_dispatched_at or job.vehicle_inspection_at

    s8_time = log_times.get('YARD_ARRIVAL_RECORDED') or log_times.get('VEHICLE_ARRIVED_YARD') or log_times.get('VEHICLE_ARRIVED_BOND') or log_times.get('YARD_ARRIVAL') or job.vehicle_arrived_at

    s9_time = job.delivered_date



    s1_duration = "Instant (Setup)"

    s2_duration = _calc_duration(s2_time, s1_time, default=("2 mins" if s2_done else None))

    s3_duration = _calc_duration(s3_time, s2_time, default=("57 mins" if s3_done else None))

    s4_duration = _calc_duration(s4_time, s3_time, default=("1h 20m" if s4_done else None))

    s5_duration = _calc_duration(s5_time, s4_time, default=("3 hrs" if s5_done else None))

    s6_duration = _calc_duration(s6_time, s5_time, default=("1.5 hrs" if s6_done else None))

    s7_duration = _calc_duration(s7_time, s6_time, default=("45 mins" if s7_done else None))

    s8_duration = _calc_duration(s8_time, s7_time, default=("1 hr" if s8_done else None))

    s9_duration = _calc_duration(s9_time, s8_time, default=("Same Day" if s9_done else None))



    milestones = [

        {'id': 1, 'name': 'File Opening', 'subtitle': s1_sub, 'done': s1_done, 'assigned_officer': s1_officer, 'completed_at': s1_time, 'time_taken': s1_duration, 'target_sla': 'Same Day'},

        {'id': 2, 'name': 'Customs Declaration', 'subtitle': s2_sub, 'done': s2_done, 'assigned_officer': s2_officer, 'completed_at': s2_time, 'time_taken': s2_duration, 'target_sla': '24 Hours'},

        {'id': 3, 'name': s3_title, 'subtitle': s3_sub, 'done': s3_done, 'assigned_officer': s3_officer, 'completed_at': s3_time, 'time_taken': s3_duration, 'target_sla': '76 Hours SLA'},

        {'id': 4, 'name': 'Delivery Order (D/O)', 'subtitle': s4_sub, 'done': s4_done, 'assigned_officer': s4_officer, 'completed_at': s4_time, 'time_taken': s4_duration, 'target_sla': '24 Hours'},

        {'id': 5, 'name': 'Physical Verification', 'subtitle': s5_sub, 'done': s5_done, 'assigned_officer': s5_officer, 'completed_at': s5_time, 'time_taken': s5_duration, 'target_sla': '1-2 Days'},

        {'id': 6, 'name': 'Port & ICD Charges', 'subtitle': s6_sub, 'done': s6_done, 'assigned_officer': s6_officer, 'completed_at': s6_time, 'time_taken': s6_duration, 'target_sla': '24 Hours'},

        {'id': 7, 'name': 'Gate Exit & Inspection', 'subtitle': s7_sub, 'done': s7_done, 'assigned_officer': s7_officer, 'completed_at': s7_time, 'time_taken': s7_duration, 'target_sla': 'Same Day'},

        {'id': 8, 'name': 'Malkia Yard Arrival', 'subtitle': s8_sub, 'done': s8_done, 'assigned_officer': s8_officer, 'completed_at': s8_time, 'time_taken': s8_duration, 'target_sla': 'Same Day'},

        {'id': 9, 'name': 'Customer Handover', 'subtitle': s9_sub, 'done': s9_done, 'assigned_officer': s9_officer, 'completed_at': s9_time, 'time_taken': s9_duration, 'target_sla': 'Upon Request'},

    ]



    # Assign active/current flag

    if is_completed:

        for m in milestones:

            m['done'] = True

            m['current'] = False

    else:

        found_current = False

        for m in milestones:

            if not m['done'] and not found_current:

                m['current'] = True

                found_current = True

            else:

                m['current'] = False



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
    Automatically compiles all PAID/APPROVED port expenses, shipping line D/O vouchers,
    fuel/transport/sundry vouchers, and agency fee into a clean ClientInvoice.
    """
    from datetime import date
    from decimal import Decimal

    existing_invoice = job.invoices.first()

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

    # Shipping Line D/O
    shipping_vouchers = vouchers.filter(category=ExpenseCategory.SHIPPING_LINE)
    shipping_line_amt = shipping_vouchers.aggregate(tot=Sum('amount'))['tot'] or Decimal('0.00')

    # Port / ICD Charges
    port_vouchers = vouchers.filter(category=ExpenseCategory.PORT_CHARGES)
    port_charges_amt = port_vouchers.aggregate(tot=Sum('amount'))['tot'] or Decimal('0.00')

    # Transport / Driver allowance (strictly actual transport vouchers, no hardcoded 20,000)
    transport_vouchers = vouchers.filter(category=ExpenseCategory.TRANSPORT)
    transport_amt = transport_vouchers.aggregate(tot=Sum('amount'))['tot'] or Decimal('0.00')

    # Fuel, Port Handling, Documentation & Other operational expenses
    sundry_vouchers = vouchers.filter(
        category__in=[
            ExpenseCategory.FUEL,
            ExpenseCategory.PORT_HANDLING,
            ExpenseCategory.DOCUMENTATION,
            ExpenseCategory.OTHER,
        ]
    )
    sundry_amt = sundry_vouchers.aggregate(tot=Sum('amount'))['tot'] or Decimal('0.00')

    duty_reimb = Decimal('0.00')
    total_bill = agency_fee + shipping_line_amt + port_charges_amt + transport_amt + sundry_amt + duty_reimb

    invoice = existing_invoice
    today = date.today()
    if not invoice:
        count = ClientInvoice.objects.filter(invoice_number__startswith=f"INV/{today.year}/").count() + 1
        inv_no = f"INV/{today.year}/{count:04d}"

        invoice = ClientInvoice.objects.create(
            invoice_number=inv_no,
            job=job,
            customer=job.customer,
            issue_date=today,
            due_date=today,
            amount_clearing_agency_fee=agency_fee,
            amount_shipping_line_do=shipping_line_amt,
            amount_port_charges=port_charges_amt,
            amount_transport=transport_amt,
            amount_sundry_charges=sundry_amt,
            amount_duty_reimbursement=duty_reimb,
            total_amount=total_bill,
            amount_paid=Decimal('0.00'),
            status='ISSUED',
            notes=f"Auto-compiled from approved port & field vouchers for {job.cargo_description or job.chassis_number}"
        )
    else:
        invoice.amount_clearing_agency_fee = agency_fee
        invoice.amount_shipping_line_do = shipping_line_amt
        invoice.amount_port_charges = port_charges_amt
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



    ready_count = base_qs.filter(

        vehicle_arrived_at_office=True,

        clearance_mode='DIRECT',

        status__in=['ACTIVE', 'DELAYED']

    ).count()



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



    if tab == 'bond':

        vehicles = base_qs.filter(

            vehicle_arrived_at_office=True,

            clearance_mode='BOND',

            status__in=['ACTIVE', 'DELAYED']

        ).order_by('-vehicle_arrived_at', '-updated_at')

    elif tab == 'en_route':

        vehicles = base_qs.filter(

            vehicle_dispatched_to_office=True,

            vehicle_arrived_at_office=False,

            status__in=['ACTIVE', 'DELAYED']

        ).order_by('-vehicle_dispatched_at', '-updated_at')

    elif tab == 'delivered':

        vehicles = base_qs.filter(status='COMPLETED').order_by('-delivered_date', '-updated_at')

    else:

        vehicles = base_qs.filter(

            vehicle_arrived_at_office=True,

            clearance_mode='DIRECT',

            status__in=['ACTIVE', 'DELAYED']

        ).order_by('-vehicle_arrived_at', '-updated_at')



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
        "Disallow: /chat/",
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
    Serves /sitemap.xml with multilingual hreflang annotations for Google Search Console & Bing Webmaster Tools.
    """
    canonical_domain = SystemConfig.get_value('SEO_CANONICAL_DOMAIN', 'https://malkiacargowave.com').rstrip('/')
    portal_domain = SystemConfig.get_value('SEO_PORTAL_DOMAIN', 'https://portal.malkiacargowave.com').rstrip('/')
    today_iso = timezone.now().strftime('%Y-%m-%d')

    xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        xmlns:xhtml="http://www.w3.org/1999/xhtml">
    <url>
        <loc>{canonical_domain}/</loc>
        <lastmod>{today_iso}</lastmod>
        <changefreq>daily</changefreq>
        <priority>1.0</priority>
        <xhtml:link rel="alternate" hreflang="sw" href="{canonical_domain}/"/>
        <xhtml:link rel="alternate" hreflang="en" href="{canonical_domain}/?lang=en"/>
        <xhtml:link rel="alternate" hreflang="x-default" href="{canonical_domain}/"/>
    </url>
    <url>
        <loc>{canonical_domain}/website/</loc>
        <lastmod>{today_iso}</lastmod>
        <changefreq>weekly</changefreq>
        <priority>0.9</priority>
    </url>
    <url>
        <loc>{canonical_domain}/portal/</loc>
        <lastmod>{today_iso}</lastmod>
        <changefreq>daily</changefreq>
        <priority>0.8</priority>
    </url>
    <url>
        <loc>{portal_domain}/portal/</loc>
        <lastmod>{today_iso}</lastmod>
        <changefreq>daily</changefreq>
        <priority>0.8</priority>
    </url>
</urlset>"""
    return HttpResponse(xml_content, content_type="application/xml; charset=utf-8")


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
    Serves /manifest.json for Mobile SEO and Progressive Web App metadata.
    """
    manifest = {
        "name": "Malkia Cargo Wave Limited",
        "short_name": "Malkia Cargo",
        "description": "Utoaji wa Magari Bandari ya Dar es Salaam, Yadi ya In-Bond, na Usafirishaji Salama.",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#0B1329",
        "theme_color": "#1E3A8A",
        "lang": "sw-TZ",
    }
    return JsonResponse(manifest)


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



    system_prompt = """You are Malkia AI, the official customer service assistant for Malkia Cargo Wave Limited (malkiacargowave.com).

Malkia Cargo Wave Limited is a premier motor vehicle clearing and forwarding agency and licensed customs broker in Dar es Salaam, Tanzania, with private in-bond yard facilities.



KEY FACTS ABOUT MALKIA CARGO WAVE LIMITED:

1. Core Focus: Motor vehicle port clearance (RORO & containers from Japan, UK, Dubai, etc.).

2. Private In-Bond Yard: Licensed customs bonded facility near Dar Port. Importers who do not have full TRA duty ready can safely store their vehicles here under customs bond without paying immediate taxes, completely eliminating expensive port demurrage fines!

3. 100% Vehicle Safety Guarantee: Every vehicle undergoes strict accessory inspection (radio, spare wheel, battery, side mirrors, tools) upon discharge from the ship. Zero theft record.

4. Upfront Transparent Pricing: Free valuation and exact TRA tax calculation with official GePG control numbers. No hidden broker fees.

5. Upcountry & Doorstep Transit: Safe delivery across Tanzania (Mwanza, Arusha, Dodoma, Mbeya) and cross-border transit (Rwanda, Burundi, DRC, Zambia).

6. Contact & Office: Bandari Road, Port Area, Dar es Salaam, Tanzania. Phone/WhatsApp: +255 787 367 474, Email: info@malkiacargowave.com.

7. Portal for registered clients: portal.malkiacargowave.com.



INSTRUCTIONS:

- You are answering public visitors, car buyers, and vehicle importers.

- Be friendly, polite, confident, professional, and helpful.

- If the user writes in Swahili, reply in clear, natural, warm Swahili.

- If the user writes in English, reply in fluent, professional English.

- Keep answers concise, formatted with clear bullet points.

- If they ask for quotes or specific vehicle taxes, explain how Malkia calculates it and invite them to leave their vehicle model or contact WhatsApp +255 787 367 474."""



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

                timeout=12

            )

            if resp.status_code == 200:

                res_data = resp.json()

                reply = res_data.get('choices', [{}])[0].get('message', {}).get('content', '')

        except Exception as e:

            logger.warning(f"Hive AI error on website chat: {e}")



    # 3. Fallback smart response if AI call failed or timed out

    if not reply:

        msg_lower = user_message.lower()

        if any(w in msg_lower for w in ['gharama', 'cost', 'bei', 'price', 'duty', 'kodi', 'tra', 'quote', 'hesabu', 'calculate']):

            reply = (

                "Kuhusu **Gharama na Kodi ya TRA**:\n\n"

                "Kodi ya gari inategemea vigezo vinne vikuu vya TRA:\n"

                "1. Aina ya gari na modeli (mfano: IST, Harrier, Prado, Canter)\n"

                "2. Mwaka wa utengenezaji (Magari ya zaidi ya miaka 8 hulipiwa uchakavu/dumping fee)\n"

                "3. Ukubwa wa injini (CC za gari)\n"

                "4. Thamani ya gari (FOB / CIF value).\n\n"

                "👉 **Ushauri:** Tutumie nyaraka zako (Export Certificate au Invoice) kupitia WhatsApp **+255 787 367 474** au ujaze fomu hapo chini ili wataalamu wetu wakupigie na kukupa mchanganuo kamili na Control Number ya TRA bila malipo yoyote!"

            )

        elif any(w in msg_lower for w in ['bond', 'inbond', 'in-bond', 'yadi', 'yard', 'hifadhi', 'storage', 'demurrage', 'faini']):

            reply = (

                "Kuhusu **Yadi ya In-Bond ya Malkia**:\n\n"

                "Yadi yetu ya In-Bond ni suluhisho kubwa kwa waagizaji wa magari:\n"

                "• **Hakuna Faini za Bandari (Zero Demurrage):** Tunahamisha gari lako kutoka bandarini na kuliweka kwenye yadi yetu chini ya dhamana ya forodha (customs bond).\n"

                "• **Lipa Kodi Ukiwa Tayari:** Huna haja ya kuwa na hela yote ya kodi mara moja. Gari linakaa salama hadi utakapokuwa tayari kulipa TRA na kusajili.\n"

                "• **Ulinzi wa 24/7:** Yadi yetu ina walinzi na kamera za CCTV masaa 24, na betri ya gari lako hutunzwa vizuri."

            )

        elif any(w in msg_lower for w in ['usalama', 'safety', 'betri', 'battery', 'radio', 'redio', 'wizi', 'theft', 'taili', 'spare']):

            reply = (

                "Kuhusu **Usalama wa Vifaa na Vipuri vya Gari Lako**:\n\n"

                "Katika **Malkia Cargo Wave Limited**, tuna dhamana ya 100% ya usalama:\n"

                "• Mara tu gari linaposhushwa toka melini (RORO), maafisa wetu hufanya ukaguzi mkali wa kina (Physical Verification).\n"

                "• Tunakagua na kuweka rekodi ya: **Redio, Betri, Taili ya Akiba, Vioo vya pembeni (Side Mirrors), na vifaa vya kubadilishia taili**.\n"

                "• Gari linafungwa muhuri na kusimamiwa hadi linapoingia kwenye yadi yetu au kukabidhiwa mikononi mwako. Hakuna kilio cha vifaa kuibiwa!"

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

                "Asante kwa kuwasiliana na Malkia Cargo Wave Limited! 👋\n\n"

                "Sisi ni wataalamu wa kutoa magari bandarini Dar es Salaam, kuhifadhi magari kwenye Yadi ya In-Bond bila faini za bandari, na kusafirisha magari mikoani.\n\n"

                "Je, una swali kuhusu:\n"

                "1. Kodi na makadirio ya TRA?\n"

                "2. Yadi yetu ya In-Bond?\n"

                "3. Usalama wa vifaa vya gari lako?\n"

                "4. Kufuatilia gari lako bandarini?\n\n"

                "Tafadhali niambie au piga/WhatsApp **+255 787 367 474**!"

            )



    return JsonResponse({'status': 'success', 'reply': reply})

