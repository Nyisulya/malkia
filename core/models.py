import os
from decimal import Decimal
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta


class UserRole(models.TextChoices):
    CEO = 'CEO', 'CEO / Managing Director'
    OPERATIONS_MGR = 'OPERATIONS_MGR', 'Yard & Customer Handover'
    DOC_OFFICER = 'DOC_OFFICER', 'Documentation Officer'
    CLEARING_OFFICER = 'CLEARING_OFFICER', 'Customs Declarer'
    FINANCE = 'FINANCE', 'Accounts / Finance'
    PORT_OFFICER = 'PORT_OFFICER', 'Port / Operations Officer'
    DISPATCH_OFFICER = 'DISPATCH_OFFICER', 'Logistics / Dispatch Officer'
    DRIVER = 'DRIVER', 'Driver'
    ADMIN = 'ADMIN', 'System Administrator'


class UserProfile(models.Model):
    DEPARTMENT_CHOICES = [
        ('EXECUTIVE', 'Executive Management'),
        ('OPERATIONS', 'Operations & Freight Forwarding'),
        ('DOCUMENTATION', 'Documentation & Shipping Lines'),
        ('CUSTOMS', 'Customs Clearance & TANCIS'),
        ('PORT_FIELD', 'Port Wharfingers & Field Logistics'),
        ('TRANSPORT', 'Transport & Fleet Logistics'),
        ('FINANCE', 'Finance, Billing & Accounts'),
        ('ADMIN_IT', 'Systems & Administration'),
    ]

    EMPLOYMENT_STATUS_CHOICES = [
        ('ACTIVE', 'Active / Kazini'),
        ('ON_LEAVE', 'On Leave / Likizo'),
        ('SUSPENDED', 'Suspended / Amesimamishwa'),
        ('TERMINATED', 'Resigned / Ametoka'),
    ]

    EMPLOYMENT_TYPE_CHOICES = [
        ('PERMANENT', 'Permanent Contract (Mkataba wa Kudumu)'),
        ('CONTRACT', 'Fixed-Term Contract (Mkataba Maalum)'),
        ('PROBATION', 'Probationary (Majaribio)'),
        ('CASUAL', 'Casual / Freelance Driver'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    employee_id = models.CharField(max_length=30, unique=True, null=True, blank=True, verbose_name="Staff ID / Nambari ya Mfanyakazi")
    role = models.CharField(max_length=30, choices=UserRole.choices, default=UserRole.DOC_OFFICER)
    department = models.CharField(max_length=30, choices=DEPARTMENT_CHOICES, default='OPERATIONS')
    title = models.CharField(max_length=100, blank=True, verbose_name="Wadhifa / Job Title")
    phone_number = models.CharField(max_length=30, blank=True, verbose_name="Nambari ya Simu")
    secondary_phone = models.CharField(max_length=30, blank=True, verbose_name="Simu ya Ziada / WhatsApp")
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)

    # Personal & Official IDs
    national_id = models.CharField(max_length=50, blank=True, verbose_name="NIDA Number / Kitambulisho cha Taifa")
    tin_number = models.CharField(max_length=50, blank=True, verbose_name="Personal TIN")
    driving_license_number = models.CharField(max_length=50, blank=True, verbose_name="Leseni ya Udereva")
    license_class = models.CharField(max_length=30, blank=True, verbose_name="Daraja la Leseni (e.g. Class C, E)")
    license_expiry = models.DateField(null=True, blank=True, verbose_name="Tarehe ya Kumalizika Leseni")

    # Employment Details
    employment_type = models.CharField(max_length=20, choices=EMPLOYMENT_TYPE_CHOICES, default='PERMANENT')
    employment_status = models.CharField(max_length=20, choices=EMPLOYMENT_STATUS_CHOICES, default='ACTIVE')
    date_joined = models.DateField(null=True, blank=True, verbose_name="Tarehe ya Kuajiriwa")
    work_station = models.CharField(max_length=100, default='Dar HQ (Posta)', verbose_name="Kituo Kikuu cha Kazi")

    # Emergency / Next of Kin
    emergency_contact_name = models.CharField(max_length=100, blank=True, verbose_name="Mtu wa Dharura / Next of Kin")
    emergency_contact_phone = models.CharField(max_length=30, blank=True, verbose_name="Simu ya Mtu wa Dharura")
    emergency_contact_relation = models.CharField(max_length=50, blank=True, verbose_name="Uhusiano")
    residential_address = models.CharField(max_length=200, blank=True, verbose_name="Makazi (Mtaa / Wilaya)")

    # Bio & Qualifications
    bio = models.TextField(blank=True, verbose_name="Wasifu / Qualifications")
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, null=True)

    class Meta:
        ordering = ['user__first_name', 'user__last_name', 'user__username']

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} ({self.get_role_display()})"

    @classmethod
    def generate_next_employee_id(cls):
        last = cls.objects.filter(employee_id__startswith='MC-').order_by('-employee_id').first()
        if last and last.employee_id:
            try:
                num = int(last.employee_id.split('-')[1]) + 1
                return f"MC-{num:03d}"
            except Exception:
                pass
        count = cls.objects.count() + 1
        return f"MC-{count:03d}"

    @property
    def today_attendance(self):
        today = timezone.now().date()
        return self.user.attendances.filter(date=today).first()

    @property
    def active_jobs_count(self):
        from .models import JobShipment
        r = self.role
        if r == UserRole.DRIVER:
            return JobShipment.objects.filter(driver=self.user, status__in=['ACTIVE', 'DELAYED']).count()
        elif r == UserRole.PORT_OFFICER:
            return JobShipment.objects.filter(port_officer=self.user, status__in=['ACTIVE', 'DELAYED']).count()
        elif r == UserRole.CLEARING_OFFICER:
            return JobShipment.objects.filter(clearing_officer=self.user, status__in=['ACTIVE', 'DELAYED']).count()
        elif r == UserRole.DOC_OFFICER:
            return JobShipment.objects.filter(documentation_officer=self.user, status__in=['ACTIVE', 'DELAYED']).count()
        return 0

    @property
    def total_jobs_count(self):
        from .models import JobShipment
        r = self.role
        if r == UserRole.DRIVER:
            return JobShipment.objects.filter(driver=self.user).count()
        elif r == UserRole.PORT_OFFICER:
            return JobShipment.objects.filter(port_officer=self.user).count()
        elif r == UserRole.CLEARING_OFFICER:
            return JobShipment.objects.filter(clearing_officer=self.user).count()
        elif r == UserRole.DOC_OFFICER:
            return JobShipment.objects.filter(documentation_officer=self.user).count()
        return 0


