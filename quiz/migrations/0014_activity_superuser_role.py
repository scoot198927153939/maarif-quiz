from django.db import migrations


def fix_roles(apps, schema_editor):
    # الأحداث المسجّلة لحساب المدير العام قبل هذا الإصلاح حُفظت بدور «تلميذ»
    ActivityLog = apps.get_model("quiz", "ActivityLog")
    ActivityLog.objects.filter(user__is_superuser=True).update(role="admin")


class Migration(migrations.Migration):
    dependencies = [("quiz", "0013_activity_log")]
    operations = [migrations.RunPython(fix_roles, migrations.RunPython.noop)]
