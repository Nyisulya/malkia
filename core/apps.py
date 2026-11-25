from django.apps import AppConfig
from django.db.models.signals import post_migrate


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
    except Exception:
        pass


class CoreConfig(AppConfig):
    name = 'core'

    def ready(self):
        post_migrate.connect(auto_add_missing_columns, sender=self)