class Customer(models.Model):
    PAYMENT_TERMS_CHOICES = [
        ('IMMEDIATE', 'Immediate / Cash on Delivery'),
        ('7_DAYS', '7 Days Credit'),
        ('14_DAYS', '14 Days Credit'),
        ('30_DAYS', '30 Days Credit'),
    ]

    company_name = models.CharField(max_length=200, verbose_name="Client Name")
    contact_person = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=50, verbose_name="Phone No")
    email = models.EmailField(blank=True, verbose_name="Email")
    tin_number = models.CharField(max_length=50, blank=True, verbose_name="TIN")
    id_number = models.CharField(max_length=50, blank=True, verbose_name="ID Number (NIDA / Passport)")
    vrn_number = models.CharField(max_length=50, blank=True, verbose_name="VRN Number")
    physical_address = models.TextField(blank=True)
    credit_limit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    payment_terms = models.CharField(max_length=30, choices=PAYMENT_TERMS_CHOICES, default='IMMEDIATE')
    logo_image = models.ImageField(upload_to='customer_logos/', null=True, blank=True, verbose_name="Client Letterhead Logo")
    stamp_image = models.ImageField(upload_to='customer_stamps/', null=True, blank=True, verbose_name="Client Official Stamp")
    signature_image = models.ImageField(upload_to='customer_signatures/', null=True, blank=True, verbose_name="Client Authorized Signature")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['company_name']

    def __str__(self):
        return self.company_name

    @property
    def total_shipments_count(self):
        return self.shipments.count()

    @property
    def active_shipments_count(self):
        return self.shipments.filter(status__in=['ACTIVE', 'DELAYED']).count()

    @property
    def total_revenue(self):
        total = self.invoices.aggregate(total=models.Sum('total_amount'))['total']
        return total or Decimal('0.00')

    @property
    def total_paid(self):
        total = self.invoices.aggregate(total=models.Sum('amount_paid'))['total']
        return total or Decimal('0.00')

    @property
    def outstanding_balance(self):
        return self.total_revenue - self.total_paid


class WorkflowStageDefinition(models.Model):
    stage_number = models.PositiveSmallIntegerField(unique=True)
    name_en = models.CharField(max_length=150)
    name_sw = models.CharField(max_length=150)
    target_days = models.PositiveSmallIntegerField(default=1, help_text="SLA in days")
    icon = models.CharField(max_length=50, default='file-text', help_text="Icon identifier")
    required_role = models.CharField(max_length=30, choices=UserRole.choices, default=UserRole.CLEARING_OFFICER)
    description = models.TextField(blank=True)
    is_controlled_gate = models.BooleanField(default=False, help_text="Requires verification before proceeding")

    class Meta:
        ordering = ['stage_number']

    def __str__(self):
        return f"{self.stage_number}. {self.name_en} ({self.target_days}d)"


