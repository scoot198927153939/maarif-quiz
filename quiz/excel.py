"""استيراد وتصدير ملفات Excel (الأسئلة، التلاميذ، النتائج)."""
from decimal import Decimal, InvalidOperation

from django.db import transaction
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

from .models import Choice, Classe, Question, User
from .topics import guess_topic

ARABIC_LETTERS = {"أ": "A", "ا": "A", "ب": "B", "ج": "C", "د": "D", "ه": "E", "هـ": "E", "و": "F"}
QUESTION_HEADERS = ["السؤال", "A", "B", "C", "D", "الإجابة الصحيحة", "النقاط", "المستوى", "صورة", "المحور"]
LEVEL_CODES = {"بسيط": "E", "متوسط": "M", "صعب": "H", "E": "E", "M": "M", "H": "H"}
STUDENT_HEADERS = ["اسم المستخدم", "الاسم الكامل", "كلمة المرور", "القسم"]

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


def import_questions(exam, file):
    """يعيد (عدد الأسئلة المضافة، قائمة الأخطاء). لا يُحفظ شيء إذا وُجد خطأ."""
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
        for n, (text, choices, correct, points, level, topic) in enumerate(parsed, start=1):
            q = Question.objects.create(
                exam=exam, text=text, correct_answer=correct, points=points, order=start_order + n, level=level,
                topic=topic or guess_topic(exam.subject.name, text, [t for _, t in choices]),
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
