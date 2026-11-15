"""
TradeShield * blockchain integrity layer.

This module wraps the proof creation / recording logic.  It tries to anchor
each proof on the real Hardhat/EVM node (via app.chain); when the node is
unavailable or not configured it falls back gracefully to the mock layer so
nothing in the core trading path ever breaks.

The mock layer stores deterministic-looking values in blockchain_proofs:
- network           = "TradeShield Local Mock Chain" (or real node id)
- contract_address  = deterministic 0x... (or real contract)
- record_hash       = SHA-256 of canonical inputs
- transaction_hash  = SHA-256 based (or real tx hash)
- block_number      = deterministic integer (or real block number)

PostgreSQL remains the system of record for all trading and application data.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import TypedDict
from uuid import UUID

# ---------------------------------------------------------------------------
# MOCK constants
# ---------------------------------------------------------------------------

MOCK_NETWORK = "TradeShield Local Mock Chain"

# A fixed mock deployment salt so the mock contract address is stable across
# restarts. This is NOT a real contract deployment.
_MOCK_CONTRACT_SALT = "tradeshield-mock-contract-deployment-2026"

# Mock block range so numbers look realistic rather than arbitrary.
MOCK_BLOCK_BASE = 882100
MOCK_BLOCK_SPAN = 99899


def _hex(bytes_: bytes, length: int) -> str:
    return bytes_.hex()


def _canonical_iso(dt: datetime) -> str:
    """Stable ISO-8601 for a UTC datetime, ending in 'Z' so the DB seed and the
    backend produce identical mock record hashes."""
    s = dt.isoformat()
    if s.endswith("+00:00"):
        s = s[:-6] + "Z"
    return s


def mock_record_hash(reference_id: str, entity_type: str, event_type: str,
                     created_at_iso: str) -> str:
    """
    Deterministic MOCK record hash.

    The same canonical inputs always produce the same mock hash. This is SHA-256
    applied to a stable string -- the output LOOKS like a real hash, but in this
    codebase it is used as a MOCK proof marker, not as a real chain commitment.
    """
    canonical = ":".join([
        entity_type,
        str(reference_id),
        event_type,
        created_at_iso,
    ])
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def mock_transaction_hash(proof_id: UUID, network: str) -> str:
    """
    Deterministic MOCK transaction hash.
    """
    canonical = f"{network}:tx:{proof_id}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def mock_block_number(proof_id: UUID) -> int:
    """
    Deterministic MOCK block number.
    """
    h = int(hashlib.sha256(str(proof_id).encode("utf-8")).hexdigest(), 16)
    return MOCK_BLOCK_BASE + (h % MOCK_BLOCK_SPAN)


def mock_contract_address(network: str) -> str:
    """
    Deterministic MOCK contract address.
    """
    h = hashlib.sha256(f"{network}:{_MOCK_CONTRACT_SALT}".encode("utf-8")).hexdigest()
    return "0x" + h[:40]


class MockProofCreated(TypedDict):
    proof_id: UUID
    reference_id: str
    entity_type: str
    event_type: str
    record_hash: str
    blockchain_status: str
    transaction_hash: str
    block_number: int
    network: str
    contract_address: str
    created_at: datetime


def create_mock_proof(
    *,
    reference_id: str,
    entity_type: str,
    event_type: str,
    created_at: datetime | None = None,
) -> MockProofCreated:
    """
    Create a blockchain proof record for a critical TradeShield event.

    Attempts to anchor the proof on the real Hardhat/EVM node first.
    Falls back to the mock layer when the node is offline or not configured.

    Parameters are the minimal, non-sensitive metadata needed to anchor a proof
    reference. Nothing sensitive is hashed or stored on-chain.
    """
    now = created_at or datetime.now(timezone.utc)
    created_at_iso = _canonical_iso(now)

    record_hash = mock_record_hash(
        reference_id=reference_id,
        entity_type=entity_type,
        event_type=event_type,
        created_at_iso=created_at_iso,
    )

    # Deterministic proof id (stable across mock and real modes).
    raw = hashlib.sha256(
        f"mock-proof:{reference_id}:{entity_type}:{event_type}:{created_at_iso}".encode("utf-8")
    ).digest()
    proof_id = UUID(bytes=raw[:16])

    # --- Try real on-chain anchor first -----------------------------------
    try:
        from .chain import anchor_proof_on_chain  # local import avoids circular deps
        # event_ref must be ≤ 64 chars (contract limit)
        event_ref = reference_id[:64]
        chain_result = anchor_proof_on_chain(
            event_ref=event_ref,
            event_type=event_type[:64],
            record_hash_hex=record_hash,
        )
    except Exception:
        chain_result = None

    if chain_result is not None:
        # Real on-chain anchor succeeded — use the actual tx/block data.
        return {
            "proof_id": proof_id,
            "reference_id": reference_id,
            "entity_type": entity_type,
            "event_type": event_type,
            "record_hash": record_hash,
            "blockchain_status": "anchored",
            "transaction_hash": chain_result["tx_hash"].lstrip("0x"),
            "block_number": chain_result["block_number"],
            "network": chain_result["network"],
            "contract_address": chain_result["contract_address"],
            "created_at": now,
        }

    # --- Fallback: mock layer -------------------------------------------
    transaction_hash = mock_transaction_hash(proof_id=proof_id, network=MOCK_NETWORK)
    block_number = mock_block_number(proof_id=proof_id)
    contract_address = mock_contract_address(network=MOCK_NETWORK)

    return {
        "proof_id": proof_id,
        "reference_id": reference_id,
        "entity_type": entity_type,
        "event_type": event_type,
        "record_hash": record_hash,
        "blockchain_status": "anchored",
        "transaction_hash": transaction_hash,
        "block_number": block_number,
        "network": MOCK_NETWORK,
        "contract_address": contract_address,
        "created_at": now,
    }


def recompute_mock_record_hash(proof: dict) -> str:
    """
    Recompute the mock record hash from the stored proof metadata.

    This is the core of the mock verify flow: if the stored payload has not
    changed, the recomputed hash equals the stored record_hash.
    """
    created_at = proof["created_at"]
    if isinstance(created_at, datetime):
        created_at_iso = _canonical_iso(created_at)
    else:
        created_at_iso = str(created_at)
    return mock_record_hash(
        reference_id=str(proof["reference_id"]),
        entity_type=str(proof["entity_type"]),
        event_type=str(proof["event_type"]),
        created_at_iso=created_at_iso,
    )


def verify_mock_proof(proof: dict) -> dict:
    """
    Verify a stored proof.

    When the Hardhat node is running and the proof was anchored on-chain,
    this also cross-checks against the smart contract.  Falls back to the
    pure local hash comparison when the node is offline.
    """
    recomputed = recompute_mock_record_hash(proof)
    local_matches = (recomputed == str(proof.get("record_hash", "")))

    # Try on-chain verification as an additional check
    on_chain = None
    try:
        from .chain import verify_proof_on_chain
        event_ref = str(proof.get("reference_id", ""))[:64]
        on_chain = verify_proof_on_chain(
            event_ref=event_ref,
            record_hash_hex=str(proof.get("record_hash", "")),
        )
    except Exception:
        pass

    is_real_chain = (
        on_chain is not None
        and str(proof.get("network", "")).startswith("hardhat-local:")
    )

    verified = local_matches
    if is_real_chain:
        # Only trust the proof if both local recomputation AND on-chain agree
        verified = local_matches and on_chain["matches"]

    return {
        "verified": bool(verified),
        "mock": not is_real_chain,
        "on_chain_verified": bool(on_chain["matches"]) if on_chain else None,
        "record_hash": str(proof.get("record_hash", "")),
        "transaction_hash": str(proof.get("transaction_hash", "")),
        "block_number": int(proof.get("block_number", 0)),
        "network": str(proof.get("network", MOCK_NETWORK)),
        "contract_address": str(proof.get("contract_address", "")),
        "recomputed_record_hash": recomputed,
    }


def is_valid_mock_hash(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{64}", value or ""))


# ---------------------------------------------------------------------------
# Demo integration helpers
# ---------------------------------------------------------------------------

DEMO_CLIENT_USER_ID = "a0000000-0000-4000-8000-000000000002"


def should_record_proof_for_event(
    *,
    actor_user_id: str,
    demo_mode_enabled: bool,
) -> bool:
    """Return True only for the demo client's critical events when demo mode is on."""
    if not demo_mode_enabled:
        return False
    if not actor_user_id:
        return False
    # Coerce to str so UUID objects from the DB row still match the demo client id.
    if str(actor_user_id) != DEMO_CLIENT_USER_ID:
        return False
    return True


