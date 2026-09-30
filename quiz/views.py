import json
import random
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import excel
from .analysis import analyze
from .forms import ExamForm, ImportFileForm, QuestionForm, ResultsFilterForm, UserForm
from .models import Answer, Attempt, Classe, Exam, Question, Subject, User


# ---------------------------------------------------------------- helpers

def role_required(*roles):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapper(request, *args, **kwargs):
            u = request.user
            ok = (
                ("admin" in roles and u.is_admin_role)
                or ("teacher" in roles and u.is_teacher)
                or ("student" in roles and u.is_student)
            )
            if not ok:
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return wrapper
    return decorator


staff_required = role_required("admin", "teacher")
admin_required = role_required("admin")
student_required = role_required("student")


def get_managed_exam(user, exam_id):
    exam = get_object_or_404(Exam.objects.select_related("classe", "subject", "teacher"), pk=exam_id)
    if not (user.is_admin_role or exam.teacher_id == user.id):
        raise PermissionDenied
    return exam


def xlsx_response(wb, filename):
    resp = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    wb.save(resp)
    return resp


@login_required
def home(request):
    u = request.user
    if u.is_student:
        return redirect("student_dashboard")
    if u.is_admin_role:
        return redirect("admin_dashboard")
    return redirect("teacher_dashboard")


# ---------------------------------------------------------------- student

@student_required
def student_dashboard(request):
    student = request.user
    exams = (
        Exam.objects.filter(classe=student.classe, is_published=True)
        .select_related("subject", "teacher")
        .annotate(n_questions=Count("questions"))
    )
    attempts = {a.exam_id: a for a in Attempt.objects.filter(student=student)}
    available, finished, upcoming = [], [], []
    for exam in exams:
        exam.attempt = attempts.get(exam.id)
        if exam.attempt and exam.attempt.status == Attempt.SUBMITTED:
            finished.append(exam)
        elif exam.is_open_now():
            available.append(exam)
        elif exam.available_from and not exam.attempt:
            upcoming.append(exam)
    return render(request, "quiz/student_dashboard.html", {
        "available": available, "finished": finished, "upcoming": upcoming,
    })


def _student_exam(request, exam_id):
    """الامتحان يجب أن يكون لقسم التلميذ نفسه."""
    exam = get_object_or_404(Exam, pk=exam_id, is_published=True)
    if exam.classe_id != request.user.classe_id:
        raise PermissionDenied
    return exam


@student_required
def exam_intro(request, exam_id):
    exam = _student_exam(request, exam_id)
    attempt = Attempt.objects.filter(exam=exam, student=request.user).first()
    if attempt and attempt.status == Attempt.SUBMITTED:
        return redirect("attempt_result", exam_id=exam.id)
    if request.method == "POST":
        if not exam.is_open_now():
            messages.error(request, "هذا الامتحان غير متاح الآن.")
            return redirect("student_dashboard")
        if not exam.questions.exists():
            messages.error(request, "هذا الامتحان لا يحتوي على أسئلة بعد.")
            return redirect("student_dashboard")
        if attempt is None:
            order = list(exam.questions.values_list("id", flat=True))
            if exam.shuffle_questions:
                random.shuffle(order)
            Attempt.objects.create(exam=exam, student=request.user, question_order=order)
        return redirect("take_exam", exam_id=exam.id)
    return render(request, "quiz/exam_intro.html", {
        "exam": exam, "n_questions": exam.questions.count(),
        "max_violations": settings.EXAM_MAX_VIOLATIONS,
    })


def _in_progress_attempt(request, exam_id):
    exam = _student_exam(request, exam_id)
    return get_object_or_404(Attempt, exam=exam, student=request.user, status=Attempt.IN_PROGRESS)


