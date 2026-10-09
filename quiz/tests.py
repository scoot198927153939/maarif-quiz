import io
import json

from django.test import TestCase, override_settings
from django.urls import reverse

from . import excel
from .models import Answer, Attempt, Choice, Classe, Exam, Question, Subject, User


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
        self.assertEqual(Classe.objects.count(), 11)
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

    def _template_file(self):
        buf = io.BytesIO()
        excel.questions_template().save(buf)
        buf.seek(0)
        buf.name = "q.xlsx"
        return buf

    def test_excel_import_replace_keeps_matching_images(self):
        old = self.exam.questions.first()
        old.text = "كم يساوي 5 + 7 ؟"
        old.image = "questions/fig.png"
        old.save()
        count, errors = excel.import_questions(self.exam, self._template_file(), replace=True)
        self.assertEqual((count, errors), (3, []))
        self.assertEqual(self.exam.questions.count(), 3)  # الأسئلة القديمة حُذفت
        q = self.exam.questions.get(text="كم يساوي 5 + 7 ؟")
        self.assertEqual(q.image.name, "questions/fig.png")
        # استيراد نفس الملف مرة ثانية لا يكرر الأسئلة
        excel.import_questions(self.exam, self._template_file(), replace=True)
        self.assertEqual(self.exam.questions.count(), 3)

    def test_import_view_replace_keeps_past_results(self):
        qs = list(self.exam.questions.all())
        a = Attempt.objects.create(exam=self.exam, student=self.s1, question_order=[q.id for q in qs])
        Answer.objects.create(attempt=a, question=qs[0], selected=qs[0].correct_answer)
        a.submit()
        old_score, old_total = a.score, a.total
        self.assertGreater(old_score, 0)
        self.client.login(username="prof", password="x")
        url = reverse("exam_import", args=[self.exam.id])
        with self.settings(BASE_DIR=self._tmp()):
            self.client.post(url, {"file": self._template_file(), "replace": "1"})
        self.assertEqual(self.exam.questions.count(), 3)  # الأسئلة القديمة لا تظهر في الامتحان
        a.refresh_from_db()
        self.assertEqual((a.score, a.total), (old_score, old_total))  # النتيجة محفوظة
        self.assertEqual(a.answers.count(), 1)
        self.assertEqual({q.id for q in a.graded_questions()}, {q.id for q in qs})
        r = self.client.get(reverse("attempt_report", args=[a.id]))
        self.assertEqual(r.status_code, 200)
        # بدون الاستبدال تُضاف الأسئلة
        self.client.post(url, {"file": self._template_file()})
        self.assertEqual(self.exam.questions.count(), 6)

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
        res = self.client.get(f"/teacher/attempts/{a.id}/report/?lang=fr")
        self.assertContains(res, "Recommandations")
        self.assertContains(res, 'dir="ltr"')
        self.assertContains(res, "Imprimer en français")

    def test_french_report_texts(self):
        from .analysis import analyze
        a = self._attempt("frr", lambda i, q: "A", seconds=3)
        r = analyze(a, lang="fr")
        self.assertEqual(r["lang"], "fr")
        self.assertEqual(r["verdict"], "Réponses probablement données au hasard")
        self.assertTrue(all("ال" not in x for x in r["recs"]))