class JobShipment(models.Model):
    STATUS_CHOICES = [
        ('ACTIVE', 'Active / In Progress'),
        ('DELAYED', 'Delayed / Attention Needed'),
        ('COMPLETED', 'Delivered / Completed'),
        ('CLOSED', 'Closed & Archived'),
    ]

    DOC_RECEIVE_METHODS = [
        ('PHYSICAL', 'Physical (In-Office)'),
        ('EMAIL', 'Via Email'),
        ('BOTH', 'Physical & Via Email'),
    ]

    CLEARANCE_BOND_TYPES = [
        ('DIRECT', 'Direct Clearance (Duty Paid)'),
        ('BOND', 'In-Bond (Duty Unpaid - Held at Office)'),
        ('EX_BOND', 'Ex-Bond (Duty Paid After Bond)'),
    ]

    CONTAINER_TYPES = [
        ('RORO', 'Single Motor Vehicle (RoRo)'),
        ('20FT', '20ft Standard Container'),
        ('40FT', '40ft Standard Container'),
        ('40HC', '40ft High Cube (HC)'),
        ('2X20FT', '2 x 20ft Containers'),
        ('REEFER', 'Reefer Container (Cold Chain)'),
        ('LCL', 'LCL / Loose Cargo'),
    ]

    SHIPPING_LINES = [
        ('MSC', 'Mediterranean Shipping Company (MSC)'),
        ('MAERSK', 'Maersk Line / Safmarine'),
        ('CMA_CGM', 'CMA CGM Shipping Line'),
        ('HAPAG_LLOYD', 'Hapag-Lloyd'),
        ('PIL', 'Pacific International Lines (PIL)'),
        ('ONE', 'Ocean Network Express (ONE)'),
        ('COSCO', 'COSCO Shipping Lines'),
        ('EVERGREEN', 'Evergreen Line'),
        ('GRIMALDI', 'Grimaldi Lines'),
        ('ARKAS', 'Arkas Container Transport'),
        ('MESSINA', 'Ignazio Messina & C.'),
        ('ZIM', 'ZIM Integrated Shipping'),
        ('OTHER', 'Other / RoRo Line'),
    ]

    SHIPMENT_REGIMES = [
        ('IMPORT', 'Local Import (Tanzania Domestic)'),
        ('TRANSIT', 'Transit Cargo (Rwanda, Burundi, DRC, Zambia, Uganda, Malawi)'),
        ('EXPORT', 'Export Cargo (Outbound)'),
        ('BONDED_WH', 'Bonded Warehouse (In-Bond Clearance)'),
        ('RE_EXPORT', 'Re-Export'),
    ]

    job_number = models.CharField(max_length=50, unique=True, help_text="e.g. CF/2026/0001")
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='shipments')
    bl_number = models.CharField(max_length=100, blank=True, verbose_name="Bill of Lading (BL) Number")
    chassis_number = models.CharField(max_length=100, blank=True, verbose_name="Chassis Number")
    shipping_line = models.CharField(max_length=50, choices=SHIPPING_LINES, default='OTHER', blank=True, verbose_name="Shipping Line")
    shipment_type = models.CharField(max_length=30, choices=SHIPMENT_REGIMES, default='IMPORT', verbose_name="Shipment Regime / Type")
    customs_manifest_number = models.CharField(max_length=100, blank=True, verbose_name="Manifest / Rotational Number")
    container_numbers = models.TextField(blank=True, default='', help_text="Chassis or Container Numbers")
    container_size_type = models.CharField(max_length=30, choices=CONTAINER_TYPES, default='RORO')
    vessel_name = models.CharField(max_length=150, blank=True, default='', help_text="Vessel name & voyage")
    voyage_number = models.CharField(max_length=50, blank=True)
    port_of_origin = models.CharField(max_length=100, default='Yokohama, Japan', blank=True)
    port_of_arrival = models.CharField(max_length=100, default='Dar es Salaam Port (TPA)', blank=True)
    eta_arrival_date = models.DateField(null=True, blank=True, verbose_name="ETA / Expected Arrival Date")
    actual_arrival_date = models.DateField(null=True, blank=True, verbose_name="Actual Vessel Arrival")
    final_destination = models.CharField(max_length=150, default='Dar es Salaam, Tanzania', blank=True)
    cargo_description = models.TextField(blank=True, default='', help_text="Detailed description of vehicle/cargo")

    # 1. DOCUMENT RECEIVE (Checklist from Client - No scanning required)
    doc_receive_method = models.CharField(max_length=20, choices=DOC_RECEIVE_METHODS, default='PHYSICAL', verbose_name="Document Receive Method")
    doc_bl_received = models.BooleanField(default=False, verbose_name="BL Document")
    doc_invoice_received = models.BooleanField(default=False, verbose_name="Invoice")
    doc_packing_list_received = models.BooleanField(default=False, verbose_name="Packing List")
    doc_tbs_cert_received = models.BooleanField(default=False, verbose_name="TBS Certificate")
    doc_export_cert_received = models.BooleanField(default=False, verbose_name="Export Certificate")
    doc_received_at = models.DateTimeField(null=True, blank=True)
    box_number = models.CharField(max_length=50, blank=True, verbose_name="Box Number (Upon File Completion)")

    # 2. OPENING FILE, CLEARANCE MODE (DIRECT VS BOND) & COMPANY-GENERATED DOCUMENTS (C41 & TBS LETTER)
    clearance_mode = models.CharField(
        max_length=20,
        choices=CLEARANCE_BOND_TYPES,
        default='DIRECT',
        verbose_name="Clearance / Duty Mode (Direct vs Bond)"
    )
    doc_c41_generated = models.BooleanField(default=True, verbose_name="C41 (TRA) Generated by Company")
    doc_tbs_letter_generated = models.BooleanField(default=True, verbose_name="TBS Letter Generated by Company")
    c41_reference_no = models.CharField(max_length=80, blank=True, verbose_name="C41 (TRA) Reference No")
    tbs_letter_reference_no = models.CharField(max_length=80, blank=True, verbose_name="TBS Letter Reference No")
    file_opened_at = models.DateTimeField(null=True, blank=True)
    
    # Responsible Officers
    documentation_officer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='doc_jobs')
    clearing_officer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='clearing_jobs')
    port_officer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='port_jobs')
    driver = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='driver_jobs')
    truck_number = models.CharField(max_length=50, blank=True)
    trailer_number = models.CharField(max_length=50, blank=True)
    seal_number = models.CharField(max_length=100, blank=True)

    # Current workflow progress
    current_stage_number = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE')
    contracted_revenue = models.DecimalField(max_digits=14, decimal_places=2, default=0, help_text="Agreed billing to client in TSh")
    
    CUSTOMS_CHANNELS = [
        ('GREEN', 'Green Channel (Direct Release upon Payment)'),
        ('YELLOW', 'Yellow Channel (Documentary Review Only)'),
        ('RED', 'Red Channel (Physical Verification Required at Port/ICD)'),
    ]

    # Customs & port data
    declaration_number = models.CharField(max_length=100, blank=True, verbose_name="TANSAD / Entry No")
    customs_channel = models.CharField(max_length=20, choices=CUSTOMS_CHANNELS, default='YELLOW', blank=True, verbose_name="Customs Risk Channel")
    assessed_duty_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name="TRA Assessed Duty (TSh)")
    duty_control_number = models.CharField(max_length=50, blank=True, verbose_name="TRA Control Number")
    duty_paid = models.BooleanField(default=False)
    duty_payment_reference = models.CharField(max_length=100, blank=True)
    duty_payment_date = models.DateField(null=True, blank=True)

    # Physical Original Documents Handover to Field Agent for Shipping Line D/O
    original_docs_dispatched_to_field = models.BooleanField(default=False, verbose_name="Original Docs Given to Field Agent")
    original_docs_dispatched_at = models.DateTimeField(null=True, blank=True)
    original_docs_recipient = models.CharField(max_length=150, blank=True, verbose_name="Field Agent Name for D/O")
    original_docs_dispatch_notes = models.CharField(max_length=255, blank=True)

    # Step 3: TANESW (TRA) & TBS Declarations
    tanesw_lodged_at = models.DateTimeField(null=True, blank=True, verbose_name="TANESW Lodgement Time")
    
    TRA_STATUS_CHOICES = [
        ('PENDING_LODGEMENT', 'Awaiting TANESW Lodgement'),
        ('LODGED_76H', 'Lodged in TANESW (Awaiting TRA Review within 76h)'),
        ('ACCEPTED', 'TRA Accepted (Control Number Issued)'),
        ('OBJECTION', 'TRA Objection / Query Raised'),
    ]
    tra_status = models.CharField(max_length=30, choices=TRA_STATUS_CHOICES, default='PENDING_LODGEMENT', verbose_name="TRA Customs Status")
    tra_accepted_at = models.DateTimeField(null=True, blank=True)
    tra_objection_notes = models.TextField(blank=True, verbose_name="TRA Objection / Query Reason")
    tra_objection_at = models.DateTimeField(null=True, blank=True)

    TBS_STATUS_CHOICES = [
        ('NOT_LODGED', 'Not Submitted to TBS'),
        ('PENDING_APPROVAL', 'Submitted to TBS (Pending Approval)'),
        ('APPROVED', 'TBS Approved / Released'),
        ('QUERY', 'TBS Query / Inspection Required'),
    ]
    tbs_status = models.CharField(max_length=30, choices=TBS_STATUS_CHOICES, default='NOT_LODGED', verbose_name="TBS Inspection Status")
    tbs_submitted_at = models.DateTimeField(null=True, blank=True)
    tbs_approved_at = models.DateTimeField(null=True, blank=True)
    tbs_reference_no = models.CharField(max_length=100, blank=True, verbose_name="TBS Batch / Certificate Ref")
    tbs_notes = models.TextField(blank=True)

    delivery_order_number = models.CharField(max_length=100, blank=True)
    release_order_number = models.CharField(max_length=100, blank=True)
    port_invoice_number = models.CharField(max_length=100, blank=True)
    gate_pass_number = models.CharField(max_length=100, blank=True)

    # Field & Port Vehicle Inspection (Port Officer Ground Check at ICD)
    vehicle_inspection_done = models.BooleanField(default=False, verbose_name="Vehicle Inspected at ICD")
    vehicle_has_scratches = models.BooleanField(default=False, verbose_name="Has Scratches / Dents")
    vehicle_radio_present = models.BooleanField(default=True, verbose_name="Radio / Screen Present")
    vehicle_spare_wheel_present = models.BooleanField(default=True, verbose_name="Spare Wheel Present")
    vehicle_jack_tools_present = models.BooleanField(default=True, verbose_name="Jack & Tools Present")
    vehicle_mirrors_ok = models.BooleanField(default=True, verbose_name="Side Mirrors OK")
    vehicle_battery_ok = models.BooleanField(default=True, verbose_name="Battery Working")
    vehicle_inspection_notes = models.TextField(blank=True, verbose_name="Vehicle Condition Notes")
    vehicle_inspection_at = models.DateTimeField(null=True, blank=True)
    vehicle_inspection_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='inspected_jobs')

    # Port Exit & Dispatch to Office Yard
    vehicle_dispatched_to_office = models.BooleanField(default=False, verbose_name="Dispatched from Port/ICD")
    vehicle_dispatched_at = models.DateTimeField(null=True, blank=True)
    vehicle_driver_name = models.CharField(max_length=150, blank=True, verbose_name="Office Driver Name")
    vehicle_arrived_at_office = models.BooleanField(default=False, verbose_name="Arrived at Malkia Yard")
    vehicle_arrived_at = models.DateTimeField(null=True, blank=True)

    # Delivery & Completion
    delivered_date = models.DateTimeField(null=True, blank=True)
    received_by_name = models.CharField(max_length=150, blank=True)
    proof_of_delivery_image = models.ImageField(upload_to='pod/%Y/%m/', null=True, blank=True)
    closure_notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.job_number} - {self.customer.company_name} ({self.bl_number})"

    @property
    def current_stage_obj(self):
        return self.stages.filter(stage_number=self.current_stage_number).first()

    @property
    def current_stage_display_name(self):
        st = self.stages.filter(stage_number=self.current_stage_number).first()
        if st and st.name_en:
            return st.name_en
        stage_names = {
            1: "Document Receipt & Opening",
            2: "TRA Declaration (TANCIS)",
            3: "Assessment & Duty Notice",
            4: "Customs Duty Payment",
            5: "Physical Verification",
            6: "Delivery Order (D/O)",
            7: "Shipping Line Release",
            8: "Port Invoice & Assessment",
            9: "Port Charges Payment",
            10: "In-Bond Yard Transfer",
            11: "Gate Pass & Handover"
        }
        return stage_names.get(self.current_stage_number, f"Stage {self.current_stage_number}")

    @property
    def received_docs_checklist(self):
        return [
            ('BL Document', self.doc_bl_received),
            ('Invoice', self.doc_invoice_received),
            ('Packing List', self.doc_packing_list_received),
            ('TBS Certificate', self.doc_tbs_cert_received),
            ('Export Certificate', self.doc_export_cert_received),
        ]

    @property
    def received_docs_count(self):
        return sum(1 for _, received in self.received_docs_checklist if received)

    @property
    def tanesw_hours_elapsed(self):
        if not self.tanesw_lodged_at:
            return 0
        end_time = self.tra_accepted_at or self.tra_objection_at or timezone.now()
        diff = end_time - self.tanesw_lodged_at
        return round(diff.total_seconds() / 3600, 1)

    @property
    def tanesw_hours_remaining(self):
        if not self.tanesw_lodged_at or self.tra_status in ['ACCEPTED', 'OBJECTION']:
            return 0
        return max(0.0, round(76.0 - self.tanesw_hours_elapsed, 1))

    @property
    def is_tanesw_overdue(self):
        if not self.tanesw_lodged_at or self.tra_status in ['ACCEPTED', 'OBJECTION']:
            return False
        return self.tanesw_hours_elapsed > 76.0

    @property
    def total_expenses(self):
        total = self.expenses.filter(approval_status='APPROVED').aggregate(total=models.Sum('amount'))['total']
        return total or Decimal('0.00')

    @property
    def all_expenses_sum(self):
        total = self.expenses.exclude(approval_status__in=['REJECTED', 'CANCELLED']).aggregate(total=models.Sum('amount'))['total']
        return total or Decimal('0.00')

    @property
    def client_billed_revenue(self):
        total = self.invoices.aggregate(total=models.Sum('total_amount'))['total']
        if total:
            return total
        return self.contracted_revenue

    @property
    def gross_margin(self):
        return self.client_billed_revenue - self.total_expenses

    @property
    def gross_margin_percentage(self):
        rev = self.client_billed_revenue
        if rev and rev > 0:
            return round((self.gross_margin / rev) * 100, 1)
        return 0.0

    @property
    def total_client_paid(self):
        total = self.invoices.aggregate(total=models.Sum('amount_paid'))['total']
        return total or Decimal('0.00')

    @property
    def client_outstanding_balance(self):
        return self.client_billed_revenue - self.total_client_paid

    @property
    def days_in_system(self):
        end_time = self.delivered_date or timezone.now()
        diff = end_time - self.created_at
        return max(1, diff.days)

    @property
    def is_overdue(self):
        curr = self.current_stage_obj
        if curr and curr.is_overdue:
            return True
        return False

    @classmethod
    def generate_next_job_number(cls):
        year = timezone.now().year
        prefix = f"MF/{year}/"
        last_job = cls.objects.filter(job_number__startswith=prefix).order_by('-job_number').first()
        if last_job:
            try:
                seq = int(last_job.job_number.split('/')[-1]) + 1
            except (ValueError, IndexError):
                seq = 1
        else:
            seq = cls.objects.filter(created_at__year=year).count() + 1
        return f"{prefix}{seq:04d}"

    @property
    def staff_file_name(self):
        """Internal staff see BL Number as the primary file name (just like on the physical file cover)."""
        return self.bl_number if self.bl_number else self.job_number

    @property
    def boss_file_name(self):
        """Boss/CEO sees MF/YYYY/XXXX with the BL Number in front."""
        if self.bl_number:
            return f"{self.job_number} — {self.bl_number}"
        return self.job_number

    @property
    def total_containers_count(self):
        cnt = self.containers.count()
        if cnt > 0:
            return cnt
        if self.container_numbers:
            return len([c for c in self.container_numbers.split(',') if c.strip()])
        return 1

    @property
    def containers_delivered_count(self):
        return self.containers.filter(status__in=['DELIVERED', 'EMPTY_RETURNED']).count()

    @property
    def containers_returned_count(self):
        return self.containers.filter(status='EMPTY_RETURNED').count()