@student_required
def take_exam(request, exam_id):
    attempt = Attempt.objects.filter(
        exam_id=exam_id, student=request.user, status=Attempt.IN_PROGRESS
    ).select_related("exam").first()
    if attempt is None:
        return redirect("exam_intro", exam_id=exam_id)
    if attempt.is_expired():
        attempt.submit(auto=True)
        return redirect("attempt_result", exam_id=exam_id)
    questions = {q.id: q for q in attempt.exam.questions.prefetch_related("choices")}
    order = [qid for qid in attempt.question_order if qid in questions]
    order += [qid for qid in questions if qid not in order]
    saved = dict(attempt.answers.values_list("question_id", "selected"))
    ordered = []
    for qid in order:
        q = questions[qid]
        q.saved = saved.get(qid, "")
        ordered.append(q)
    return render(request, "quiz/take_exam.html", {
        "attempt": attempt, "exam": attempt.exam, "questions": ordered,
        "seconds_left": attempt.seconds_left(),
        "max_violations": settings.EXAM_MAX_VIOLATIONS,
    })


@student_required
@require_POST
def save_answer(request, exam_id):
    attempt = Attempt.objects.filter(
        exam_id=exam_id, student=request.user, status=Attempt.IN_PROGRESS
    ).first()
    if attempt is None or attempt.is_expired():
        if attempt:
            attempt.submit(auto=True)
        return JsonResponse({"ok": False, "submitted": True})
    try:
        data = json.loads(request.body)
        question = Question.objects.get(pk=int(data["question"]), exam_id=exam_id)
        selected = str(data.get("selected", ""))[:1].upper()
    except (ValueError, KeyError, TypeError, Question.DoesNotExist):
        return JsonResponse({"ok": False}, status=400)
    answer, created = Answer.objects.get_or_create(attempt=attempt, question=question)
    if created or answer.selected != selected:
        if not created and answer.selected:
            answer.changes += 1
        answer.selected = selected
        answer.answered_at = timezone.now()
        answer.save()
    return JsonResponse({"ok": True})


@student_required
@require_POST
def report_violation(request, exam_id):
    attempt = Attempt.objects.filter(
        exam_id=exam_id, student=request.user, status=Attempt.IN_PROGRESS
    ).first()
    if attempt is None:
        return JsonResponse({"submitted": True})
    attempt.violations += 1
    attempt.save(update_fields=["violations"])
    if attempt.violations >= settings.EXAM_MAX_VIOLATIONS:
        attempt.submit(auto=True)
        return JsonResponse({"submitted": True, "violations": attempt.violations})
    return JsonResponse({
        "submitted": False, "violations": attempt.violations,
        "remaining": settings.EXAM_MAX_VIOLATIONS - attempt.violations,
    })


@student_required
@require_POST
def submit_exam(request, exam_id):
    attempt = Attempt.objects.filter(
        exam_id=exam_id, student=request.user, status=Attempt.IN_PROGRESS
    ).first()
    if attempt:
        # حفظ الإجابات المرسلة مع النموذج (احتياطاً إن فشل الحفظ التلقائي)
        valid_ids = set(attempt.exam.questions.values_list("id", flat=True))
        if not attempt.is_expired():
            for key, value in request.POST.items():
                if key.startswith("q_"):
                    try:
                        qid = int(key[2:])
                    except ValueError:
                        continue
                    if qid in valid_ids:
                        Answer.objects.update_or_create(
                            attempt=attempt, question_id=qid, defaults={"selected": value[:1].upper()}
                        )
        attempt.submit(auto=request.POST.get("auto") == "1")
    return redirect("attempt_result", exam_id=exam_id)


@student_required
def attempt_result(request, exam_id):
    exam = _student_exam(request, exam_id)
    attempt = get_object_or_404(Attempt, exam=exam, student=request.user, status=Attempt.SUBMITTED)
    details = []
    if exam.show_result:
        answers = dict(attempt.answers.values_list("question_id", "selected"))
        for q in exam.questions.prefetch_related("choices"):
            sel = answers.get(q.id, "")
            details.append({"q": q, "selected": sel, "correct": sel == q.correct_answer})
    return render(request, "quiz/attempt_result.html", {
        "exam": exam, "attempt": attempt, "details": details,
    })


