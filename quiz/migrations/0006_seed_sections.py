from django.db import migrations

SECTIONS = [
    "1AS1", "1AS2", "2AS1", "2AS2", "3AS1", "3AS2", "4AS1", "4AS2",
    "5MA1", "5MA2", "5SN1", "5SN2", "6MA1", "6MA2", "6SN1", "6SN2",
    "7MA1", "7MA2", "7SN1", "7SN2", "7SN3", "7SN4", "7SN6",
]


def seed(apps, schema_editor):
    Classe = apps.get_model("quiz", "Classe")
    Section = apps.get_model("quiz", "Section")
    for i, code in enumerate(SECTIONS, start=1):
        classe = Classe.objects.filter(code=code[:3]).first()
        if classe:
            Section.objects.get_or_create(code=code, defaults={"classe": classe, "order": i})


class Migration(migrations.Migration):
    dependencies = [("quiz", "0005_sections_attendance")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
