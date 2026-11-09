"""الفيديوهات التعليمية: الأستاذ أو المشرف يضيف فيديوهات لكل قسم ومادة مرتّبة حسب الدروس،
ويرى كل تلميذ فيديوهات قسمه فقط."""
import mimetypes
import os
import re
from itertools import groupby

from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import Classe, Subject, User, Video
from .views import role_required, staff_required

videos_viewer = role_required("admin", "teacher", "student")

VIDEO_EXTENSIONS = (".mp4", ".webm", ".m4v", ".mov", ".ogv")
MAX_VIDEO_MB = 500


class VideoForm(forms.ModelForm):
    class Meta:
        model = Video
        fields = ["classe", "subject", "lesson_number", "lesson", "title", "order", "youtube_url", "file"]

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["classe"].queryset = user.allowed_classes()
        self.fields["subject"].queryset = user.allowed_subjects()
        self.fields["lesson"].widget.attrs["list"] = "lesson-names"
        self.fields["youtube_url"].widget.attrs.update({"dir": "ltr", "placeholder": "https://youtu.be/…"})
        self.fields["file"].widget.attrs["accept"] = "video/*"

    def clean_file(self):
        f = self.cleaned_data.get("file")
        if f and hasattr(f, "size") and getattr(f, "content_type", None) is not None:
            if not f.name.lower().endswith(VIDEO_EXTENSIONS):
                raise forms.ValidationError("صيغة الفيديو غير مقبولة. استعمل ملف MP4.")
            if f.size > MAX_VIDEO_MB * 1024 * 1024:
                raise forms.ValidationError(
                    f"الفيديو أكبر من {MAX_VIDEO_MB} ميغا. ضعه على يوتيوب (غير مُدرج) وألصق الرابط.")
        return f

    def clean(self):
        data = super().clean()
        url = data.get("youtube_url")
        if url and not Video(youtube_url=url).youtube_id:
            self.add_error("youtube_url", "هذا ليس رابط فيديو يوتيوب صحيحاً.")
        if not url and not data.get("file"):
            self.add_error("file", "ارفع ملف الفيديو أو ألصق رابط يوتيوب.")
        classe, subject = data.get("classe"), data.get("subject")
        if classe and subject and not subject.classes.filter(pk=classe.pk).exists():
            self.add_error("subject", f"هذه المادة لا تُدرَّس في {classe}.")
        return data


def _can_manage(user, video):
    return user.is_admin_role or (
        user.is_teacher
        and user.teaching_classes.filter(pk=video.classe_id).exists()
        and user.teaching_subjects.filter(pk=video.subject_id).exists()
    )


def _can_watch(user, video):
    if user.is_student:
        return Video.classes_for_student(user).filter(pk=video.classe_id).exists()
    return user.is_admin_role or user.is_teacher and user.teaching_classes.filter(pk=video.classe_id).exists()


def _shelves(videos):
    """[(المادة، [(رقم الدرس، عنوان الدرس، [فيديوهات])])] بالترتيب."""
    shelves = []
    for subject, items in groupby(sorted(videos, key=lambda v: (v.subject.name, v.lesson_number, v.order, v.id)),
                                  key=lambda v: v.subject):
        lessons = []
        for (num, _), vids in groupby(items, key=lambda v: (v.lesson_number, v.lesson.strip())):
            vids = list(vids)
            lessons.append({"number": num, "title": vids[0].lesson, "videos": vids})
        shelves.append({"subject": subject, "lessons": lessons, "count": sum(len(l["videos"]) for l in lessons)})
    return shelves


@videos_viewer
def videos_home(request):
    user = request.user
    classes = list(Video.classes_for_student(user) if user.is_student else user.allowed_classes())
    code = request.GET.get("c")
    current = next((c for c in classes if c.code == code), classes[0] if classes else None)
    videos = Video.objects.none()
    if current:
        videos = Video.objects.filter(classe=current).select_related("subject", "classe")
        if user.is_teacher and not user.is_admin_role:
            videos = videos.filter(subject__in=user.teaching_subjects.all())
    shelves = _shelves(videos)
    for sh in shelves:
        for l in sh["lessons"]:
            for v in l["videos"]:
                v.can_manage = _can_manage(user, v)
    return render(request, "quiz/videos/home.html", {
        "classes": classes, "current": current, "shelves": shelves,
        "can_add": user.is_admin_role or user.is_teacher,
    })


