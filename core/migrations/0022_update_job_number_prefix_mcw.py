from django.db import migrations

def update_mf_to_mcw(apps, schema_editor):
    JobShipment = apps.get_model('core', 'JobShipment')
    for job in JobShipment.objects.filter(job_number__startswith='MF/'):
        job.job_number = job.job_number.replace('MF/', 'MCW/')
        job.save(update_fields=['job_number'])

    AuditLog = apps.get_model('core', 'AuditLog')
    for log in AuditLog.objects.filter(details__contains='MF/'):
        log.details = log.details.replace('MF/', 'MCW/')
        log.save(update_fields=['details'])

    ExpenseVoucher = apps.get_model('core', 'ExpenseVoucher')
    for exp in ExpenseVoucher.objects.filter(description__contains='MF/'):
        exp.description = exp.description.replace('MF/', 'MCW/')
        exp.save(update_fields=['description'])

def reverse_mcw_to_mf(apps, schema_editor):
    JobShipment = apps.get_model('core', 'JobShipment')
    for job in JobShipment.objects.filter(job_number__startswith='MCW/'):
        job.job_number = job.job_number.replace('MCW/', 'MF/')
        job.save(update_fields=['job_number'])

class Migration(migrations.Migration):

    dependencies = [
        ('core', '0021_expensevoucher_audited_at_expensevoucher_audited_by_and_more'),
    ]

    operations = [
        migrations.RunPython(update_mf_to_mcw, reverse_mcw_to_mf),
    ]