class JobContainer(models.Model):
    STATUS_CHOICES = [
        ('AT_PORT', 'At Port / ICD Yard'),
        ('VERIFIED', 'Customs Verified / Inspected'),
        ('LOADED', 'Loaded on Truck'),
        ('IN_TRANSIT', 'In Transit / On Delivery'),
        ('DELIVERED', 'Delivered / Offloaded at Consignee'),
        ('EMPTY_RETURNED', 'Empty Returned to Depot (Completed)'),
    ]

    job = models.ForeignKey(JobShipment, on_delete=models.CASCADE, related_name='containers')
    container_number = models.CharField(max_length=50, help_text="e.g. MSCU9482110")
    size_type = models.CharField(max_length=30, choices=JobShipment.CONTAINER_TYPES, default='40HC')
    seal_number = models.CharField(max_length=100, blank=True)
    tare_weight_kg = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Tare weight in kg")
    gross_weight_kg = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Gross weight in kg (VGM)")

    # Transport Assignment (Individual truck & driver)
    assigned_truck = models.CharField(max_length=50, blank=True, help_text="e.g. MCW 101 or T 412 DXE")
    assigned_trailer = models.CharField(max_length=50, blank=True, help_text="e.g. T 881 AYM")
    assigned_driver = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_containers')

    # Gate & Port status
    gate_pass_number = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='AT_PORT')

    # Timeline
    loaded_at = models.DateTimeField(null=True, blank=True)
    gate_out_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    # Empty Return Tracking (Detention control)
    empty_free_days = models.PositiveSmallIntegerField(default=7, help_text="Days allowed to return empty container before demurrage")
    empty_returned_date = models.DateField(null=True, blank=True, verbose_name="Empty Container Returned Date")
    empty_return_depot = models.CharField(max_length=150, blank=True, help_text="e.g. AMI Depot, Bravo Yard, Kurasini")
    eir_number = models.CharField(max_length=100, blank=True, verbose_name="Equipment Interchange Receipt (EIR) No")
    container_deposit_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, help_text="Security deposit paid to shipping line")
    is_deposit_refunded = models.BooleanField(default=False)

    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['container_number']

    def __str__(self):
        return f"{self.container_number} ({self.get_size_type_display()}) - {self.job.job_number}"

    @property
    def effective_gate_out(self):
        if self.gate_out_at:
            return self.gate_out_at
        if self.status in ['IN_TRANSIT', 'DELIVERED', 'EMPTY_RETURNED']:
            return self.loaded_at or self.created_at
        return None

    @property
    def days_since_gate_out(self):
        start = self.effective_gate_out
        if not start:
            return 0
        end = timezone.now() if not self.empty_returned_date else timezone.make_aware(timezone.datetime.combine(self.empty_returned_date, timezone.datetime.min.time()))
        diff = end - start
        return max(0, diff.days)

    @property
    def free_days_remaining(self):
        if self.status == 'EMPTY_RETURNED':
            return 0
        spent = self.days_since_gate_out
        return max(0, self.empty_free_days - spent)

    @property
    def is_detention_overdue(self):
        if self.status == 'EMPTY_RETURNED':
            return False
        if not self.effective_gate_out:
            return False
        return self.days_since_gate_out > self.empty_free_days

    @property
    def is_detention_expiring_soon(self):
        if self.status == 'EMPTY_RETURNED':
            return False
        if not self.effective_gate_out:
            return False
        return not self.is_detention_overdue and self.free_days_remaining <= 2

    @property
    def detention_overdue_days(self):
        if self.is_detention_overdue:
            return self.days_since_gate_out - self.empty_free_days
        return 0


