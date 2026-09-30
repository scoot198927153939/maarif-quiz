from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Answer, Attempt, Choice, Classe, Exam, Question, Subject, User


@admin.register(User)
class QuizUserAdmin(UserAdmin):
    list_display = ("username", "full_name", "role", "classe", "is_active")
    list_filter = ("role", "classe", "is_active")
    search_fields = ("username", "full_name")
    fieldsets = UserAdmin.fieldsets + (
        ("المدرسة", {"fields": ("role", "full_name", "classe", "teaching_classes", "teaching_subjects")}),
    )
    filter_horizontal = ("teaching_classes", "teaching_subjects", "groups", "user_permissions")


@admin.register(Classe)
class ClasseAdmin(admin.ModelAdmin):
    list_display = ("code", "order")


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
