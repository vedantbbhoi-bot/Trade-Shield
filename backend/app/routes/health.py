"""Liveness / database connectivity check."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify

from ..db import fetch_one

bp = Blueprint("health", __name__, url_prefix="/api")


@bp.get("/health")
def health():
    # Database check
    try:
        fetch_one("SELECT 1 AS ok")
        database = True
    except Exception:  # noqa: BLE001 - health must never 500
        current_app.logger.exception("health check: database unreachable")
        database = False

    # Blockchain node check (best-effort, never fails the health response)
    blockchain: dict = {"available": False, "reason": "not checked"}
    try:
        from ..chain import chain_status
        blockchain = chain_status()
    except Exception:  # noqa: BLE001
        pass

    status = "ok" if database else "degraded"
    return jsonify({
        "data": {
            "status": status,
            "database": database,
            "blockchain": blockchain,
        }
    }), (200 if database else 503)