# ---------------------------------------------------------------- teacher

@staff_required
def teacher_dashboard(request):
    u = request.user
    exams = Exam.objects.select_related("classe", "subject", "teacher").annotate(
        n_questions=Count("questions", distinct=True),
        n_attempts=Count("attempts", filter=Q(attempts__status=Attempt.SUBMITTED), distinct=True),
    )
    if not u.is_admin_role:
        exams = exams.filter(teacher=u)
    classe = request.GET.get("classe")
    if classe:
        exams = exams.filter(classe__code=classe)
    return render(request, "quiz/teacher_dashboard.html", {
        "exams": exams, "classes": u.allowed_classes(), "current_classe": classe,
        "no_assignment": u.is_teacher and not (u.teaching_classes.exists() and u.teaching_subjects.exists()),
    })


@staff_required
def exam_create(request):
    form = ExamForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        exam = form.save(commit=False)
        exam.teacher = request.user
        exam.save()
        messages.success(request, "تم إنشاء الامتحان. أضف الأسئلة الآن يدوياً أو من ملف Excel.")
        return redirect("exam_detail", exam_id=exam.id)
    return render(request, "quiz/exam_form.html", {"form": form, "subject_map": _subject_map()})


def _subject_map():
    return json.dumps({
        s.id: list(s.classes.values_list("id", flat=True)) for s in Subject.objects.prefetch_related("classes")
    })


@staff_required
def exam_edit(request, exam_id):
    exam = get_managed_exam(request.user, exam_id)
    form = ExamForm(request.POST or None, instance=exam, user=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "تم حفظ التعديلات.")
        return redirect("exam_detail", exam_id=exam.id)
    return render(request, "quiz/exam_form.html", {"form": form, "exam": exam, "subject_map": _subject_map()})


@staff_required
def exam_delete(request, exam_id):
    exam = get_managed_exam(request.user, exam_id)
    if request.method == "POST":
        exam.delete()
        messages.success(request, "تم حذف الامتحان.")
        return redirect("teacher_dashboard")
    return render(request, "quiz/confirm_delete.html", {"object": exam, "cancel_url": "exam_detail", "cancel_id": exam.id})


@staff_required
@require_POST
def exam_toggle_publish(request, exam_id):
    exam = get_managed_exam(request.user, exam_id)
    if not exam.is_published and not exam.questions.exists():
        messages.error(request, "لا يمكن نشر امتحان بدون أسئلة.")
    else:
        exam.is_published = not exam.is_published
        exam.save(update_fields=["is_published"])
        messages.success(request, "تم نشر الامتحان للتلاميذ." if exam.is_published else "تم إخفاء الامتحان.")
    return redirect("exam_detail", exam_id=exam.id)


@staff_required
def exam_detail(request, exam_id):
    exam = get_managed_exam(request.user, exam_id)
    return render(request, "quiz/exam_detail.html", {
        "exam": exam,
        "questions": exam.questions.prefetch_related("choices"),
        "import_form": ImportFileForm(),
        "question_form": QuestionForm(),
    })


@staff_required
def question_add(request, exam_id):
    exam = get_managed_exam(request.user, exam_id)
    form = QuestionForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        form.instance.exam = exam
        form.instance.order = exam.questions.count() + 1
        form.save()
        messages.success(request, "تمت إضافة السؤال.")
        if "add_another" in request.POST:
            return redirect("question_add", exam_id=exam.id)
        return redirect("exam_detail", exam_id=exam.id)
    return render(request, "quiz/question_form.html", {"form": form, "exam": exam})


