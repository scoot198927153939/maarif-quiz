"""استيراد وتصدير ملفات Excel (الأسئلة، التلاميذ، النتائج)."""
from decimal import Decimal, InvalidOperation

from django.db import transaction
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

from .models import Choice, Classe, Question, Section, Teacher, User
from .topics import guess_topic

ARABIC_LETTERS = {"أ": "A", "ا": "A", "ب": "B", "ج": "C", "د": "D", "ه": "E", "هـ": "E", "و": "F"}
QUESTION_HEADERS = ["السؤال", "A", "B", "C", "D", "الإجابة الصحيحة", "النقاط", "المستوى", "صورة", "المحور"]
LEVEL_CODES = {"بسيط": "E", "متوسط": "M", "صعب": "H", "E": "E", "M": "M", "H": "H"}
STUDENT_HEADERS = ["اسم المستخدم", "الاسم الكامل", "كلمة المرور", "القسم"]
ROSTER_HEADERS = ["رقم قيد الطالب", "القسم", "اسم الطالب", "رقم هاتف الوكيل", "رقم الواتساب", "رقم هاتف الوكيل2"]
TEACHER_HEADERS = ["اسم الأستاذ", "المادة"]

HEADER_FILL = PatternFill("solid", fgColor="1F6F5C")
HEADER_FONT = Font(bold=True, color="FFFFFF")


