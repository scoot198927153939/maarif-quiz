"""الحضور والغياب والملاحظات اليومية للتلاميذ، وحضور الأساتذة (دور المراقب)."""
import datetime

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import excel
from .forms import ImportFileForm
from .models import (
    ABSENT, ATTENDANCE_CHOICES, LATE, PRESENT, SESSION_CHOICES, SESSION_TIMES, Section, StudentAttendance,
    StudentNote, Teacher, TeacherAttendance, User,
)
from .views import admin_required, role_required, xlsx_response

supervisor_required = role_required("admin", "supervisor")

MONTHS = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
          "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
WEEKDAYS = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
STATUS_LABELS = dict(ATTENDANCE_CHOICES)


def _date(value, default=None):
    try:
        return datetime.date.fromisoformat(value)
    except (TypeError, ValueError):
        return default or timezone.localdate()


def _current_session():
    now = timezone.localtime().strftime("%H:%M")
    for n, (start, end) in SESSION_TIMES.items():
        if now < end:
            return n
    return SESSION_CHOICES[-1][0]


def _session(request):
    value = request.POST.get("session") or request.GET.get("session")
    if value and value.isdigit() and int(value) in SESSION_TIMES:
        return int(value)
    return _current_session()


def _sessions(taken=()):
    return [{"n": n, "label": label, "start": SESSION_TIMES[n][0], "end": SESSION_TIMES[n][1], "taken": n in taken}
            for n, label in SESSION_CHOICES]


SESSION_LABELS = dict(SESSION_CHOICES)


def _month(value):
    """يعيد (أول يوم في الشهر، أول يوم في الشهر التالي)."""
    try:
        y, m = (int(x) for x in value.split("-"))
        start = datetime.date(y, m, 1)
    except (AttributeError, ValueError):
        start = timezone.localdate().replace(day=1)
    end = (start + datetime.timedelta(days=32)).replace(day=1)
    return start, end


def _day_label(d):
    return f"{WEEKDAYS[d.weekday()]} {d.day} {MONTHS[d.month - 1]} {d.year}"


def _month_nav(start):
    prev = (start - datetime.timedelta(days=1)).replace(day=1)
    nxt = (start + datetime.timedelta(days=32)).replace(day=1)
    return {
        "month": start.strftime("%Y-%m"), "month_label": f"{MONTHS[start.month - 1]} {start.year}",
        "prev_month": prev.strftime("%Y-%m"), "next_month": nxt.strftime("%Y-%m"),
    }


def _get_section(user, section_id):
    section = get_object_or_404(Section, pk=section_id)
    if not user.allowed_sections().filter(pk=section.pk).exists():
        raise PermissionDenied
    return section


def _get_student(user, student_id):
    student = get_object_or_404(User.objects.select_related("section"), pk=student_id, role=User.STUDENT)
    if not user.is_admin_role and not user.allowed_sections().filter(pk=student.section_id).exists():
        raise PermissionDenied
    return student


def _counts(qs):
    c = dict(qs.values_list("status").annotate(n=Count("id")))
    return {"present": c.get(PRESENT, 0), "absent": c.get(ABSENT, 0), "late": c.get(LATE, 0)}


# ---------------------------------------------------------------- الصفحة الرئيسية

@supervisor_required
def attendance_home(request):
    today = timezone.localdate()
    sections = request.user.allowed_sections().annotate(
        n_students=Count("students", filter=Q(students__role=User.STUDENT, students__is_active=True), distinct=True),
    )
    day = StudentAttendance.objects.filter(date=today)
    absent = dict(day.filter(status=ABSENT).values_list("student__section").annotate(n=Count("id")))
    late = dict(day.filter(status=LATE).values_list("student__section").annotate(n=Count("id")))
    taken = {}
    for sec, n in day.order_by().values_list("student__section", "session").distinct():
        taken.setdefault(sec, set()).add(n)
    for s in sections:
        s.absent_today, s.late_today = absent.get(s.id, 0), late.get(s.id, 0)
        s.sessions = _sessions(taken.get(s.id, ()))
        s.taken_today = bool(taken.get(s.id))
    return render(request, "quiz/attendance/home.html", {
        "sections": sections, "today": today, "today_label": _day_label(today), "current_session": _current_session(),
        "import_form": ImportFileForm(),
        "n_teachers": Teacher.objects.filter(is_active=True).count(),
        "teachers_taken": TeacherAttendance.objects.filter(date=today).exists(),
    })


