from django.conf import settings
from django.shortcuts import redirect
from django.urls import resolve, Resolver404

from .models import Attempt

# الصفحات المسموح بها للتلميذ أثناء امتحان جارٍ
EXAM_URL_NAMES = {"take_exam", "save_answer", "submit_exam", "report_violation"}


class ExamLockMiddleware:
    """يمنع التلميذ من فتح أي صفحة أخرى في التطبيق ما دام له امتحان جارٍ."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        path = request.path
        if (
            user is not None and user.is_authenticated and user.is_student
            and not path.startswith((settings.STATIC_URL, settings.MEDIA_URL))
        ):
            attempt = (
                Attempt.objects.select_related("exam")
                .filter(student=user, status=Attempt.IN_PROGRESS)
                .first()
            )
            if attempt:
                if attempt.is_expired():
                    attempt.submit(auto=True)
                else:
                    try:
                        name = resolve(path).url_name
                    except Resolver404:
                        name = None
                    if name not in EXAM_URL_NAMES:
                        return redirect("take_exam", exam_id=attempt.exam_id)
        return self.get_response(request)
