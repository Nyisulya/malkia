#!/usr/bin/env python3
"""
Malkia Cargo Wave - Safely Delete Job #2 & Shift Job #3 to Job #2
Usage:
    python delete_second_job.py
"""
import os
import sys

sys.path.insert(0, os.path.abspath('.'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'malkia_project.settings')

import django
django.setup()

from django.db import transaction
from core.models import JobShipment, ClientInvoice, ExpenseVoucher, JobDocument, AuditLog, JobStageInstance, JobContainer


def run_cleanup():
    print("=" * 65)
    print("  MALKIA CARGO WAVE - ONDOA KAZI YA PILI & SOGEZA KAZI YA 3 IWE YA 2")
    print("=" * 65)

    with transaction.atomic():
        # 1. Ondoa test benchmark jobs kama zipo
        test_jobs = JobShipment.objects.filter(bl_number__startswith='TEST-BL-')
        if test_jobs.exists():
            t_count = test_jobs.count()
            test_jobs.delete()
            print(f"[+] Zimeondolewa test jobs {t_count} za muda.")

        # 2. Pata kazi zote zilizopo kwenye mfumo kwa mpangilio wa tarehe/namba
        all_jobs = list(JobShipment.objects.all().order_by('id'))
        print(f"\n[1/4] Kazi zilizopo sasa hivi ({len(all_jobs)}):")
        for idx, j in enumerate(all_jobs, 1):
            cust = j.customer.company_name if j.customer else 'N/A'
            print(f"   #{idx}: {j.job_number} | B/L: {j.bl_number} | Mteja: {cust} (ID: {j.id})")

        # 3. Tambua Kazi ya Pili (Job #2)
        job2 = None
        # Jaribu kutafuta kwa namba 0002 kwanza
        job2 = JobShipment.objects.filter(job_number__endswith='0002').first()
        if not job2 and len(all_jobs) >= 2:
            job2 = all_jobs[1]

        if not job2:
            print("\n[!] Hakuna kazi ya pili iliyopatikana ya kufuta.")
            return

        job2_no = job2.job_number
        job2_bl = job2.bl_number
        job2_cust = job2.customer.company_name if job2.customer else 'N/A'
        print(f"\n[2/4] Kazi ya Pili itakayofutwa:")
        print(f"   -> Namba: {job2_no} | B/L: {job2_bl} | Mteja: {job2_cust}")

        # Futa rekodi zote zinazohusiana nayo
        AuditLog.objects.filter(job=job2).delete()
        JobStageInstance.objects.filter(job=job2).delete()
        JobDocument.objects.filter(job=job2).delete()
        ExpenseVoucher.objects.filter(job=job2).delete()
        ClientInvoice.objects.filter(job=job2).delete()
        JobContainer.objects.filter(job=job2).delete()
        job2.delete()
        print(f"[OK] Kazi ya Pili ({job2_no}) imefutwa kikamilifu bila kuacha mabaki yoyote.")

        # 4. Tambua Kazi ya Tatu (Job #3) ili iwe Kazi ya Pili (Job #2)
        job3 = JobShipment.objects.filter(job_number__endswith='0003').first()
        if not job3:
            # Tafuta inayofuata baada ya ya kwanza
            remaining = list(JobShipment.objects.all().order_by('id'))
            if len(remaining) >= 2:
                job3 = remaining[1]

        if job3:
            old_no = job3.job_number
            new_no = "MCW/2026/0002"
            print(f"\n[3/4] Inasogeza Kazi ya Tatu ({old_no}) kuwa Kazi ya Pili ({new_no})...")

            job3.job_number = new_no
            if job3.c41_reference_no:
                job3.c41_reference_no = f"TRA-C41/{new_no}"
            if job3.tbs_letter_reference_no:
                job3.tbs_letter_reference_no = f"MALKIA/TBS/{new_no}"

            job3.save()

            # Sasisha namba ya ankara (invoice) kama ipo kwa kazi hii
            invoices = ClientInvoice.objects.filter(job=job3)
            for inv in invoices:
                if '0003' in inv.invoice_number or '0001' not in inv.invoice_number:
                    old_inv = inv.invoice_number
                    inv.invoice_number = f"INV/2026/0002"
                    try:
                        inv.save(update_fields=['invoice_number'])
                        print(f"   -> Ankara {old_inv} imesasishwa kuwa {inv.invoice_number}")
                    except Exception:
                        pass

            print(f"[OK] Kazi {old_no} sasa imekuwa {new_no} kwa mafanikio!")

        # 5. Onyesha orodha ya sasa baada ya mabadiliko
        updated_jobs = list(JobShipment.objects.all().order_by('id'))
        print(f"\n[4/4] Mpangilio Mpya wa Kazi zilizobaki ({len(updated_jobs)}):")
        for idx, j in enumerate(updated_jobs, 1):
            cust = j.customer.company_name if j.customer else 'N/A'
            print(f"   Hatua #{idx}: {j.job_number} | B/L: {j.bl_number} | Mteja: {cust} (ID: {j.id})")

        print("\n" + "=" * 65)
        print("  ZOTE ZIMESASISHWA KIKAMILIFU BILA KUGUSA WALA KUHARIBU UI!")
        print("=" * 65)


if __name__ == '__main__':
    run_cleanup()