class JobStageInstance(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETED', 'Completed'),
        ('DELAYED', 'Delayed / Bottleneck'),
        ('BLOCKED', 'Blocked (Awaiting Duty/Docs)'),
    ]

    job = models.ForeignKey(JobShipment, on_delete=models.CASCADE, related_name='stages')
    stage_definition = models.ForeignKey(WorkflowStageDefinition, on_delete=models.PROTECT)
    stage_number = models.PositiveSmallIntegerField()
    name_en = models.CharField(max_length=150)
    name_sw = models.CharField(max_length=150)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    target_days = models.PositiveSmallIntegerField(default=1)
    responsible_officer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    remarks = models.TextField(blank=True)
    stage_data = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['stage_number']
        unique_together = ['job', 'stage_number']

    def __str__(self):
        return f"{self.job.job_number} - Step {self.stage_number}: {self.name_en}"

    @property
    def duration_days(self):
        if not self.started_at:
            return 0
        end = self.completed_at or timezone.now()
        diff = end - self.started_at
        return max(1, diff.days)

    @property
    def is_overdue(self):
        if self.status in ['COMPLETED']:
            if self.started_at and self.completed_at:
                return (self.completed_at - self.started_at).days > self.target_days
            return False
        if self.status in ['IN_PROGRESS', 'DELAYED', 'BLOCKED']:
            if self.started_at:
                days_spent = (timezone.now() - self.started_at).days
                return days_spent > self.target_days
        return False


