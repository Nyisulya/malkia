import shutil
from pathlib import Path
from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.utils import timezone

from core.models import (
    AuditLog,
    ClientInvoice,
    ClientPayment,
    Customer,
    Employee,
    ExpenseVoucher,
    FieldIssue,
    FleetVehicle,
    JobContainer,
    JobDocument,
    JobShipment,
    JobStageInstance,
    OperatingExpense,
    OperatingExpenseCategory,
    OtherRevenue,
    SalaryPayment,
    StaffAttendance,
    StaffChatMessage,
    SystemConfig,
    UserProfile,
    WorkflowStageDefinition,
)


class Command(BaseCommand):
    help = (
        "Safely wipes transactional/test data (jobs, invoices, payments, expenses, payroll, logs) "
        "while preserving staff accounts, employees, workflow stages, expense categories, fleet, and settings."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Actually execute the deletion. Without --confirm, runs in dry-run preview mode.',
        )
        parser.add_argument(
            '--keep-customers',
            action='store_true',
            help='Keep Customer directory records while wiping jobs and financial transactions.',
        )
        parser.add_argument(
            '--jobs-only',
            action='store_true',
            help='Wipe only job-related records (jobs, stages, docs, containers, invoices, payments, vouchers, job refunds, audit logs). Keeps customers, office expenses, and payroll.',
        )
        parser.add_argument(
            '--no-backup',
            action='store_true',
            help='Skip creating a pre-wipe SQLite backup file.',
        )

    def _build_targets(self, keep_customers=False, jobs_only=False):
        targets = [
            ('ClientPayment', ClientPayment, ClientPayment.objects.all()),
            ('ClientInvoice', ClientInvoice, ClientInvoice.objects.all()),
            ('ExpenseVoucher', ExpenseVoucher, ExpenseVoucher.objects.all()),
            ('FieldIssue', FieldIssue, FieldIssue.objects.all()),
            ('JobDocument', JobDocument, JobDocument.objects.all()),
            ('JobContainer', JobContainer, JobContainer.objects.all()),
            ('JobStageInstance', JobStageInstance, JobStageInstance.objects.all()),
        ]
        if jobs_only:
            targets.append(('OtherRevenue (job-linked)', OtherRevenue, OtherRevenue.objects.filter(job__isnull=False)))
        else:
            targets.append(('OtherRevenue', OtherRevenue, OtherRevenue.objects.all()))
            targets.append(('SalaryPayment', SalaryPayment, SalaryPayment.objects.all()))
            targets.append(('OperatingExpense', OperatingExpense, OperatingExpense.objects.all()))

        targets.append(('AuditLog', AuditLog, AuditLog.objects.all()))

        if not jobs_only:
            targets.append(('StaffAttendance', StaffAttendance, StaffAttendance.objects.all()))
            targets.append(('StaffChatMessage', StaffChatMessage, StaffChatMessage.objects.all()))

        targets.append(('JobShipment', JobShipment, JobShipment.objects.all()))

        if not jobs_only and not keep_customers:
            targets.append(('Customer', Customer, Customer.objects.all()))

        return targets

    def _preserved_summary(self, keep_customers=False, jobs_only=False):
        preserved = [
            ('User (Staff logins)', User.objects.count()),
            ('UserProfile', UserProfile.objects.count()),
            ('Employee', Employee.objects.count()),
            ('WorkflowStageDefinition', WorkflowStageDefinition.objects.count()),
            ('SystemConfig', SystemConfig.objects.count()),
            ('OperatingExpenseCategory', OperatingExpenseCategory.objects.count()),
            ('FleetVehicle', FleetVehicle.objects.count()),
        ]
        if jobs_only or keep_customers:
            preserved.append(('Customer', Customer.objects.count()))
        if jobs_only:
            preserved.append(('OperatingExpense', OperatingExpense.objects.count()))
            preserved.append(('SalaryPayment', SalaryPayment.objects.count()))
        return preserved

    def _backup_sqlite(self):
        if connection.vendor != 'sqlite':
            return None
        db_name = connection.settings_dict.get('NAME')
        if not db_name or str(db_name) == ':memory:':
            return None
        db_path = Path(db_name)
        if not db_path.exists():
            return None

        with connection.cursor() as cursor:
            cursor.execute("PRAGMA wal_checkpoint(TRUNCATE);")

        backups_dir = Path(settings.BASE_DIR) / 'backups'
        backups_dir.mkdir(parents=True, exist_ok=True)
        stamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        backup_path = backups_dir / f'db_backup_{stamp}.sqlite3'
        shutil.copy2(db_path, backup_path)
        return backup_path

    def _reset_sqlite_sequences(self, table_names):
        if connection.vendor != 'sqlite' or not table_names:
            return
        with connection.cursor() as cursor:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sqlite_sequence';")
            if not cursor.fetchone():
                return
            placeholders = ', '.join(['%s'] * len(table_names))
            cursor.execute(f"DELETE FROM sqlite_sequence WHERE name IN ({placeholders});", table_names)

    def handle(self, *args, **options):
        confirm = options['confirm']
        keep_customers = options['keep_customers']
        jobs_only = options['jobs_only']
        no_backup = options['no_backup']

        targets = self._build_targets(keep_customers=keep_customers, jobs_only=jobs_only)
        preserved = self._preserved_summary(keep_customers=keep_customers, jobs_only=jobs_only)

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("=== MALKIA TRANSACTIONAL DATA RESET ==="))
        mode_label = "LIVE EXECUTION (--confirm)" if confirm else "DRY-RUN PREVIEW (no changes will be made)"
        self.stdout.write(f"Mode: {mode_label}")
        if jobs_only:
            self.stdout.write("Scope: --jobs-only (jobs & billing only)")
        elif keep_customers:
            self.stdout.write("Scope: full transactional reset (--keep-customers)")
        else:
            self.stdout.write("Scope: full transactional reset (jobs, billing, expenses, payroll, audit logs, customers)")

        self.stdout.write("\nRecords targeted for deletion:")
        total_to_delete = 0
        for label, model_cls, qs in targets:
            cnt = qs.count()
            total_to_delete += cnt
            self.stdout.write(f"  - {label:28s}: {cnt}")
        self.stdout.write(f"  Total rows to delete        : {total_to_delete}")

        self.stdout.write("\nRecords that will be PRESERVED untouched:")
        for label, cnt in preserved:
            self.stdout.write(f"  + {label:28s}: {cnt}")

        if not confirm:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING("Dry-run complete. Re-run with --confirm to create a backup and delete the rows above."))
            return

        if not no_backup:
            backup_path = self._backup_sqlite()
            if backup_path:
                self.stdout.write(self.style.SUCCESS(f"\nBackup saved to: {backup_path}"))

        cleared_tables = []
        deleted_counts = []
        with transaction.atomic():
            for label, model_cls, qs in targets:
                deleted, _ = qs.delete()
                deleted_counts.append((label, deleted))
                if not jobs_only or model_cls is not OtherRevenue:
                    cleared_tables.append(model_cls._meta.db_table)

        self._reset_sqlite_sequences(list(dict.fromkeys(cleared_tables)))

        self.stdout.write("\nDeletion summary:")
        for label, deleted in deleted_counts:
            self.stdout.write(f"  [OK] {label:28s}: {deleted} removed")
        self.stdout.write(self.style.SUCCESS("\nAll selected transactional data wiped cleanly. System is ready for live office entry."))
