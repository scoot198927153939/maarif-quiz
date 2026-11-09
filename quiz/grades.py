"""الاختبارات والامتحانات: إدخال نقاط التلاميذ (من 20) وملاحظاتهم، لكل قسم ولكل اختبار ولكل مادة.
المشرف يرى كل الأقسام، المراقب أقسامه، والأستاذ أقسام المستويات التي يدرّسها."""
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from .models import (
    GRADE_MAX, GRADE_SUBJECT_NAMES, STUDENT_ORDER, Grade, GradeAssessment, Section, User, grade_subjects,
)
from .excel import HEADER_FILL, HEADER_FONT
from .views import admin_required, role_required, xlsx_response

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


SENDER = "مدارس المعارف الحرة\nمسؤول الشؤون الطلابية: محمد اسحاق"


def results_message(student, section, assessment, lines):
    """نص رسالة واتساب للوكيل: نتائج التلميذ في كل المواد التي لها نتيجة."""
    body = "\n".join(lines)
    return (f"السلام عليكم ورحمة الله وبركاته\n"
            f"نود اطلاعكم على نتائج {assessment.name} للتلميذ(ة): {student.full_name or student.username}\n"
            f"القسم: {section.code}    رقم القيد: {student.matricule or ''}\n\n"
            f"المادة: النتيجة\n{body}\n\n{SENDER}")


@grades_required
def grades_whatsapp(request, section_id):
    """إرسال النتائج للوكلاء عبر واتساب: رسالة جاهزة لكل تلميذ، تُفتح واحدة بعد الأخرى."""
    from urllib.parse import quote
    from .models import wa_link_for
    section = _section(request.user, section_id)
    assessment = _assessment(request)
    students = _students(section)
    subjects = grade_subjects(section.classe.code)
    grades = {(g.student_id, g.subject): g for g in _filled(Grade.objects.filter(assessment=assessment,
                                                                                  student__in=students))}
    rows = []
    for st in students:
        lines = []
        for code, name in subjects:
            g = grades.get((st.id, code))
            if g:
                score = f"{_fmt(g.score)} / {GRADE_MAX}" if g.score is not None else "—"
                lines.append(f"• {name}: {score}" + (f" ({g.note})" if g.note else ""))
        link = st.wa_link or wa_link_for(st.guardian_phone)
        text = results_message(st, section, assessment, lines) if lines else ""
        rows.append({"student": st, "n": len(lines), "link": f"{link}?text={quote(text)}" if link and text else "",
                     "phone": st.wa_number or st.guardian_phone, "text": text})
    return render(request, "quiz/grades/whatsapp.html", {
        "section": section, "assessment": assessment, "rows": rows,
        "n_ready": sum(1 for r in rows if r["link"]), "n_subjects": len(subjects),
    })


@grades_required
def grades_sheet(request, section_id):
    """ورقة فارغة للطباعة يكتب فيها الأستاذ النتائج بيده: لمادة واحدة (?subject=MATH) أو لكل المواد (صفحة لكل مادة)."""
    section = _section(request.user, section_id)
    assessment = _assessment(request)
    subjects = grade_subjects(section.classe.code)
    code = request.GET.get("subject")
    if code:
        subjects = [(c, n) for c, n in subjects if c == code]
        if not subjects:
            raise PermissionDenied
    return render(request, "quiz/grades/sheet.html", {
        "section": section, "assessment": assessment, "subjects": subjects, "students": _students(section),
        "max": GRADE_MAX,
    })


