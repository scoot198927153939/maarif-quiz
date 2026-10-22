import re
from decimal import Decimal

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q
from django.db.models.functions import Length
from django.utils import timezone


class Classe(models.Model):
    """قسم دراسي مثل 1AS أو 7SN."""

    code = models.CharField("رمز القسم", max_length=10, unique=True)
    order = models.PositiveSmallIntegerField("الترتيب", default=0)

    class Meta:
        ordering = ["order", "code"]
        verbose_name = "قسم"
        verbose_name_plural = "الأقسام"

    def __str__(self):
        return self.code


class Section(models.Model):
    """فصل داخل المستوى، مثل 1AS1 و 1AS2. الامتحانات تبقى على المستوى (1AS)."""

    code = models.CharField("رمز القسم", max_length=10, unique=True)
    classe = models.ForeignKey(Classe, on_delete=models.CASCADE, related_name="sections", verbose_name="المستوى")
    order = models.PositiveSmallIntegerField("الترتيب", default=0)

    class Meta:
        ordering = ["order", "code"]
        verbose_name = "قسم (فصل)"
        verbose_name_plural = "الأقسام (الفصول)"

    def __str__(self):
        return self.code


class Subject(models.Model):
    name = models.CharField("المادة", max_length=100, unique=True)
    classes = models.ManyToManyField(Classe, related_name="subjects", verbose_name="الأقسام")

    class Meta:
        ordering = ["name"]
        verbose_name = "مادة"
        verbose_name_plural = "المواد"

    def __str__(self):
        return self.name


class User(AbstractUser):
    ADMIN = "admin"
    TEACHER = "teacher"
    STUDENT = "student"
    SUPERVISOR = "supervisor"
    LIBRARIAN = "librarian"
    RECORDER = "recorder"
    ROLE_CHOICES = [
        (ADMIN, "مشرف"),
        (TEACHER, "أستاذ"),
        (STUDENT, "تلميذ"),
        (SUPERVISOR, "مراقب"),
        (LIBRARIAN, "مسؤول المكتبة"),
        (RECORDER, "مسجّل الدروس"),
    ]

    role = models.CharField("الدور", max_length=10, choices=ROLE_CHOICES, default=STUDENT)
    full_name = models.CharField("الاسم الكامل", max_length=150, blank=True)
    classe = models.ForeignKey(
        Classe, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="students", verbose_name="القسم (للتلميذ)",
    )
    teaching_classes = models.ManyToManyField(
        Classe, blank=True, related_name="teachers", verbose_name="الأقسام التي يدرسها",
    )
    teaching_subjects = models.ManyToManyField(
        Subject, blank=True, related_name="teachers", verbose_name="المواد التي يدرسها",
    )
    # التلميذ: فصله وبيانات الاتصال بوليّه (تُملأ من لائحة Excel)
    section = models.ForeignKey(
        Section, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="students", verbose_name="الفصل (للتلميذ)",
    )
    matricule = models.CharField("رقم القيد", max_length=30, unique=True, null=True, blank=True)
    guardian_phone = models.CharField("هاتف الوكيل", max_length=30, blank=True)
    whatsapp = models.CharField("واتساب آخر", max_length=30, blank=True)
    # «هاتف الوكيل 2» في لائحة المدرسة هو رقم الواتساب
    guardian_phone2 = models.CharField("رقم الواتساب (هاتف الوكيل 2)", max_length=30, blank=True)
    # المراقب: الفصول التي يسجّل غيابها
    supervised_sections = models.ManyToManyField(
        Section, blank=True, related_name="supervisors", verbose_name="الأقسام التي يراقبها",
    )
    # آخر طلب من هذا المستخدم: يُعرف به من هو متصل الآن
    last_seen = models.DateTimeField("آخر نشاط", null=True, blank=True)
    # التلميذ يُطلب منه تغيير كلمة المرور عند الدخول ما دامت هي التي وضعتها الإدارة
    must_change_password = models.BooleanField("يجب تغيير كلمة المرور", default=False)

    class Meta:
        verbose_name = "مستخدم"
        verbose_name_plural = "المستخدمون"

    def __str__(self):
        return self.full_name or self.username

    @property
    def effective_role(self):
        """الدور الفعلي: حساب المدير العام (superuser) مشرف مهما كانت قيمة خانة الدور."""
        return self.ADMIN if self.is_superuser else self.role

    @property
    def effective_role_label(self):
        return dict(self.ROLE_CHOICES).get(self.effective_role, "")

    @property
    def is_admin_role(self):
        return self.role == self.ADMIN or self.is_superuser

    @property
    def is_teacher(self):
        return self.role == self.TEACHER and not self.is_superuser

    @property
    def is_student(self):
        return self.role == self.STUDENT and not self.is_superuser

    @property
    def is_supervisor(self):
        return self.role == self.SUPERVISOR and not self.is_superuser

    @property
    def is_librarian(self):
        return self.role == self.LIBRARIAN and not self.is_superuser

    @property
    def is_recorder(self):
        return self.role == self.RECORDER and not self.is_superuser

    @property
    def wa_number(self):
        """رقم الواتساب: هاتف الوكيل 2، وإلا الرقم المسجّل كواتساب."""
        return self.guardian_phone2 or self.whatsapp

    @property
    def wa_link(self):
        """رابط يفتح محادثة واتساب مع الرقم مباشرة."""
        digits = "".join(ch for ch in self.wa_number if ch.isdigit())
        if not digits:
            return ""
        if len(digits) == 8:  # رقم موريتاني بدون رمز الدولة
            digits = "222" + digits
        return f"https://wa.me/{digits}"

    def allowed_sections(self):
        if self.is_admin_role:
            return Section.objects.all()
        if self.is_supervisor:
            return self.supervised_sections.all()
        return Section.objects.none()

    def save(self, *args, **kwargs):
        if self.section_id:
            self.classe_id = self.section.classe_id
        if self.matricule == "":
            self.matricule = None
        super().save(*args, **kwargs)

    def allowed_classes(self):
        if self.is_admin_role:
            return Classe.objects.all()
        if self.is_teacher:
            return self.teaching_classes.all()
        return Classe.objects.none()

    def allowed_subjects(self):
        if self.is_admin_role:
            return Subject.objects.all()
        if self.is_teacher:
            return self.teaching_subjects.all()
        return Subject.objects.none()


