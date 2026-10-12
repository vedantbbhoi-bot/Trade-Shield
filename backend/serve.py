"""TradeShield dev server wrapper.

Used only to preview the app in this environment; production uses the normal
Flask dev server (run.py) or a proper WSGI host.

Keep this thin: it just launches gunicorn against the create_app() factory.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

cmd = [
    sys.executable, "-m", "gunicorn",
    "app.create_app",
    "--bind", "127.0.0.1:5001",
    "-w", "1",
    "--timeout", "240",
    "--log-level", "info",
]

print("starting backend dev server on 127.0.0.1:5001", flush=True)
subprocess.run(cmd, cwd=str(REPO_ROOT))
