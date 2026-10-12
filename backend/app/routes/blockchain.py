"""
TradeShield * MOCK blockchain proof API.

All endpoints are admin-only and return clearly-labelled MOCK data.

TradeShield's PostgreSQL database is the system of record. This API does not
write to any chain and does not perform real cryptographic commitments.
"""

from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from ..blockchain import (
    MOCK_NETWORK,
    create_mock_proof,
    is_valid_mock_hash,
    recompute_mock_record_hash,
    verify_mock_proof,
)
from ..db import fetch_all, fetch_one, run, transaction
from ..errors import ApiError
from flask import current_app

from ..security import admin_required, client_ip

bp = Blueprint("blockchain", __name__, url_prefix="/api/blockchain")


def _parse_paging() -> tuple[int, int]:
    try:
        limit = int(request.args.get("limit", 50))
        offset = int(request.args.get("offset", 0))
    except ValueError as exc:
        raise ApiError(422, "VALIDATION_ERROR",
                       "limit and offset must be integers.") from exc
    if not (1 <= limit <= 200) or offset < 0:
        raise ApiError(422, "VALIDATION_ERROR",
                       "limit must be 1..200 and offset must be >= 0.")
    return limit, offset


@bp.get("/proofs")
@admin_required
def list_proofs():
    limit, offset = _parse_paging()
    rows = fetch_all(
        """SELECT proof_id, reference_id, entity_type, event_type,
                  record_hash, blockchain_status, transaction_hash,
                  block_number, network, contract_address, created_at
           FROM blockchain_proofs
           ORDER BY created_at DESC
           LIMIT %s OFFSET %s""",
        (limit, offset),
    )
    total = fetch_one("SELECT count(*) AS n FROM blockchain_proofs")["n"]
    return jsonify({
        "data": {
            "items": rows,
            "total": total,
            "mock": True,
            "network": MOCK_NETWORK,
        }
    }), 200


@bp.get("/proofs/<uuid:proof_id>")
@admin_required
def get_proof(proof_id):
    row = fetch_one(
        """SELECT proof_id, reference_id, entity_type, event_type,
                  record_hash, blockchain_status, transaction_hash,
                  block_number, network, contract_address, created_at
           FROM blockchain_proofs
           WHERE proof_id = %s""",
        (str(proof_id),),
    )
    if not row:
        raise ApiError(404, "PROOF_NOT_FOUND", "Mock proof record not found.")
    return jsonify({
        "data": row,
        "mock": True,
        "network": MOCK_NETWORK,
    }), 200


@bp.get("/proofs/<uuid:proof_id>/verify")
@admin_required
def verify_proof(proof_id):
    """
    MOCK verification endpoint.

    Recomputes the stored mock record hash from the proof's own metadata and
    compares it to the stored record_hash. The result is labelled mock.
    """
    row = fetch_one(
        """SELECT proof_id, reference_id, entity_type, event_type,
                  record_hash, blockchain_status, transaction_hash,
                  block_number, network, contract_address, created_at
           FROM blockchain_proofs
           WHERE proof_id = %s""",
        (str(proof_id),),
    )
    if not row:
        raise ApiError(404, "PROOF_NOT_FOUND", "Mock proof record not found.")

    result = verify_mock_proof(row)
    return jsonify({
        "data": result,
        "proof_id": str(proof_id),
        "mock": True,
        "network": MOCK_NETWORK,
    }), 200


# --------------------------------------------------------------------------
# Demo feature toggle (admin only)
# --------------------------------------------------------------------------

DEMO_FLAG_KEY = "demo_client_blockchain_proofs"


@bp.get("/demo-toggle")
@admin_required
def demo_toggle_status():
    row = fetch_one(
        "SELECT flag_key, flag_value, updated_by, updated_at "
        "FROM demo_feature_flags WHERE flag_key = %s",
        (DEMO_FLAG_KEY,),
    )
    if not row:
        return jsonify({
            "data": {
                "key": DEMO_FLAG_KEY,
                "enabled": False,
                "mock": True,
                "network": MOCK_NETWORK,
            }
        }), 200
    return jsonify({
        "data": {
            "key": row["flag_key"],
            "enabled": row["flag_value"] == "true",
            "updated_by": row["updated_by"],
            "updated_at": row["updated_at"],
            "mock": True,
            "network": MOCK_NETWORK,
        }
    }), 200


@bp.post("/demo-toggle")
@admin_required
def demo_toggle_set():
    body = request.get_json(silent=True) or {}
    desired = str(body.get("enabled", False)).lower()
    if desired not in ("true", "false"):
        raise ApiError(422, "VALIDATION_ERROR", "enabled must be true or false.")

    new_value = "true" if desired == "true" else "false"
    try:
        with transaction():
            run(
                """INSERT INTO demo_feature_flags (flag_key, flag_value, updated_by)
                   VALUES (%s, %s, %s)
                   ON CONFLICT (flag_key) DO UPDATE SET
                       flag_value = EXCLUDED.flag_value,
                       updated_by = EXCLUDED.updated_by,
                       updated_at = now()
                   RETURNING flag_value""",
                (DEMO_FLAG_KEY, new_value, g.user["user_id"]),
            )
    except Exception:  # noqa: BLE001 - toggle failure must not be fatal
        current_app.logger.exception(
            "demo_blockchain: failed to set demo toggle for admin %s",
            g.user["user_id"],
        )
        raise ApiError(500, "INTERNAL_ERROR", "Could not update demo toggle.")

    enabled = new_value == "true"
    return jsonify({
        "data": {
            "key": DEMO_FLAG_KEY,
            "enabled": enabled,
            "mock": True,
            "network": MOCK_NETWORK,
            "message": (
                "Demo trade flagging (MOCK) is enabled. Trades from client@tradeshield.dev will be flagged for demonstration." if enabled
                else "Demo trade flagging (MOCK) is disabled. Trades from client@tradeshield.dev will trade normally."
            ),
        }
    }), 200
