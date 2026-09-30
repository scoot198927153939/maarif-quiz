import io
import json

from django.test import TestCase, override_settings
from django.urls import reverse

from . import excel
from .models import Attempt, Choice, Classe, Exam, Question, Subject, User


class QuizFlowTests(TestCase):
    def setUp(self):
        self.c1 = Classe.objects.get(code="1AS")
        self.c7 = Classe.objects.get(code="7SN")
        self.math = Subject.objects.get(name="الرياضيات")
        self.physique = Subject.objects.get(name="الفيزياء والكيمياء")
        self.teacher = User.objects.create_user("prof", password="x", role=User.TEACHER)
        self.teacher.teaching_classes.set([self.c1, self.c7])
        self.teacher.teaching_subjects.set([self.math, self.physique])
        self.other_teacher = User.objects.create_user("prof2", password="x", role=User.TEACHER)
        self.s1 = User.objects.create_user("s1", password="x", role=User.STUDENT, classe=self.c1)
        self.s7 = User.objects.create_user("s7", password="x", role=User.STUDENT, classe=self.c7)
        self.exam = Exam.objects.create(
            title="T", classe=self.c1, subject=self.math, teacher=self.teacher, is_published=True,
        )
        for i, (correct, pts) in enumerate([("B", 2), ("A", 3)]):
            q = Question.objects.create(exam=self.exam, text=f"q{i}", correct_answer=correct, points=pts)
            for l in "ABC":
                Choice.objects.create(question=q, letter=l, text=l)

    def test_seeded_classes_and_subjects(self):
        self.assertEqual(Classe.objects.count(), 10)
        self.assertFalse(self.physique.classes.filter(code="1AS").exists())
        self.assertTrue(self.physique.classes.filter(code="7SN").exists())
        self.assertTrue(Subject.objects.get(name="العربية").classes.filter(code="4AS").exists())

    def test_student_only_sees_own_class(self):
        self.client.login(username="s7", password="x")
        r = self.client.get(reverse("student_dashboard"))
        self.assertNotContains(r, "ابدأ الامتحان")
        r = self.client.get(reverse("exam_intro", args=[self.exam.id]))
        self.assertEqual(r.status_code, 403)
        r = self.client.get(reverse("teacher_dashboard"))
        self.assertEqual(r.status_code, 403)

    def test_full_attempt_and_grading(self):
        self.client.login(username="s1", password="x")
        self.client.post(reverse("exam_intro", args=[self.exam.id]))
        q1, q2 = self.exam.questions.all()
        r = self.client.post(
            reverse("save_answer", args=[self.exam.id]),
            data=json.dumps({"question": q1.id, "selected": "B"}), content_type="application/json",
        )
        self.assertTrue(r.json()["ok"])
        # أثناء الامتحان: أي صفحة أخرى تعيده للامتحان
        r = self.client.get(reverse("student_dashboard"))
        self.assertRedirects(r, reverse("take_exam", args=[self.exam.id]))
        self.client.post(reverse("submit_exam", args=[self.exam.id]), {f"q_{q2.id}": "C"})
        a = Attempt.objects.get(student=self.s1)
        self.assertEqual(a.status, Attempt.SUBMITTED)
        self.assertEqual(a.score, 2)
        self.assertEqual(a.total, 5)
        # لا يمكن إعادة الامتحان
        r = self.client.get(reverse("exam_intro", args=[self.exam.id]))
        self.assertRedirects(r, reverse("attempt_result", args=[self.exam.id]))

    @override_settings(EXAM_MAX_VIOLATIONS=2)
    def test_violations_auto_submit(self):
        self.client.login(username="s1", password="x")
        self.client.post(reverse("exam_intro", args=[self.exam.id]))
        url = reverse("report_violation", args=[self.exam.id])
        self.assertFalse(self.client.post(url).json()["submitted"])
        self.assertTrue(self.client.post(url).json()["submitted"])
        a = Attempt.objects.get(student=self.s1)
        self.assertTrue(a.auto_submitted)

    def test_teacher_cannot_manage_other_exam(self):
        self.client.login(username="prof2", password="x")
        self.assertEqual(self.client.get(reverse("exam_detail", args=[self.exam.id])).status_code, 403)

    def test_exam_subject_must_match_class(self):
        self.client.login(username="prof", password="x")
        r = self.client.post(reverse("exam_create"), {
            "title": "x", "classe": self.c1.id, "subject": self.physique.id, "duration_minutes": 10,
        })
        self.assertContains(r, "لا تُدرَّس")
        self.assertEqual(Exam.objects.count(), 1)

    def test_excel_import_questions(self):
        buf = io.BytesIO()
        excel.questions_template().save(buf)
        buf.seek(0)
        count, errors = excel.import_questions(self.exam, buf)
        self.assertEqual(errors, [])
        self.assertEqual(count, 3)
        last = self.exam.questions.last()
        self.assertEqual(last.correct_answer, "D")  # «د» تحولت إلى D

    def test_excel_import_rejects_bad_answer(self):
        from openpyxl import Workbook
        wb = Workbook()
        wb.active.append(excel.QUESTION_HEADERS)
        wb.active.append(["س", "1", "2", "", "", "C", 1])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        count, errors = excel.import_questions(self.exam, buf)
        self.assertEqual(count, 0)
        self.assertTrue(errors)

    def test_excel_import_students(self):
        buf = io.BytesIO()
        excel.students_template().save(buf)
        buf.seek(0)
        created, updated, errors = excel.import_students(buf)
        self.assertEqual((created, updated, errors), (2, 0, []))
        u = User.objects.get(username="fatima.7sn")
        self.assertEqual(u.classe.code, "7SN")
        self.assertTrue(u.check_password("abcd"))

    def test_class_results_and_export(self):
        Attempt.objects.create(exam=self.exam, student=self.s1, status=Attempt.SUBMITTED, score=4, total=5)
        self.client.login(username="prof", password="x")
        r = self.client.get(reverse("class_results"), {"classe": self.c1.id})
        self.assertContains(r, "s1")
        r = self.client.get(reverse("class_results"), {"classe": self.c1.id, "export": "xlsx"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("spreadsheetml", r["Content-Type"])

    def test_teacher_adds_question_with_image(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (10, 10), "red").save(buf, "PNG")
        img = SimpleUploadedFile("fig.png", buf.getvalue(), content_type="image/png")
        self.client.login(username="prof", password="x")
        with self.settings(MEDIA_ROOT=self._tmp()):
            r = self.client.post(reverse("question_add", args=[self.exam.id]), {
                "text": "مع صورة", "image": img, "points": "1.5", "correct_answer": "C",
                "choice_A": "a", "choice_B": "b", "choice_C": "c", "choice_D": "",
            })
            self.assertEqual(r.status_code, 302)
            q = self.exam.questions.get(text="مع صورة")
            self.assertTrue(q.image.name.startswith("questions/"))
            self.assertEqual(q.choices.count(), 3)

    def _tmp(self):
        import tempfile
        d = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, d, True)
        return d


class AttemptReportTests(TestCase):
    """تقرير التلميذ: المستوى، مؤشرات العشوائية، المحاور."""

    def setUp(self):
        from datetime import timedelta
        from django.utils import timezone
        from .models import Answer, Attempt, Choice, Classe, Exam, Question, Subject, User
        self.tz, self.td = timezone, timedelta
        self.Answer, self.Attempt = Answer, Attempt
        classe = Classe.objects.get(code="4AS")
        subject = Subject.objects.get(name="الرياضيات")
        self.teacher = User.objects.create_user("t_rep", password="x", role=User.TEACHER)
        self.teacher.teaching_classes.add(classe)
        self.teacher.teaching_subjects.add(subject)
        self.exam = Exam.objects.create(title="امتحان القبول في مدارس المعارف الحرة - الرياضيات", classe=classe,
                                        subject=subject, teacher=self.teacher, is_published=True)
        self.qs = []
        for i in range(40):
            lvl = "E" if i < 18 else ("M" if i < 36 else "H")
            text = f"Calcule : {i} + 3/4 =" if i % 2 else f"Le triangle ABC numéro {i} est :"
            q = Question.objects.create(exam=self.exam, text=text, correct_answer="ABCD"[i % 4],
                                        points={"E": 1, "M": 2, "H": 3}[lvl], level=lvl, order=i)
            Choice.objects.bulk_create([Choice(question=q, letter=l, text=f"{l}{i}") for l in "ABCD"])
            self.qs.append(q)

    def _attempt(self, username, pick, seconds=60):
        from .models import User
        s = User.objects.create_user(username, password="x", role=User.STUDENT, classe=self.exam.classe)
        start = self.tz.now() - self.td(minutes=90)
        a = self.Attempt.objects.create(exam=self.exam, student=s, question_order=[q.id for q in self.qs])
        self.Attempt.objects.filter(pk=a.pk).update(started_at=start)
        a.refresh_from_db()
        for i, q in enumerate(self.qs):
            self.Answer.objects.create(attempt=a, question=q, selected=pick(i, q),
                                       answered_at=start + self.td(seconds=seconds * (i + 1)))
        a.submit()
        return a

    def test_good_student(self):
        from .analysis import analyze
        a = self._attempt("good", lambda i, q: q.correct_answer if i not in (20, 30, 38) else "A")
        r = analyze(a)
        self.assertIn(r["grade"], ("جيد جدًا", "جيد"))
        self.assertEqual(r["verdict_css"], "ok")
        self.assertTrue(r["by_topic"])

    def test_random_student(self):
        from .analysis import analyze
        a = self._attempt("rnd", lambda i, q: "A", seconds=3)
        r = analyze(a)
        self.assertEqual(r["verdict_css"], "ko")
        self.assertTrue(any("الحرف A" in x for x in r["indicators"]))
        self.assertTrue(any("بسرعة" in x for x in r["indicators"]))

    def test_report_page(self):
        a = self._attempt("pg", lambda i, q: q.correct_answer if i % 3 else "B")
        self.client.login(username="t_rep", password="x")
        res = self.client.get(f"/teacher/attempts/{a.id}/report/")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "التوصيات")
        res = self.client.get(f"/teacher/exams/{self.exam.id}/results/")
        self.assertContains(res, "تقرير")
