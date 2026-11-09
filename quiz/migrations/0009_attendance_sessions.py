from django.db import migrations, models
import django.db.models.deletion


def copy_section(apps, schema_editor):
    TeacherAttendance = apps.get_model("quiz", "TeacherAttendance")
    for rec in TeacherAttendance.objects.all():
        first = rec.sections.order_by("order").first()
        if first:
            rec.section = first
            rec.save(update_fields=["section"])


class Migration(migrations.Migration):
    dependencies = [("quiz", "0008_section_6af")]

    operations = [
        migrations.AddField(
            model_name="studentattendance", name="session",
            field=models.PositiveSmallIntegerField(
                choices=[(1, "الحصة 1"), (2, "الحصة 2"), (3, "الحصة 3")], default=1, verbose_name="الحصة"),
        ),
        migrations.AddField(
            model_name="teacherattendance", name="session",
            field=models.PositiveSmallIntegerField(
                choices=[(1, "الحصة 1"), (2, "الحصة 2"), (3, "الحصة 3")], default=1, verbose_name="الحصة"),
        ),
        migrations.AddField(
            model_name="teacherattendance", name="section",
            field=models.ForeignKey(
                null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="+", to="quiz.section", verbose_name="القسم"),
        ),
        migrations.RunPython(copy_section, migrations.RunPython.noop),
        migrations.RemoveField(model_name="teacherattendance", name="sections"),
        migrations.AlterField(
            model_name="teacherattendance", name="section",
            field=models.ForeignKey(
                null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="teacher_attendance", to="quiz.section", verbose_name="القسم"),
        ),
        migrations.AlterUniqueTogether(name="studentattendance", unique_together={("student", "date", "session")}),
        migrations.AlterUniqueTogether(name="teacherattendance", unique_together={("teacher", "date", "session")}),
        migrations.AlterModelOptions(name="studentattendance", options={
            "ordering": ["-date", "session"], "verbose_name": "حضور تلميذ", "verbose_name_plural": "حضور التلاميذ"}),
        migrations.AlterModelOptions(name="teacherattendance", options={
            "ordering": ["-date", "session"], "verbose_name": "حضور أستاذ", "verbose_name_plural": "حضور الأساتذة"}),
    ]