def _form_page(request, form, video=None):
    lessons = (Video.objects.filter(classe__in=request.user.allowed_classes())
               .order_by("lesson").values_list("lesson", flat=True).distinct())
    return render(request, "quiz/videos/form.html", {"form": form, "video": video, "lesson_names": lessons,
                                                     "max_mb": MAX_VIDEO_MB})


@staff_required
def video_new(request):
    initial = {}
    c = Classe.objects.filter(code=request.GET.get("c")).first()
    if c:
        initial["classe"] = c
    s = Subject.objects.filter(pk=request.GET.get("s") or 0).first()
    if s:
        initial["subject"] = s
    if request.GET.get("n"):
        last = Video.objects.filter(classe=c, subject=s, lesson_number=request.GET.get("n")).last()
        if last:
            initial.update(lesson_number=last.lesson_number, lesson=last.lesson, order=last.order + 1)
    form = VideoForm(request.user, request.POST or None, request.FILES or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        video = form.save(commit=False)
        video.added_by = request.user
        video.save()
        messages.success(request, f"تمت إضافة الفيديو «{video.display_title}».")
        return redirect(f"{_home_url()}?c={video.classe.code}#s{video.subject_id}")
    return _form_page(request, form)


@staff_required
def video_edit(request, video_id):
    video = get_object_or_404(Video, pk=video_id)
    if not _can_manage(request.user, video):
        raise PermissionDenied
    old_file = video.file.name
    form = VideoForm(request.user, request.POST or None, request.FILES or None, instance=video)
    if request.method == "POST" and form.is_valid():
        video = form.save()
        if old_file and video.file.name != old_file:
            video.file.storage.delete(old_file)
        messages.success(request, "تم حفظ التعديل.")
        return redirect(f"{_home_url()}?c={video.classe.code}#s{video.subject_id}")
    return _form_page(request, form, video)


@staff_required
@require_POST
def video_delete(request, video_id):
    video = get_object_or_404(Video, pk=video_id)
    if not _can_manage(request.user, video):
        raise PermissionDenied
    code = video.classe.code
    if video.file:
        video.file.delete(save=False)
    video.delete()
    messages.success(request, "تم حذف الفيديو.")
    return redirect(f"{_home_url()}?c={code}")


def _home_url():
    from django.urls import reverse
    return reverse("videos_home")


@videos_viewer
def video_watch(request, video_id):
    video = get_object_or_404(Video.objects.select_related("classe", "subject"), pk=video_id)
    if not _can_watch(request.user, video):
        raise PermissionDenied
    playlist = list(Video.objects.filter(classe=video.classe, subject=video.subject).select_related("subject"))
    i = next(k for k, v in enumerate(playlist) if v.pk == video.pk)
    return render(request, "quiz/videos/watch.html", {
        "video": video, "shelf": _shelves(playlist)[0],
        "prev": playlist[i - 1] if i > 0 else None,
        "next": playlist[i + 1] if i + 1 < len(playlist) else None,
        "can_manage": _can_manage(request.user, video),
    })


RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")
CHUNK = 512 * 1024


def _read(path, start, length):
    with open(path, "rb") as f:
        f.seek(start)
        while length > 0:
            data = f.read(min(CHUNK, length))
            if not data:
                break
            length -= len(data)
            yield data


@videos_viewer
def video_file(request, video_id):
    """يرسل ملف الفيديو بأجزاء (Range) حتى يعمل التقديم والترجيع في المتصفح والهاتف."""
    video = get_object_or_404(Video, pk=video_id)
    if not _can_watch(request.user, video) or not video.file:
        raise PermissionDenied
    try:
        path = video.file.path
        size = os.path.getsize(path)
    except (OSError, NotImplementedError):
        raise Http404
    ctype = mimetypes.guess_type(path)[0] or "video/mp4"
    m = RANGE_RE.match(request.headers.get("Range", ""))
    if not m or not (m.group(1) or m.group(2)):
        response = FileResponse(open(path, "rb"), content_type=ctype)
        response["Accept-Ranges"] = "bytes"
        return response
    if m.group(1):
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) else size - 1
    else:  # آخر N بايت
        start, end = max(0, size - int(m.group(2))), size - 1
    end = min(end, size - 1)
    if start > end:
        response = StreamingHttpResponse(iter(()), status=416)
        response["Content-Range"] = f"bytes */{size}"
        return response
    response = StreamingHttpResponse(_read(path, start, end - start + 1), status=206, content_type=ctype)
    response["Content-Length"] = str(end - start + 1)
    response["Content-Range"] = f"bytes {start}-{end}/{size}"
    response["Accept-Ranges"] = "bytes"
    return response
