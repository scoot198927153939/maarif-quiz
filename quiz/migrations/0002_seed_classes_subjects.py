from django.db import migrations

CLASSES = ["1AS", "2AS", "3AS", "4AS", "5MA", "5SN", "6MA", "6SN", "7MA", "7SN"]
COLLEGE = ["1AS", "2AS", "3AS", "4AS"]
LYCEE = ["5MA", "5SN", "6MA", "6SN", "7MA", "7SN"]
SUBJECTS = {
    "الرياضيات": COLLEGE + LYCEE,
    "الفيزياء والكيمياء": LYCEE,
    "العلوم الطبيعية": LYCEE,
    "العربية": COLLEGE,
    "الفرنسية": COLLEGE,
}


def seed(apps, schema_editor):
    Classe = apps.get_model("quiz", "Classe")
    Subject = apps.get_model("quiz", "Subject")
    classes = {}
    for i, code in enumerate(CLASSES, start=1):
        classes[code], _ = Classe.objects.get_or_create(code=code, defaults={"order": i})
    for name, codes in SUBJECTS.items():
        subject, _ = Subject.objects.get_or_create(name=name)
        subject.classes.add(*[classes[c] for c in codes])


class Migration(migrations.Migration):
    dependencies = [("quiz", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