@staff_required
def question_edit(request, question_id):
    question = get_object_or_404(Question, pk=question_id)
    exam = get_managed_exam(request.user, question.exam_id)
    form = QuestionForm(request.POST or None, request.FILES or None, instance=question)
    if request.method == "POST" and form.is_valid():
        if request.POST.get("remove_image") and question.image:
            question.image.delete(save=False)
            form.instance.image = None
        form.save()
        _regrade(exam)
        messages.success(request, "تم حفظ السؤال.")
        return redirect("exam_detail", exam_id=exam.id)
    return render(request, "quiz/question_form.html", {"form": form, "exam": exam, "question": question})


@staff_required
def question_delete(request, question_id):
    question = get_object_or_404(Question, pk=question_id)
    exam = get_managed_exam(request.user, question.exam_id)
    if request.method == "POST":
        question.delete()
        _regrade(exam)
        messages.success(request, "تم حذف السؤال.")
        return redirect("exam_detail", exam_id=exam.id)
    return render(request, "quiz/confirm_delete.html", {"object": question, "cancel_url": "exam_detail", "cancel_id": exam.id})


def _regrade(exam):
    """إعادة حساب نقاط المحاولات المسلّمة بعد تعديل الأسئلة أو الإجابات الصحيحة."""
    for attempt in exam.attempts.filter(status=Attempt.SUBMITTED):
        attempt.grade()
        attempt.save(update_fields=["score", "total"])


@staff_required
@require_POST
def exam_import(request, exam_id):
    exam = get_managed_exam(request.user, exam_id)
    form = ImportFileForm(request.POST, request.FILES)
    if not form.is_valid():
        for e in form.errors.get("file", []):
            messages.error(request, e)
        return redirect("exam_detail", exam_id=exam.id)
    count, errors = excel.import_questions(exam, form.cleaned_data["file"])
    if errors:
        messages.error(request, "لم يتم استيراد أي سؤال بسبب الأخطاء التالية:")
        for e in errors[:15]:
            messages.error(request, e)
    else:
        _regrade(exam)
        messages.success(request, f"تم استيراد {count} سؤال بنجاح.")
    return redirect("exam_detail", exam_id=exam.id)


@staff_required
def questions_template(request):
    return xlsx_response(excel.questions_template(), "questions_template.xlsx")


@staff_required
def exam_results(request, exam_id):
    exam = get_managed_exam(request.user, exam_id)
    attempts = {a.student_id: a for a in exam.attempts.all()}
    rows = []
    for s in exam.classe.students.filter(role=User.STUDENT, is_active=True).order_by("full_name", "username"):
        rows.append((s, attempts.get(s.id)))
    submitted = [a for a in attempts.values() if a.status == Attempt.SUBMITTED]
    avg = sum(a.score for a in submitted) / len(submitted) if submitted else None
    return render(request, "quiz/exam_results.html", {
        "exam": exam, "rows": rows, "avg": avg, "n_submitted": len(submitted),
    })


@staff_required
def attempt_report(request, attempt_id):
    attempt = get_object_or_404(Attempt.objects.select_related("exam", "student"), pk=attempt_id,
                                status=Attempt.SUBMITTED)
    get_managed_exam(request.user, attempt.exam_id)
    return render(request, "quiz/attempt_report.html", {"r": analyze(attempt)})


@staff_required
@require_POST
def attempt_reset(request, attempt_id):
    attempt = get_object_or_404(Attempt, pk=attempt_id)
    get_managed_exam(request.user, attempt.exam_id)
    exam_id = attempt.exam_id
    name = str(attempt.student)
    attempt.delete()
    messages.success(request, f"تم إلغاء محاولة {name}، ويمكنه إعادة الامتحان.")
    return redirect("exam_results", exam_id=exam_id)


