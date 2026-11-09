"""الاختبارات والامتحانات: إدخال نقاط التلاميذ (من 20) وملاحظاتهم، لكل قسم ولكل اختبار ولكل مادة.
المشرف يرى كل الأقسام، المراقب أقسامه، والأستاذ أقسام المستويات التي يدرّسها."""
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .models import (
    GRADE_MAX, GRADE_SUBJECT_NAMES, STUDENT_ORDER, Grade, GradeAssessment, Section, User, grade_subjects,
)
from .views import admin_required, role_required

grades_required = role_required("admin", "supervisor", "teacher")


def _section(user, section_id):
    section = get_object_or_404(Section.objects.select_related("classe"), pk=section_id)
    if not user.grade_sections().filter(pk=section.pk).exists():
        raise PermissionDenied
    return section


def _assessment(request):
    a = GradeAssessment.objects.filter(pk=request.GET.get("a") or 0).first()
    return a or GradeAssessment.objects.first()


def _students(section):
    return list(User.objects.filter(role=User.STUDENT, section=section, is_active=True).order_by(*STUDENT_ORDER))


def _filled(qs):
    """النقاط التي فيها شيء (نقطة أو ملاحظة)."""
    return qs.filter(Q(score__isnull=False) | ~Q(note=""))


@grades_required
def grades_home(request):
    if request.method == "POST" and request.user.is_admin_role:
        name = " ".join(request.POST.get("name", "").split())[:60]
        if name:
            a, created = GradeAssessment.objects.get_or_create(
                name=name, defaults={"order": GradeAssessment.objects.count() + 1})
            if created:
                messages.success(request, f"تمت إضافة «{a}».")
            else:
                messages.error(request, f"«{a}» موجود من قبل.")
        return redirect("grades_home")
    assessment = _assessment(request)
    sections = list(request.user.grade_sections().select_related("classe").annotate(
        n_students=Count("students", filter=Q(students__role=User.STUDENT, students__is_active=True), distinct=True)))
    done = {}
    if assessment:
        for sec, subj in (_filled(Grade.objects.filter(assessment=assessment, section__in=sections))
                          .values_list("section", "subject").distinct()):
            done.setdefault(sec, set()).add(subj)
    levels = {}
    for s in sections:
        subjects = grade_subjects(s.classe.code)
        s.n_subjects = len(subjects)
        s.n_done = len(done.get(s.id, set()) & {c for c, _ in subjects})
        levels.setdefault(s.classe, []).append(s)
    return render(request, "quiz/grades/home.html", {
        "levels": levels.items(), "assessment": assessment, "assessments": GradeAssessment.objects.all(),
    })


@grades_required
def grades_section(request, section_id):
    section = _section(request.user, section_id)
    assessment = _assessment(request)
    students = _students(section)
    counts = dict(_filled(Grade.objects.filter(assessment=assessment, student__in=students))
                  .values_list("subject").annotate(n=Count("id")))
    subjects = [{"code": c, "name": n, "n": counts.get(c, 0)} for c, n in grade_subjects(section.classe.code)]
    return render(request, "quiz/grades/section.html", {
        "section": section, "assessment": assessment, "assessments": GradeAssessment.objects.all(),
        "subjects": subjects, "n_students": len(students),
        "n_done": sum(1 for s in subjects if s["n"]),
    })


def _parse_score(raw):
    """يعيد (النقطة أو None، رسالة الخطأ أو None)."""
    raw = (raw or "").strip().replace("،", ".").replace(",", ".")
    if not raw:
        return None, None
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return None, "النقطة يجب أن تكون رقماً"
    if value < 0 or value > GRADE_MAX:
        return None, f"النقطة بين 0 و {GRADE_MAX}"
    return value.quantize(Decimal("0.01")), None


@grades_required
def grades_entry(request, section_id, assessment_id, subject):
    section = _section(request.user, section_id)
    assessment = get_object_or_404(GradeAssessment, pk=assessment_id)
    subjects = dict(grade_subjects(section.classe.code))
    if subject not in subjects:
        raise PermissionDenied
    students = _students(section)
    existing = {g.student_id: g for g in Grade.objects.filter(assessment=assessment, subject=subject,
                                                               student__in=students)}
    errors, posted = {}, {}
    if request.method == "POST":
        changes = []
        for st in students:
            key = f"s_{st.id}"
            if key not in request.POST:  # سطر لم يُفتح للتعديل: يبقى كما هو
                continue
            score, err = _parse_score(request.POST.get(key))
            note = " ".join(request.POST.get(f"n_{st.id}", "").split())[:255]
            posted[st.id] = {"score": request.POST.get(key, ""), "note": note}
            if err:
                errors[st.id] = err
            changes.append((st, score, note))
        if errors:
            messages.error(request, f"لم يُحفظ شيء: صحّح {len(errors)} نقطة (يجب أن تكون بين 0 و {GRADE_MAX}).")
        else:
            saved = 0
            for st, score, note in changes:
                if score is None and not note:
                    Grade.objects.filter(assessment=assessment, subject=subject, student=st).delete()
                    continue
                Grade.objects.update_or_create(
                    assessment=assessment, subject=subject, student=st,
                    defaults={"score": score, "note": note, "section": section, "updated_by": request.user})
                saved += 1
            messages.success(request, f"تم حفظ نتائج {subjects[subject]} · {assessment} · {section} ({saved} تلميذ).")
            return redirect("grades_entry", section_id=section.id, assessment_id=assessment.id, subject=subject)
    rows = []
    for st in students:
        g = existing.get(st.id)
        p = posted.get(st.id)
        rows.append({
            "student": st, "grade": g, "error": errors.get(st.id),
            "score": p["score"] if p else (_fmt(g.score) if g else ""),
            "note": p["note"] if p else (g.note if g else ""),
            "locked": bool(g) and not p,  # المحفوظ يُعرض مقفلاً حتى يُضغط «تعديل»
        })
    scores = [g.score for g in existing.values() if g.score is not None]
    return render(request, "quiz/grades/entry.html", {
        "section": section, "assessment": assessment, "subject": subject, "subject_name": subjects[subject],
        "rows": rows, "max": GRADE_MAX, "n_saved": len(existing),
        "average": _fmt(sum(scores) / len(scores)) if scores else "",
        "subjects": [(c, n) for c, n in subjects.items()],
    })


def _fmt(value):
    """12.50 ← 12.5، و 14.00 ← 14."""
    if value is None:
        return ""
    value = Decimal(value).quantize(Decimal("0.01"))
    return format(value.normalize(), "f")


@admin_required
@require_POST
def grades_assessment_delete(request, pk):
    a = get_object_or_404(GradeAssessment, pk=pk)
    if a.grades.exists():
        messages.error(request, f"لا يمكن حذف «{a}» لأن فيه نقاطاً مسجّلة.")
    else:
        a.delete()
        messages.success(request, f"تم حذف «{a}».")
    return redirect(reverse("grades_home"))


__all__ = ["grades_home", "grades_section", "grades_entry", "grades_assessment_delete", "GRADE_SUBJECT_NAMES"]
