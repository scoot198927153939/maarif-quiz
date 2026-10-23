"""الدروس المصوّرة: مسجّل الدروس يصوّر صفحات كل درس بهاتفه، وتُجمع دروس كل مادة في كل فصل
في ملف PDF واحد يتابع به المشرف تقدّم الأستاذ ويطبعه للتلاميذ المتغيبين."""
import datetime
import io
import tempfile
import zipfile

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Count, Max
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from PIL import Image, ImageOps

from .models import LESSON_SUBJECTS, Lesson, LessonPage, LessonScope, Section, User
from .views import admin_required, role_required

lessons_required = role_required("admin", "supervisor", "recorder")
recorder_required = role_required("recorder")

SUBJECT_LABELS = dict(LESSON_SUBJECTS)
# أسماء الملفات داخل الملف المضغوط بحروف لاتينية: مستخرج ويندوز يشوّه الأسماء العربية
FILE_NAMES = {"AR": "Arabe", "FR": "Francais", "AN": "Anglais", "M": "Maths", "PC": "Physique-Chimie",
              "SN": "Sciences-naturelles", "HG": "Histoire-Geo", "IR": "Education-islamique",
              "IC": "Education-civique", "PH": "Philosophie", "TI": "Informatique"}
MAX_PAGES = 12
MAX_SIDE = 1600  # بكسل: يكفي للقراءة ويُبقي الملف صغيراً


def _date(value, default=None):
    try:
        return datetime.date.fromisoformat(value)
    except (TypeError, ValueError):
        return default


def _subject(code):
    if code not in SUBJECT_LABELS:
        raise PermissionDenied
    return code


def can_view(user, section, subject):
    if user.is_admin_role:
        return True
    if user.is_supervisor:
        return user.supervised_sections.filter(pk=section.pk).exists()
    if user.is_recorder:
        return user.lesson_scopes.filter(section=section, subject=subject).exists()
    return False


def compress(upload):
    """يدير الصورة حسب وضع الهاتف ويصغّرها ويحفظها JPEG."""
    img = Image.open(upload)
    img = ImageOps.exif_transpose(img).convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=72, optimize=True)
    return out.getvalue(), img.size


# ---------------------------------------------------------------- PDF

def build_pdf(lessons, heading):
    """ملف PDF: كل صورة صفحة بعرض A4، وفي أعلاها تاريخ الدرس. الصور تُضمَّن كما هي (JPEG) دون إعادة ترميز."""
    width, band, margin = 595.0, 26.0, 18.0
    objects = []  # نص كل كائن، رقمه = موضعه + 1

    def add(body):
        objects.append(body)
        return len(objects)

    catalog = add(b"")  # يُملأ لاحقاً
    pages_id = add(b"")
    font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    kids = []
    for lesson in lessons:
        pages = list(lesson.pages.all())
        for n, page in enumerate(pages, start=1):
            try:
                with page.image.open("rb") as f:
                    data = f.read()
                with Image.open(io.BytesIO(data)) as im:
                    w, h = im.size
                    if im.format != "JPEG" or im.mode != "RGB":
                        buf = io.BytesIO()
                        im.convert("RGB").save(buf, "JPEG", quality=72)
                        data = buf.getvalue()
            except (OSError, ValueError):
                continue  # صورة مفقودة أو تالفة: لا تُسقط الملف كله
            draw_w = width - 2 * margin
            draw_h = draw_w * h / w
            height = draw_h + band + 2 * margin
            img = add(b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceRGB "
                      b"/BitsPerComponent 8 /Filter /DCTDecode /Length %d >>\nstream\n" % (w, h, len(data))
                      + data + b"\nendstream")
            label = f"{heading}   {lesson.date:%d/%m/%Y}   ({n}/{len(pages)})"
            label = label.encode("latin-1", "replace").replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
            content = (b"q %.2f 0 0 %.2f %.2f %.2f cm /Im0 Do Q\n" % (draw_w, draw_h, margin, margin)
                       + b"BT /F1 12 Tf %.2f %.2f Td (" % (margin, height - margin - 12) + label + b") Tj ET")
            stream = add(b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream")
            kids.append(add(b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %.2f %.2f] "
                            b"/Resources << /XObject << /Im0 %d 0 R >> /Font << /F1 %d 0 R >> >> /Contents %d 0 R >>"
                            % (pages_id, width, height, img, font, stream)))
    objects[catalog - 1] = b"<< /Type /Catalog /Pages %d 0 R >>" % pages_id
    objects[pages_id - 1] = (b"<< /Type /Pages /Kids [" + b" ".join(b"%d 0 R" % k for k in kids)
                             + b"] /Count %d >>" % len(kids))

    out = io.BytesIO()
    out.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % i + body + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1))
    for off in offsets:
        out.write(b"%010d 00000 n \n" % off)
    out.write(b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, catalog, xref))
    return out.getvalue(), len(kids)


# ---------------------------------------------------------------- مسجّل الدروس