def job_document_upload_path(instance, filename):
    """
    Organizes every uploaded file in Cloudflare R2 (or local storage) by:
    malkia_files/<YEAR>/<MF-YYYY-XXXX>_BL-<BL_NUMBER>/<filename>
    """
    year = timezone.now().year
    job_slug = "UNASSIGNED"
    if instance.job:
        if instance.job.created_at:
            year = instance.job.created_at.year
        raw_jnum = (instance.job.job_number or "FILE").replace("/", "-").replace(" ", "")
        raw_bl = (instance.job.bl_number or "NOBL").replace("/", "-").replace(" ", "")
        job_slug = f"{raw_jnum}_BL-{raw_bl}"
    safe_name = os.path.basename(filename)
    return f"malkia_files/{year}/{job_slug}/{safe_name}"


class JobDocument(models.Model):
    DOC_TYPES = [
        ('BILL_OF_LADING', 'Bill of Lading (BL)'),
        ('COMMERCIAL_INVOICE', 'Commercial Invoice'),
        ('PACKING_LIST', 'Packing List'),
        ('TBS_CERT', 'TBS Inspection Certificate'),
        ('EXPORT_CERT', 'Export Certificate'),
        ('CERTIFICATE_OF_ORIGIN', 'Certificate of Origin'),
        ('DECLARATION_ASSESSMENT', 'Customs Assessment / Declaration'),
        ('DUTY_PAYMENT_RECEIPT', 'Duty Payment Receipt'),
        ('DELIVERY_ORDER', 'Delivery Order (DO)'),
        ('RELEASE_ORDER', 'Release Order'),
        ('PORT_INVOICE', 'Port Invoice (TPA/TICTS)'),
        ('PORT_PAYMENT_RECEIPT', 'Port Charges Receipt'),
        ('GATE_PASS', 'Gate Pass & Inspection Sheet'),
        ('CONTAINER_PHOTO', 'Container / Seal Photo'),
        ('PROOF_OF_DELIVERY', 'Proof of Delivery (POD)'),
        ('OTHER', 'Other Supporting Document'),
    ]

    job = models.ForeignKey(JobShipment, on_delete=models.CASCADE, related_name='documents')
    stage = models.ForeignKey(JobStageInstance, on_delete=models.SET_NULL, null=True, blank=True, related_name='documents')
    document_type = models.CharField(max_length=50, choices=DOC_TYPES)
    title = models.CharField(max_length=200)
    file = models.FileField(upload_to=job_document_upload_path)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.job.job_number} - {self.get_document_type_display()}: {self.title}"

    @property
    def filename(self):
        return os.path.basename(self.file.name)


class ExpenseCategory(models.TextChoices):
    PORT_CHARGES = 'PORT_CHARGES', 'Port Charges (TPA / TICTS Wharfage & Stevedoring)'
    SHIPPING_LINE = 'SHIPPING_LINE', 'Shipping Line DO & Demurrage Charges'
    TRANSPORT = 'TRANSPORT', 'Transport, Trucking & Offloading'
    FUEL = 'FUEL', 'Mafuta & Fuel Top-up (Petrol / Diesel / Field Run)'
    CUSTOMS_DUTY = 'CUSTOMS_DUTY', 'TRA Customs Duty & Taxes'
    DOCUMENTATION = 'DOCUMENTATION', 'Documentation, Permits & Inspection'
    PORT_HANDLING = 'PORT_HANDLING', 'Port Handling, Tally & Sundry'
    OTHER = 'OTHER', 'Other Operational Expense'


