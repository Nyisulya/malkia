import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'malkia_project.settings')
django.setup()

from datetime import date, timedelta
from decimal import Decimal
from django.contrib.auth.models import User
from django.utils import timezone
from core.models import (
    UserRole, UserProfile, Customer, WorkflowStageDefinition,
    JobShipment, JobStageInstance, JobDocument, ExpenseVoucher,
    ExpenseCategory, ClientInvoice, ClientPayment, AuditLog
)

def seed_data():
    print("--- 1. Seeding Workflow Stages ---")
    JobStageInstance.objects.all().delete()
    WorkflowStageDefinition.objects.all().delete()
    stages_data = [
        (1, "DOCUMENT RECEIVE", "1. Kupokea Nyaraka (BL, Invoice, Packing List, TBS & Export Cert)", 1, "inbox", UserRole.DOC_OFFICER, "Kupokea nyaraka Physical au kwa Email kutoka kwa mteja bila kuscan; Box No inarekodiwa file likishakamilika.", False),
    ]

    for num, name_en, name_sw, days, icon, role, desc, is_gate in stages_data:
        stage, created = WorkflowStageDefinition.objects.update_or_create(
            stage_number=num,
            defaults={
                'name_en': name_en,
                'name_sw': name_sw,
                'target_days': days,
                'icon': icon,
                'required_role': role,
                'description': desc,
                'is_controlled_gate': is_gate,
            }
        )
        print(f"  Stage {num}: {name_en} ({days} days) {'[CREATED]' if created else '[UPDATED]'}")

    print("\n--- 2. Seeding Users & Roles ---")
    users_info = [
        ('admin', 'admin@malkiafreight.com', 'admin123', 'Super', 'Administrator', UserRole.ADMIN, 'System Administrator'),
        ('ceo', 'ceo@malkiafreight.com', 'ceo123', 'Hashim', 'Mkwawa', UserRole.CEO, 'Managing Director & CEO'),
        ('operations_mgr', 'operations@malkiafreight.com', 'ops123', 'Grace', 'Mushi', UserRole.OPERATIONS_MGR, 'Operations Director'),
        ('doc_officer', 'docs@malkiafreight.com', 'doc123', 'Amani', 'Bakari', UserRole.DOC_OFFICER, 'Senior Documentation Officer'),
        ('clearing_officer', 'clearing@malkiafreight.com', 'clear123', 'Rashid', 'Nassor', UserRole.CLEARING_OFFICER, 'Head Customs Broker / Clearing Officer'),
        ('finance_mgr', 'finance@malkiafreight.com', 'fin123', 'Subira', 'Kilonzo', UserRole.FINANCE, 'Chief Accountant / Finance Manager'),
        ('port_officer', 'port@malkiafreight.com', 'port123', 'Juma', 'Kavishe', UserRole.PORT_OFFICER, 'Port Field Inspector'),
        ('driver1', 'driver@malkiafreight.com', 'driver123', 'Mohamed', 'Said', UserRole.DRIVER, 'Heavy Logistics Driver'),
    ]

    user_map = {}
    for uname, email, pw, fname, lname, role, title in users_info:
        u, created = User.objects.get_or_create(username=uname, defaults={'email': email, 'first_name': fname, 'last_name': lname})
        if created:
            u.set_password(pw)
            if role == UserRole.ADMIN:
                u.is_superuser = True
                u.is_staff = True
            u.save()
        profile, p_created = UserProfile.objects.get_or_create(user=u, defaults={'role': role, 'title': title, 'phone_number': '+255 754 123 456'})
        if not p_created:
            profile.role = role
            profile.title = title
            profile.save()
        user_map[role] = u
        print(f"  User: {uname} ({title}) - Role: {role}")

    print("\n--- 3. Seeding Customers ---")
    customers_data = [
        ("Kilimanjaro Industrial Mills Ltd", "Mr. David Tarimo", "+255 784 987 654", "david@kili-industries.co.tz", "100-245-891", "40-008129", "Plot 42, Nyerere Road, Dar es Salaam", Decimal('50000000'), "30_DAYS"),
        ("AfriTrade Import & Export Co. Ltd", "Ms. Fatima Al-Jabri", "+255 713 555 112", "fatima@afritrade.co.tz", "102-887-340", "40-019382", "Kariakoo Commercial Complex, Dar es Salaam", Decimal('30000000'), "14_DAYS"),
        ("Victoria Motors Tanzania Ltd", "Eng. Peter Malima", "+255 767 332 990", "pmalima@victoriamotors.co.tz", "101-764-219", "40-015543", "Plot 18, Tabata Industrial Area, Dar es Salaam", Decimal('40000000'), "14_DAYS"),
        ("Great Lakes Agro Supplies (Kigali Hub)", "Jean-Luc Habimana", "+250 788 123 987", "jluc@greatlakes-rw.com", "998-001-443", "", "Gikondo Industrial Park, Kigali, Rwanda", Decimal('20000000'), "IMMEDIATE"),
    ]

    customers = []
    for cname, contact, phone, email, tin, vrn, addr, cred, terms in customers_data:
        c, created = Customer.objects.update_or_create(
            company_name=cname,
            defaults={
                'contact_person': contact,
                'phone': phone,
                'email': email,
                'tin_number': tin,
                'vrn_number': vrn,
                'physical_address': addr,
                'credit_limit': cred,
                'payment_terms': terms,
            }
        )
        customers.append(c)
        print(f"  Customer: {cname}")

    print("\n--- 4. Seeding Sample Jobs & Workflows ---")
    now = timezone.now()
    today = now.date()
    stage_defs = list(WorkflowStageDefinition.objects.all().order_by('stage_number'))

    def init_stages_for_job(job, active_stage_num):
        for s_def in stage_defs:
            s_num = s_def.stage_number
            if s_num < active_stage_num:
                status = 'COMPLETED'
                started = now - timedelta(days=2 * (active_stage_num - s_num) + 1)
                completed = started + timedelta(days=1)
            elif s_num == active_stage_num:
                status = 'DELAYED' if job.status == 'DELAYED' else 'IN_PROGRESS'
                started = now - timedelta(days=2)
                completed = None
            else:
                status = 'PENDING'
                started = None
                completed = None

            officer = None
            if s_def.required_role in user_map:
                officer = user_map[s_def.required_role]

            JobStageInstance.objects.update_or_create(
                job=job,
                stage_number=s_num,
                defaults={
                    'stage_definition': s_def,
                    'name_en': s_def.name_en,
                    'name_sw': s_def.name_sw,
                    'status': status,
                    'target_days': s_def.target_days,
                    'responsible_officer': officer,
                    'started_at': started,
                    'completed_at': completed,
                    'remarks': f"Automatic record for {s_def.name_en}",
                }
            )

    # Job 1: In Progress at Stage 6 (Delivery Order)
    j1, _ = JobShipment.objects.update_or_create(
        job_number="CF/2026/0001",
        defaults={
            'customer': customers[0],
            'bl_number': "MSCU-DAR-987210",
            'container_numbers': "MSCU9482110, MSCU9482111",
            'container_size_type': '40HC',
            'vessel_name': "MSC LAURA",
            'voyage_number': "261W",
            'port_of_origin': "Yokohama, Japan",
            'port_of_arrival': "Dar es Salaam Port (TPA)",
            'eta_arrival_date': today - timedelta(days=5),
            'actual_arrival_date': today - timedelta(days=5),
            'final_destination': "Plot 42, Nyerere Road, Dar es Salaam",
            'cargo_description': "Industrial Mill Spare Parts and Heavy Electric Motors",
            'documentation_officer': user_map[UserRole.DOC_OFFICER],
            'clearing_officer': user_map[UserRole.CLEARING_OFFICER],
            'port_officer': user_map[UserRole.PORT_OFFICER],
            'current_stage_number': 6,
            'status': 'ACTIVE',
            'contracted_revenue': Decimal('5800000'),
            'declaration_number': "T26/DAR/048921",
            'assessed_duty_amount': Decimal('14250000'),
            'duty_paid': True,
            'duty_payment_reference': "CRDB-TRA-7788192",
            'duty_payment_date': today - timedelta(days=3),
            'delivery_order_number': "DO-MSC-89102",
        }
    )
    init_stages_for_job(j1, 6)

    # Job 2: Advanced at Stage 10 (Gate Pass & Loading)
    j2, _ = JobShipment.objects.update_or_create(
        job_number="CF/2026/0002",
        defaults={
            'customer': customers[1],
            'bl_number': "COSU-SHA-449102",
            'container_numbers': "COSU6621980",
            'container_size_type': '40FT',
            'vessel_name': "COSCO SHIPPING PRIDE",
            'voyage_number': "014E",
            'port_of_origin': "Guangzhou, China",
            'port_of_arrival': "Dar es Salaam Port (TPA)",
            'eta_arrival_date': today - timedelta(days=8),
            'actual_arrival_date': today - timedelta(days=8),
            'final_destination': "Kariakoo Commercial Complex, Dar es Salaam",
            'cargo_description': "Textiles, Garments, and Footwear Commercial Consignment",
            'documentation_officer': user_map[UserRole.DOC_OFFICER],
            'clearing_officer': user_map[UserRole.CLEARING_OFFICER],
            'port_officer': user_map[UserRole.PORT_OFFICER],
            'driver': user_map[UserRole.DRIVER],
            'truck_number': "T 412 DXE",
            'trailer_number': "T 881 AYM",
            'seal_number': "SL-COS-883910",
            'gate_pass_number': "TPA-GP-2026-9041",
            'current_stage_number': 10,
            'status': 'ACTIVE',
            'contracted_revenue': Decimal('4200000'),
            'declaration_number': "T26/DAR/039120",
            'assessed_duty_amount': Decimal('9800000'),
            'duty_paid': True,
            'duty_payment_reference': "NMB-TRA-441029",
            'duty_payment_date': today - timedelta(days=6),
            'delivery_order_number': "DO-COS-4491",
            'release_order_number': "RO-TRA-99210",
            'port_invoice_number': "TPA-INV-887192",
        }
    )
    init_stages_for_job(j2, 10)

    # Job 3: Delayed at Stage 4 (Duty Payment Pending from Client)
    j3, _ = JobShipment.objects.update_or_create(
        job_number="CF/2026/0003",
        defaults={
            'customer': customers[2],
            'bl_number': "EGLV-NBO-112940",
            'container_numbers': "EVER8819201",
            'container_size_type': '40HC',
            'vessel_name': "EVER GIVEN",
            'voyage_number': "098S",
            'port_of_origin': "Keelung, Taiwan",
            'port_of_arrival': "Dar es Salaam Port (TPA)",
            'eta_arrival_date': today - timedelta(days=2),
            'final_destination': "Tabata Industrial Area, Dar es Salaam",
            'cargo_description': "Automotive Shock Absorbers, Filters and Engine Parts",
            'documentation_officer': user_map[UserRole.DOC_OFFICER],
            'clearing_officer': user_map[UserRole.CLEARING_OFFICER],
            'current_stage_number': 4,
            'status': 'DELAYED',
            'contracted_revenue': Decimal('3800000'),
            'declaration_number': "T26/DAR/055102",
            'assessed_duty_amount': Decimal('18500000'),
            'duty_paid': False,
        }
    )
    init_stages_for_job(j3, 4)

    # Job 4: Completed & Delivered at Stage 11
    j4, _ = JobShipment.objects.update_or_create(
        job_number="CF/2026/0004",
        defaults={
            'customer': customers[3],
            'bl_number': "MAEU-DXB-771920",
            'container_numbers': "MRKU5510928, MRKU5510929",
            'container_size_type': '2X20FT',
            'vessel_name': "MAERSK BULWARK",
            'voyage_number': "2602",
            'port_of_origin': "Jebel Ali, Dubai UAE",
            'port_of_arrival': "Dar es Salaam Port (TPA)",
            'eta_arrival_date': today - timedelta(days=14),
            'actual_arrival_date': today - timedelta(days=14),
            'final_destination': "Kigali Logistics Hub, Rwanda (Transit)",
            'cargo_description': "Agricultural Irrigation Pipes and Water Pump Systems",
            'documentation_officer': user_map[UserRole.DOC_OFFICER],
            'clearing_officer': user_map[UserRole.CLEARING_OFFICER],
            'port_officer': user_map[UserRole.PORT_OFFICER],
            'driver': user_map[UserRole.DRIVER],
            'truck_number': "T 219 DHH",
            'trailer_number': "T 554 BLK",
            'seal_number': "SL-MRK-992144",
            'current_stage_number': 11,
            'status': 'COMPLETED',
            'contracted_revenue': Decimal('8500000'),
            'declaration_number': "T26/TRANSIT/00918",
            'assessed_duty_amount': Decimal('0'),
            'duty_paid': True,
            'delivered_date': now - timedelta(days=1),
            'received_by_name': "Mr. Claude Nsengiyumva (Stores Mgr)",
            'closure_notes': "Consignment delivered in immaculate condition. Both seals intact at Kigali inspection.",
        }
    )
    init_stages_for_job(j4, 11)
    # Mark stage 11 as completed for Job 4
    st11 = j4.stages.filter(stage_number=11).first()
    if st11:
        st11.status = 'COMPLETED'
        st11.completed_at = now - timedelta(days=1)
        st11.save()

    print("  Created 4 Realistic Shipments across stages 1, 4, 6, 10, 11")

    print("\n--- 5. Seeding Expenses & Multi-Tier Approvals ---")
    expenses_data = [
        # Job 1 Expenses
        ("EXP/2026/0001", j1, ExpenseCategory.SHIPPING_LINE, Decimal('1250000'), "MSC Delivery Order (DO) and documentation processing fees", user_map[UserRole.CLEARING_OFFICER], UserRole.FINANCE, user_map[UserRole.FINANCE], 'APPROVED', True, "NMB-TR-99881"),
        ("EXP/2026/0002", j1, ExpenseCategory.PORT_CHARGES, Decimal('1850000'), "TPA Port charges, wharfage & handling for 40HC container", user_map[UserRole.PORT_OFFICER], UserRole.FINANCE, user_map[UserRole.FINANCE], 'APPROVED', True, "CRDB-TPA-0091"),
        ("EXP/2026/0003", j1, ExpenseCategory.TRANSPORT, Decimal('950000'), "Truck mobilization and local Dar es Salaam haulage deposit", user_map[UserRole.OPERATIONS_MGR], UserRole.OPERATIONS_MGR, user_map[UserRole.OPERATIONS_MGR], 'APPROVED', False, ""),

        # Job 2 Expenses
        ("EXP/2026/0004", j2, ExpenseCategory.SHIPPING_LINE, Decimal('900000'), "COSCO DO fees and container deposit warranty", user_map[UserRole.CLEARING_OFFICER], UserRole.FINANCE, user_map[UserRole.FINANCE], 'APPROVED', True, "STANBIC-DO-881"),
        ("EXP/2026/0005", j2, ExpenseCategory.PORT_CHARGES, Decimal('1400000'), "Port invoice settlement for TICTS container terminal", user_map[UserRole.PORT_OFFICER], UserRole.FINANCE, user_map[UserRole.FINANCE], 'APPROVED', True, "NMB-PORT-112"),
        ("EXP/2026/0006", j2, ExpenseCategory.TRANSPORT, Decimal('800000'), "Offloading and escort arrangements to Kariakoo", user_map[UserRole.OPERATIONS_MGR], UserRole.OPERATIONS_MGR, user_map[UserRole.OPERATIONS_MGR], 'APPROVED', True, "CASH-DISB-441"),

        # High Value Pending Expense (> 2M -> CEO Approval Required)
        ("EXP/2026/0007", j3, ExpenseCategory.PORT_HANDLING, Decimal('2850000'), "Emergency collateral bond facility & port demurrage advance guarantee", user_map[UserRole.OPERATIONS_MGR], UserRole.CEO, None, 'REQUESTED', False, ""),
    ]

    for vnum, job, cat, amt, desc, req, rrole, apprv, astatus, is_paid, pref in expenses_data:
        ev, _ = ExpenseVoucher.objects.update_or_create(
            voucher_number=vnum,
            defaults={
                'job': job,
                'category': cat,
                'amount': amt,
                'description': desc,
                'requester': req,
                'required_role': rrole,
                'approver': apprv,
                'approval_status': astatus,
                'approval_date': now - timedelta(days=1) if astatus == 'APPROVED' else None,
                'is_paid': is_paid,
                'paid_at': now - timedelta(hours=12) if is_paid else None,
                'payment_reference': pref,
            }
        )
        print(f"  Expense: {vnum} ({cat}) - TSh {amt:,.2f} [{astatus}]")

    print("\n--- 6. Seeding Client Invoices & Payments ---")
    # Invoice for Job 4 (Completed)
    inv4, _ = ClientInvoice.objects.update_or_create(
        invoice_number="INV/2026/0001",
        defaults={
            'job': j4,
            'customer': j4.customer,
            'issue_date': today - timedelta(days=10),
            'due_date': today + timedelta(days=4),
            'amount_clearing_agency_fee': Decimal('2500000'),
            'amount_duty_reimbursement': Decimal('0'),
            'amount_port_charges': Decimal('2200000'),
            'amount_shipping_line_do': Decimal('1300000'),
            'amount_transport': Decimal('2500000'),
            'amount_sundry_charges': Decimal('0'),
            'total_amount': Decimal('8500000'),
            'amount_paid': Decimal('8500000'),
            'status': 'PAID',
            'notes': "Transit consignment to Kigali. All invoices settled in full via wire transfer.",
        }
    )
    ClientPayment.objects.get_or_create(
        invoice=inv4,
        payment_reference="BK-RW-WIRE-99018",
        defaults={
            'amount': Decimal('8500000'),
            'payment_date': today - timedelta(days=2),
            'payment_method': 'BANK_TRANSFER',
            'recorded_by': user_map[UserRole.FINANCE],
            'notes': "Full payment received via Bank of Kigali swift transfer.",
        }
    )

    # Invoice for Job 1 (Partially Billed)
    inv1, _ = ClientInvoice.objects.update_or_create(
        invoice_number="INV/2026/0002",
        defaults={
            'job': j1,
            'customer': j1.customer,
            'issue_date': today - timedelta(days=4),
            'due_date': today + timedelta(days=10),
            'amount_clearing_agency_fee': Decimal('2000000'),
            'amount_duty_reimbursement': Decimal('0'),
            'amount_port_charges': Decimal('1850000'),
            'amount_shipping_line_do': Decimal('1250000'),
            'amount_transport': Decimal('700000'),
            'amount_sundry_charges': Decimal('0'),
            'total_amount': Decimal('5800000'),
            'amount_paid': Decimal('3000000'),
            'status': 'PARTIALLY_PAID',
            'notes': "Advance deposit received. Remaining balance payable upon container arrival at site.",
        }
    )
    ClientPayment.objects.get_or_create(
        invoice=inv1,
        payment_reference="CRDB-TRF-338192",
        defaults={
            'amount': Decimal('3000000'),
            'payment_date': today - timedelta(days=3),
            'payment_method': 'BANK_TRANSFER',
            'recorded_by': user_map[UserRole.FINANCE],
            'notes': "Initial advance payment deposit.",
        }
    )

    print("\n--- 7. Seeding Audit Logs ---")
    AuditLog.objects.create(
        user=user_map[UserRole.DOC_OFFICER],
        job=j1,
        action="OPEN_JOB_FILE",
        details="Digital job file opened for MSC LAURA BL #MSCU-DAR-987210.",
        ip_address="192.168.1.10"
    )
    AuditLog.objects.create(
        user=user_map[UserRole.CLEARING_OFFICER],
        job=j1,
        action="CONFIRM_DUTY_PAYMENT",
        details="Verified TRA duty payment receipt CRDB-TRA-7788192 for TSh 14,250,000.",
        ip_address="192.168.1.14"
    )
    AuditLog.objects.create(
        user=user_map[UserRole.OPERATIONS_MGR],
        job=j3,
        action="STAGE_DELAY_ALERT",
        details="Stage 4 (Duty Payment) exceeded SLA target of 1 day. Notification sent to customer representative.",
        ip_address="192.168.1.12"
    )

    print("\n===========================================")
    print("SUCCESS: Database successfully seeded with realistic C&F data!")
    print("===========================================")

if __name__ == '__main__':
    seed_data()
