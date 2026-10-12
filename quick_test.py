#!/usr/bin/env python3
"""Quick inline test of the TradeShield API."""
from __future__ import annotations

import sys
import json
sys.path.insert(0, "backend")

from app import create_app

app = create_app()
client = app.test_client()

def test(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {name}" + (f" :: {detail}" if detail else ""))
    return condition

results = []

print("=" * 70)
print("TradeShield * Quick API Verification (test client)")
print("=" * 70)

# ---- Health ----
print("\n[1] Health Check")
resp = client.get("/api/health")
data = resp.get_json()
results.append(test("Health endpoint", resp.status_code == 200))
results.append(test("DB connected", data.get("data", {}).get("database") is True))

# ---- Auth ----
print("\n[2] Authentication")
resp = client.post("/api/auth/login", json={"email": "admin@tradeshield.dev", "password": "Admin@123"})
admin_data = resp.get_json()
admin_token = admin_data.get("data", {}).get("token")
results.append(test("Admin login", resp.status_code == 200 and admin_token is not None))

resp = client.post("/api/auth/login", json={"email": "client@tradeshield.dev", "password": "Client@123"})
client_data = resp.get_json()
client_token = client_data.get("data", {}).get("token")
results.append(test("Client login", resp.status_code == 200 and client_token is not None))

# ---- Admin Security Pages ----
print("\n[3] Admin Security Pages")
headers = {"Authorization": f"Bearer {admin_token}"}

resp = client.get("/api/security/dashboard", headers=headers)
data = resp.get_json()
results.append(test("Dashboard accessible", resp.status_code == 200))
dash = data.get("data", {})
results.append(test("Dashboard has KPIs", all(k in dash for k in ["blocked_orders_total", "active_threats"])))
print(f"      Dashboard: blocked={dash.get('blocked_orders_total')}, flagged={dash.get('flagged_orders_total')}, active={dash.get('active_threats')}")

resp = client.get("/api/security/blocked-orders", headers=headers)
data = resp.get_json()
results.append(test("Blocked orders endpoint", resp.status_code == 200))
blocked = data.get("data", {})
results.append(test("Blocked orders has data", "items" in blocked and "total" in blocked))
print(f"      Blocked total: {blocked.get('total')}, items: {len(blocked.get('items', []))}")

resp = client.get("/api/security/events", headers=headers)
results.append(test("Events endpoint", resp.status_code == 200))

resp = client.get("/api/security/audit-logs", headers=headers)
results.append(test("Audit logs endpoint", resp.status_code == 200))

# ---- Demo Flagging ----
print("\n[4] Demo Flagging Flow")

# Check toggle
resp = client.get("/api/blockchain/demo-toggle", headers=headers)
toggle_data = resp.get_json()
print(f"      Initial toggle: {toggle_data.get('data', {}).get('enabled')}")

# Enable toggle
resp = client.post("/api/blockchain/demo-toggle", json={"enabled": True}, headers=headers)
toggle_data = resp.get_json()
results.append(test("Enable demo toggle", resp.status_code == 200 and toggle_data.get("data", {}).get("enabled") is True))
print(f"      Toggle enabled: {toggle_data.get('data', {}).get('enabled')}")

# Place order as demo client
headers_client = {"Authorization": f"Bearer {client_token}"}
resp = client.post("/api/orders", json={
    "instrument": "ACME", "side": "BUY", "order_type": "MARKET", "quantity": 1
}, headers=headers_client)
order_data = resp.get_json()
order = order_data.get("data", {}).get("order", {})
results.append(test("Demo order FLAGGED", order.get("risk_status") == "FLAGGED", f"got {order.get('risk_status')}"))
results.append(test("Demo order has note", order.get("security_note", "").startswith("DEMO:")))
results.append(test("Demo order executed", order.get("status") == "EXECUTED"))
print(f"      Order: risk_status={order.get('risk_status')}, status={order.get('status')}")
print(f"      Note: {order.get('security_note', '')[:60]}...")

# Check ORDER_FLAGGED_DEMO event
resp = client.get("/api/security/events?event_type=ORDER_FLAGGED_DEMO", headers=headers)
events_data = resp.get_json()
demo_events = events_data.get("data", [])
results.append(test("ORDER_FLAGGED_DEMO event created", len(demo_events) > 0, f"count={len(demo_events)}"))
if demo_events:
    print(f"      Event order_id: {demo_events[0].get('order_id')}")
    print(f"      Event demo flag: {demo_events[0].get('details', {}).get('demo')}")

# Check blocked-orders includes ORDER_FLAGGED_DEMO
resp = client.get("/api/security/blocked-orders", headers=headers)
blocked_data = resp.get_json()
blocked_items = blocked_data.get("data", {}).get("items", [])
demo_in_blocked = any(item.get("event_type") == "ORDER_FLAGGED_DEMO" for item in blocked_items)
results.append(test("ORDER_FLAGGED_DEMO in blocked-orders", demo_in_blocked, f"total={blocked_data.get('data', {}).get('total')}"))

# Check blockchain proof
resp = client.get("/api/blockchain/proofs?limit=10", headers=headers)
proofs_data = resp.get_json()
proofs = proofs_data.get("data", {}).get("items", [])
demo_proofs = [p for p in proofs if p.get("event_type") == "ORDER_FLAGGED_DEMO"]
results.append(test("Mock proof created", len(demo_proofs) > 0, f"count={len(demo_proofs)}"))
if demo_proofs:
    print(f"      Proof status: {demo_proofs[0].get('blockchain_status')}")
    print(f"      Proof ref: {demo_proofs[0].get('reference_id')}")

# ---- Summary ----
print("\n" + "=" * 70)
passed = sum(1 for r in results if r)
total = len(results)
print(f"RESULTS: {passed}/{total} checks passed")
print("=" * 70)

if passed == total:
    print("\nALL CHECKS PASSED")
    sys.exit(0)
else:
    print(f"\n{total - passed} CHECKS FAILED")
    sys.exit(1)
