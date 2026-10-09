from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import (
    Answer, Attempt, Choice, Classe, Exam, Question, Section, StudentAttendance, StudentNote, Subject,
    Teacher, TeacherAttendance, User,
)


@admin.register(User)
class QuizUserAdmin(UserAdmin):
    list_display = ("username", "full_name", "role", "classe", "is_active")
    list_filter = ("role", "classe", "is_active")
    search_fields = ("username", "full_name")
    fieldsets = UserAdmin.fieldsets + (
        ("المدرسة", {"fields": (
            "role", "full_name", "section", "classe", "matricule", "guardian_phone", "whatsapp", "guardian_phone2",
            "teaching_classes", "teaching_subjects", "supervised_sections",
        )}),
    )
    filter_horizontal = ("teaching_classes", "teaching_subjects", "supervised_sections", "groups", "user_permissions")


@admin.register(Classe)
class ClasseAdmin(admin.ModelAdmin):
    list_display = ("code", "order")


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ("code", "classe", "order")
    list_filter = ("classe",)


@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display = ("name", "subject", "is_active")
    search_fields = ("name",)


admin.site.register(StudentAttendance)
admin.site.register(StudentNote)
admin.site.register(TeacherAttendance)


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("name",)
    filter_horizontal = ("classes",)


class ChoiceInline(admin.TabularInline):
    model = Choice
    extra = 0


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("__str__", "exam", "points", "correct_answer")
    list_filter = ("exam__classe", "exam__subject")
    inlines = [ChoiceInline]


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ("title", "classe", "subject", "teacher", "is_published", "created_at")
    list_filter = ("classe", "subject", "is_published")


class AnswerInline(admin.TabularInline):
    model = Answer
    extra = 0


@admin.register(Attempt)
class AttemptAdmin(admin.ModelAdmin):
    list_display = ("student", "exam", "status", "score", "total", "violations", "submitted_at")
    list_filter = ("status", "exam__classe", "exam__subject")
    inlines = [AnswerInline]