class ExpenseVoucher(models.Model):
    APPROVAL_STATUS_CHOICES = [
        ('REQUESTED', 'Requested / Pending Audit'),
        ('VERIFIED', 'Verified by Accountant / Pending CEO Payout'),
        ('APPROVED', 'Approved by CEO'),
        ('REJECTED', 'Rejected'),
        ('PAID', 'Disbursed / Paid'),
        ('CANCELLED', 'Cancelled'),
    ]

    voucher_number = models.CharField(max_length=50, unique=True, help_text="e.g. EXP/2026/0001")
    job = models.ForeignKey(JobShipment, on_delete=models.CASCADE, related_name='expenses')
    category = models.CharField(max_length=50, choices=ExpenseCategory.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    control_number = models.CharField(max_length=100, blank=True, verbose_name="Control Number / Bill Reference")
    beneficiary_name = models.CharField(max_length=150, blank=True, verbose_name="Payee / Shipping Line / ICD")
    description = models.TextField(help_text="Purpose and details of expense")
    supporting_document = models.FileField(upload_to='expense_vouchers/%Y/%m/', null=True, blank=True)
    
    requester = models.ForeignKey(User, on_delete=models.CASCADE, related_name='requested_expenses')
    requested_at = models.DateTimeField(auto_now_add=True)

    # Verification by Accountant (Bridge role)
    audited_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='audited_expenses')
    audited_at = models.DateTimeField(null=True, blank=True)

    # Approval Matrix tracking (Authorized by CEO / Admin)
    required_role = models.CharField(max_length=30, choices=UserRole.choices, default=UserRole.CEO)
    approver = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_expenses')
    approval_status = models.CharField(max_length=20, choices=APPROVAL_STATUS_CHOICES, default='REQUESTED')
    approval_date = models.DateTimeField(null=True, blank=True)
    approval_remarks = models.TextField(blank=True)

    # Disbursement
    PAYMENT_METHOD_CHOICES = [
        ('BANK', 'Direct Bank Transfer / Cheque'),
        ('CASH', 'Cashier Cash / Petty Cash'),
        ('MOBILE_MONEY', 'Mobile Money (M-Pesa / TigoPesa)'),
    ]
    payment_method = models.CharField(max_length=30, choices=PAYMENT_METHOD_CHOICES, default='BANK')
    is_paid = models.BooleanField(default=False)
    paid_at = models.DateTimeField(null=True, blank=True)
    payment_reference = models.CharField(max_length=100, blank=True, help_text="Bank Ref / Cheque No / Mobile Money Ref")

    class Meta:
        ordering = ['-requested_at']

    def __str__(self):
        return f"{self.voucher_number} - {self.job.job_number} (TSh {self.amount:,.2f})"

    @classmethod
    def determine_required_role(cls, amount):
        amt = Decimal(str(amount))
        if amt <= Decimal('500000'):
            return UserRole.OPERATIONS_MGR
        elif amt <= Decimal('2000000'):
            return UserRole.FINANCE
        else:
            return UserRole.CEO

    @classmethod
    def generate_next_voucher_number(cls):
        year = timezone.now().year
        prefix = f"EXP/{year}/"
        last = cls.objects.filter(voucher_number__startswith=prefix).order_by('-voucher_number').first()
        if last:
            try:
                seq = int(last.voucher_number.split('/')[-1]) + 1
            except (ValueError, IndexError):
                seq = 1
        else:
            seq = 1
        return f"{prefix}{seq:04d}"


class ClientInvoice(models.Model):
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('ISSUED', 'Issued to Client'),
        ('PARTIALLY_PAID', 'Partially Paid'),
        ('PAID', 'Fully Paid'),
        ('OVERDUE', 'Overdue'),
    ]

    invoice_number = models.CharField(max_length=50, unique=True, help_text="e.g. INV/2026/0001")
    job = models.ForeignKey(JobShipment, on_delete=models.CASCADE, related_name='invoices')
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='invoices')
    issue_date = models.DateField(default=timezone.now)
    due_date = models.DateField()

    # Breakdown of items
    amount_clearing_agency_fee = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name="Agency / Clearance Fee")
    amount_duty_reimbursement = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name="TRA Duty Reimbursement")
    amount_port_charges = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name="Port & Wharfage Charges")
    amount_shipping_line_do = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name="Shipping Line DO Fees")
    amount_transport = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name="Transport & Offloading")
    amount_sundry_charges = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name="Sundry / Documentation")

    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ISSUED')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-issue_date']

    def __str__(self):
        return f"{self.invoice_number} - {self.customer.company_name} (TSh {self.total_amount:,.2f})"

    @property
    def balance_due(self):
        return max(Decimal('0.00'), self.total_amount - self.amount_paid)

    def calculate_total(self):
        return (
            self.amount_clearing_agency_fee +
            self.amount_duty_reimbursement +
            self.amount_port_charges +
            self.amount_shipping_line_do +
            self.amount_transport +
            self.amount_sundry_charges
        )

    @classmethod
    def generate_next_invoice_number(cls):
        year = timezone.now().year
        prefix = f"INV/{year}/"
        last = cls.objects.filter(invoice_number__startswith=prefix).order_by('-invoice_number').first()
        if last:
            try:
                seq = int(last.invoice_number.split('/')[-1]) + 1
            except (ValueError, IndexError):
                seq = 1
        else:
            seq = 1
        return f"{prefix}{seq:04d}"


