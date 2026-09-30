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
    ROLE_CHOICES = [
        (ADMIN, "مشرف"),
        (TEACHER, "أستاذ"),
        (STUDENT, "تلميذ"),
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

    class Meta:
        verbose_name = "مستخدم"
        verbose_name_plural = "المستخدمون"

    def __str__(self):
        return self.full_name or self.username

    @property
    def is_admin_role(self):
        return self.role == self.ADMIN or self.is_superuser

    @property
    def is_teacher(self):
        return self.role == self.TEACHER and not self.is_superuser

    @property
    def is_student(self):
        return self.role == self.STUDENT and not self.is_superuser

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

    class Meta:
        ordering = ["order", "id"]
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

    def grade(self):
        answers = {a.question_id: a.selected for a in self.answers.all()}
        score = 0
        total = 0
        for q in self.exam.questions.all():
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