@staff_required
def class_results(request):
    u = request.user
    form = ResultsFilterForm(request.GET or None, user=u)
    classe = subject = None
    exams, rows = [], []
    if form.is_valid():
        classe = form.cleaned_data["classe"]
        subject = form.cleaned_data["subject"]
    if classe:
        qs = Exam.objects.filter(classe=classe).select_related("subject").order_by("subject__name", "created_at")
        if not u.is_admin_role:
            qs = qs.filter(teacher=u)
        if subject:
            qs = qs.filter(subject=subject)
        exams = list(qs.prefetch_related("questions"))
        scores = {
            (a.student_id, a.exam_id): a.score
            for a in Attempt.objects.filter(exam__in=exams, status=Attempt.SUBMITTED)
        }
        for s in classe.students.filter(role=User.STUDENT, is_active=True).order_by("full_name", "username"):
            rows.append((s, [scores.get((s.id, e.id)) for e in exams]))
        if request.GET.get("export") == "xlsx":
            return xlsx_response(excel.results_workbook(classe, exams, rows), f"results_{classe.code}.xlsx")
    return render(request, "quiz/class_results.html", {
        "form": form, "classe": classe, "exams": exams, "rows": rows,
    })


# ---------------------------------------------------------------- admin

@admin_required
def admin_dashboard(request):
    stats = {
        "students": User.objects.filter(role=User.STUDENT).count(),
        "teachers": User.objects.filter(role=User.TEACHER).count(),
        "exams": Exam.objects.count(),
        "attempts": Attempt.objects.filter(status=Attempt.SUBMITTED).count(),
    }
    classes = Classe.objects.annotate(
        n_students=Count("students", filter=Q(students__role=User.STUDENT), distinct=True),
        n_exams=Count("exams", distinct=True),
    ).prefetch_related("subjects")
    return render(request, "quiz/admin_dashboard.html", {"stats": stats, "classes": classes})


@admin_required
def user_list(request):
    users = User.objects.select_related("classe").order_by("role", "classe__order", "full_name", "username")
    role = request.GET.get("role")
    classe = request.GET.get("classe")
    q = request.GET.get("q", "").strip()
    if role:
        users = users.filter(role=role)
    if classe:
        users = users.filter(classe__code=classe)
    if q:
        users = users.filter(Q(username__icontains=q) | Q(full_name__icontains=q))
    return render(request, "quiz/user_list.html", {
        "users": users[:500], "roles": User.ROLE_CHOICES, "classes": Classe.objects.all(),
        "current_role": role, "current_classe": classe, "q": q, "import_form": ImportFileForm(),
    })


@admin_required
def user_create(request):
    initial = {"role": request.GET.get("role", User.STUDENT)}
    form = UserForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        messages.success(request, f"تم إنشاء الحساب «{user.username}».")
        return redirect("user_list")
    return render(request, "quiz/user_form.html", {"form": form})


@admin_required
def user_edit(request, user_id):
    obj = get_object_or_404(User, pk=user_id)
    form = UserForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "تم حفظ الحساب.")
        return redirect("user_list")
    return render(request, "quiz/user_form.html", {"form": form, "obj": obj})


@admin_required
def user_delete(request, user_id):
    obj = get_object_or_404(User, pk=user_id)
    if obj == request.user:
        messages.error(request, "لا يمكنك حذف حسابك.")
        return redirect("user_list")
    if request.method == "POST":
        obj.delete()
        messages.success(request, "تم حذف الحساب.")
        return redirect("user_list")
    return render(request, "quiz/confirm_delete.html", {"object": obj, "cancel_url": "user_list"})


@admin_required
@require_POST
def students_import(request):
    form = ImportFileForm(request.POST, request.FILES)
    if not form.is_valid():
        for e in form.errors.get("file", []):
            messages.error(request, e)
        return redirect("user_list")
    created, updated, errors = excel.import_students(form.cleaned_data["file"])
    if created or updated:
        messages.success(request, f"تمت إضافة {created} تلميذ وتحديث {updated}.")
    for e in errors[:15]:
        messages.error(request, e)
    return redirect("user_list")


@admin_required
def students_template(request):
    return xlsx_response(excel.students_template(), "students_template.xlsx")
