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


def _proof_row_to_api(row: dict) -> dict:
    """Normalize a blockchain_proofs row for the API, including optional trade
    context so the admin UI can show the linked instrument / side / quantity."""
    out = {
        "proof_id": str(row["proof_id"]),
        "reference_id": str(row["reference_id"]),
        "entity_type": str(row["entity_type"]),
        "event_type": str(row["event_type"]),
        "record_hash": str(row["record_hash"]),
        "blockchain_status": str(row["blockchain_status"]),
        "transaction_hash": str(row["transaction_hash"]),
        "block_number": int(row["block_number"]),
        "network": str(row["network"]),
        "contract_address": str(row["contract_address"]),
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "order_id": str(row["order_id"]) if row["order_id"] else None,
        "execution_id": str(row["execution_id"]) if row["execution_id"] else None,
        "instrument_id": str(row["instrument_id"]) if row["instrument_id"] else None,
        "side": str(row["side"]) if row["side"] else None,
        "quantity": float(row["quantity"]) if row["quantity"] is not None else None,
    }
    return out


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
                  block_number, network, contract_address, created_at,
                  order_id, execution_id, instrument_id, side, quantity
           FROM blockchain_proofs
           ORDER BY created_at DESC
           LIMIT %s OFFSET %s""",
        (limit, offset),
    )
    total = fetch_one("SELECT count(*) AS n FROM blockchain_proofs")["n"]
    return jsonify({
        "data": {
            "items": [_proof_row_to_api(r) for r in rows],
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
                  block_number, network, contract_address, created_at,
                  order_id, execution_id, instrument_id, side, quantity
           FROM blockchain_proofs
           WHERE proof_id = %s""",
        (str(proof_id),),
    )
    if not row:
        raise ApiError(404, "PROOF_NOT_FOUND", "Mock proof record not found.")
    return jsonify({
        "data": _proof_row_to_api(row),
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


@bp.get("/proofs/<uuid:proof_id>/link")
@admin_required
def proof_linked_order(proof_id):
    """Return the trade an admin FLAG proof is anchored to, if any.

    Only demo FLAG proofs carry trade context (order_id / instrument_id / side /
    quantity). For seed or execution proofs this returns an empty trade object.
    """
    proof = fetch_one(
        """SELECT proof_id, reference_id, entity_type, event_type,
                  order_id, execution_id, instrument_id, side, quantity
           FROM blockchain_proofs
           WHERE proof_id = %s""",
        (str(proof_id),),
    )
    if not proof:
        raise ApiError(404, "PROOF_NOT_FOUND", "Mock proof record not found.")

    trade: dict = {
        "order_id": None,
        "execution_id": None,
        "instrument_id": None,
        "instrument_symbol": None,
        "instrument_name": None,
        "side": None,
        "quantity": None,
        "executed_price": None,
        "executed_quantity": None,
        "mock": True,
    }

    oid = proof["order_id"]
    if oid:
        order = fetch_one(
            """SELECT o.order_id, o.side, o.order_type, o.quantity,
                      o.execution_price, o.risk_status, o.security_note,
                      i.symbol, i.name AS instrument_name,
                      e.execution_id, e.quantity AS executed_quantity,
                      e.price AS executed_price
               FROM orders o
               JOIN instruments i ON i.instrument_id = o.instrument_id
               LEFT JOIN trade_executions e ON e.order_id = o.order_id
               WHERE o.order_id = %s""",
            (oid,),
        )
        if order:
            trade = {
                "order_id": str(order["order_id"]),
                "order_type": str(order["order_type"]),
                "execution_id": str(order["execution_id"]) if order["execution_id"] else None,
                "instrument_id": str(order["instrument_id"]),
                "instrument_symbol": str(order["symbol"]),
                "instrument_name": str(order["instrument_name"]),
                "side": str(order["side"]),
                "quantity": float(order["quantity"]) if order["quantity"] is not None else None,
                "executed_price": float(order["executed_price"]) if order["executed_price"] is not None else None,
                "executed_quantity": float(order["executed_quantity"]) if order["executed_quantity"] is not None else None,
                "risk_status": str(order["risk_status"]),
                "security_note": str(order["security_note"]) if order["security_note"] else None,
                "mock": True,
            }

    return jsonify({
        "data": {
            "proof_id": str(proof["proof_id"]),
            "reference_id": str(proof["reference_id"]),
            "entity_type": str(proof["entity_type"]),
            "event_type": str(proof["event_type"]),
            "trade": trade,
            "mock": True,
        }
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