class AttendanceTests(TestCase):
    def setUp(self):
        from .models import Section
        self.Section = Section
        self.s1 = Section.objects.get(code="1AS1")
        self.s2 = Section.objects.get(code="7SN6")
        self.admin = User.objects.create_user("boss", password="x", role=User.ADMIN)
        self.sup = User.objects.create_user("sup", password="x", role=User.SUPERVISOR)
        self.sup.supervised_sections.set([self.s1])
        self.st = User.objects.create_user("1001", password="x", role=User.STUDENT, section=self.s1, full_name="أحمد")
        self.other = User.objects.create_user("2002", password="x", role=User.STUDENT, section=self.s2)

    def _xlsx(self, rows):
        from openpyxl import Workbook
        wb = Workbook()
        for r in rows:
            wb.active.append(r)
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        buf.name = "list.xlsx"
        return buf

    def test_sections_seeded_and_linked_to_level(self):
        self.assertEqual(self.Section.objects.count(), 24)
        self.assertEqual(self.st.classe.code, "1AS")
        self.assertEqual(self.s2.classe.code, "7SN")

    def test_supervisor_only_sees_assigned_sections(self):
        self.client.login(username="sup", password="x")
        self.assertRedirects(self.client.get("/"), reverse("attendance_home"))
        r = self.client.get(reverse("attendance_home"))
        self.assertContains(r, "1AS1")
        self.assertNotContains(r, "7SN6")
        self.assertEqual(self.client.get(reverse("section_roll", args=[self.s2.id])).status_code, 403)
        self.assertEqual(self.client.get(reverse("student_file", args=[self.other.id])).status_code, 403)
        self.assertEqual(self.client.get(reverse("teacher_dashboard")).status_code, 403)
        self.assertEqual(self.client.get(reverse("user_list")).status_code, 403)

    def test_roll_call_notes_and_student_file(self):
        from .models import StudentAttendance, StudentNote
        self.client.login(username="sup", password="x")
        url = reverse("section_roll", args=[self.s1.id])
        r = self.client.post(url, {"date": "2026-10-05", "session": 1, f"s_{self.st.id}": "A", f"n_{self.st.id}": "لم يحضر الواجب"})
        self.assertEqual(r.status_code, 302)
        self.client.post(url, {"date": "2026-10-06", "session": 2, f"s_{self.st.id}": "L"})
        self.client.post(url, {"date": "2026-10-06", "session": 2, f"s_{self.st.id}": "L"})  # إعادة الحفظ لا تكرر
        self.client.post(url, {"date": "2026-10-06", "session": 3, f"s_{self.st.id}": "A"})
        self.assertEqual(StudentAttendance.objects.filter(student=self.st).count(), 3)
        r = self.client.get(url + "?date=2026-10-06&session=1")
        self.assertContains(r, "الحصة 2: متأخر")
        self.assertEqual(StudentNote.objects.get().text, "لم يحضر الواجب")
        r = self.client.get(reverse("section_report", args=[self.s1.id]) + "?from=2026-10-05&to=2026-10-06")
        self.assertContains(r, "غائب")
        self.assertContains(r, "لم يحضر الواجب")
        r = self.client.get(reverse("student_file", args=[self.st.id]))
        self.assertContains(r, "لم يحضر الواجب")
        self.assertEqual(r.context["totals"], {"present": 0, "absent": 2, "late": 1})

    def test_roster_import_keeps_history(self):
        from .models import StudentAttendance
        StudentAttendance.objects.create(student=self.st, date="2026-10-01", status="A")
        self.client.login(username="boss", password="x")
        f = self._xlsx([
            ["رقم قيد الطالب", "القسم", "اسم الطالب", "رقم هاتف الوكيل", "رقم الواتساب", "رقم هاتف الوكيل2"],
            [1001, "1AS2", "أحمد محمد", 22000001, 22000001, None],
            [3003, "7sn6", "مريم", "33000003", "", ""],
        ])
        self.client.post(reverse("roster_import"), {"file": f})
        self.st.refresh_from_db()
        self.assertEqual(self.st.section.code, "1AS2")
        self.assertEqual(self.st.matricule, "1001")
        self.assertEqual(self.st.guardian_phone, "22000001")
        self.assertEqual(self.st.attendance.count(), 1)
        new = User.objects.get(matricule="3003")
        self.assertEqual((new.section.code, new.classe.code, new.username), ("7SN6", "7SN", "3003"))
        self.assertTrue(new.check_password("3003"))
        # إعادة الاستيراد تحدّث ولا تكرر
        self.client.post(reverse("roster_import"), {"file": self._xlsx([[1001, "1AS1", "أحمد", "", "", ""]])})
        self.assertEqual(User.objects.filter(matricule="1001").count(), 1)
        self.assertEqual(self.st.attendance.count(), 1)

    def test_roster_import_detects_columns_in_any_order(self):
        self.client.login(username="boss", password="x")
        f = self._xlsx([
            ["لائحة التلاميذ 2026"],
            ["الرقم", "الإسم الكامل", "الفصل", "الواتساب", "هاتف الولي"],
            [4001, "زيدان محمد العربي", "1AS 1", 46000001, 22000001],
            [4002, "اسماء احمدو", "7sn2", None, 22000002],
        ])
        r = self.client.post(reverse("roster_import"), {"file": f}, follow=True)
        self.assertNotContains(r, "غير موجود")
        u = User.objects.get(matricule="4001")
        self.assertEqual((u.full_name, u.section.code, u.whatsapp, u.guardian_phone),
                         ("زيدان محمد العربي", "1AS1", "46000001", "22000001"))
        self.assertEqual(User.objects.get(matricule="4002").section.code, "7SN2")
        # بدون عناوين وبترتيب مختلف
        f = self._xlsx([[5001, "مريم سيدي", "5MA2", 33000001], [5002, "محمد", "6SN1", 33000002]])
        self.client.post(reverse("roster_import"), {"file": f})
        self.assertEqual(User.objects.get(matricule="5001").section.code, "5MA2")

    def test_roster_import_rejects_unknown_section(self):
        self.client.login(username="boss", password="x")
        r = self.client.post(reverse("roster_import"), {"file": self._xlsx([[5, "9XX1", "x"]])}, follow=True)
        self.assertContains(r, "غير موجود")
        self.assertFalse(User.objects.filter(matricule="5").exists())

    def test_teachers_import_and_monthly(self):
        from .models import Teacher, TeacherAttendance
        self.client.login(username="boss", password="x")
        self.client.post(reverse("teachers_import"), {"file": self._xlsx([["اسم الأستاذ", "المادة"], ["محمد", "الرياضيات"], ["Aicha", "الفرنسية"]])})
        self.assertEqual(Teacher.objects.count(), 2)
        t = Teacher.objects.get(name="محمد")
        self.client.logout()
        self.client.login(username="sup", password="x")
        self.client.post(reverse("teacher_roll"), {"date": "2026-10-05", "session": 1, f"s_{t.id}": "A", f"c_{t.id}": self.s1.id})
        self.client.post(reverse("teacher_roll"), {"date": "2026-10-06", "session": 1, f"s_{t.id}": "P", f"c_{t.id}": self.s1.id})
        self.client.post(reverse("teacher_roll"), {"date": "2026-10-06", "session": 3, f"s_{t.id}": "P", f"c_{t.id}": self.s2.id})
        self.assertEqual(
            list(TeacherAttendance.objects.filter(teacher=t, date="2026-10-06").values_list("session", "section__code")),
            [(1, "1AS1"), (3, "7SN6")],
        )
        # «لا حصة» يلغي التسجيل، واليوم التالي يبدأ فارغاً
        self.client.post(reverse("teacher_roll"), {"date": "2026-10-06", "session": 3, f"s_{t.id}": ""})
        self.assertEqual(TeacherAttendance.objects.filter(teacher=t, date="2026-10-06").count(), 1)
        r = self.client.get(reverse("teacher_roll") + "?date=2026-10-07&session=1")
        row = [x for x in r.context["rows"] if x["teacher"].id == t.id][0]
        self.assertEqual((row["status"], row["section"]), ("", None))
        self.client.logout()
        self.client.login(username="boss", password="x")
        self.client.post(reverse("teachers_import"), {"file": self._xlsx([["محمد", "الفيزياء"]])})
        self.assertEqual(TeacherAttendance.objects.filter(teacher=t).count(), 2)
        self.client.logout()
        self.client.login(username="sup", password="x")
        r = self.client.get(reverse("teacher_monthly") + "?month=2026-10")
        row = [x for x in r.context["teachers"] if x.id == t.id][0]
        self.assertEqual((row.n_present, row.n_absent, row.subject), (1, 1, "الفيزياء"))
        self.assertEqual(row.month_sections, ["1AS1"])
        self.assertEqual(self.client.get(reverse("teacher_file", args=[t.id]) + "?month=2026-10").status_code, 200)
        # المراقب لا يستورد
        self.assertEqual(self.client.post(reverse("teachers_import")).status_code, 403)

    def test_students_list_and_export(self):
        self.st.matricule, self.st.guardian_phone = "1001", "22000001"
        self.st.save()
        self.client.login(username="sup", password="x")
        r = self.client.get(reverse("students_list"))
        self.assertContains(r, "22000001")
        self.assertNotContains(r, "2002")  # تلميذ قسم لا يراقبه
        r = self.client.get(reverse("students_list") + "?section=1AS1&export=xlsx")
        self.assertEqual(r.status_code, 200)
        from openpyxl import load_workbook
        rows = list(load_workbook(io.BytesIO(r.content)).active.iter_rows(values_only=True))
        self.assertEqual(rows[1][1:5], ("1001", "أحمد", "1AS1", "22000001"))
        self.client.logout()
        self.client.login(username="boss", password="x")
        self.assertContains(self.client.get(reverse("students_list")), "2002")

    def test_admin_creates_supervisor(self):
        self.client.login(username="boss", password="x")
        r = self.client.post(reverse("user_create"), {
            "username": "mourakib", "full_name": "م", "role": "supervisor", "password": "p",
            "supervised_sections": [self.s1.id, self.s2.id], "is_active": "on",
        })
        self.assertEqual(r.status_code, 302)
        u = User.objects.get(username="mourakib")
        self.assertEqual(u.supervised_sections.count(), 2)
        for name in ["user_create", "attendance_home", "teacher_roll", "teacher_monthly"]:
            self.assertEqual(self.client.get(reverse(name)).status_code, 200)
