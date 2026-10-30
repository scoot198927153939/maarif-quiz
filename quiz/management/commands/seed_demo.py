from django.core.management.base import BaseCommand

from quiz.models import Choice, Classe, Exam, Question, Subject, User


class Command(BaseCommand):
    help = "إنشاء حسابات تجريبية (مشرف، أستاذ، تلاميذ) وامتحان تجريبي."

    def handle(self, *args, **options):
        def make(username, password, **fields):
            user, created = User.objects.get_or_create(username=username, defaults=fields)
            if created:
                user.set_password(password)
                user.save()
            return user

        make("admin", "admin123", role=User.ADMIN, full_name="المشرف", is_staff=True, is_superuser=True)
        teacher = make("prof", "prof123", role=User.TEACHER, full_name="أستاذ الرياضيات")
        teacher.teaching_classes.set(Classe.objects.all())
        teacher.teaching_subjects.set(Subject.objects.filter(name="الرياضيات"))
        c1 = Classe.objects.get(code="1AS")
        c7 = Classe.objects.get(code="7SN")
        make("eleve1", "1234", role=User.STUDENT, full_name="تلميذ 1AS", classe=c1)
        make("eleve7", "1234", role=User.STUDENT, full_name="تلميذ 7SN", classe=c7)

        math = Subject.objects.get(name="الرياضيات")
        exam, created = Exam.objects.get_or_create(
            title="امتحان تجريبي في الحساب", classe=c1, subject=math, teacher=teacher,
            defaults={"duration_minutes": 10, "is_published": True,
                      "instructions": "اختر الإجابة الصحيحة لكل سؤال ثم اضغط «تسليم»."},
        )
        if created:
            data = [
                ("كم يساوي 5 + 7 ؟", ["10", "12", "13", "15"], "B", 2),
                ("كم يساوي 9 × 3 ؟", ["27", "21", "36", "18"], "A", 2),
                ("ما هو نصف العدد 50 ؟", ["20", "30", "25", "15"], "C", 1),
            ]
            for i, (text, opts, correct, pts) in enumerate(data, start=1):
                q = Question.objects.create(exam=exam, text=text, correct_answer=correct, points=pts, order=i)
                for letter, t in zip("ABCD", opts):
                    Choice.objects.create(question=q, letter=letter, text=t)
        self.stdout.write(self.style.SUCCESS(
            "تم. الحسابات: admin/admin123 (مشرف) - prof/prof123 (أستاذ) - eleve1/1234 (1AS) - eleve7/1234 (7SN)"
        ))
