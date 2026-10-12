from django.db import migrations, models
import django.db.models.deletion


def to_levels(apps, schema_editor):
    """يجمع مخزون فصول المستوى الواحد في مخزون واحد للمستوى."""
    BookStock = apps.get_model("quiz", "BookStock")
    totals = {}
    for b in BookStock.objects.select_related("section"):
        key = (b.section.classe_id, b.subject, b.part)
        totals[key] = totals.get(key, 0) + b.quantity
    BookStock.objects.all().delete()
    for (classe_id, subject, part), qty in totals.items():
        BookStock.objects.create(classe_id=classe_id, section_id=None, subject=subject, part=part, quantity=qty)


class Migration(migrations.Migration):
    dependencies = [("quiz", "0010_library")]

    operations = [
        migrations.RemoveConstraint(model_name="bookstock", name="uniq_book_stock"),
        migrations.AddField(
            model_name="bookstock", name="classe",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE,
                                    related_name="book_stock", to="quiz.classe", verbose_name="المستوى"),
        ),
        migrations.AlterField(
            model_name="bookstock", name="section",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to="quiz.section"),
        ),
        migrations.RunPython(to_levels, migrations.RunPython.noop),
        migrations.RemoveField(model_name="bookstock", name="section"),
        migrations.AlterField(
            model_name="bookstock", name="classe",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                    related_name="book_stock", to="quiz.classe", verbose_name="المستوى"),
        ),
        migrations.AddConstraint(
            model_name="bookstock",
            constraint=models.UniqueConstraint(fields=("classe", "subject", "part"), name="uniq_book_stock_level"),
        ),
    ]