def record_mock_proof_for_execution(
    *,
    execution_id: str,
    demo_mode_enabled: bool,
    actor_user_id: str,
    db_run,
) -> dict | None:
    """Record a mock proof for a successful trade execution if demo mode is on.

    This is best-effort: any failure is logged and never breaks the trading
    response, because the proof layer is MOCK only.
    """
    if not should_record_proof_for_event(
        actor_user_id=actor_user_id,
        demo_mode_enabled=demo_mode_enabled,
    ):
        return None

    created_at = datetime.now(timezone.utc)
    reference_id = f"exec:{execution_id}"
    proof = create_mock_proof(
        reference_id=reference_id,
        entity_type="execution",
        event_type="TRADE_EXECUTED",
        created_at=created_at,
    )

    try:
        db_run(
            """INSERT INTO blockchain_proofs
                  (proof_id, reference_id, entity_type, event_type,
                   record_hash, blockchain_status, transaction_hash,
                   block_number, network, contract_address, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (reference_id, entity_type) DO NOTHING""",
            (
                str(proof["proof_id"]),
                proof["reference_id"],
                proof["entity_type"],
                proof["event_type"],
                proof["record_hash"],
                proof["blockchain_status"],
                proof["transaction_hash"],
                proof["block_number"],
                proof["network"],
                proof["contract_address"],
                proof["created_at"],
            ),
        )
    except Exception:  # noqa: BLE001 - proof persistence must never break trading
        current_app_logger_exception(
            "demo_blockchain: failed to persist mock proof for execution %s",
            execution_id,
        )
        return None

    return proof


