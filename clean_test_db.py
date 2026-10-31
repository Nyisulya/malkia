import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'malkia_project.settings')
django.setup()

from core.models import (
    JobShipment, JobStageInstance, JobDocument, ExpenseVoucher,
    ClientInvoice, ClientPayment, AuditLog, StaffChatMessage, JobContainer,
    Customer, WorkflowStageDefinition, UserRole, UserProfile
)
from django.contrib.auth.models import User

def reset_test_data():
    print("=====================================================")
    print("  MALKIA C&F - CLEAN DATABASE RESET FOR LIVE TRIAL   ")
    print("=====================================================")

    # 1. Clear all shipments and transactional records
    print("\n[1/4] Clearing test jobs, expenses, invoices, and audit logs...")
    c_docs = JobDocument.objects.all().delete()[0]
    c_exp = ExpenseVoucher.objects.all().delete()[0]
    c_pay = ClientPayment.objects.all().delete()[0]
    c_inv = ClientInvoice.objects.all().delete()[0]
    c_stages = JobStageInstance.objects.all().delete()[0]
    c_containers = JobContainer.objects.all().delete()[0]
    c_jobs = JobShipment.objects.all().delete()[0]
    c_audit = AuditLog.objects.all().delete()[0]
    c_chat = StaffChatMessage.objects.all().delete()[0]

    print(f"  - Deleted {c_jobs} test shipments / files")
    print(f"  - Deleted {c_exp} expense vouchers")
    print(f"  - Deleted {c_inv} invoices & {c_pay} payments")
    print(f"  - Deleted {c_docs} file documents")
    print(f"  - Deleted {c_audit} audit trail logs")

    # 2. Ensure Workflow Stage Definitions (1 to 9) are in place
    print("\n[2/4] Verifying 9 Workflow Stage Definitions...")
    stages_data = [
        (1, "FILE OPENING & DOC INTAKE", "1. Kupokea Nyaraka & Kufungua Jalada", 1, "folder-plus", UserRole.DOC_OFFICER, "Kupokea nyaraka za mteja (B/L, Invoice, Packing List, TBS, Export Cert) na kuanzisha jalada rasmi."),
        (2, "CUSTOMS DECLARATION (TANSAD)", "2. Kulodge TANSAD & Kutathmini Ushuru", 2, "file-invoice", UserRole.CLEARING_OFFICER, "Kuingiza TANSAD kwenye mfumo wa TRA TANESW kwa ajili ya tathmini ya forodha."),
        (3, "TRA DUTY / IN-BOND CLEARANCE", "3. Uthibitisho wa Malipo ya TRA / Bond (C41)", 1, "shield-halved", UserRole.FINANCE, "Kulipa kodi ya forodha kupitia GePG control number au kuingia chini ya Customs Bond (Form C41)."),
        (4, "DELIVERY ORDER (D/O)", "4. Kupokea D/O ya Meli (Shipping Line)", 1, "stamp", UserRole.PORT_OFFICER, "Kukabidhi nyaraka asili na kupokea Delivery Order kutoka kwa wakala wa meli."),
        (5, "PHYSICAL VERIFICATION", "5. Ukaguzi wa Gari Bandarini (TRA & TBS)", 2, "clipboard-check", UserRole.PORT_OFFICER, "Ukaguzi wa pamoja wa gari (Joint Inspection) kati ya TRA, TBS na Port Wharfinger."),
        (6, "PORT & ICD CHARGES", "6. Malipo ya Bandari & ICD (TICTS / TPA)", 1, "receipt", UserRole.FINANCE, "Kupokea na kulipa ankara za bandari na ICD ili kupata ruhusa ya kutolewa gari."),
        (7, "GATE EXIT & VEHICLE INSPECTION", "7. Kutoa Gari Lango Kuu (Gate Exit)", 1, "truck-ramp-box", UserRole.PORT_OFFICER, "Kukagua hali ya gari, kupokea Gate Pass, na kumkabidhi dereva kuanza safari."),
        (8, "MALKIA YARD ARRIVAL", "8. Kupokea Gari Yadi ya Malkia", 1, "warehouse", UserRole.OPERATIONS_MGR, "Kupokea gari kwenye yadi ya Malkia, kuthibitisha hali yake, na kuliweka kwenye Storage Box."),
        (9, "CUSTOMER HANDOVER", "9. Kukabidhi Gari kwa Mteja", 1, "handshake", UserRole.OPERATIONS_MGR, "Kukabidhi gari na nyaraka zote halisi kwa mteja baada ya kumaliza malipo na kusaini POD."),
    ]

    for num, name_en, name_sw, days, icon, role, desc in stages_data:
        WorkflowStageDefinition.objects.update_or_create(
            stage_number=num,
            defaults={
                'name_en': name_en,
                'name_sw': name_sw,
                'target_days': days,
                'icon': icon,
                'required_role': role,
                'description': desc,
                'is_controlled_gate': (num in [3, 7]),
            }
        )
    print("  - All 9 workflow milestones verified!")

    # 3. Ensure Client database has ready clients
    print("\n[3/4] Ensuring Client Accounts...")
    customers_data = [
        ("Sebagold Company Limited", "Director Sebagold", "+255 787 367 474", "info@sebagold.co.tz", "8674-7673-834", "Plot 14, Industrial Area, Dar es Salaam"),
        ("Erengeti Agro & Logistics Ltd", "Managing Director", "+255 786 677 799", "logistics@erengeti.co.tz", "105-334-921", "Nyerere Road, Dar es Salaam"),
        ("Victoria Motors Tanzania Ltd", "Eng. Peter Malima", "+255 767 332 990", "pmalima@victoriamotors.co.tz", "101-764-219", "Plot 18, Tabata, Dar es Salaam"),
    ]
    for cname, contact, phone, email, tin, addr in customers_data:
        Customer.objects.update_or_create(
            company_name=cname,
            defaults={
                'contact_person': contact,
                'phone': phone,
                'email': email,
                'tin_number': tin,
                'physical_address': addr,
            }
        )
    print("  - Active clients ready in database!")

    # 4. Verify system users
    print("\n[4/4] Verifying Staff & Executive Users...")
    users_info = [
        ('admin', 'Super', 'Administrator', UserRole.ADMIN, 'System Administrator'),
        ('nyisulya', 'System', 'Administrator', UserRole.ADMIN, 'IT Lead & DevOps Engineer'),
        ('ceo', 'Hashim', 'Mkwawa', UserRole.CEO, 'Managing Director & CEO'),
        ('operations_mgr', 'Grace', 'Mushi', UserRole.OPERATIONS_MGR, 'Operations Director'),
        ('doc_officer', 'Amani', 'Bakari', UserRole.DOC_OFFICER, 'Senior Documentation Officer'),
        ('clearing_officer', 'Rashid', 'Nassor', UserRole.CLEARING_OFFICER, 'Head Customs Broker / Clearing Officer'),
        ('finance_mgr', 'Subira', 'Kilonzo', UserRole.FINANCE, 'Chief Accountant / Finance Manager'),
        ('port_officer', 'Juma', 'Kavishe', UserRole.PORT_OFFICER, 'Port Field Inspector'),
        ('driver1', 'Mohamed', 'Said', UserRole.DRIVER, 'Heavy Logistics Driver'),
    ]
    for uname, fn, ln, role, title in users_info:
        u = User.objects.filter(username=uname).first()
        if u:
            print(f"  - {uname:18} | {u.get_full_name() or uname:22} | Role: {role}")

    print("\n=====================================================")
    print("[SUCCESS] MFUMO UPO SAFI KABISA KWA AJILI YA MAJARIBIO!")
    print("Huna gari hata moja kwa sasa. Unaweza kuanza Step 1 mara moja.")
    print("=====================================================")

if __name__ == '__main__':
    reset_test_data()