class Exam(models.Model):
    title = models.CharField("عنوان الامتحان", max_length=200)
    classe = models.ForeignKey(Classe, on_delete=models.CASCADE, related_name="exams", verbose_name="القسم")
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="exams", verbose_name="المادة")
    teacher = models.ForeignKey(User, on_delete=models.CASCADE, related_name="exams", verbose_name="الأستاذ")
    instructions = models.TextField("تعليمات", blank=True)
    duration_minutes = models.PositiveIntegerField("المدة (بالدقائق)", default=30)
    available_from = models.DateTimeField("متاح من", null=True, blank=True)
    available_until = models.DateTimeField("متاح حتى", null=True, blank=True)
    is_published = models.BooleanField("منشور للتلاميذ", default=False)
    show_result = models.BooleanField("إظهار النتيجة للتلميذ بعد التسليم", default=True)
    shuffle_questions = models.BooleanField("خلط ترتيب الأسئلة", default=False)
    # امتحان خاص بمجموعة من الحصص المسائية: لا يراه إلا تلاميذها (ولا يراه تلاميذ المستوى في النهار)
    evening_group = models.ForeignKey(
        "EveningGroup", null=True, blank=True, on_delete=models.SET_NULL, related_name="exams",
        verbose_name="المجموعة المسائية (اختياري)",
        help_text="اتركها فارغة لامتحان المستوى كله. إن اخترت مجموعة مسائية فلا يراه إلا تلاميذها.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "امتحان"
        verbose_name_plural = "الامتحانات"

    def __str__(self):
        return f"{self.title} ({self.target_label} - {self.subject})"

    @property
    def target_label(self):
        return self.evening_group.code if self.evening_group_id else str(self.classe)

    def target_students(self):
        """التلاميذ المعنيون بالامتحان: تلاميذ المجموعة المسائية، أو تلاميذ المستوى."""
        if self.evening_group_id:
            return User.objects.filter(role=User.STUDENT, is_active=True, evening_records__group=self.evening_group_id,
                                       evening_records__is_active=True).distinct()
        return self.classe.students.filter(role=User.STUDENT, is_active=True)

    @classmethod
    def for_student(cls, student):
        groups = student.evening_records.filter(is_active=True).values_list("group_id", flat=True)
        return cls.objects.filter(Q(classe=student.classe_id, evening_group__isnull=True) | Q(evening_group__in=list(groups)))

    @property
    def total_points(self):
        return sum(q.points for q in self.questions.all())

    def is_open_now(self):
        now = timezone.now()
        if not self.is_published:
            return False
        if self.available_from and now < self.available_from:
            return False
        if self.available_until and now > self.available_until:
            return False
        return True


def normalize_written(text):
    """يبسّط الجواب المكتوب للمقارنة: بدون حركات ولا تشكيل ولا علامات، وبدون أدوات التعريف الفرنسية."""
    import unicodedata
    text = unicodedata.normalize("NFKD", str(text or "").lower())
    text = "".join(c for c in text if not unicodedata.combining(c) and not "\u064b" <= c <= "\u0652")
    text = text.replace("œ", "oe").replace("æ", "ae").replace("’", "'")
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ة", "ه"), ("ى", "ي")):
        text = text.replace(a, b)
    text = re.sub(r"[^\w']+", " ", text)
    words = [w for w in re.split(r"[\s']+", text) if w]
    stop = {"le", "la", "les", "l", "un", "une", "des", "du", "de", "d", "ال"}
    words = [w for w in words if w not in stop] or words
    # الجمع: «mitochondries» = «mitochondrie»
    words = [w[:-1] if len(w) > 3 and w.endswith(("s", "x")) else w for w in words]
    words = [{"i": "1", "ii": "2", "iii": "3"}.get(w, w) for w in words]
    return " ".join(words)


def written_matches(answer, accepted):
    """هل الجواب المكتوب يطابق أحد الأجوبة المقبولة (مفصولة بـ |)؟ يُتسامح مع خطأ إملائي صغير."""
    from difflib import SequenceMatcher
    got = normalize_written(answer)
    if not got:
        return False
    for option in str(accepted or "").split("|"):
        want = normalize_written(option)
        if not want:
            continue
        if got == want:
            return True
        # خطأ إملائي صغير مقبول، لكن الكلمات القصيرة والأرقام (I و II) يجب أن تكون نفسها
        short = lambda t: [w for w in t.split() if len(w) <= 3 or any(c.isdigit() for c in w)]
        if len(want) >= 5 and short(got) == short(want) and SequenceMatcher(None, got, want).ratio() >= 0.85:
            return True
    return False


class ActiveQuestionManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(archived=False)


class Question(models.Model):
    LETTERS = ["A", "B", "C", "D", "E", "F"]

    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="questions", verbose_name="الامتحان")
    text = models.TextField("نص السؤال")
    image = models.ImageField("صورة توضيحية", upload_to="questions/", blank=True, null=True)
    points = models.DecimalField("النقاط", max_digits=6, decimal_places=2, default=1)
    # حرف الخيار الصحيح، أو عدة حروف (مثل AD) لسؤال له أكثر من جواب صحيح
    correct_answer = models.CharField(
        "رمز الإجابة الصحيحة", max_length=6, blank=True,
        help_text="حرف الخيار الصحيح: A أو B أو C أو D ... ، أو عدة حروف (مثل AD) إذا كان للسؤال أكثر من جواب صحيح.",
    )
    # سؤال يكتب فيه التلميذ الجواب بنفسه: الأجوبة المقبولة مفصولة بـ |
    written_answer = models.CharField(
        "الجواب المكتوب", max_length=300, blank=True,
        help_text="للسؤال الذي يكتب فيه التلميذ الجواب بنفسه (بدون خيارات). "
                  "يمكن وضع أكثر من جواب مقبول مفصولة بـ | مثل: queue | flagelle",
    )
    order = models.PositiveIntegerField("الترتيب", default=0)
    LEVEL_CHOICES = [("E", "بسيط"), ("M", "متوسط"), ("H", "صعب")]
    level = models.CharField("المستوى", max_length=1, choices=LEVEL_CHOICES, blank=True)
    topic = models.CharField("المحور", max_length=100, blank=True,
                             help_text="الدرس أو المحور الذي يقيسه السؤال (يُستعمل في تقرير التلميذ).")
    # سؤال قديم استُبدل بملف Excel: يُخفى من الامتحان ويبقى لنتائج من أجابوا عليه
    archived = models.BooleanField("مؤرشف", default=False)

    objects = ActiveQuestionManager()
    all_objects = models.Manager()

    class Meta:
        ordering = ["order", "id"]
        base_manager_name = "all_objects"
        verbose_name = "سؤال"
        verbose_name_plural = "الأسئلة"

    def __str__(self):
        return self.text[:60]

    @property
    def is_written(self):
        return bool(self.written_answer.strip())

    @property
    def written_display(self):
        return " / ".join(p.strip() for p in self.written_answer.split("|") if p.strip())

    @property
    def correct_letters(self):
        return sorted({c for c in self.correct_answer.upper() if c in self.LETTERS})

    @property
    def is_multi(self):
        return len(self.correct_letters) > 1

    def clean_selection(self, raw):
        """حروف الخيارات التي اختارها التلميذ، مرتبة وبلا تكرار، ولا تتجاوز عدد الأجوبة الصحيحة."""
        letters = sorted({c for c in str(raw or "").upper() if c in self.LETTERS})
        return "".join(letters[:max(1, len(self.correct_letters))])

    def is_right(self, selected="", text=""):
        if self.is_written:
            return written_matches(text, self.written_answer)
        return bool(selected) and sorted(set(selected.upper())) == self.correct_letters

    def earned(self, selected="", text=""):
        """نقاط التلميذ في السؤال. السؤال متعدد الأجوبة تُقسم نقاطه على أجوبته الصحيحة:
        كل جواب صحيح اختاره التلميذ يأخذ نصيبه (ولا يمكن اختيار أكثر من عدد الأجوبة الصحيحة)."""
        if not self.is_multi:
            return self.points if self.is_right(selected, text) else 0
        correct = set(self.correct_letters)
        hits = len(correct & set(self.clean_selection(selected)))
        return (Decimal(str(self.points)) * hits / len(correct)).quantize(Decimal("0.01"))

    def save(self, *args, **kwargs):
        if not self.topic and self.exam_id:
            from .topics import guess_topic
            self.topic = guess_topic(self.exam.subject.name, self.text)
        super().save(*args, **kwargs)


