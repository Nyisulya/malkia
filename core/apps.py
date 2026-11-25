from django.apps import AppConfig
from django.db.backends.signals import connection_created
from django.db.models.signals import post_migrate


def _configure_sqlite_pragmas(sender, connection, **kwargs):
    if connection.vendor == 'sqlite':
        try:
            with connection.cursor() as cursor:
                cursor.execute("PRAGMA journal_mode=WAL;")
                cursor.execute("PRAGMA synchronous=NORMAL;")
                cursor.execute("PRAGMA temp_store=MEMORY;")
                cursor.execute("PRAGMA cache_size=-20000;")
                cursor.execute("PRAGMA busy_timeout=30000;")
        except Exception:
            pass


def auto_add_missing_columns(sender, **kwargs):
    try:
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA table_info(core_jobshipment)")
            cols = [r[1] for r in cursor.fetchall()]
            if cols:
                if 'cost_running_other' not in cols:
                    cursor.execute("ALTER TABLE core_jobshipment ADD COLUMN cost_running_other decimal(14, 2) DEFAULT 0")
                if 'cost_running_other_description' not in cols:
                    cursor.execute("ALTER TABLE core_jobshipment ADD COLUMN cost_running_other_description text DEFAULT ''")

            cursor.execute("PRAGMA table_info(core_clientinvoice)")
            inv_cols = [r[1] for r in cursor.fetchall()]
            if inv_cols and 'extra_line_items' not in inv_cols:
                cursor.execute("ALTER TABLE core_clientinvoice ADD COLUMN extra_line_items text DEFAULT ''")
    except Exception:
        pass


class CoreConfig(AppConfig):
    name = 'core'

    def ready(self):
        connection_created.connect(_configure_sqlite_pragmas)
        post_migrate.connect(auto_add_missing_columns, sender=self)
