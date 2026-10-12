"""المكتبة: مخزون كتب كل فصل وتسليمها للتلاميذ (دور مسؤول المكتبة)."""
from django.contrib import messages
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from openpyxl import Workbook

from . import excel
from .models import BOOK_PARTS, BOOK_SUBJECTS, LIBRARY_LEVELS, BookDelivery, BookStock, Section, User
from .views import role_required, xlsx_response

library_required = role_required("admin", "librarian")

# كل كتاب له نسختان: (المادة، النسخة)
BOOKS = [(code, label, part, part_label) for code, label in BOOK_SUBJECTS for part, part_label in BOOK_PARTS]


def _sections():
    return Section.objects.filter(classe__code__in=LIBRARY_LEVELS).select_related("classe")


def _summary(stock, delivered):
    """لكل كتاب: الموجود، المسلَّم، الباقي."""
    rows = []
    for code, label, part, part_label in BOOKS:
        have, given = stock.get((code, part), 0), delivered.get((code, part), 0)
        rows.append({"subject": code, "label": label, "part": part, "part_label": part_label,
                     "stock": have, "given": given, "left": have - given})
    return rows


@library_required
def library_home(request):
    sections = list(_sections())
    stock, given = {}, {}
    for sec, subject, part, qty in BookStock.objects.values_list("section", "subject", "part", "quantity"):
        stock.setdefault(sec, {})[(subject, part)] = qty
    for sec, subject, part, n in (BookDelivery.objects.order_by().values_list("section", "subject", "part")
                                  .annotate(n=Count("id"))):
        given.setdefault(sec, {})[(subject, part)] = n
    counts = dict(User.objects.filter(role=User.STUDENT, is_active=True, section__in=sections)
                  .order_by().values_list("section").annotate(n=Count("id")))
    for s in sections:
        s.books = _summary(stock.get(s.id, {}), given.get(s.id, {}))
        s.n_students = counts.get(s.id, 0)
        s.total_stock = sum(b["stock"] for b in s.books)
        s.total_given = sum(b["given"] for b in s.books)
        s.short = any(b["left"] < 0 for b in s.books)
    return render(request, "quiz/library/home.html", {"sections": sections, "books": BOOKS})


@library_required
def library_section(request, section_id):
    section = get_object_or_404(_sections(), pk=section_id)
    students = list(section.students.filter(role=User.STUDENT, is_active=True).order_by("full_name", "username"))

    if request.method == "POST" and request.POST.get("action") == "stock":
        for code, _, part, _ in BOOKS:
            raw = request.POST.get(f"stock_{code}_{part}", "").strip()
            qty = int(raw) if raw.isdigit() else 0
            BookStock.objects.update_or_create(section=section, subject=code, part=part, defaults={"quantity": qty})
        messages.success(request, f"تم حفظ عدد الكتب الموجودة للقسم {section}.")
        return redirect("library_section", section.id)

    if request.method == "POST" and request.POST.get("action") == "deliver":
        today = timezone.localdate()
        existing = {(d.student_id, d.subject, d.part): d
                    for d in BookDelivery.objects.filter(student__in=students)}
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

    stock = {(b.subject, b.part): b.quantity for b in BookStock.objects.filter(section=section)}
    given = dict(((s, p), n) for s, p, n in BookDelivery.objects.filter(section=section).order_by()
                 .values_list("subject", "part").annotate(n=Count("id")))
    have = {}
    for d in BookDelivery.objects.filter(student__in=students):
        have.setdefault(d.student_id, {})[(d.subject, d.part)] = d.date
    for st in students:
        mine = have.get(st.id, {})
        st.cells = [{"name": f"d_{st.id}_{code}_{part}", "date": mine.get((code, part))} for code, _, part, _ in BOOKS]
        st.n_books = len(mine)

    summary = _summary(stock, given)
    if request.GET.get("export") == "xlsx":
        return xlsx_response(_section_workbook(section, students, summary), f"books_{section.code}.xlsx")
    return render(request, "quiz/library/section.html", {
        "section": section, "students": students, "books": BOOKS, "summary": summary,
        "subjects": BOOK_SUBJECTS, "has_stock": any(stock.values()),
    })


def _section_workbook(section, students, summary):
    wb = Workbook()
    ws = wb.active
    ws.title = f"كتب {section.code}"[:31]
    ws.append(["#", "رقم القيد", "اسم التلميذ"] + [f"{label} - {part_label}" for _, label, _, part_label in BOOKS])
    for i, st in enumerate(students, start=1):
        ws.append([i, st.matricule or "", st.full_name or st.username]
                  + ["✓" if c["date"] else "" for c in st.cells])
    ws.append([])
    ws.append(["", "", "الموجود"] + [b["stock"] for b in summary])
    ws.append(["", "", "المسلَّم"] + [b["given"] for b in summary])
    ws.append(["", "", "الباقي"] + [b["left"] for b in summary])
    excel._style_header(ws, [6, 14, 32] + [16] * len(BOOKS))
    return wb