class Choice(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="choices")
    letter = models.CharField("الرمز", max_length=1)
    text = models.CharField("نص الخيار", max_length=500)

    class Meta:
        ordering = ["letter"]
        unique_together = [("question", "letter")]

    def __str__(self):
        return f"{self.letter}) {self.text}"


class Attempt(models.Model):
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    STATUS_CHOICES = [(IN_PROGRESS, "جارٍ"), (SUBMITTED, "مُسلَّم")]

    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="attempts", verbose_name="الامتحان")
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="attempts", verbose_name="التلميذ")
    status = models.CharField("الحالة", max_length=15, choices=STATUS_CHOICES, default=IN_PROGRESS)
    started_at = models.DateTimeField("بداية", auto_now_add=True)
    submitted_at = models.DateTimeField("التسليم", null=True, blank=True)
    score = models.DecimalField("النقطة", max_digits=7, decimal_places=2, default=0)
    total = models.DecimalField("المجموع", max_digits=7, decimal_places=2, default=0)
    violations = models.PositiveIntegerField("محاولات الخروج", default=0)
    auto_submitted = models.BooleanField("سُلّم تلقائياً", default=False)
    question_order = models.JSONField(default=list, blank=True)

    class Meta:
        unique_together = [("exam", "student")]
        verbose_name = "محاولة"
        verbose_name_plural = "المحاولات"

    def __str__(self):
        return f"{self.student} - {self.exam}"

    @property
    def deadline(self):
        return self.started_at + timezone.timedelta(minutes=self.exam.duration_minutes)

    def seconds_left(self):
        return max(0, int((self.deadline - timezone.now()).total_seconds()))

    def is_expired(self):
        # مهلة 15 ثانية لتغطية تأخر الشبكة عند التسليم
        return timezone.now() > self.deadline + timezone.timedelta(seconds=15)

    def graded_questions(self):
        """أسئلة هذه المحاولة: أسئلة الامتحان الحالية، أو الأسئلة القديمة التي أجاب عليها
        التلميذ إن كانت قد استُبدلت بعد تسليمه."""
        active = self.exam.questions.all()
        if self.status == self.SUBMITTED:
            ids = self.question_order or list(self.answers.values_list("question_id", flat=True))
            if ids and not active.filter(id__in=ids).exists():
                old = Question.all_objects.filter(exam=self.exam, id__in=ids)
                if old.exists():
                    return old
        return active

    def grade(self):
        answers = {a.question_id: a for a in self.answers.all()}
        score = 0
        total = 0
        for q in self.graded_questions():
            total += q.points
            a = answers.get(q.id)
            if a:
                score += q.earned(a.selected, a.text)
        self.score = score
        self.total = total
        return score

    def submit(self, auto=False):
        if self.status == self.SUBMITTED:
            return
        self.grade()
        self.status = self.SUBMITTED
        self.submitted_at = timezone.now()
        self.auto_submitted = auto
        self.save()


