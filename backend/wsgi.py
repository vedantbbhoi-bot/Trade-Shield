"""TradeShield WSGI entry point for dev preview (gunicorn etc.).

Kept thin on purpose: the real application factory is ``app.create_app`` and
this module only exists so a WSGI host can import a single object without
accidentally starting the app at import time.
"""

from __future__ import annotations

from app import create_app

app = create_app()
