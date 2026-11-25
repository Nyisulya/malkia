import os
from decimal import Decimal
from django.db import models
from django.db.models import Q
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta


class UserRole(models.TextChoices):
    # 3 Primary System Roles (Operations, Financial, CEO)
    OPERATIONS = 'OPERATIONS', 'Operations'
    FINANCE = 'FINANCE', 'Financial / Accountant'
    CEO = 'CEO', 'CEO / Management'

    # Backward compatibility aliases
    OPERATIONS_MGR = 'OPERATIONS_MGR', 'Operations'
    DOC_OFFICER = 'DOC_OFFICER', 'Operations'
    CLEARING_OFFICER = 'CLEARING_OFFICER', 'Operations'
    PORT_OFFICER = 'PORT_OFFICER', 'Operations'
    DISPATCH_OFFICER = 'DISPATCH_OFFICER', 'Operations'
    DRIVER = 'DRIVER', 'Operations'
    ADMIN = 'ADMIN', 'CEO / Administrator'

    @classmethod
    def primary_choices(cls):
        return [
            (cls.OPERATIONS.value, 'Operations'),
            (cls.FINANCE.value, 'Financial / Accountant'),
            (cls.CEO.value, 'CEO / Management'),
        ]


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
    can_assign_declaration = models.BooleanField(default=False, verbose_name="Head of Declaration (Can Assign Stage 2 Jobs)")
    can_assign_port = models.BooleanField(default=False, verbose_name="Head of Port Clearance (Can Assign Stage 3 Jobs)")
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
    phone = models.CharField(max_length=50, blank=True, verbose_name="Phone No")
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
    container_qty = models.PositiveIntegerField(default=1, verbose_name="Qty (Containers)")
    container_size_type = models.CharField(max_length=30, choices=CONTAINER_TYPES, default='RORO')
    vessel_name = models.CharField(max_length=150, blank=True, default='', help_text="Vessel name & voyage")
    voyage_number = models.CharField(max_length=50, blank=True)
    port_of_origin = models.CharField(max_length=100, default='Yokohama, Japan', blank=True)
    port_of_arrival = models.CharField(max_length=100, default='Dar es Salaam Port (TPA)', blank=True)
    eta_arrival_date = models.DateField(null=True, blank=True, verbose_name="ETA / Expected Arrival Date")
    actual_arrival_date = models.DateField(null=True, blank=True, verbose_name="Actual Vessel Arrival")
    final_destination = models.CharField(max_length=150, default='Dar es Salaam, Tanzania', blank=True)
    cargo_description = models.TextField(blank=True, default='', help_text="Detailed description of vehicle/cargo")
    vehicle_make = models.CharField(max_length=60, blank=True, default='', verbose_name="Vehicle Make (e.g. TOYOTA)")
    vehicle_model = models.CharField(max_length=80, blank=True, default='', verbose_name="Vehicle Model (e.g. VANGUARD)")
    registration_year = models.CharField(max_length=20, blank=True, default='', verbose_name="Registration / Manufacture Year (e.g. 2008)")
    cif_usd = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name="CIF Buying Price / Invoice ($ USD)")

    # Direct Payment Costs (Accountant Ledger - Matching VEHICLES OUT format)
    cost_duty = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name="Duty (TRA Customs)")
    cost_do = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name="D/O (Shipping Line Delivery Order)")
    cost_wharfage = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name="Wharfage (TPA Port)")
    cost_tiss_wharfage = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name="Tiss Wharfage")
    cost_handling = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name="Handling (Port / ICD)")
    cost_facilitation = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name="Facilitation")
    cost_transport = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name="Transport")
    cost_agent_fee = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name="Agent Fee (Malkia Agency)")
    cost_fuel = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name="Fuel (Mafuta)")
    cost_ferry_charges = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name="Ferry Charges")
    cost_container_deposit = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name="Container Deposit")
    cost_shipping_fee = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name="Shipping Fee")
    cost_demurrage = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name="Demurrage Charges")
    cost_storage = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name="Storage Charges")
    cost_other = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name="Other / Miscellaneous Costs (TBS, Demurrage, Storage, etc.)")
    cost_other_description = models.CharField(max_length=255, blank=True, verbose_name="Description for Other Costs")

    # 1. DOCUMENT RECEIVE (Checklist from Client - No scanning required)
    doc_receive_method = models.CharField(max_length=20, choices=DOC_RECEIVE_METHODS, default='PHYSICAL', verbose_name="Document Receive Method")
    doc_bl_received = models.BooleanField(default=False, verbose_name="BL Document")
    doc_invoice_received = models.BooleanField(default=False, verbose_name="Invoice")
    doc_packing_list_received = models.BooleanField(default=False, verbose_name="Packing List")
    doc_tbs_cert_received = models.BooleanField(default=False, verbose_name="TBS Certificate")
    doc_export_cert_received = models.BooleanField(default=False, verbose_name="Export Certificate")
    doc_received_at = models.DateTimeField(null=True, blank=True)
    doc_intake_finalized = models.BooleanField(default=False, verbose_name="Documents Saved and Finalized")
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
    tbs_officer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='tbs_jobs')
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
            1: "File Opening & Doc Intake",
            2: "Customs Declaration (TANSAD)",
            3: "TBS Inspection & Clearance",
            4: "Port Clearance & Gate Exit",
            5: "Vehicle Arrival (Yard / Office)",
            6: "Customer Handover",
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
    def display_make_model(self):
        parts = [p for p in [self.vehicle_make, self.vehicle_model] if p]
        if parts:
            return " ".join(parts)
        return self.cargo_description or "Motor Vehicle"

    @property
    def total_direct_costs(self):
        """
        Direct disbursements paid by Malkia office on behalf of the client.
        NOTE: Excludes TRA Customs Duty, as the client pays TRA directly via Government Control Number.
        """
        from decimal import Decimal
        return (
            (self.cost_do or Decimal('0')) +
            (self.cost_wharfage or Decimal('0')) +
            (self.cost_tiss_wharfage or Decimal('0')) +
            (self.cost_handling or Decimal('0')) +
            (self.cost_facilitation or Decimal('0')) +
            (self.cost_transport or Decimal('0')) +
            (self.cost_fuel or Decimal('0')) +
            (self.cost_ferry_charges or Decimal('0')) +
            self.net_container_deposit +
            (self.cost_shipping_fee or Decimal('0')) +
            (self.cost_demurrage or Decimal('0')) +
            (self.cost_storage or Decimal('0')) +
            (self.cost_other or Decimal('0'))
        )

    @property
    def client_billable_costs(self):
        """
        Recoverable direct disbursements billed to client (D/O, Wharfage, TISS, Handling, Container & Extra Costs).
        """
        from decimal import Decimal
        return (
            (self.cost_do or Decimal('0')) +
            (self.cost_wharfage or Decimal('0')) +
            (self.cost_tiss_wharfage or Decimal('0')) +
            (self.cost_handling or Decimal('0')) +
            self.net_container_deposit +
            (self.cost_shipping_fee or Decimal('0')) +
            (self.cost_demurrage or Decimal('0')) +
            (self.cost_storage or Decimal('0')) +
            (self.cost_other or Decimal('0'))
        )

    @property
    def internal_running_costs(self):
        """
        Direct operational costs incurred by Malkia for this specific vehicle/shipment
        (Facilitation, Fuel, Ferry, Transport), which are absorbed from the Agency Fee.
        """
        from decimal import Decimal
        return (
            (self.cost_facilitation or Decimal('0')) +
            (self.cost_fuel or Decimal('0')) +
            (self.cost_ferry_charges or Decimal('0')) +
            (self.cost_transport or Decimal('0'))
        )

    @property
    def net_agency_margin(self):
        """
        Actual profit margin earned on this job:
        Agency Fee minus the direct running costs incurred for this vehicle.
        """
        from decimal import Decimal
        return (self.cost_agent_fee or Decimal('0')) - self.internal_running_costs

    @property
    def container_deposit_refunded(self):
        if hasattr(self, '_deposit_refunded_cache'):
            return self._deposit_refunded_cache
        from django.db.models import Sum
        total = self.other_revenues.filter(
            inflow_type='CONTAINER_REFUND',
            deposit_status__in=['RETURNED_FULL', 'PARTIAL'],
        ).aggregate(s=Sum('returned_amount'))['s']
        return total or Decimal('0')

    @property
    def net_container_deposit(self):
        dep = self.cost_container_deposit or Decimal('0')
        if dep <= 0:
            return Decimal('0')
        return max(Decimal('0'), dep - self.container_deposit_refunded)

    @property
    def costing_status(self):
        """
        Calculates progressive costing status:
        - 'PENDING': No disbursements and no agent fee entered yet.
        - 'IN_PROGRESS': Partial disbursements or Duty entered, but clearance ongoing / Agent fee not entered.
        - 'FULLY_COSTED': Disbursements entered and Agent Fee finalized.
        """
        has_direct = (self.total_direct_costs or 0) > 0
        has_fee = (self.cost_agent_fee or 0) > 0
        if not has_direct and not has_fee:
            return 'PENDING'
        elif has_direct and not has_fee:
            return 'IN_PROGRESS'
        else:
            return 'FULLY_COSTED'

    @property
    def total_disbursement_with_agent_fee(self):
        from decimal import Decimal
        return self.total_direct_costs + (self.cost_agent_fee or Decimal('0'))

    @property
    def signed_tra_doc(self):
        return self.documents.filter(document_type__in=['TRA_AUTH_SIGNED', 'C41_SIGNED']).order_by('-uploaded_at').first()

    @property
    def signed_c41_doc(self):
        return self.signed_tra_doc

    @property
    def signed_tbs_doc(self):
        return self.documents.filter(document_type='TBS_SIGNED').order_by('-uploaded_at').first()

    @property
    def c41_doc(self):
        return self.documents.filter(document_type__in=['FORM_C41', 'C41_SIGNED']).order_by('-uploaded_at').first()

    @property
    def signed_handover_doc(self):
        return self.documents.filter(document_type='HANDOVER_SIGNED').order_by('-uploaded_at').first()

    @property
    def latest_invoice(self):
        return self.invoices.order_by('-created_at').first()

    @property
    def bl_doc(self):
        return self.documents.filter(document_type='BILL_OF_LADING').order_by('-uploaded_at').first()

    @property
    def invoice_doc(self):
        return self.documents.filter(document_type='COMMERCIAL_INVOICE').order_by('-uploaded_at').first()

    @property
    def packing_list_doc(self):
        return self.documents.filter(document_type='PACKING_LIST').order_by('-uploaded_at').first()

    @property
    def tbs_cert_doc(self):
        return self.documents.filter(document_type='TBS_CERT').order_by('-uploaded_at').first()

    @property
    def export_cert_doc(self):
        return self.documents.filter(document_type='EXPORT_CERT').order_by('-uploaded_at').first()

    @property
    def other_documents(self):
        standard_types = [
            'TRA_AUTH_SIGNED', 'C41_SIGNED', 'TBS_SIGNED', 'FORM_C41',
            'BILL_OF_LADING', 'COMMERCIAL_INVOICE', 'PACKING_LIST',
            'TBS_CERT', 'EXPORT_CERT'
        ]
        return self.documents.exclude(document_type__in=standard_types).order_by('-uploaded_at')

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
        prefix = f"MCW/{year}/"
        last_job = cls.objects.filter(Q(job_number__startswith=prefix) | Q(job_number__startswith=f"MF/{year}/")).order_by('-job_number').first()
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
        """Boss/CEO sees MCW/YYYY/XXXX with the BL Number in front."""
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
        # 1. Office Generated Letters (Signed & Scanned Back)
        ('TRA_AUTH_SIGNED', 'Signed TRA Authorization Letter'),
        ('TBS_SIGNED', 'Signed TBS Inspection Letter'),
        ('C41_SIGNED', 'Signed Form C41 (from TRA)'),  # Backwards compatibility

        # 2. External Customs & Statutory Documents
        ('FORM_C41', 'Form C41 (from TRA Portal)'),
        ('DECLARATION_ASSESSMENT', 'Customs Assessment / TANSAD'),
        ('DUTY_PAYMENT_RECEIPT', 'TRA Duty Payment Receipt'),
        ('TAX_CLEARANCE', 'Tax Clearance Certificate'),
        ('TBS_CERT', 'TBS Inspection Certificate'),

        # 3. Shipping & Carrier Intake Documents
        ('BILL_OF_LADING', 'Bill of Lading (BL)'),
        ('COMMERCIAL_INVOICE', 'Commercial Invoice'),
        ('PACKING_LIST', 'Packing List'),
        ('EXPORT_CERT', 'Export Certificate / Logbook'),
        ('CERTIFICATE_OF_ORIGIN', 'Certificate of Origin'),

        # 4. Port & Gate Release
        ('DELIVERY_ORDER', 'Delivery Order (D/O)'),
        ('RELEASE_ORDER', 'Release Order'),
        ('PORT_INVOICE', 'Port Charges Invoice (TPA/TICTS/DPW)'),
        ('PORT_PAYMENT_RECEIPT', 'Port Charges Receipt'),
        ('GATE_PASS', 'Gate Pass & Inspection Sheet'),
        ('CONTAINER_PHOTO', 'Container / Vehicle Photo'),

        # 5. Handover & Identification
        ('HANDOVER_SIGNED', 'Signed Vehicle Handover Note / POD'),
        ('PROOF_OF_DELIVERY', 'Proof of Delivery (POD)'),
        ('CLIENT_ID', 'Client ID Copy / Power of Attorney'),
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
    amount_port_charges = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name="Port Wharfage (TPA Port)")
    amount_terminal_handling = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name="Terminal Handling / ICD Charges")
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
        from decimal import Decimal
        tot = self.total_amount if self.total_amount is not None else Decimal('0.00')
        paid = self.amount_paid if self.amount_paid is not None else Decimal('0.00')
        if not isinstance(tot, Decimal):
            tot = Decimal(str(tot))
        if not isinstance(paid, Decimal):
            paid = Decimal(str(paid))
        return max(Decimal('0.00'), tot - paid)

    def calculate_total(self):
        from decimal import Decimal
        return (
            (self.amount_clearing_agency_fee or Decimal('0')) +
            (self.amount_duty_reimbursement or Decimal('0')) +
            (self.amount_port_charges or Decimal('0')) +
            (self.amount_terminal_handling or Decimal('0')) +
            (self.amount_shipping_line_do or Decimal('0')) +
            (self.amount_transport or Decimal('0')) +
            (self.amount_sundry_charges or Decimal('0'))
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


class Employee(models.Model):
    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('ON_LEAVE', 'On Leave'),
        ('SUSPENDED', 'Suspended'),
        ('TERMINATED', 'Terminated / Left'),
    ]
    EMPLOYMENT_TYPE_CHOICES = [
        ('FULL_TIME', 'Full Time'),
        ('PART_TIME', 'Part Time'),
        ('CONTRACT', 'Contract'),
        ('CASUAL', 'Casual / Daily'),
    ]

    employee_number = models.CharField(max_length=20, unique=True, blank=True)
    full_name = models.CharField(max_length=150)
    position = models.CharField(max_length=100, verbose_name="Job Title / Position")
    department = models.CharField(max_length=100, blank=True)
    employment_type = models.CharField(max_length=20, choices=EMPLOYMENT_TYPE_CHOICES, default='FULL_TIME')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE')
    date_joined = models.DateField(default=timezone.now)

    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=10, choices=[('MALE', 'Male'), ('FEMALE', 'Female')], blank=True)
    physical_address = models.CharField(max_length=255, blank=True)

    basic_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    allowances = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Monthly Allowances")
    no_deductions = models.BooleanField(default=False, verbose_name="Flat pay — no PAYE/NSSF/WCF")

    bank_name = models.CharField(max_length=100, blank=True)
    bank_branch = models.CharField(max_length=100, blank=True)
    bank_account_number = models.CharField(max_length=50, blank=True)
    nida_number = models.CharField(max_length=40, blank=True, verbose_name="NIDA Number")
    tin_number = models.CharField(max_length=40, blank=True, verbose_name="TIN Number")
    nssf_number = models.CharField(max_length=40, blank=True, verbose_name="NSSF Number")

    emergency_contact_name = models.CharField(max_length=150, blank=True)
    emergency_contact_phone = models.CharField(max_length=30, blank=True)
    notes = models.TextField(blank=True)

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='employee_record')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_employees')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['full_name']

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.employee_number:
            self.employee_number = f"MCW-EMP-{self.id:04d}"
            super().save(update_fields=['employee_number'])

    @property
    def initials(self):
        parts = [part for part in (self.full_name or '').split() if part]
        if not parts:
            return '?'
        return (parts[0][0] + (parts[-1][0] if len(parts) > 1 else '')).upper()

    @property
    def monthly_gross(self):
        return (self.basic_salary or 0) + (self.allowances or 0)

    @property
    def is_on_payroll(self):
        return self.status in ('ACTIVE', 'ON_LEAVE')

    def __str__(self):
        return f"{self.full_name} ({self.employee_number})"


class OperatingExpenseCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_expense_categories')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'Operating expense categories'

    def __str__(self):
        return self.name


class OperatingExpense(models.Model):
    PAYMENT_METHOD_CHOICES = [
        ('BANK', 'Direct Bank Transfer / Cheque'),
        ('CASH', 'Cashier Cash / Petty Cash'),
        ('MOBILE_MONEY', 'Mobile Money (M-Pesa / TigoPesa)'),
    ]

    date = models.DateField(default=timezone.now)
    category = models.ForeignKey(OperatingExpenseCategory, on_delete=models.PROTECT, related_name='expenses')
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    payee = models.CharField(max_length=150, verbose_name="Paid To / Payee")
    payment_method = models.CharField(max_length=30, choices=PAYMENT_METHOD_CHOICES, default='BANK')
    payment_reference = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    receipt_file = models.FileField(upload_to='operating_expenses/%Y/%m/', null=True, blank=True)
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='recorded_operating_expenses')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-id']

    def __str__(self):
        return f"{self.category.name} - TSh {self.amount:,.2f} ({self.date})"


class OtherRevenue(models.Model):
    INFLOW_TYPE_CHOICES = [
        ('OTHER_REVENUE', 'Other Business Revenue (Counts as Profit)'),
        ('CONTAINER_REFUND', 'Container Deposit (Shipping Line)'),
        ('CAPITAL_INJECTION', 'Capital Injection / Boss Deposit'),
    ]

    DEPOSIT_STATUS_CHOICES = [
        ('PENDING', 'Pending (At Shipping Line)'),
        ('RETURNED_FULL', 'Returned in Full'),
        ('PARTIAL', 'Partial / Deducted'),
        ('FORFEITED', 'Forfeited in Full'),
    ]

    date = models.DateField(default=timezone.now)
    inflow_type = models.CharField(max_length=30, choices=INFLOW_TYPE_CHOICES, default='OTHER_REVENUE')
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    deposit_status = models.CharField(max_length=20, choices=DEPOSIT_STATUS_CHOICES, default='PENDING')
    returned_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    source = models.CharField(max_length=150, verbose_name="Received From / Source")
    job = models.ForeignKey(JobShipment, on_delete=models.SET_NULL, null=True, blank=True, related_name='other_revenues')
    payment_method = models.CharField(max_length=30, choices=OperatingExpense.PAYMENT_METHOD_CHOICES, default='BANK')
    payment_reference = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    receipt_file = models.FileField(upload_to='other_revenues/%Y/%m/', null=True, blank=True)
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='recorded_other_revenues')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-id']

    def __str__(self):
        return f"{self.get_inflow_type_display()} - TSh {self.amount:,.2f} ({self.date})"


