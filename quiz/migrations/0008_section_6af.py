from django.db import migrations


def add(apps, schema_editor):
    Classe = apps.get_model("quiz", "Classe")
    Section = apps.get_model("quiz", "Section")
    classe, _ = Classe.objects.get_or_create(code="6AF", defaults={"order": 11})
    Section.objects.get_or_create(code="6AF", defaults={"classe": classe, "order": 24})


def remove(apps, schema_editor):
    Section = apps.get_model("quiz", "Section")
    Classe = apps.get_model("quiz", "Classe")
    Section.objects.filter(code="6AF").delete()
    Classe.objects.filter(code="6AF", exams__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [("quiz", "0007_teacher_attendance_sections")]
    operations = [migrations.RunPython(add, remove)]