class ClientPayment(models.Model):
    PAYMENT_METHODS = [
        ('BANK_TRANSFER', 'Direct Bank Transfer / TT / RTGS'),
        ('CHEQUE', 'Cheque'),
        ('MOBILE_MONEY', 'Mobile Money (M-Pesa / TigoPesa / AirtelMoney)'),
        ('CASH', 'Cashier Cash Receipt'),
    ]

    invoice = models.ForeignKey(ClientInvoice, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    payment_date = models.DateField(default=timezone.now)
    payment_method = models.CharField(max_length=30, choices=PAYMENT_METHODS, default='BANK_TRANSFER')
    payment_reference = models.CharField(max_length=100, help_text="Transaction ID / Cheque No / Slip No")
    receipt_file = models.FileField(upload_to='client_receipts/%Y/%m/', null=True, blank=True)
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-payment_date']

    def __str__(self):
        return f"Payment of TSh {self.amount:,.2f} for {self.invoice.invoice_number} ({self.payment_reference})"


class AuditLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    job = models.ForeignKey(JobShipment, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_logs')
    action = models.CharField(max_length=100)
    details = models.TextField()
    ip_address = models.CharField(max_length=50, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        user_name = self.user.username if self.user else "System"
        return f"[{self.timestamp.strftime('%Y-%m-%d %H:%M')}] {user_name} -> {self.action}"


class FieldIssue(models.Model):
    ISSUE_TYPES = [
        ('PORT_DELAY', 'Port Terminal Delay / Crane Breakdown'),
        ('VEHICLE_PROBLEM', 'Vehicle Breakdown / Mechanical Challenge'),
        ('INSPECTION_DELAY', 'Inspection Delay / Verification Query'),
        ('CUSTOMS_HOLD', 'Customs Physical Hold / TFDA / TBS Delay'),
        ('OTHER', 'Other Operational Challenge'),
    ]

    STATUS_CHOICES = [
        ('OPEN', 'Active / Investigating'),
        ('ACTION_TAKEN', 'Action Taken / Escalated'),
        ('RESOLVED', 'Resolved'),
    ]

    job = models.ForeignKey(JobShipment, on_delete=models.CASCADE, related_name='field_issues')
    issue_type = models.CharField(max_length=50, choices=ISSUE_TYPES, default='PORT_DELAY')
    description = models.TextField(help_text="Detailed challenge description")
    action_taken = models.TextField(blank=True, help_text="Immediate action taken")
    evidence_photo = models.ImageField(upload_to='field_issues/%Y/%m/', null=True, blank=True)
    reported_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='OPEN')
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_issue_type_display()} on {self.job.job_number} ({self.status})"


class FleetVehicle(models.Model):
    VEHICLE_STATUS = [
        ('AVAILABLE', 'Available / Standby'),
        ('IN_TRANSIT', 'In Transit / On Delivery'),
        ('MAINTENANCE', 'Maintenance / Workshop'),
        ('OFF_DUTY', 'Off Duty'),
    ]
    VEHICLE_TYPES = [
        ('PRIME_MOVER', 'Prime Mover (Heavy Tractor Head)'),
        ('FLATBED_TRAILER', 'Flatbed Semi-Trailer (40ft/20ft)'),
        ('SKELETAL_TRAILER', 'Skeletal Container Chassis'),
        ('RIGID_TRUCK', 'Rigid Box Truck (15-Ton)'),
    ]
    plate_number = models.CharField(max_length=30, unique=True, help_text="e.g. T 412 DXE")
    trailer_plate = models.CharField(max_length=30, blank=True, help_text="e.g. T 789 DXX")
    vehicle_type = models.CharField(max_length=30, choices=VEHICLE_TYPES, default='PRIME_MOVER')
    make_model = models.CharField(max_length=100, default='Scania R440 / Mercedes Actros')
    carrying_capacity_tons = models.DecimalField(max_digits=5, decimal_places=1, default=30.0)
    current_status = models.CharField(max_length=30, choices=VEHICLE_STATUS, default='AVAILABLE')
    assigned_driver = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_vehicles')
    gps_tracking_id = models.CharField(max_length=100, blank=True, help_text="Telematics device ID")
    current_location = models.CharField(max_length=150, default='Dar es Salaam Central Yard')
    insurance_expiry = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['plate_number']

    def __str__(self):
        return f"{self.plate_number} ({self.get_vehicle_type_display()}) - {self.get_current_status_display()}"


class StaffAttendance(models.Model):
    ATTENDANCE_TYPE = [
        ('OFFICE', 'Head Office (Posta HQ)'),
        ('FIELD', 'Port & Field / Wharfinger (TPA / ICD)'),
        ('REMOTE', 'Remote / On Duty Off-site'),
    ]
    STATUS_CHOICES = [
        ('PRESENT', 'Present (On Time)'),
        ('LATE', 'Late Arrival'),
        ('HALF_DAY', 'Half Day'),
        ('ON_LEAVE', 'On Approved Leave'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='attendances')
    date = models.DateField(default=timezone.now)
    clock_in_time = models.DateTimeField(null=True, blank=True)
    clock_out_time = models.DateTimeField(null=True, blank=True)
    attendance_type = models.CharField(max_length=20, choices=ATTENDANCE_TYPE, default='OFFICE')
    location_name = models.CharField(max_length=150, default='Malkia HQ - Posta Dar es Salaam')
    ip_address = models.CharField(max_length=50, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PRESENT')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-clock_in_time']
        unique_together = ('user', 'date')

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} - {self.date} ({self.get_status_display()})"


class SystemConfig(models.Model):
    key = models.CharField(max_length=100, unique=True)
    value = models.TextField()
    description = models.CharField(max_length=255, blank=True)
    category = models.CharField(max_length=50, default='GENERAL')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category', 'key']

    def __str__(self):
        return f"{self.key}: {self.value[:30]}"

    @classmethod
    def get_value(cls, key, default=''):
        obj = cls.objects.filter(key=key).first()
        return obj.value if obj else default

    @classmethod
    def set_value(cls, key, value, description='', category='GENERAL'):
        obj, _ = cls.objects.update_or_create(
            key=key,
            defaults={'value': str(value), 'description': description, 'category': category}
        )
        return obj


class StaffChatMessage(models.Model):
    """
    Real-time internal messaging between staff members (Boss <-> Employees, Peer <-> Peer, and Broadcasts).
    """
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_chat_messages')
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_chat_messages', null=True, blank=True)
    reply_to = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='replies')
    message = models.TextField(blank=True)
    attachment = models.FileField(upload_to='chat_attachments/', null=True, blank=True)
    is_broadcast = models.BooleanField(default=False, help_text="True if this message is a broadcast to all staff")
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    is_deleted = models.BooleanField(default=False, help_text="True if message was deleted like in WhatsApp")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['sender', 'recipient', 'created_at']),
            models.Index(fields=['recipient', 'is_read']),
            models.Index(fields=['is_broadcast', 'created_at']),
        ]

    def __str__(self):
        target = "ALL STAFF" if self.is_broadcast else (self.recipient.username if self.recipient else "None")
        return f"[{self.created_at.strftime('%H:%M')}] {self.sender.username} -> {target}: {self.message[:30]}"



