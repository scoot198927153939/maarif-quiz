from django.conf import settings
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path, re_path
from django.views.static import serve

admin.site.site_header = "إدارة Quiz El Maarif"
admin.site.site_title = "Quiz El Maarif"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("login/", auth_views.LoginView.as_view(redirect_authenticated_user=True), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", include("quiz.urls")),
    # صور الأسئلة (تُخدم من Django حتى بعد النشر، مناسب لمدرسة واحدة)
    re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
]
