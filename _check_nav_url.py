from django.test import RequestFactory
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "SSAPI.settings")
django.setup()

from django.conf import settings
from core.context_processors import _is_local_stack, _nav_asset_base, paldaca_urls

print("local", _is_local_stack())
print("DEBUG", settings.DEBUG)
print("asset", _nav_asset_base())
print("css", paldaca_urls(RequestFactory().get("/"))["paldaca_nav_css"])
