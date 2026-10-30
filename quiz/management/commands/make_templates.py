from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from quiz import excel


class Command(BaseCommand):
    help = "حفظ نماذج Excel للاستيراد في مجلد samples/"

    def handle(self, *args, **options):
        out = Path(settings.BASE_DIR) / "samples"
        out.mkdir(exist_ok=True)
        excel.questions_template().save(out / "نموذج_الأسئلة.xlsx")
        excel.students_template().save(out / "نموذج_التلاميذ.xlsx")
        self.stdout.write(self.style.SUCCESS(f"تم الحفظ في {out}"))
