from django.urls import path

from . import attendance, views

urlpatterns = [
    path("", views.home, name="home"),
    # التلميذ
    path("student/", views.student_dashboard, name="student_dashboard"),
    path("exam/<int:exam_id>/", views.exam_intro, name="exam_intro"),
    path("exam/<int:exam_id>/take/", views.take_exam, name="take_exam"),
    path("exam/<int:exam_id>/save/", views.save_answer, name="save_answer"),
    path("exam/<int:exam_id>/violation/", views.report_violation, name="report_violation"),
    path("exam/<int:exam_id>/submit/", views.submit_exam, name="submit_exam"),
    path("exam/<int:exam_id>/result/", views.attempt_result, name="attempt_result"),
    # الأستاذ
    path("teacher/", views.teacher_dashboard, name="teacher_dashboard"),
    path("teacher/exams/new/", views.exam_create, name="exam_create"),
    path("teacher/exams/<int:exam_id>/", views.exam_detail, name="exam_detail"),
    path("teacher/exams/<int:exam_id>/edit/", views.exam_edit, name="exam_edit"),
    path("teacher/exams/<int:exam_id>/delete/", views.exam_delete, name="exam_delete"),
    path("teacher/exams/<int:exam_id>/publish/", views.exam_toggle_publish, name="exam_toggle_publish"),
    path("teacher/exams/<int:exam_id>/import/", views.exam_import, name="exam_import"),
    path("teacher/exams/<int:exam_id>/results/", views.exam_results, name="exam_results"),
    path("teacher/exams/<int:exam_id>/questions/new/", views.question_add, name="question_add"),
    path("teacher/questions/<int:question_id>/edit/", views.question_edit, name="question_edit"),
    path("teacher/questions/<int:question_id>/delete/", views.question_delete, name="question_delete"),
    path("teacher/attempts/<int:attempt_id>/reset/", views.attempt_reset, name="attempt_reset"),
    path("teacher/attempts/<int:attempt_id>/report/", views.attempt_report, name="attempt_report"),
    path("teacher/results/", views.class_results, name="class_results"),
    path("teacher/questions-template.xlsx", views.questions_template, name="questions_template"),
    # المشرف
    path("manage/", views.admin_dashboard, name="admin_dashboard"),
    path("manage/users/", views.user_list, name="user_list"),
    path("manage/users/new/", views.user_create, name="user_create"),
    path("manage/users/<int:user_id>/", views.user_edit, name="user_edit"),
    path("manage/users/<int:user_id>/delete/", views.user_delete, name="user_delete"),
    path("manage/users/import/", views.students_import, name="students_import"),
    path("manage/students-template.xlsx", views.students_template, name="students_template"),
    # الحضور والملاحظات (المراقب والمشرف)
    path("attendance/", attendance.attendance_home, name="attendance_home"),
    path("attendance/section/<int:section_id>/", attendance.section_roll, name="section_roll"),
    path("attendance/section/<int:section_id>/report/", attendance.section_report, name="section_report"),
    path("attendance/students/", attendance.students_list, name="students_list"),
    path("attendance/student/<int:student_id>/", attendance.student_file, name="student_file"),
    path("attendance/notes/<int:note_id>/delete/", attendance.note_delete, name="note_delete"),
    path("attendance/teachers/", attendance.teacher_roll, name="teacher_roll"),
    path("attendance/teachers/monthly/", attendance.teacher_monthly, name="teacher_monthly"),
    path("attendance/teachers/<int:teacher_id>/", attendance.teacher_file, name="teacher_file"),
    path("attendance/import/students/", attendance.roster_import, name="roster_import"),
    path("attendance/import/teachers/", attendance.teachers_import, name="teachers_import"),
    path("attendance/students-list-template.xlsx", attendance.roster_template, name="roster_template"),
    path("attendance/teachers-list-template.xlsx", attendance.teachers_template, name="teachers_template"),
]