# ---------------------------------------------------------------- غياب القسم

@supervisor_required
def section_roll(request, section_id):
    section = _get_section(request.user, section_id)
    day = _date(request.POST.get("date") or request.GET.get("date"))
    session = _session(request)
    students = list(section.students.filter(role=User.STUDENT, is_active=True).order_by("full_name", "username"))
    here = f"{reverse('section_roll', args=[section.id])}?date={day.isoformat()}&session={session}"

    if request.method == "POST":
        if day > timezone.localdate():
            messages.error(request, "لا يمكن تسجيل الغياب ليوم لم يأتِ بعد.")
            return redirect(here)
        n_notes = 0
        for st in students:
            status = request.POST.get(f"s_{st.id}")
            if status in STATUS_LABELS:
                StudentAttendance.objects.update_or_create(
                    student=st, date=day, session=session,
                    defaults={"status": status, "section": section, "recorded_by": request.user},
                )
            note = request.POST.get(f"n_{st.id}", "").strip()
            if note:
                StudentNote.objects.create(student=st, date=day, text=note, author=request.user)
                n_notes += 1
        msg = f"تم حفظ غياب {section} في {SESSION_LABELS[session]} ليوم {_day_label(day)}."
        if n_notes:
            msg += f" وأُضيفت {n_notes} ملاحظة."
        messages.success(request, msg)
        return redirect(here)

    day_records = StudentAttendance.objects.filter(student__in=students, date=day)
    records = {a.student_id: a.status for a in day_records if a.session == session}
    others = {}
    for a in day_records:
        if a.session != session and a.status != PRESENT:
            others.setdefault(a.student_id, []).append(f"{SESSION_LABELS[a.session]}: {a.get_status_display()}")
    notes = {}
    for n in StudentNote.objects.filter(student__in=students, date=day).order_by("created_at"):
        notes.setdefault(n.student_id, []).append(n)
    rows = [{"student": st, "status": records.get(st.id, PRESENT), "notes": notes.get(st.id, []),
             "others": others.get(st.id, [])} for st in students]
    return render(request, "quiz/attendance/section_roll.html", {
        "section": section, "rows": rows, "day": day, "day_label": _day_label(day),
        "session": session, "session_label": SESSION_LABELS[session],
        "sessions": _sessions({a.session for a in day_records}),
        "taken": bool(records), "choices": ATTENDANCE_CHOICES,
        "prev_day": (day - datetime.timedelta(days=1)).isoformat(),
        "next_day": (day + datetime.timedelta(days=1)).isoformat(),
        "is_future": day > timezone.localdate(),
        "summary": {
            "absent": [r["student"] for r in rows if records.get(r["student"].id) == ABSENT],
            "late": [r["student"] for r in rows if records.get(r["student"].id) == LATE],
        },
    })


@supervisor_required
def section_report(request, section_id):
    """لائحة الغياب والتأخر والملاحظات للقسم خلال فترة (يوم واحد افتراضياً)."""
    section = _get_section(request.user, section_id)
    today = timezone.localdate()
    start = _date(request.GET.get("from"), today)
    end = _date(request.GET.get("to"), start)
    if end < start:
        start, end = end, start
    students = section.students.filter(role=User.STUDENT)
    events = (
        StudentAttendance.objects.filter(student__in=students, date__range=(start, end))
        .exclude(status=PRESENT).select_related("student").order_by("-date", "session", "student__full_name")
    )
    notes = (
        StudentNote.objects.filter(student__in=students, date__range=(start, end))
        .select_related("student", "author").order_by("-date", "student__full_name")
    )
    totals = (
        students.annotate(
            n_absent=Count("attendance", filter=Q(attendance__status=ABSENT, attendance__date__range=(start, end))),
            n_late=Count("attendance", filter=Q(attendance__status=LATE, attendance__date__range=(start, end))),
        ).filter(Q(n_absent__gt=0) | Q(n_late__gt=0)).order_by("-n_absent", "-n_late", "full_name")
    )
    return render(request, "quiz/attendance/section_report.html", {
        "section": section, "start": start, "end": end, "events": events, "notes": notes, "totals": totals,
        "single_day": start == end, "start_label": _day_label(start), "end_label": _day_label(end),
    })


# ---------------------------------------------------------------- ملف التلميذ

