"""Vercel Python entrypoint: exposes the Django WSGI app.

Vercel routes /api/* and /admin/* here (see vercel.json); the React
build is served as static files by Vercel's CDN.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from django.core.wsgi import get_wsgi_application  # noqa: E402

app = get_wsgi_application()
