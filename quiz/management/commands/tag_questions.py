"""يملأ محور كل سؤال (ومستواه في امتحانات القبول) إذا كان فارغًا، لاستعماله في تقارير التلاميذ.

python manage.py tag_questions           # الأسئلة التي ليس لها محور فقط
python manage.py tag_questions --force   # إعادة التحديد لكل الأسئلة
"""
from django.core.management.base import BaseCommand

from quiz.models import Question
from quiz.topics import guess_topic, level_from_points

ADMISSION_TITLE = "امتحان القبول في مدارس المعارف الحرة"


class Command(BaseCommand):
    help = "تحديد محور ومستوى الأسئلة تلقائيًا"

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true")

    def handle(self, *args, force=False, **kw):
        n = 0
        for q in Question.objects.select_related("exam__subject"):
            changed = False
            if force or not q.topic:
                q.topic = guess_topic(q.exam.subject.name, q.text, [c.text for c in q.choices.all()])
                changed = True
            if not q.level and q.exam.title.startswith(ADMISSION_TITLE):
                q.level = level_from_points(q.points)
                changed = True
            if changed:
                q.save(update_fields=["topic", "level"])
                n += 1
        self.stdout.write(f"تم تحديث {n} سؤال.")
