"""
TradeShield * MOCK blockchain integrity layer.

IMPORTANT: This is a MOCK proof layer for demonstration only.

It is NOT a real blockchain.
It does NOT submit real transactions.
It does NOT use Web3.py, Hardhat, or any real chain client.
It does NOT replace PostgreSQL, which remains the system of record.

What it does:
- Generates deterministic-looking MOCK proof records for critical TradeShield
  events (successful trade executions and blocked/security events).
- Stores mock proof metadata in the `blockchain_proofs` table.
- Provides a mock "verify" check that recomputes the stored mock record hash
  from the same canonical inputs and compares it to the stored value.

Mock values are intentionally clearly fake:
- network = "TradeShield Local Mock Chain"
- contract_address = deterministic-looking 0x... address
- record_hash / transaction_hash = 64-char hex strings
- block_number = deterministic-looking integer
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
    Create a MOCK blockchain proof record for a critical TradeShield event.

    Parameters are the minimal, non-sensitive metadata needed to anchor a proof
    reference. Nothing sensitive is hashed or stored here.

    Returns the created mock proof payload.
    """
    now = created_at or datetime.now(timezone.utc)
    created_at_iso = _canonical_iso(now)

    record_hash = mock_record_hash(
        reference_id=reference_id,
        entity_type=entity_type,
        event_type=event_type,
        created_at_iso=created_at_iso,
    )

    # Deterministic proof id (mocks do not need real randomness here).
    raw = hashlib.sha256(
        f"mock-proof:{reference_id}:{entity_type}:{event_type}:{created_at_iso}".encode("utf-8")
    ).digest()
    proof_id = UUID(bytes=raw[:16])

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
    MOCK verification result for a stored proof.

    Returns a clearly-labelled mock verification response.
    """
    recomputed = recompute_mock_record_hash(proof)
    matches = (recomputed == str(proof.get("record_hash", "")))

    return {
        "verified": bool(matches),
        "mock": True,
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
) -> dict | None:
    """Record a MOCK proof for a demo-flagged trade.

    This is the demo trade flagging integration: when the admin toggle is ON and
    the actor is the demo client, each trade is marked FLAGGED for demonstration
    and a mock proof is recorded. It is best-effort and never changes the trading
    response, because the proof layer is MOCK only.
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
            "demo_blockchain: failed to persist mock proof for demo-flagged trade %s",
            order_id,
        )
        return None

    return proof