class Answer(models.Model):
    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    selected = models.CharField(max_length=6, blank=True)
    text = models.CharField("الجواب المكتوب", max_length=300, blank=True)
    answered_at = models.DateTimeField(null=True, blank=True)
    changes = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = [("attempt", "question")]


# ---------------------------------------------------------------- الحضور والملاحظات

PRESENT, ABSENT, LATE = "P", "A", "L"
ATTENDANCE_CHOICES = [(PRESENT, "حاضر"), (ABSENT, "غائب"), (LATE, "متأخر")]

# ثلاث حصص في اليوم، كل حصة ساعتان، والغياب يُسجَّل لكل حصة
def student_order(prefix=""):
    """ترتيب التلاميذ برقم القيد تصاعدياً (10 بعد 9 وليس بعد 1)، ومن لا رقم له في الآخر."""
    from django.db.models import F
    return [Length(f"{prefix}matricule").asc(nulls_last=True), F(f"{prefix}matricule").asc(nulls_last=True),
            f"{prefix}full_name", f"{prefix}username"]


STUDENT_ORDER = student_order()

SESSION_CHOICES = [(1, "الحصة 1"), (2, "الحصة 2"), (3, "الحصة 3")]
SESSION_TIMES = {1: ("08:00", "10:00"), 2: ("10:00", "12:00"), 3: ("12:00", "14:00")}