@grades_required
def grades_export(request, section_id):
    """ملف Excel لنتائج القسم في اختبار: ورقة «كل المواد» (تلميذ × مادة + المعدل والترتيب)،
    ثم ورقة لكل مادة فيها النتيجة والملاحظة."""
    section = _section(request.user, section_id)
    assessment = _assessment(request)
    students = _students(section)
    subjects = grade_subjects(section.classe.code)
    grades = {(g.student_id, g.subject): g for g in Grade.objects.filter(assessment=assessment, student__in=students)}

    thin = Side(style="thin", color="B9C7C2")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    low_font = Font(color="B42318", bold=True)
    zebra = PatternFill("solid", fgColor="F2F7F5")

    def title(ws, text, ncols):
        ws.sheet_view.rightToLeft = True
        ws.append([text])
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncols)
        ws["A1"].font = Font(bold=True, size=14, color="1F6F5C")
        ws["A1"].alignment = Alignment(horizontal="center")
        ws.row_dimensions[1].height = 24

    def style_table(ws, ncols, score_cols):
        for cell in ws[2]:
            cell.fill, cell.font, cell.alignment, cell.border = HEADER_FILL, HEADER_FONT, center, border
        ws.row_dimensions[2].height = 34
        for r in range(3, ws.max_row + 1):
            for c in range(1, ncols + 1):
                cell = ws.cell(row=r, column=c)
                cell.border = border
                if c != 3:
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                if r % 2 == 0:
                    cell.fill = zebra
                if c in score_cols and isinstance(cell.value, (int, float)) and cell.value < GRADE_MAX / 2:
                    cell.font = low_font
        ws.freeze_panes = "D3"

    def num(value):
        return float(value) if value is not None else None

    wb = Workbook()
    ws = wb.active
    ws.title = "كل المواد"
    head = ["#", "رقم القيد", "اسم التلميذ"] + [n for _, n in subjects] + ["المعدل", "الترتيب"]
    title(ws, f"نتائج {assessment} · القسم {section.code}", len(head))
    ws.append(head)
    rows = []
    for st in students:
        scores = [num(grades[(st.id, c)].score) if (st.id, c) in grades else None for c, _ in subjects]
        got = [x for x in scores if x is not None]
        rows.append((st, scores, round(sum(got) / len(got), 2) if got else None))
    ranked = sorted((r[2] for r in rows if r[2] is not None), reverse=True)
    for i, (st, scores, avg) in enumerate(rows, start=1):
        ws.append([i, st.matricule, st.full_name or st.username] + scores
                  + [avg, ranked.index(avg) + 1 if avg is not None else None])
    # سطر معدل كل مادة
    avgs = []
    for k in range(len(subjects)):
        col = [r[1][k] for r in rows if r[1][k] is not None]
        avgs.append(round(sum(col) / len(col), 2) if col else None)
    ws.append(["", "", "معدل القسم"] + avgs)
    n = len(head)
    style_table(ws, n, set(range(4, 4 + len(subjects) + 1)))
    for cell in ws[ws.max_row]:
        cell.font = Font(bold=True)
    for c in range(1, n + 1):
        letter = ws.cell(row=2, column=c).column_letter
        ws.column_dimensions[letter].width = [5, 12, 30][c - 1] if c <= 3 else 13
    ws.cell(row=ws.max_row + 2, column=1, value="المعدل = متوسط المواد التي لها نتيجة، بدون معاملات.").font = Font(
        italic=True, color="666666")

    for code, name in subjects:
        sh = wb.create_sheet(name[:31])
        title(sh, f"{name} · {assessment} · {section.code}", 5)
        sh.append(["#", "رقم القيد", "اسم التلميذ", f"النتيجة / {GRADE_MAX}", "الملاحظة"])
        for i, st in enumerate(students, start=1):
            g = grades.get((st.id, code))
            sh.append([i, st.matricule, st.full_name or st.username, num(g.score) if g else None, g.note if g else ""])
        style_table(sh, 5, {4})
        for letter, w in zip("ABCDE", [5, 12, 30, 12, 40]):
            sh.column_dimensions[letter].width = w

    return xlsx_response(wb, f"notes_{section.code}_{assessment.id}.xlsx")


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


__all__ = ["grades_whatsapp", "results_message", "grades_sheet", "grades_home", "grades_section", "grades_entry", "grades_export", "grades_assessment_delete", "GRADE_SUBJECT_NAMES"]