@supervisor_required
def student_file(request, student_id):
    student = _get_student(request.user, student_id)
    if request.method == "POST":
        text = request.POST.get("text", "").strip()
        if text:
            StudentNote.objects.create(
                student=student, date=_date(request.POST.get("date")), text=text, author=request.user,
            )
            messages.success(request, "تمت إضافة الملاحظة.")
        return redirect("student_file", student_id=student.id)
    attendance = student.attendance.all()
    history = {}
    for a in attendance.exclude(status=PRESENT).order_by("session"):
        history.setdefault(a.date, {"date": a.date, "events": [], "notes": []})["events"].append(a)
    for n in student.notes.select_related("author"):
        history.setdefault(n.date, {"date": n.date, "events": [], "notes": []})["notes"].append(n)
    days = sorted(history.values(), key=lambda h: h["date"], reverse=True)
    for d in days:
        d["label"] = _day_label(d["date"])
        d["notes"].sort(key=lambda n: n.created_at)
    month_start = timezone.localdate().replace(day=1)
    return render(request, "quiz/attendance/student_file.html", {
        "student": student, "totals": _counts(attendance),
        "month_totals": _counts(attendance.filter(date__gte=month_start)),
        "month_label": f"{MONTHS[month_start.month - 1]} {month_start.year}",
        "days": days, "n_notes": student.notes.count(), "today": timezone.localdate(),
        "whatsapp_link": _whatsapp_link(student.whatsapp),
    })


def _whatsapp_link(number):
    digits = "".join(ch for ch in number if ch.isdigit())
    if not digits:
        return ""
    if len(digits) == 8:  # رقم موريتاني بدون رمز الدولة
        digits = "222" + digits
    return f"https://wa.me/{digits}"


@supervisor_required
@require_POST
def note_delete(request, note_id):
    note = get_object_or_404(StudentNote, pk=note_id)
    _get_student(request.user, note.student_id)
    if not (request.user.is_admin_role or note.author_id == request.user.id):
        raise PermissionDenied
    note.delete()
    messages.success(request, "تم حذف الملاحظة.")
    return redirect(request.POST.get("next") or reverse("student_file", args=[note.student_id]))


# ---------------------------------------------------------------- حضور الأساتذة

@supervisor_required
def teacher_roll(request):
    day = _date(request.POST.get("date") or request.GET.get("date"))
    session = _session(request)
    teachers = list(Teacher.objects.filter(is_active=True))
    here = f"{reverse('teacher_roll')}?date={day.isoformat()}&session={session}"
    if request.method == "POST":
        if "add_teacher" in request.POST:
            name = " ".join(request.POST.get("name", "").split())[:150]
            if name:
                t, created = Teacher.objects.get_or_create(
                    name=name, defaults={"subject": request.POST.get("subject", "").strip()[:100]},
                )
                if not created and not t.is_active:
                    t.is_active = True
                    t.save()
                messages.success(request, f"تمت إضافة الأستاذ «{t}»." if created else f"الأستاذ «{t}» موجود في اللائحة.")
            return redirect(here)
        if day > timezone.localdate():
            messages.error(request, "لا يمكن تسجيل الحضور ليوم لم يأتِ بعد.")
            return redirect(here)
        sections = {str(s.id): s for s in Section.objects.all()}
        missing, saved = [], 0
        for t in teachers:
            status = request.POST.get(f"s_{t.id}", "")
            section = sections.get(request.POST.get(f"c_{t.id}", ""))
            if status in STATUS_LABELS:
                TeacherAttendance.objects.update_or_create(
                    teacher=t, date=day, session=session,
                    defaults={"status": status, "section": section, "recorded_by": request.user,
                              "note": request.POST.get(f"n_{t.id}", "").strip()[:255]},
                )
                saved += 1
                if section is None:
                    missing.append(t.name)
            else:  # «لا حصة»: يُلغى أي تسجيل سابق لهذه الحصة
                TeacherAttendance.objects.filter(teacher=t, date=day, session=session).delete()
        messages.success(request, f"تم حفظ حضور {saved} أستاذ في {SESSION_LABELS[session]} ليوم {_day_label(day)}.")
        if missing:
            messages.error(request, "لم يُحدَّد القسم لـ: " + "، ".join(missing))
        return redirect(here)

    day_records = TeacherAttendance.objects.filter(date=day)
    records = {a.teacher_id: a for a in day_records if a.session == session}
    rows = []
    for t in teachers:
        rec = records.get(t.id)
        rows.append({"teacher": t, "status": rec.status if rec else "", "note": rec.note if rec else "",
                     "section": rec.section_id if rec else None})
    return render(request, "quiz/attendance/teacher_roll.html", {
        "rows": rows, "all_sections": Section.objects.all(), "day": day, "day_label": _day_label(day),
        "taken": bool(records), "session": session, "session_label": SESSION_LABELS[session],
        "sessions": _sessions({a.session for a in day_records}),
        "choices": ATTENDANCE_CHOICES, "is_future": day > timezone.localdate(),
        "prev_day": (day - datetime.timedelta(days=1)).isoformat(),
        "next_day": (day + datetime.timedelta(days=1)).isoformat(),
        "month": day.strftime("%Y-%m"),
    })