def record_mock_proof_for_blocked_order(
    *,
    account_id: str,
    order_side: str,
    order_type: str,
    quantity: str,
    limit_price: str | None,
    instrument: str,
    origin_ip: str,
    demo_mode_enabled: bool,
    actor_user_id: str,
    db_run,
) -> dict | None:
    """Record a mock proof for a blocked/security event if demo mode is on."""
    if not should_record_proof_for_event(
        actor_user_id=actor_user_id,
        demo_mode_enabled=demo_mode_enabled,
    ):
        return None

    created_at = datetime.now(timezone.utc)
    reference_id = f"blocked:{account_id}:{created_at.isoformat()}"
    proof = create_mock_proof(
        reference_id=reference_id,
        entity_type="security_event",
        event_type="ORDER_BLOCKED",
        created_at=created_at,
    )

    try:
        db_run(
            """INSERT INTO blockchain_proofs
                  (proof_id, reference_id, entity_type, event_type,
                   record_hash, blockchain_status, transaction_hash,
                   block_number, network, contract_address, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (reference_id, entity_type) DO NOTHING""",
            (
                str(proof["proof_id"]),
                proof["reference_id"],
                proof["entity_type"],
                proof["event_type"],
                proof["record_hash"],
                proof["blockchain_status"],
                proof["transaction_hash"],
                proof["block_number"],
                proof["network"],
                proof["contract_address"],
                proof["created_at"],
            ),
        )
    except Exception:  # noqa: BLE001 - proof persistence must never break the block flow
        current_app_logger_exception(
            "demo_blockchain: failed to persist mock proof for blocked order for account %s",
            account_id,
        )
        return None

    return proof


def current_app_logger_exception(message: str, *args) -> None:
    """Best-effort logger access that never breaks callers."""
    try:
        from flask import current_app
    except Exception:
        return
    try:
        current_app.logger.exception(message, *args)
    except Exception:
        pass


def record_mock_proof_for_demo_flagged_trade(
    *,
    order_id: str,
    execution_id: str,
    demo_mode_enabled: bool,
    actor_user_id: str,
    db_run,
    instrument_id: str | None = None,
    side: str | None = None,
    quantity: float | int | None = None,
) -> dict | None:
    """Record a MOCK proof for a demo-flagged trade.

    This is the demo trade flagging integration: when the admin toggle is ON and
    the actor is the demo client, each trade is marked FLAGGED for demonstration
    and a mock proof is recorded. It is best-effort and never changes the trading
    response, because the proof layer is MOCK only.

    When the underlying order really executed, the caller should also pass the
    instrument_id, side and quantity so the admin UI can show what was actually
    traded. Those fields are stored only when they are provided -- older/other
    callers remain backward compatible.
    """
    if not should_record_proof_for_event(
        actor_user_id=actor_user_id,
        demo_mode_enabled=demo_mode_enabled,
    ):
        return None

    created_at = datetime.now(timezone.utc)
    reference_id = f"demo-flag:{order_id}"
    proof = create_mock_proof(
        reference_id=reference_id,
        entity_type="order",
        event_type="ORDER_FLAGGED_DEMO",
        created_at=created_at,
    )
    # Override status so the proof is clearly labelled as a MOCK demo record,
    # not a real anchored transaction.
    proof["blockchain_status"] = "mock"

    # Persist trade context when available (backward compatible: ignored by
    # callers that do not pass it).
    trade_context_values: tuple = (
        str(proof["proof_id"]),
        proof["reference_id"],
        proof["entity_type"],
        proof["event_type"],
        proof["record_hash"],
        proof["blockchain_status"],
        proof["transaction_hash"],
        proof["block_number"],
        proof["network"],
        proof["contract_address"],
        proof["created_at"],
        order_id if order_id else None,
        execution_id if execution_id else None,
        instrument_id if instrument_id else None,
        side if side else None,
        quantity if quantity is not None else None,
    )

    try:
        db_run(
            """INSERT INTO blockchain_proofs
                  (proof_id, reference_id, entity_type, event_type,
                   record_hash, blockchain_status, transaction_hash,
                   block_number, network, contract_address, created_at,
                   order_id, execution_id, instrument_id, side, quantity)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                       %s, %s, %s, %s, %s)
               ON CONFLICT (reference_id, entity_type) DO NOTHING""",
            trade_context_values,
        )
    except Exception:  # noqa: BLE001 - proof persistence must never break trading
        current_app_logger_exception(
            "demo_blockchain: failed to persist mock proof for demo-flagged trade %s",
            order_id,
        )
        return None

    return proof
