"""المكتبة: مخزون كتب كل مستوى وتسليمها للتلاميذ (دور مسؤول المكتبة).
فصول المستوى الواحد (7SN1 … 7SN6 مثلاً) تدرس نفس الكتب، فالمخزون للمستوى والتسليم لكل تلميذ."""
from django.contrib import messages
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from openpyxl import Workbook

from . import excel
from .models import STUDENT_ORDER, BOOK_PARTS, BOOK_SUBJECTS, LIBRARY_LEVELS, BookDelivery, BookStock, Classe, Section, User
from .views import role_required, xlsx_response

library_required = role_required("admin", "librarian")

# كل كتاب له نسختان: (المادة، النسخة)
BOOKS = [(code, label, part, part_label) for code, label in BOOK_SUBJECTS for part, part_label in BOOK_PARTS]


def _levels():
    order = {c: i for i, c in enumerate(LIBRARY_LEVELS)}
    return sorted(Classe.objects.filter(code__in=LIBRARY_LEVELS), key=lambda c: order[c.code])


def _level_summary(classe):
    """لكل مادة: سطر فيه النسختان، ولكل نسخة الموجود والمسلَّم والباقي."""
    stock = {(b.subject, b.part): b.quantity for b in BookStock.objects.filter(classe=classe)}
    given = {(s, p): n for s, p, n in BookDelivery.objects.filter(section__classe=classe).order_by()
             .values_list("subject", "part").annotate(n=Count("id"))}
    rows = []
    for code, label in BOOK_SUBJECTS:
        parts = []
        for part, part_label in BOOK_PARTS:
            have, out = stock.get((code, part), 0), given.get((code, part), 0)
            parts.append({"part": part, "part_label": part_label, "stock": have, "given": out, "left": have - out,
                          "field": f"stock_{code}_{part}"})
        rows.append({"subject": code, "label": label, "parts": parts})
    return rows


def _flat(summary):
    return [p for row in summary for p in row["parts"]]


@library_required
def library_home(request):
    levels = _levels()
    counts = dict(User.objects.filter(role=User.STUDENT, is_active=True, section__classe__in=levels)
                  .order_by().values_list("section").annotate(n=Count("id")))
    for c in levels:
        c.summary = _level_summary(c)
        flat = _flat(c.summary)
        c.has_stock = any(p["stock"] for p in flat)
        c.short = any(p["left"] < 0 for p in flat)
        c.sections_list = list(c.sections.all())
        for s in c.sections_list:
            s.n_students = counts.get(s.id, 0)
    return render(request, "quiz/library/home.html", {"levels": levels})


@library_required
def library_level(request, classe_id):
    classe = get_object_or_404(Classe, pk=classe_id, code__in=LIBRARY_LEVELS)
    if request.method == "POST":
        for code, _, part, _ in BOOKS:
            raw = request.POST.get(f"stock_{code}_{part}", "").strip()
            qty = int(raw) if raw.isdigit() else 0
            BookStock.objects.update_or_create(classe=classe, subject=code, part=part, defaults={"quantity": qty})
        messages.success(request, f"تم حفظ عدد الكتب الموجودة للمستوى {classe.code}.")
        return redirect("library_home")
    return render(request, "quiz/library/level.html", {"classe": classe, "summary": _level_summary(classe)})


@library_required
def library_section(request, section_id):
    section = get_object_or_404(Section.objects.select_related("classe"), pk=section_id,
                                classe__code__in=LIBRARY_LEVELS)
    students = list(section.students.filter(role=User.STUDENT, is_active=True).order_by(*STUDENT_ORDER))

    if request.method == "POST":
        today = timezone.localdate()
        existing = {(d.student_id, d.subject, d.part): d for d in BookDelivery.objects.filter(student__in=students)}
        added = removed = 0
        for st in students:
            for code, _, part, _ in BOOKS:
                key = (st.id, code, part)
                checked = request.POST.get(f"d_{st.id}_{code}_{part}") == "1"
                if checked and key not in existing:
                    BookDelivery.objects.create(student=st, subject=code, part=part, section=section,
                                                date=today, delivered_by=request.user)
                    added += 1
                elif not checked and key in existing:
                    existing[key].delete()
                    removed += 1
        msg = f"تم الحفظ: {added} كتاب سُلِّم"
        if removed:
            msg += f"، وأُلغي تسليم {removed}"
        messages.success(request, msg + ".")
        return redirect("library_section", section.id)

    have = {}
    for d in BookDelivery.objects.filter(student__in=students):
        have.setdefault(d.student_id, {})[(d.subject, d.part)] = d.date
    in_section = {(s, p): n for s, p, n in BookDelivery.objects.filter(section=section).order_by()
                  .values_list("subject", "part").annotate(n=Count("id"))}
    for st in students:
        mine = have.get(st.id, {})
        st.cells = [{"name": f"d_{st.id}_{code}_{part}", "date": mine.get((code, part)), "col": f"{code}-{part}",
                     "first": part == 1} for code, _, part, _ in BOOKS]
        st.n_books = len(mine)

    summary = _level_summary(section.classe)
    for row in summary:
        for p in row["parts"]:
            p["in_section"] = in_section.get((row["subject"], p["part"]), 0)
    if request.GET.get("export") == "xlsx":
        return xlsx_response(_section_workbook(section, students, summary), f"books_{section.code}.xlsx")
    return render(request, "quiz/library/section.html", {
        "section": section, "students": students, "summary": summary,
        "has_stock": any(p["stock"] for p in _flat(summary)),
        "siblings": section.classe.sections.all(),
    })


def _section_workbook(section, students, summary):
    wb = Workbook()
    ws = wb.active
    ws.title = f"كتب {section.code}"[:31]
    ws.append(["#", "رقم القيد", "اسم التلميذ"] + [f"{label} - {part_label}" for _, label, _, part_label in BOOKS])
    for i, st in enumerate(students, start=1):
        ws.append([i, st.matricule or "", st.full_name or st.username]
                  + ["✓" if c["date"] else "" for c in st.cells])
    flat = _flat(summary)
    ws.append([])
    ws.append(["", "", f"سُلِّم في {section.code}"] + [p["in_section"] for p in flat])
    ws.append(["", "", f"الموجود للمستوى {section.classe.code}"] + [p["stock"] for p in flat])
    ws.append(["", "", f"الباقي للمستوى {section.classe.code}"] + [p["left"] for p in flat])
    excel._style_header(ws, [6, 14, 32] + [16] * len(BOOKS))
    return wb
