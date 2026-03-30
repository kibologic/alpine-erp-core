import websocket
import threading
import json
import time
import requests
import sys

resp = requests.post(
    "http://localhost:8000/api/v1/auth/login",
    json={"email": "admin@kibologic.com",
          "password": "admin123"}
)
data = resp.json()
TOKEN = data.get("token")
if not TOKEN:
    print(f"Failed to get token! Response: {resp.text}")
    sys.exit(1)

TENANT_ID = data["tenants"][0]["tenant_id"]
print(f"Tenant: {TENANT_ID}")
print(f"Tier: {data.get('tier')}")

received = []

def on_message(ws, msg):
    d = json.loads(msg)
    received.append(d)
    if d.get("type") != "ping":
        print(f"✅ EVENT: {d.get('type')} payload={json.dumps(d.get('payload',{}))[:80]}")
    else:
        print("💓 ping")

def on_open(ws):
    print("✅ WebSocket CONNECTED")

def on_error(ws, e):
    print(f"❌ ERROR: {e}")

ws = websocket.WebSocketApp(
    f"ws://localhost:8000/ws/tenant/{TENANT_ID}?token={TOKEN}",
    on_open=on_open,
    on_message=on_message,
    on_error=on_error
)

t = threading.Thread(target=ws.run_forever)
t.daemon = True
t.start()
time.sleep(2)

HEADERS = {
    "X-Internal-Token": "alpine_dev_internal_token_2026",
    "X-Tenant-ID": TENANT_ID,
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

# Get existing open session or open new one
try:
    sessions = requests.get(
        "http://localhost:8000/api/v1/pos/sessions",
        headers=HEADERS
    ).json()
    open_sessions = [s for s in sessions if s.get("status") == "open"]

    if open_sessions:
        session_id = open_sessions[0]["id"]
        print(f"Using existing session: {session_id}")
    else:
        print("Opening new POS session...")
        sr = requests.post(
            "http://localhost:8000/api/v1/pos/sessions/open",
            headers=HEADERS,
            json={
                "register_id": "REG-WS-TEST",
                "opening_float": 500,
                "device_id": "ws-test-device"
            }
        )
        print(f"Session open status: {sr.status_code}")
        if sr.status_code == 200:
            session_id = sr.json()["id"]
        else:
            print(f"Error: {sr.text}")
            session_id = None
except Exception as e:
    print(f"Error in fetching pos sessions: {e}")

time.sleep(1)

# Adjust stock to trigger inventory event
try:
    products = requests.get(
        "http://localhost:8000/api/v1/inventory/products",
        headers=HEADERS
    ).json()

    if products:
        pid = products[0]["id"]
        pname = products[0].get("name", "unknown")
        print(f"Adjusting stock for: {pname}")
        ar = requests.post(
            "http://localhost:8000/api/v1/inventory/adjust",
            headers=HEADERS,
            json={
                "product_id": pid,
                "quantity": 1,
                "reason": "ws_e2e_test"
            }
        )
        print(f"Adjust status: {ar.status_code}")
except Exception as e:
    print(f"Error fetching/adjusting products: {e}")

time.sleep(2)

real_events = [e for e in received if e.get("type") != "ping"]
print(f"\n━━━ RESULTS ━━━")
print(f"Total events (excl ping): {len(real_events)}")
for e in real_events:
    print(f"  ✅ {e.get('type')}")

if not real_events:
    print("  ❌ No domain events received")
    print("  Check: ws_manager.py broadcast called?")
    print("  Check: tenant_id matches in broadcast?")

ws.close()