class SalaryPayment(models.Model):
    STATUS_CHOICES = [
        ('DRAFT', 'Draft / Not Paid'),
        ('PAID', 'Paid'),
        ('CANCELLED', 'Cancelled'),
    ]

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='salary_payments')
    period = models.DateField(help_text="First day of the salary month")
    basic_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    allowances = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    paye = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="PAYE")
    nssf = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="NSSF (10%)")
    wcf = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="WCF (0.5%) — employer cost")
    sdl = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="SDL (3.5%) — employer cost")
    salary_advance = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Salary Advance")
    loan_deduction = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Loan Deduction")
    other_deductions = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    deduction_notes = models.CharField(max_length=255, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    payment_date = models.DateField(null=True, blank=True)
    payment_method = models.CharField(max_length=30, choices=OperatingExpense.PAYMENT_METHOD_CHOICES, default='BANK')
    payment_reference = models.CharField(max_length=100, blank=True)
    receipt_file = models.FileField(upload_to='salaries/%Y/%m/', null=True, blank=True)
    notes = models.TextField(blank=True)

    operating_expense = models.OneToOneField(OperatingExpense, on_delete=models.SET_NULL, null=True, blank=True, related_name='salary_payment')
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='recorded_salary_payments')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-period', 'employee__full_name']
        constraints = [
            models.UniqueConstraint(fields=['employee', 'period'], name='unique_salary_per_employee_period'),
        ]

    @property
    def gross_pay(self):
        return (self.basic_salary or 0) + (self.allowances or 0)

    @property
    def taxable_amount(self):
        gross = self.gross_pay or Decimal('0.00')
        nssf = self.nssf or Decimal('0.00')
        return max(Decimal('0.00'), gross - nssf)

    @property
    def pay_before_personal_deductions(self):
        gross = self.gross_pay or Decimal('0.00')
        nssf = self.nssf or Decimal('0.00')
        paye = self.paye or Decimal('0.00')
        return gross - nssf - paye

    @property
    def total_deductions(self):
        return (self.paye or 0) + (self.nssf or 0) + (self.salary_advance or 0) + (self.loan_deduction or 0) + (self.other_deductions or 0)

    @property
    def employer_statutory_cost(self):
        return (self.wcf or 0) + (self.sdl or 0)

    @property
    def net_pay(self):
        return self.gross_pay - self.total_deductions

    def __str__(self):
        return f"{self.employee.full_name} - {self.period:%B %Y} (TSh {self.net_pay:,.2f})"


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



