from django.contrib.auth.models import AbstractUser
from django.db import models
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
    ROLE_CHOICES = [
        (ADMIN, "مشرف"),
        (TEACHER, "أستاذ"),
        (STUDENT, "تلميذ"),
        (SUPERVISOR, "مراقب"),
        (LIBRARIAN, "مسؤول المكتبة"),
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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "امتحان"
        verbose_name_plural = "الامتحانات"

    def __str__(self):
        return f"{self.title} ({self.classe} - {self.subject})"

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


class ActiveQuestionManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(archived=False)


class Question(models.Model):
    LETTERS = ["A", "B", "C", "D", "E", "F"]

    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="questions", verbose_name="الامتحان")
    text = models.TextField("نص السؤال")
    image = models.ImageField("صورة توضيحية", upload_to="questions/", blank=True, null=True)
    points = models.DecimalField("النقاط", max_digits=6, decimal_places=2, default=1)
    correct_answer = models.CharField(
        "رمز الإجابة الصحيحة", max_length=1,
        help_text="حرف الخيار الصحيح: A أو B أو C أو D ...",
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
        answers = {a.question_id: a.selected for a in self.answers.all()}
        score = 0
        total = 0
        for q in self.graded_questions():
            total += q.points
            if answers.get(q.id, "").upper() == q.correct_answer.upper():
                score += q.points
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
    selected = models.CharField(max_length=1, blank=True)
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
    from django.db.models.functions import Length
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
