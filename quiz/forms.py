from django import forms

from .models import Classe, Exam, Question, Subject, User

N_CHOICES = 4


class DateTimeInput(forms.DateTimeInput):
    input_type = "datetime-local"

    def __init__(self, **kwargs):
        super().__init__(format="%Y-%m-%dT%H:%M", **kwargs)


class ExamForm(forms.ModelForm):
    class Meta:
        model = Exam
        fields = [
            "title", "classe", "subject", "duration_minutes", "available_from", "available_until",
            "instructions", "is_published", "show_result", "shuffle_questions",
        ]
        widgets = {
            "available_from": DateTimeInput(),
            "available_until": DateTimeInput(),
            "instructions": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["classe"].queryset = user.allowed_classes()
        self.fields["subject"].queryset = user.allowed_subjects()

    def clean(self):
        data = super().clean()
        classe, subject = data.get("classe"), data.get("subject")
        if classe and subject and not subject.classes.filter(pk=classe.pk).exists():
            raise forms.ValidationError(f"مادة «{subject}» لا تُدرَّس في القسم {classe}.")
        start, end = data.get("available_from"), data.get("available_until")
        if start and end and end <= start:
            raise forms.ValidationError("تاريخ النهاية يجب أن يكون بعد تاريخ البداية.")
        return data


class QuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = ["text", "image", "points", "correct_answer", "level", "topic"]
        widgets = {"text": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        letters = Question.LETTERS[:N_CHOICES]
        self.fields["correct_answer"] = forms.ChoiceField(
            label="رمز الإجابة الصحيحة", choices=[(l, l) for l in letters],
        )
        existing = {}
        if self.instance.pk:
            existing = {c.letter: c.text for c in self.instance.choices.all()}
        for l in letters:
            self.fields[f"choice_{l}"] = forms.CharField(
                label=f"الخيار {l}", required=l in ("A", "B"), max_length=500,
                initial=existing.get(l, ""),
            )
        if self.instance.pk:
            self.initial["correct_answer"] = self.instance.correct_answer

    def choice_fields(self):
        return [self[f"choice_{l}"] for l in Question.LETTERS[:N_CHOICES]]

    def clean(self):
        data = super().clean()
        correct = data.get("correct_answer")
        if correct and not data.get(f"choice_{correct}"):
            self.add_error("correct_answer", "الخيار المحدد كإجابة صحيحة فارغ.")
        return data

    def save(self, commit=True):
        question = super().save(commit=commit)
        question.choices.all().delete()
        for l in Question.LETTERS[:N_CHOICES]:
            text = self.cleaned_data.get(f"choice_{l}")
            if text:
                question.choices.create(letter=l, text=text)
        return question


class ImportFileForm(forms.Form):
    file = forms.FileField(label="ملف Excel (‎.xlsx)")

    def clean_file(self):
        f = self.cleaned_data["file"]
        if not f.name.lower().endswith((".xlsx", ".xlsm")):
            raise forms.ValidationError("يجب أن يكون الملف بصيغة ‎.xlsx")
        return f


class UserForm(forms.ModelForm):
    password = forms.CharField(
        label="كلمة المرور", required=False, widget=forms.PasswordInput(render_value=False),
        help_text="اتركها فارغة للإبقاء على كلمة المرور الحالية.",
    )

    class Meta:
        model = User
        fields = [
            "username", "full_name", "role", "section", "classe", "matricule",
            "guardian_phone", "whatsapp", "guardian_phone2",
            "teaching_classes", "teaching_subjects", "supervised_sections", "is_active",
        ]
        widgets = {
            "teaching_classes": forms.CheckboxSelectMultiple,
            "teaching_subjects": forms.CheckboxSelectMultiple,
            "supervised_sections": forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].help_text = ""
        self.fields["classe"].label = "المستوى (للتلميذ)"
        self.fields["classe"].help_text = "يُحدَّد تلقائياً من الفصل إذا اخترته."
        if not self.instance.pk:
            self.fields["password"].required = True
            self.fields["password"].help_text = ""

    def clean(self):
        data = super().clean()
        role = data.get("role")
        if role == User.STUDENT and not data.get("classe") and not data.get("section"):
            self.add_error("section", "يجب تحديد قسم التلميذ.")
        if role == User.SUPERVISOR and not data.get("supervised_sections"):
            self.add_error("supervised_sections", "اختر الأقسام التي يراقبها.")
        return data

    def save(self, commit=True):
        user = super().save(commit=False)
        if self.cleaned_data.get("password"):
            user.set_password(self.cleaned_data["password"])
        if user.role != User.STUDENT:
            user.classe = None
            user.section = None
            user.matricule = None
        user.is_staff = user.role == User.ADMIN
        if commit:
            user.save()
            self.save_m2m()
            if user.role != User.TEACHER:
                user.teaching_classes.clear()
                user.teaching_subjects.clear()
            if user.role != User.SUPERVISOR:
                user.supervised_sections.clear()
        return user


class ResultsFilterForm(forms.Form):
    classe = forms.ModelChoiceField(queryset=Classe.objects.none(), label="القسم", required=False)
    subject = forms.ModelChoiceField(queryset=Subject.objects.none(), label="المادة", required=False)

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["classe"].queryset = user.allowed_classes()
        self.fields["subject"].queryset = user.allowed_subjects()