def _scope_cards(scopes):
    stats = _stats(Lesson.objects.all())
    for sc in scopes:
        st = stats.get((sc.section_id, sc.subject), {})
        sc.n, sc.last = st.get("n", 0), st.get("last")
    return scopes


def _stats(lessons):
    """(فصل، مادة) → عدد الدروس وتاريخ آخرها."""
    return {(r["section"], r["subject"]): r for r in
            lessons.order_by().values("section", "subject").annotate(n=Count("id"), last=Max("date"))}


@lessons_required
def lessons_home(request):
    if not request.user.is_recorder:
        return redirect("lessons_overview")
    scopes = _scope_cards(list(request.user.lesson_scopes.select_related("section")))
    recent = (Lesson.objects.filter(uploaded_by=request.user).select_related("section")
              .annotate(n_pages=Count("pages")).order_by("-created_at")[:10])
    return render(request, "quiz/lessons/home.html", {"scopes": scopes, "recent": recent})


@recorder_required
def lesson_new(request, scope_id):
    scope = get_object_or_404(LessonScope.objects.select_related("section"), pk=scope_id, user=request.user)
    today = timezone.localdate()
    if request.method == "POST":
        files = request.FILES.getlist("pages")[:MAX_PAGES]
        day = _date(request.POST.get("date"))
        error = None
        if not day:
            error = "اختر تاريخ الدرس."
        elif day > today:
            error = "تاريخ الدرس لا يمكن أن يكون بعد اليوم."
        elif not files:
            error = "صوّر صفحة واحدة على الأقل."
        images = []
        if not error:
            try:
                images = [compress(f)[0] for f in files]
            except (OSError, ValueError):
                error = "إحدى الصور لم تُقرأ. أعد تصويرها."
        if error:
            messages.error(request, error)
        else:
            with transaction.atomic():
                lesson = Lesson.objects.create(
                    section=scope.section, subject=scope.subject, date=day,
                    title=request.POST.get("title", "").strip()[:200], uploaded_by=request.user,
                )
                stamp = timezone.now().strftime("%Y%m%d%H%M%S")
                for i, data in enumerate(images, start=1):
                    page = LessonPage(lesson=lesson, order=i)
                    page.image.save(f"{scope.section.code}_{scope.subject}_{stamp}_{i}.jpg", ContentFile(data), save=False)
                    page.save()
            messages.success(request, f"تم حفظ درس {lesson.date:%d/%m/%Y} ({len(images)} صفحة) وأُضيف إلى ملف "
                                      f"{scope.section} · {scope.get_subject_display()}.")
            return redirect("lessons_home")
    return render(request, "quiz/lessons/new.html", {
        "scope": scope, "today": today.isoformat(), "max_pages": MAX_PAGES,
        "last": Lesson.objects.filter(section=scope.section, subject=scope.subject).order_by("-date", "-created_at").first(),
    })


@lessons_required
@require_POST
def lesson_delete(request, lesson_id):
    lesson = get_object_or_404(Lesson.objects.select_related("section"), pk=lesson_id)
    if not (request.user.is_admin_role or lesson.uploaded_by_id == request.user.id):
        raise PermissionDenied
    section, subject = lesson.section, lesson.subject
    for page in lesson.pages.all():
        page.image.delete(save=False)
    lesson.delete()
    messages.success(request, "تم حذف الدرس.")
    if request.user.is_recorder:
        return redirect("lessons_home")
    return redirect("lesson_board", section_id=section.id, subject=subject)


# ---------------------------------------------------------------- المتابعة (المشرف والمراقب)

def _notebooks(sections):
    """دفاتر كل فصل: دفتر لكل مادة فيها دروس أو مسجّل مكلَّف بها."""
    stats = _stats(Lesson.objects.filter(section__in=sections))
    latest = {}
    for l in Lesson.objects.filter(section__in=sections).order_by("date", "created_at"):
        latest[(l.section_id, l.subject)] = l  # يبقى آخر درس
    pages = {}
    for sec, sub, n in (LessonPage.objects.filter(lesson__section__in=sections).order_by()
                        .values("lesson__section", "lesson__subject").annotate(n=Count("id"))
                        .values_list("lesson__section", "lesson__subject", "n")):
        pages[(sec, sub)] = n
    scoped = set(LessonScope.objects.filter(section__in=sections).values_list("section", "subject"))
    shelves = []
    for s in sections:
        books = []
        for code, label in LESSON_SUBJECTS:
            key = (s.id, code)
            if key in stats or key in scoped:
                books.append({"subject": code, "label": label, "n": stats.get(key, {}).get("n", 0),
                              "pages": pages.get(key, 0), "last": latest.get(key)})
        if books:
            shelves.append({"section": s, "books": books, "has_lessons": any(b["n"] for b in books)})
    return shelves


@role_required("admin", "supervisor")
def lessons_overview(request):
    sections = list(request.user.allowed_sections().select_related("classe"))
    shelves = _notebooks(sections)
    recorders = []
    if request.user.is_admin_role:
        recorders = list(User.objects.filter(role=User.RECORDER).prefetch_related("lesson_scopes__section"))
    return render(request, "quiz/lessons/overview.html", {
        "shelves": shelves, "recorders": recorders, "any_lessons": any(sh["has_lessons"] for sh in shelves),
    })