class StudentAttendance(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="attendance", verbose_name="التلميذ")
    date = models.DateField("التاريخ")
    session = models.PositiveSmallIntegerField("الحصة", choices=SESSION_CHOICES, default=1)
    status = models.CharField("الحالة", max_length=1, choices=ATTENDANCE_CHOICES, default=PRESENT)
    section = models.ForeignKey(Section, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="الفصل")
    recorded_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("student", "date", "session")]
        ordering = ["-date", "session"]
        verbose_name = "حضور تلميذ"
        verbose_name_plural = "حضور التلاميذ"

    def __str__(self):
        return f"{self.student} {self.date} {self.get_status_display()}"


class StudentNote(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notes", verbose_name="التلميذ")
    date = models.DateField("التاريخ")
    text = models.TextField("الملاحظة")
    author = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        verbose_name = "ملاحظة"
        verbose_name_plural = "الملاحظات اليومية"

    def __str__(self):
        return f"{self.student} {self.date}"


class Teacher(models.Model):
    """أستاذ في لائحة الحضور (مستقل عن حسابات الأساتذة في الامتحانات)."""

    name = models.CharField("اسم الأستاذ", max_length=150, unique=True)
    subject = models.CharField("المادة", max_length=100, blank=True)
    is_active = models.BooleanField("في اللائحة", default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "أستاذ (الحضور)"
        verbose_name_plural = "الأساتذة (الحضور)"

    def __str__(self):
        return self.name


class TeacherAttendance(models.Model):
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE, related_name="attendance", verbose_name="الأستاذ")
    date = models.DateField("التاريخ")
    session = models.PositiveSmallIntegerField("الحصة", choices=SESSION_CHOICES, default=1)
    status = models.CharField("الحالة", max_length=1, choices=ATTENDANCE_CHOICES, default=PRESENT)
    section = models.ForeignKey(Section, null=True, blank=True, on_delete=models.SET_NULL,
                                related_name="teacher_attendance", verbose_name="القسم")
    note = models.CharField("ملاحظة", max_length=255, blank=True)
    recorded_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("teacher", "date", "session")]
        ordering = ["-date", "session"]
        verbose_name = "حضور أستاذ"
        verbose_name_plural = "حضور الأساتذة"


# ---------------------------------------------------------------- المكتبة: توزيع الكتب

BOOK_SUBJECTS = [("math", "الرياضيات"), ("phys", "الفيزياء"), ("sci", "العلوم"), ("isl", "التربية الإسلامية")]
BOOK_PARTS = [(1, "النسخة 1"), (2, "النسخة 2")]
LIBRARY_LEVELS = ["3AS", "4AS", "5MA", "5SN", "6MA", "6SN", "7MA", "7SN"]


