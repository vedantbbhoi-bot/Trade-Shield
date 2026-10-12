"""TradeShield * demo flagging integration tests (MOCK blockchain).

Covers the admin demo toggle path and the MOCK demo trade flagging flow:
  - admin enables demo_client_blockchain_proofs
  - subsequent client@tradeshield.dev orders are flagged FLAGGED with a DEMO note
  - an ORDER_FLAGGED_DEMO security event is recorded
  - a MOCK blockchain proof is persisted for the flagged trade

These are small, deterministic, session-scoped integration checks that use the
shared session client from conftest.py but authenticate as the seed accounts.
"""

from __future__ import annotations

import pytest

BLOCKED_IP = "198.51.100.66"          # seed: confidence 95 -> BLOCK
DEMO_FLAG_KEY = "demo_client_blockchain_proofs"


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def demo_client_token(client):
    res = client.post(
        "/api/auth/login",
        json={"email": "client@tradeshield.dev", "password": "Client@123"},
    )
    assert res.status_code == 200, res.get_data(as_text=True)
    return res.get_json()["data"]["token"]


@pytest.fixture(scope="session")
def admin_token(client):
    res = client.post(
        "/api/auth/login",
        json={"email": "admin@tradeshield.dev", "password": "Admin@123"},
    )
    assert res.status_code == 200, res.get_data(as_text=True)
    return res.get_json()["data"]["token"]


def _place_order(client, token, **overrides):
    body = {"instrument": "ACME", "side": "BUY", "order_type": "MARKET", "quantity": 1}
    body.update(overrides)
    return client.post("/api/orders", json=body, headers=_headers(token))


def test_demo_toggle_default_is_disabled(client, admin_token, db):
    row = db.execute(
        "SELECT flag_value FROM demo_feature_flags WHERE flag_key = %s",
        (DEMO_FLAG_KEY,),
    ).fetchone()
    assert row is not None
    assert row["flag_value"] == "false"


def test_demo_toggle_can_be_enabled_and_disabled(client, admin_token, db):
    # enable
    r = client.post(
        "/api/blockchain/demo-toggle",
        json={"enabled": True},
        headers=_headers(admin_token),
    )
    assert r.status_code == 200
    assert r.get_json()["data"]["enabled"] is True

    row = db.execute(
        "SELECT flag_value FROM demo_feature_flags WHERE flag_key = %s",
        (DEMO_FLAG_KEY,),
    ).fetchone()
    assert row is not None and row["flag_value"] == "true"

    # disable
    r = client.post(
        "/api/blockchain/demo-toggle",
        json={"enabled": False},
        headers=_headers(admin_token),
    )
    assert r.status_code == 200
    assert r.get_json()["data"]["enabled"] is False

    row = db.execute(
        "SELECT flag_value FROM demo_feature_flags WHERE flag_key = %s",
        (DEMO_FLAG_KEY,),
    ).fetchone()
    assert row is not None and row["flag_value"] == "false"


def test_demo_flagging_flow_flows_when_toggle_is_on(
    client, admin_token, demo_client_token, db
):
    # ensure the toggle is ON for this test
    client.post(
        "/api/blockchain/demo-toggle",
        json={"enabled": True},
        headers=_headers(admin_token),
    )

    res = _place_order(client, demo_client_token)
    assert res.status_code == 201, res.get_data(as_text=True)
    order = res.get_json()["data"]["order"]
    assert order["risk_status"] == "FLAGGED", order
    assert order["security_note"].startswith("DEMO:")
    assert order["status"] == "EXECUTED"

    event_id = order["order_id"]

    # ORDER_FLAGGED_DEMO security event exists
    events = db.execute(
        "SELECT * FROM security_events WHERE event_type = 'ORDER_FLAGGED_DEMO' AND order_id = %s",
        (event_id,),
    ).fetchall()
    assert len(events) == 1, events
    ev = events[0]
    assert ev["severity"] == "medium"
    assert ev["details"]["demo"] == "true"
    assert ev["details"]["rejected_by"] is None

    # MOCK blockchain proof exists for the flagged trade
    proofs = db.execute(
        "SELECT * FROM blockchain_proofs WHERE event_type = 'ORDER_FLAGGED_DEMO' AND reference_id = %s",
        (f"demo-flag:{event_id}",),
    ).fetchall()
    assert len(proofs) == 1, proofs
    proof = proofs[0]
    assert proof["blockchain_status"] == "mock"
    assert proof["network"] == "TradeShield Local Mock Chain"
    assert proof["entity_type"] == "order"


def test_demo_flagging_does_not_trigger_when_toggle_is_off(
    client, admin_token, demo_client_token, db
):
    # ensure the toggle is OFF
    client.post(
        "/api/blockchain/demo-toggle",
        json={"enabled": False},
        headers=_headers(admin_token),
    )

    res = _place_order(client, demo_client_token)
    assert res.status_code == 201, res.get_data(as_text=True)
    order = res.get_json()["data"]["order"]
    # demo flagging is OFF, so the order should trade normally (CLEAR) unless
    # another indicator matched; the seeded client has no active indicator, so
    # it must be CLEAR here.
    assert order["risk_status"] == "CLEAR", order
    assert order.get("security_note") is None or not order["security_note"].startswith("DEMO:")

    # no ORDER_FLAGGED_DEMO event for this order
    events = db.execute(
        "SELECT count(*) AS n FROM security_events "
        "WHERE event_type = 'ORDER_FLAGGED_DEMO' AND order_id = %s",
        (order["order_id"],),
    ).fetchone()
    assert events["n"] == 0