@lessons_required
def lesson_board(request, section_id, subject):
    """الدفتر: كل دروس المادة في الفصل بالترتيب، تُقرأ صفحة بعد صفحة."""
    section = get_object_or_404(Section, pk=section_id)
    subject = _subject(subject)
    if not can_view(request.user, section, subject):
        raise PermissionDenied
    lessons = list(Lesson.objects.filter(section=section, subject=subject)
                   .select_related("uploaded_by").prefetch_related("pages").order_by("date", "created_at"))
    for i, l in enumerate(lessons, start=1):
        l.number = i
    return render(request, "quiz/lessons/board.html", {
        "section": section, "subject": subject, "subject_label": SUBJECT_LABELS[subject],
        "lessons": lessons, "n_pages": sum(len(l.pages.all()) for l in lessons),
        "last": lessons[-1] if lessons else None,
    })


@role_required("admin", "supervisor")
def lessons_zip(request):
    """كل الدفاتر (أو دفاتر فصل واحد) في ملف مضغوط: ملف PDF لكل مادة داخل مجلد الفصل."""
    sections = request.user.allowed_sections()
    one = request.GET.get("section")
    if one:
        sections = sections.filter(pk=one)
    sections = list(sections)
    tmp = tempfile.SpooledTemporaryFile(max_size=20 * 1024 * 1024)
    count = 0
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED) as zf:  # الصور مضغوطة أصلاً
        for s in sections:
            for code, _ in LESSON_SUBJECTS:
                lessons = list(Lesson.objects.filter(section=s, subject=code)
                               .prefetch_related("pages").order_by("date", "created_at"))
                if not lessons:
                    continue
                data, n = build_pdf(lessons, f"{s.code} - {code}")
                if n:
                    zf.writestr(f"{s.code}/{s.code}_{FILE_NAMES.get(code, code)}.pdf", data)
                    count += 1
    if not count:
        messages.error(request, "لا توجد دروس مصوّرة لتحميلها.")
        return redirect("lessons_overview")
    tmp.seek(0)
    name = f"lessons_{sections[0].code}" if one and sections else "lessons_all"
    resp = FileResponse(tmp, as_attachment=True, filename=f"{name}_{timezone.localdate():%Y-%m-%d}.zip")
    return resp


@lessons_required
def lesson_pdf(request, section_id, subject):
    section = get_object_or_404(Section, pk=section_id)
    subject = _subject(subject)
    if not can_view(request.user, section, subject):
        raise PermissionDenied
    lessons = Lesson.objects.filter(section=section, subject=subject).prefetch_related("pages").order_by("date", "created_at")
    start, end = _date(request.GET.get("from")), _date(request.GET.get("to"))
    if start:
        lessons = lessons.filter(date__gte=start)
    if end:
        lessons = lessons.filter(date__lte=end)
    data, n = build_pdf(list(lessons), f"{section.code} - {subject}")
    if not n:
        messages.error(request, "لا توجد صفحات في هذه الفترة.")
        return redirect("lesson_board", section_id=section.id, subject=subject)
    name = f"{section.code}_{subject}"
    if start or end:
        name += f"_{start or ''}_{end or ''}"
    resp = HttpResponse(data, content_type="application/pdf")
    disposition = "attachment" if request.GET.get("download") else "inline"
    resp["Content-Disposition"] = f'{disposition}; filename="{name}.pdf"'
    return resp


@admin_required
def lesson_scopes(request, user_id):
    recorder = get_object_or_404(User, pk=user_id, role=User.RECORDER)
    sections = list(Section.objects.select_related("classe"))
    current = set(recorder.lesson_scopes.values_list("section", "subject"))
    if request.method == "POST":
        wanted = set()
        for value in request.POST.getlist("scope"):
            sec, _, sub = value.partition(":")
            if sec.isdigit() and sub in SUBJECT_LABELS:
                wanted.add((int(sec), sub))
        valid = {s.id for s in sections}
        wanted = {w for w in wanted if w[0] in valid}
        with transaction.atomic():
            for sec, sub in current - wanted:
                LessonScope.objects.filter(user=recorder, section_id=sec, subject=sub).delete()
            LessonScope.objects.bulk_create([LessonScope(user=recorder, section_id=sec, subject=sub)
                                             for sec, sub in wanted - current])
        messages.success(request, f"تم حفظ مواد وأقسام {recorder}: {len(wanted)} اختيار.")
        return redirect("lessons_overview")
    rows = [{"section": s, "cells": [{"value": f"{s.id}:{c}", "on": (s.id, c) in current} for c, _ in LESSON_SUBJECTS]}
            for s in sections]
    return render(request, "quiz/lessons/scopes.html", {
        "recorder": recorder, "subjects": LESSON_SUBJECTS, "rows": rows,
    })