class BookStock(models.Model):
    """عدد الكتب الموجودة لمستوى (كل فصول 7SN مثلاً تشترك في نفس الكتب) من مادة ونسخة."""
    classe = models.ForeignKey(Classe, on_delete=models.CASCADE, related_name="book_stock", verbose_name="المستوى")
    subject = models.CharField("المادة", max_length=10, choices=BOOK_SUBJECTS)
    part = models.PositiveSmallIntegerField("النسخة", choices=BOOK_PARTS)
    quantity = models.PositiveIntegerField("العدد", default=0)

    class Meta:
        verbose_name = "مخزون كتب"
        verbose_name_plural = "مخزون الكتب"
        constraints = [models.UniqueConstraint(fields=["classe", "subject", "part"], name="uniq_book_stock_level")]


class BookDelivery(models.Model):
    """تسليم نسخة كتاب لتلميذ. الفصل يُحفظ وقت التسليم لأن الكتاب خرج من مخزونه."""
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="books", verbose_name="التلميذ")
    subject = models.CharField("المادة", max_length=10, choices=BOOK_SUBJECTS)
    part = models.PositiveSmallIntegerField("النسخة", choices=BOOK_PARTS)
    section = models.ForeignKey(Section, null=True, on_delete=models.SET_NULL, related_name="book_deliveries", verbose_name="الفصل")
    date = models.DateField("تاريخ التسليم")
    delivered_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        verbose_name = "تسليم كتاب"
        verbose_name_plural = "تسليم الكتب"
        constraints = [models.UniqueConstraint(fields=["student", "subject", "part"], name="uniq_book_delivery")]


class ActivityLog(models.Model):
    """حدث قام به مستخدم في التطبيق (دخول، إضافة، تعديل، حذف، امتحان...)."""

    LOGIN = "login"
    LOGOUT = "logout"
    FAILED = "failed"
    ADD = "add"
    EDIT = "edit"
    DELETE = "delete"
    IMPORT = "import"
    EXAM = "exam"
    OTHER = "other"
    KIND_CHOICES = [
        (LOGIN, "دخول"),
        (LOGOUT, "خروج"),
        (FAILED, "محاولة دخول فاشلة"),
        (ADD, "إضافة"),
        (EDIT, "تعديل"),
        (DELETE, "حذف"),
        (IMPORT, "استيراد"),
        (EXAM, "امتحان"),
        (OTHER, "أخرى"),
    ]

    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="activities")
    # يُحفظ الاسم والدور نصاً حتى يبقى السجل مقروءاً لو حُذف المستخدم
    username = models.CharField("المستخدم", max_length=150)
    role = models.CharField("الدور", max_length=10, blank=True)
    kind = models.CharField("النوع", max_length=10, choices=KIND_CHOICES, default=OTHER)
    action = models.CharField("العملية", max_length=200)
    target = models.CharField("على", max_length=255, blank=True)
    path = models.CharField("الصفحة", max_length=255, blank=True)
    ip = models.GenericIPAddressField("عنوان IP", null=True, blank=True)
    created_at = models.DateTimeField("الوقت", default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "حدث"
        verbose_name_plural = "سجل النشاط"

    def __str__(self):
        return f"{self.username}: {self.action}"


class TimetableEntry(models.Model):
    """حصة واحدة في الجدول الزمني لقسم (فصل)، مستوردة من الجدول العام."""

    DAYS = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]

    section_code = models.CharField("القسم", max_length=10, db_index=True)
    day = models.PositiveSmallIntegerField("اليوم")  # 0 = الاثنين
    slot_order = models.PositiveSmallIntegerField("ترتيب الحصة")
    slot = models.CharField("التوقيت", max_length=20)
    code = models.CharField("الرمز في الملف", max_length=40)
    subject_key = models.CharField("رمز المادة", max_length=5, blank=True)
    subject = models.CharField("المادة", max_length=60)
    teacher = models.CharField("الأستاذ", max_length=200, blank=True)
    created_at = models.DateTimeField("تاريخ الاستيراد", default=timezone.now)

    class Meta:
        ordering = ["section_code", "day", "slot_order"]
        verbose_name = "حصة"
        verbose_name_plural = "الجدول الزمني"

    def __str__(self):
        return f"{self.section_code} {self.DAYS[self.day]} {self.slot}: {self.subject}"