def _clean(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def normalize_letter(value):
    """يحوّل رمز الإجابة (A / أ / 1) إلى حرف لاتيني كبير."""
    v = _clean(value).upper()
    if not v:
        return ""
    if v in ARABIC_LETTERS:
        return ARABIC_LETTERS[v]
    if v.isdigit() and 1 <= int(v) <= len(Question.LETTERS):
        return Question.LETTERS[int(v) - 1]
    return v[:1]


def _style_header(ws, widths):
    ws.sheet_view.rightToLeft = True
    for i, cell in enumerate(ws[1]):
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center")
        ws.column_dimensions[cell.column_letter].width = widths[i] if i < len(widths) else 15


def questions_template():
    wb = Workbook()
    ws = wb.active
    ws.title = "الأسئلة"
    ws.append(QUESTION_HEADERS)
    ws.append(["كم يساوي 5 + 7 ؟", "10", "12", "13", "15", "B", 2, "بسيط", "", "العمليات"])
    ws.append(["ما عاصمة موريتانيا؟", "نواذيبو", "روصو", "نواكشوط", "", "C", 1])
    ws.append(["أيّ عدد أوّلي؟", "9", "15", "21", "7", "د", 1])
    _style_header(ws, [50, 20, 20, 20, 20, 18, 10, 10, 14, 22])
    notes = wb.create_sheet("طريقة الاستعمال")
    notes.sheet_view.rightToLeft = True
    for line in [
        "كل سطر في ورقة «الأسئلة» = سؤال واحد. لا تغيّر السطر الأول (العناوين).",
        "الأعمدة A و B و C و D هي الخيارات. يمكن ترك خيار فارغاً إذا كان للسؤال خياران أو ثلاثة فقط.",
        "عمود «الإجابة الصحيحة»: اكتب رمز الخيار الصحيح: A أو B أو C أو D (أو أ / ب / ج / د، أو 1 / 2 / 3 / 4).",
        "عمود «النقاط»: عدد نقاط السؤال (إذا تُرك فارغاً تُحسب نقطة واحدة).",
        "عمود «المستوى» (اختياري): بسيط أو متوسط أو صعب. عمود «المحور» (اختياري): الدرس الذي يقيسه السؤال. "
        "يُستعملان في تقرير التلميذ؛ إذا تُرك المحور فارغاً يحدده التطبيق تلقائياً.",
        "لإضافة صورة لسؤال: بعد الاستيراد افتح السؤال من صفحة الامتحان واضغط «تعديل» ثم ارفع الصورة.",
    ]:
        notes.append([line])
    notes.column_dimensions["A"].width = 110
    return wb


def students_template():
    wb = Workbook()
    ws = wb.active
    ws.title = "التلاميذ"
    ws.append(STUDENT_HEADERS)
    ws.append(["ahmed.1as", "أحمد محمد", "1234", "1AS"])
    ws.append(["fatima.7sn", "فاطمة سيدي", "abcd", "7SN"])
    _style_header(ws, [20, 30, 16, 10])
    return wb


def _norm(text):
    return " ".join(text.split())


def import_questions(exam, file, replace=False):
    """يعيد (عدد الأسئلة المضافة، قائمة الأخطاء). لا يُحفظ شيء إذا وُجد خطأ.

    replace=True: تحلّ أسئلة الملف محل أسئلة الامتحان الحالية (تُؤرشف إن كان تلاميذ قد أجابوا عليها).
    صورة السؤال القديم تُنقل إلى السؤال الجديد الذي له نفس النص."""
    try:
        wb = load_workbook(file, read_only=True, data_only=True)
    except Exception:
        return 0, ["تعذّر قراءة الملف. تأكد أنه ملف Excel بصيغة ‎.xlsx"]
    ws = wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return 0, ["الملف فارغ."]

    errors = []
    parsed = []
    start_order = exam.questions.count()
    for idx, row in enumerate(rows[1:], start=2):
        row = list(row) + [None] * 10
        text = _clean(row[0])
        options = [_clean(v) for v in row[1:5]]
        if not text and not any(options):
            continue  # سطر فارغ
        correct = normalize_letter(row[5])
        points_raw = _clean(row[6]) or "1"
        choices = [(Question.LETTERS[i], o) for i, o in enumerate(options) if o]
        if not text:
            errors.append(f"السطر {idx}: نص السؤال فارغ.")
            continue
        if len(choices) < 2:
            errors.append(f"السطر {idx}: يجب وضع خيارين على الأقل.")
            continue
        if correct not in [c[0] for c in choices]:
            errors.append(f"السطر {idx}: رمز الإجابة الصحيحة «{_clean(row[5])}» لا يطابق أي خيار.")
            continue
        try:
            points = Decimal(points_raw.replace(",", "."))
            if points < 0:
                raise InvalidOperation
        except InvalidOperation:
            errors.append(f"السطر {idx}: قيمة النقاط «{points_raw}» غير صحيحة.")
            continue
        level = LEVEL_CODES.get(_clean(row[7]), "")
        topic = _clean(row[9])[:100]
        parsed.append((text, choices, correct, points, level, topic))

    if errors:
        return 0, errors
    if not parsed:
        return 0, ["لم يتم العثور على أي سؤال في الملف."]

    with transaction.atomic():
        images = {}
        if replace:
            for old in exam.questions.all():
                if old.image:
                    images.setdefault(_norm(old.text), old.image.name)
            # إذا أجرى تلاميذ الامتحان تُؤرشف الأسئلة القديمة (لا تُحذف) حتى تبقى نتائجهم وتقاريرهم
            if exam.attempts.exists():
                exam.questions.all().update(archived=True)
            else:
                exam.questions.all().delete()
            start_order = 0
        for n, (text, choices, correct, points, level, topic) in enumerate(parsed, start=1):
            q = Question.objects.create(
                exam=exam, text=text, correct_answer=correct, points=points, order=start_order + n, level=level,
                topic=topic or guess_topic(exam.subject.name, text, [t for _, t in choices]),
                image=images.get(_norm(text)) or None,
            )
            Choice.objects.bulk_create([Choice(question=q, letter=l, text=t) for l, t in choices])
    return len(parsed), []


def import_students(file):
    """يعيد (عدد المضافين، عدد المحدَّثين، قائمة الأخطاء)."""
    try:
        wb = load_workbook(file, read_only=True, data_only=True)
    except Exception:
        return 0, 0, ["تعذّر قراءة الملف. تأكد أنه ملف Excel بصيغة ‎.xlsx"]
    rows = list(wb.worksheets[0].iter_rows(values_only=True))
    classes = {c.code.upper(): c for c in Classe.objects.all()}
    errors, parsed = [], []
    for idx, row in enumerate(rows[1:], start=2):
        row = list(row) + [None] * 4
        username, full_name, password, code = (_clean(v) for v in row[:4])
        if not any([username, full_name, password, code]):
            continue
        if not username:
            errors.append(f"السطر {idx}: اسم المستخدم فارغ.")
            continue
        classe = classes.get(code.upper())
        if not classe:
            errors.append(f"السطر {idx}: القسم «{code}» غير موجود.")
            continue
        parsed.append((username, full_name, password, classe))
    if errors:
        return 0, 0, errors

    created = updated = 0
    with transaction.atomic():
        for username, full_name, password, classe in parsed:
            user = User.objects.filter(username=username).first()
            if user and not user.is_student:
                errors.append(f"«{username}» حساب موجود لغير تلميذ، تم تجاهله.")
                continue
            if user is None:
                user = User(username=username, role=User.STUDENT)
                created += 1
                if not password:
                    password = username
            else:
                updated += 1
            user.full_name = full_name or user.full_name
            user.classe = classe
            if password:
                user.set_password(password)
            user.save()
    return created, updated, errors


def results_workbook(classe, exams, rows):
    """rows: [(student, [score_or_None,...], total)]"""
    wb = Workbook()
    ws = wb.active
    ws.title = classe.code
    ws.append(["التلميذ", "اسم المستخدم"] + [f"{e.subject} - {e.title} (/{e.total_points})" for e in exams])
    for student, scores in rows:
        ws.append([str(student), student.username] + [float(s) if s is not None else "" for s in scores])
    _style_header(ws, [28, 18] + [22] * len(exams))
    return wb


def roster_template():
    wb = Workbook()
    ws = wb.active
    ws.title = "التلاميذ"
    ws.append(ROSTER_HEADERS)
    ws.append(["1001", "1AS1", "أحمد محمد", "22000001", "22000001", ""])
    ws.append(["1002", "7SN2", "فاطمة سيدي", "33000002", "46000002", "44000002"])
    _style_header(ws, [16, 10, 30, 18, 18, 18])
    return wb


def teachers_template():
    wb = Workbook()
    ws = wb.active
    ws.title = "الأساتذة"
    ws.append(TEACHER_HEADERS)
    ws.append(["محمد الأمين", "الرياضيات"])
    ws.append(["Mme Aicha", "الفرنسية"])
    _style_header(ws, [30, 22])
    return wb


def _roster_columns(header):
    """يحدد ترتيب الأعمدة من عناوين الملف، وإن لم يتعرف عليها يعتمد الترتيب الافتراضي."""
    cols = {}
    for i, h in enumerate(_clean(v).replace(" ", "") for v in header):
        if not h:
            continue
        if "قيد" in h or "matricule" in h.lower():
            cols.setdefault("matricule", i)
        elif "واتس" in h or "whats" in h.lower():
            cols.setdefault("whatsapp", i)
        elif "هاتف" in h or "tel" in h.lower():
            key = "phone2" if ("2" in h or "٢" in h) else "phone1"
            cols.setdefault(key, i)
        elif "قسم" in h or "فصل" in h or "classe" in h.lower():
            cols.setdefault("section", i)
        elif "اسم" in h or "nom" in h.lower():
            cols.setdefault("name", i)
    if {"matricule", "section", "name"} <= cols.keys():
        return cols, True
    return {"matricule": 0, "section": 1, "name": 2, "phone1": 3, "whatsapp": 4, "phone2": 5}, False


def import_roster(file):
    """لائحة التلاميذ للحضور. التلميذ يُعرف برقم قيده: إن وُجد تُحدَّث بياناته وفصله
    (ويبقى غيابه وملاحظاته ونتائجه)، وإلا يُنشأ له حساب اسم مستخدمه وكلمة مروره رقم القيد.
    لا يُحذف أي تلميذ غير موجود في الملف. يعيد (المضافون، المحدَّثون، الأخطاء)."""
    try:
        wb = load_workbook(file, read_only=True, data_only=True)
    except Exception:
        return 0, 0, ["تعذّر قراءة الملف. تأكد أنه ملف Excel بصيغة ‎.xlsx"]
    rows = list(wb.worksheets[0].iter_rows(values_only=True))
    if not rows:
        return 0, 0, ["الملف فارغ."]
    cols, has_header = _roster_columns(rows[0])
    body = rows[1:] if has_header or not _clean(rows[0][0]).isdigit() else rows
    sections = {s.code.upper(): s for s in Section.objects.all()}

    def get(row, key):
        i = cols.get(key)
        return _clean(row[i]) if i is not None and i < len(row) else ""

    errors, parsed, seen = [], [], set()
    for idx, row in enumerate(body, start=len(rows) - len(body) + 1):
        row = list(row)
        mat, code, name = get(row, "matricule"), get(row, "section").replace(" ", "").upper(), get(row, "name")
        if not any([mat, code, name]):
            continue
        if not mat:
            errors.append(f"السطر {idx}: رقم القيد فارغ.")
            continue
        if mat in seen:
            errors.append(f"السطر {idx}: رقم القيد {mat} مكرر في الملف.")
            continue
        seen.add(mat)
        section = sections.get(code)
        if not section:
            errors.append(f"السطر {idx}: القسم «{code}» غير موجود.")
            continue
        parsed.append((mat, section, name, get(row, "phone1"), get(row, "whatsapp"), get(row, "phone2")))
    if errors:
        return 0, 0, errors
    if not parsed:
        return 0, 0, ["لم يتم العثور على أي تلميذ في الملف."]

    created = updated = 0
    with transaction.atomic():
        for mat, section, name, p1, wa, p2 in parsed:
            user = User.objects.filter(matricule=mat).first() or User.objects.filter(username=mat).first()
            if user and not user.is_student:
                errors.append(f"رقم القيد {mat} مستعمل كاسم مستخدم لحساب غير تلميذ، تم تجاهله.")
                continue
            if user is None:
                user = User(username=mat, role=User.STUDENT)
                user.set_password(mat)
                created += 1
            else:
                updated += 1
            user.matricule = mat
            user.section = section
            user.full_name = name or user.full_name
            user.guardian_phone, user.whatsapp, user.guardian_phone2 = p1, wa, p2
            user.save()
    return created, updated, errors


def import_teachers(file):
    """لائحة الأساتذة للحضور: الأستاذ يُعرف باسمه، فيُحدَّث أو يُضاف ولا يُحذف أحد."""
    try:
        wb = load_workbook(file, read_only=True, data_only=True)
    except Exception:
        return 0, 0, ["تعذّر قراءة الملف. تأكد أنه ملف Excel بصيغة ‎.xlsx"]
    rows = list(wb.worksheets[0].iter_rows(values_only=True))
    created = updated = 0
    errors = []
    with transaction.atomic():
        for idx, row in enumerate(rows, start=1):
            row = list(row) + [None, None]
            name, subject = " ".join(_clean(row[0]).split()), _clean(row[1])
            if not name or (idx == 1 and "اسم" in name):
                continue
            t, new = Teacher.objects.get_or_create(name=name[:150], defaults={"subject": subject[:100]})
            if new:
                created += 1
            else:
                updated += 1
                t.subject = subject[:100] or t.subject
                t.is_active = True
                t.save()
    if not created and not updated:
        errors.append("لم يتم العثور على أي أستاذ في الملف.")
    return created, updated, errors