@supervisor_required
def teacher_monthly(request):
    start, end = _month(request.GET.get("month"))
    rng = Q(attendance__date__gte=start, attendance__date__lt=end)
    teachers = Teacher.objects.annotate(
        n_present=Count("attendance", filter=rng & Q(attendance__status=PRESENT)),
        n_absent=Count("attendance", filter=rng & Q(attendance__status=ABSENT)),
        n_late=Count("attendance", filter=rng & Q(attendance__status=LATE)),
    ).filter(Q(is_active=True) | Q(n_present__gt=0) | Q(n_absent__gt=0) | Q(n_late__gt=0))
    n_days = TeacherAttendance.objects.filter(date__gte=start, date__lt=end).values("date").distinct().count()
    secs = {}
    for tid, code in (TeacherAttendance.objects.filter(date__gte=start, date__lt=end, section__isnull=False)
                      .order_by().values_list("teacher_id", "section__code").distinct()):
        secs.setdefault(tid, []).append(code)
    teachers = list(teachers)
    for t in teachers:
        t.month_sections = sorted(secs.get(t.id, []))
    return render(request, "quiz/attendance/teacher_monthly.html", {
        "teachers": teachers, "n_days": n_days, **_month_nav(start),
    })


@supervisor_required
def teacher_file(request, teacher_id):
    teacher = get_object_or_404(Teacher, pk=teacher_id)
    start, end = _month(request.GET.get("month"))
    if request.method == "POST" and request.user.is_admin_role:
        teacher.subject = request.POST.get("subject", "").strip()[:100]
        teacher.is_active = bool(request.POST.get("is_active"))
        teacher.save()
        messages.success(request, "تم حفظ بيانات الأستاذ.")
        return redirect(f"{reverse('teacher_file', args=[teacher.id])}?month={start.strftime('%Y-%m')}")
    records = teacher.attendance.filter(date__gte=start, date__lt=end).order_by("date", "session").select_related("section")
    for r in records:
        r.label = _day_label(r.date)
    return render(request, "quiz/attendance/teacher_file.html", {
        "teacher": teacher, "records": records, "totals": _counts(records),
        "all_totals": _counts(teacher.attendance.all()), **_month_nav(start),
    })


# ---------------------------------------------------------------- الاستيراد من Excel

def _import(request, func, label):
    form = ImportFileForm(request.POST, request.FILES)
    if not form.is_valid():
        for e in form.errors.get("file", []):
            messages.error(request, e)
        return redirect("attendance_home")
    created, updated, errors = func(form.cleaned_data["file"])
    if created or updated:
        messages.success(request, f"{label}: أُضيف {created} وحُدِّث {updated}. الغياب والملاحظات السابقة محفوظة.")
    for e in errors[:15]:
        messages.error(request, e)
    if len(errors) > 15:
        messages.error(request, f"و{len(errors) - 15} أخطاء أخرى. لم يُحفظ شيء من الملف، صحّح الأخطاء ثم أعد الاستيراد.")
    elif errors and not (created or updated):
        messages.error(request, "لم يُحفظ شيء من الملف، صحّح الأخطاء ثم أعد الاستيراد.")
    return redirect("attendance_home")


@admin_required
@require_POST
def roster_import(request):
    return _import(request, excel.import_roster, "لائحة التلاميذ")


@admin_required
@require_POST
def teachers_import(request):
    return _import(request, excel.import_teachers, "لائحة الأساتذة")


@admin_required
def roster_template(request):
    return xlsx_response(excel.roster_template(), "students_list_template.xlsx")


@admin_required
def teachers_template(request):
    return xlsx_response(excel.teachers_template(), "teachers_list_template.xlsx")