# مواد الدروس المصوّرة: نفس رموز الجدول الزمني
LESSON_SUBJECTS = [
    ("AR", "اللغة العربية"), ("FR", "اللغة الفرنسية"), ("AN", "اللغة الإنجليزية"),
    ("M", "الرياضيات"), ("PC", "الفيزياء والكيمياء"), ("SN", "العلوم الطبيعية"),
    ("HG", "التاريخ والجغرافيا"), ("IR", "التربية الإسلامية"), ("IC", "التربية المدنية"),
    ("PH", "الفلسفة"), ("TI", "المعلوماتية والتكنولوجيا"),
]


class LessonScope(models.Model):
    """مادة في فصل يحق لمسجّل الدروس تصوير دروسها (يحددها المشرف)."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="lesson_scopes")
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name="lesson_scopes")
    subject = models.CharField("المادة", max_length=5, choices=LESSON_SUBJECTS)

    class Meta:
        unique_together = [("user", "section", "subject")]
        ordering = ["section__order", "section__code", "subject"]
        verbose_name = "صلاحية تسجيل درس"
        verbose_name_plural = "صلاحيات تسجيل الدروس"

    def __str__(self):
        return f"{self.user}: {self.section} {self.get_subject_display()}"


class Lesson(models.Model):
    """درس مصوّر: تاريخه وصفحاته. دروس نفس المادة والفصل تُجمع في ملف PDF واحد."""

    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name="lessons", verbose_name="الفصل")
    subject = models.CharField("المادة", max_length=5, choices=LESSON_SUBJECTS)
    date = models.DateField("تاريخ الدرس")
    title = models.CharField("عنوان الدرس", max_length=200, blank=True)
    uploaded_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="lessons_uploaded", verbose_name="سجّله")
    created_at = models.DateTimeField("وقت التسجيل", default=timezone.now)

    class Meta:
        ordering = ["date", "created_at"]
        verbose_name = "درس مصوّر"
        verbose_name_plural = "الدروس المصوّرة"

    def __str__(self):
        return f"{self.section} {self.get_subject_display()} {self.date}"


class LessonPage(models.Model):
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="pages")
    image = models.ImageField("صورة الصفحة", upload_to="lessons/%Y/%m/")
    order = models.PositiveSmallIntegerField("الترتيب", default=0)

    class Meta:
        ordering = ["order", "id"]


# ---------------------------------------------------------------- الحصص المسائية

def wa_link_for(number):
    digits = "".join(ch for ch in (number or "") if ch.isdigit())
    if not digits:
        return ""
    if len(digits) == 8:  # رقم موريتاني بدون رمز الدولة
        digits = "222" + digits
    return f"https://wa.me/{digits}"


class EveningGroup(models.Model):
    """قسم من أقسام الحصص المسائية (مثل G1_7MA)، مستقل عن فصول النهار."""

    code = models.CharField("اسم القسم", max_length=30, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["code"]
        verbose_name = "قسم مسائي"
        verbose_name_plural = "أقسام الحصص المسائية"

    def __str__(self):
        return self.code


class EveningStudent(models.Model):
    group = models.ForeignKey(EveningGroup, on_delete=models.CASCADE, related_name="students", verbose_name="القسم")
    matricule = models.CharField("رقم القيد", max_length=30)
    full_name = models.CharField("الاسم", max_length=150)
    registered_on = models.DateField("تاريخ التسجيل", null=True, blank=True)
    guardian_phone = models.CharField("هاتف الوكيل", max_length=30, blank=True)
    whatsapp = models.CharField("الواتساب", max_length=30, blank=True)
    is_active = models.BooleanField("مسجّل", default=True)
    # حساب الدخول لإنجاز امتحانات المجموعة: حساب التلميذ في المدرسة إن وُجد، وإلا حساب جديد برقم القيد
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="evening_records",
                             verbose_name="الحساب")

    class Meta:
        unique_together = [("group", "matricule")]
        ordering = [Length("matricule"), "matricule", "full_name"]
        verbose_name = "تلميذ مسائي"
        verbose_name_plural = "تلاميذ الحصص المسائية"

    def __str__(self):
        return self.full_name

    @property
    def wa_link(self):
        return wa_link_for(self.whatsapp)

    def ensure_account(self):
        """يربط التلميذ بحساب: حسابه في المدرسة (نفس رقم القيد)، وإلا يُنشأ حساب
        اسم المستخدم وكلمة المرور فيه رقم القيد (بدون مستوى ولا فصل، فلا يظهر في لوائح النهار)."""
        if self.user_id:
            return self.user
        user = User.objects.filter(matricule=self.matricule).first() or User.objects.filter(username=self.matricule).first()
        if user and not user.is_student:
            return None
        if user is None:
            user = User(username=self.matricule, matricule=self.matricule, role=User.STUDENT, full_name=self.full_name,
                        must_change_password=True)
            user.set_password(self.matricule)
            user.save()
        self.user = user
        self.save(update_fields=["user"])
        return user


class EveningAttendance(models.Model):
    student = models.ForeignKey(EveningStudent, on_delete=models.CASCADE, related_name="attendance")
    date = models.DateField("التاريخ")
    status = models.CharField("الحالة", max_length=1, choices=ATTENDANCE_CHOICES, default=PRESENT)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("student", "date")]
        ordering = ["-date"]
        verbose_name = "حضور مسائي"
        verbose_name_plural = "حضور الحصص المسائية"


class EveningTeacher(models.Model):
    """أستاذ في الحصص المسائية: له مجموعة واحدة وأربع ساعات متتالية معها."""

    name = models.CharField("اسم الأستاذ", max_length=150, unique=True)
    group = models.ForeignKey(EveningGroup, null=True, blank=True, on_delete=models.SET_NULL,
                              related_name="teachers", verbose_name="المجموعة")
    is_active = models.BooleanField("في اللائحة", default=True)

    class Meta:
        ordering = ["id"]
        verbose_name = "أستاذ مسائي"
        verbose_name_plural = "أساتذة الحصص المسائية"

    def __str__(self):
        return self.name


EVENING_HOURS = 4


class EveningTeacherAttendance(models.Model):
    teacher = models.ForeignKey(EveningTeacher, on_delete=models.CASCADE, related_name="attendance")
    date = models.DateField("التاريخ")
    status = models.CharField("الحالة", max_length=1, choices=ATTENDANCE_CHOICES, default=PRESENT)
    group = models.ForeignKey(EveningGroup, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    hours = models.PositiveSmallIntegerField("عدد الساعات", default=EVENING_HOURS)
    note = models.CharField("ملاحظة", max_length=255, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("teacher", "date")]
        ordering = ["-date"]
        verbose_name = "حضور أستاذ مسائي"
        verbose_name_plural = "حضور أساتذة الحصص المسائية"


# ---------------------------------------------------------------- الفيديوهات التعليمية

YOUTUBE_ID = re.compile(r"(?:youtu\.be/|youtube\.com/(?:watch\?(?:.*&)?v=|embed/|shorts/|live/))([\w-]{11})")


class Video(models.Model):
    """فيديو تعليمي لمستوى ومادة، مرتّب حسب رقم الدرس. إما ملف مرفوع أو رابط يوتيوب."""

    classe = models.ForeignKey(Classe, on_delete=models.CASCADE, related_name="videos", verbose_name="القسم")
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="videos", verbose_name="المادة")
    lesson_number = models.PositiveSmallIntegerField("رقم الدرس", default=1)
    lesson = models.CharField("عنوان الدرس", max_length=150)
    title = models.CharField("عنوان الفيديو", max_length=200, blank=True,
                             help_text="اختياري، مثل: الجزء 1، تمارين محلولة…")
    order = models.PositiveSmallIntegerField("ترتيب الفيديو داخل الدرس", default=1)
    youtube_url = models.URLField("رابط يوتيوب", blank=True)
    file = models.FileField("ملف الفيديو", upload_to="videos/%Y/%m/", blank=True)
    added_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["classe__code", "subject__name", "lesson_number", "order", "id"]
        verbose_name = "فيديو تعليمي"
        verbose_name_plural = "الفيديوهات التعليمية"

    def __str__(self):
        return self.display_title

    @property
    def display_title(self):
        return self.title or self.lesson

    @property
    def youtube_id(self):
        m = YOUTUBE_ID.search(self.youtube_url or "")
        return m.group(1) if m else ""

    @property
    def thumbnail(self):
        return f"https://i.ytimg.com/vi/{self.youtube_id}/mqdefault.jpg" if self.youtube_id else ""

    @classmethod
    def classes_for_student(cls, student):
        """مستوى التلميذ، ومستوى كل مجموعة مسائية هو فيها (G1_7SN ← 7SN)."""
        codes = set()
        if student.classe_id:
            codes.add(student.classe.code)
        for r in student.evening_records.filter(is_active=True).select_related("group"):
            codes.add(r.group.code.rsplit("_", 1)[-1].upper())
        return Classe.objects.filter(code__in=codes)
