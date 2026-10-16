"""نقطة تشغيل التطبيق على استضافة cPanel (Setup Python App / Passenger) مثل GoDaddy."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DOMAIN = os.environ.get("SITE_DOMAIN", "elmaaref.net")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("DJANGO_DEBUG", "0")
os.environ.setdefault("DJANGO_ALLOWED_HOSTS", f"{DOMAIN},www.{DOMAIN}")
os.environ.setdefault("DJANGO_CSRF_TRUSTED_ORIGINS", f"https://{DOMAIN},http://{DOMAIN}")

from config.wsgi import application  # noqa: E402,F401
