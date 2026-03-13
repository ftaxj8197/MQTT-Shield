#!/usr/bin/env python3
"""
MQTT SHIELD — 4 Parts, All Connected
══════════════════════════════════════
Run ONE command:  python3 mqtt_parts.py

Opens 4 live dashboards — each is a separate component:

  Part 1 → Broker        http://localhost:8081
  Part 2 → Device        http://localhost:8082
  Part 3 → DNA + Healer  http://localhost:8083
  Part 4 → Hacker + Trap http://localhost:8084

They talk to each other via HTTP APIs in real time.
"""

import threading, time, random, json, datetime, socket as _socket
from collections import deque
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.request import urlopen, Request
from urllib.parse import urlparse, parse_qs
from urllib.error import URLError

# ════════════════════════════════════════════════════════
# PORTS
# ════════════════════════════════════════════════════════
P_BROKER  = 8081   # Broker dashboard + /publish API
P_DEVICE  = 8082   # Device dashboard
P_DNA     = 8083   # DNA + Healer dashboard + /analyze API
P_HACKER  = 8084   # Hacker + Honeypot dashboard

API_BROKER  = 9081  # Broker internal API (receives messages)
API_DNA     = 9083  # DNA internal API (receives messages to analyze)
API_HONEYPOT= 9084  # Honeypot internal API (receives redirected messages)


def ts():
    return datetime.datetime.now().strftime("%H:%M:%S")

def post(url, data):
    """Fire-and-forget HTTP POST."""
    try:
        body = json.dumps(data).encode()
        req  = Request(url, data=body, headers={"Content-Type":"application/json"})
        urlopen(req, timeout=2)
        return True
    except: return False

def find_port(start):
    for p in range(start, start+20):
        try:
            s = _socket.socket(); s.bind(('',p)); s.close(); return p
        except: pass
    return start


# ════════════════════════════════════════════════════════
# PART 1 — BROKER
# ════════════════════════════════════════════════════════
broker = {
    "messages":     deque(maxlen=40),
    "total":        0,
    "allowed":      0,
    "redirected":   0,
    "blocked":      0,
    "clients":      set(),
    "narrator":     "Broker is ready. Waiting for devices to connect.",
    "lock":         threading.Lock(),
}

def broker_receive(msg: dict):
    """Called when any client publishes a message."""
    sender  = msg.get("client_id","unknown")
    topic   = msg.get("topic","?")
    payload = msg.get("payload","")

    with broker["lock"]:
        broker["total"]   += 1
        broker["clients"].add(sender)

    broker["narrator"] = f"Received from {sender} → topic='{topic}'. Forwarding to DNA Analyzer…"

    # Ask DNA Analyzer what to do
    verdict = dna_analyze(msg)
    action  = verdict.get("action","allow")

    with broker["lock"]:
        rec = {
            "ts":      ts(),
            "from":    sender,
            "topic":   topic,
            "payload": str(payload)[:60],
            "action":  action,
            "score":   verdict.get("score", 0),
        }
        broker["messages"].appendleft(rec)

    if action == "allow":
        with broker["lock"]: broker["allowed"] += 1
        broker["narrator"] = f"✅ DNA says ALLOW — '{topic}' delivered normally."

    elif action == "redirect":
        with broker["lock"]: broker["redirected"] += 1
        broker["narrator"] = f"🪤 DNA says REDIRECT — '{sender}' silently sent to honeypot!"
        # Send to honeypot
        post(f"http://localhost:{API_HONEYPOT}/receive", {**msg, "reason": verdict.get("reason","anomaly")})

    elif action == "block":
        with broker["lock"]: broker["blocked"] += 1
        broker["narrator"] = f"🚫 DNA says BLOCK — dropped message from '{sender}'."


# ════════════════════════════════════════════════════════
# PART 2 — DEVICE (TempSensor01)
# ════════════════════════════════════════════════════════
device = {
    "id":       "TempSensor01",
    "topic":    "home/temperature",
    "total":    0,
    "last_temp": 22.0,
    "status":   "idle",
    "narrator": "TempSensor01 starting up…",
    "log":      deque(maxlen=20),
}

def device_loop():
    time.sleep(2)
    device["narrator"] = "Connected to broker. Starting to publish temperature every 3s."
    while True:
        temp = round(random.uniform(18.5, 28.5), 1)
        payload = {"temp": temp, "unit": "C"}
        device["last_temp"] = temp
        device["total"]    += 1
        device["status"]    = "sending"
        device["narrator"]  = f"📤 Sending {temp}°C to broker on topic 'home/temperature'…"
        device["log"].appendleft({"ts": ts(), "temp": temp, "topic": device["topic"]})

        # POST to broker API
        ok = post(f"http://localhost:{API_BROKER}/publish", {
            "client_id": device["id"],
            "topic":     device["topic"],
            "payload":   payload,
        })

        device["status"]   = "idle"
        device["narrator"] = f"✅ Sent {temp}°C — broker received it." if ok else f"⚠ Broker unreachable."
        time.sleep(3)


# ════════════════════════════════════════════════════════
# PART 3 — DNA ANALYZER + SELF-HEALER
# ════════════════════════════════════════════════════════
dna = {
    "samples":      0,
    "locked":       False,
    "baseline":     {"topic": "home/temperature", "rate": 3.0},
    "status":       "LEARNING",
    "match_pct":    0,
    "last_score":   0.0,
    "analyzed":     0,
    "anomalies":    0,
    "heals":        0,
    "heal_active":  False,
    "modules": [
        {"name":"IP Blocking",      "icon":"🚫","on":True },
        {"name":"Rate Limiting",    "icon":"⚡","on":True },
        {"name":"Device Isolation", "icon":"🔒","on":True },
        {"name":"DNA Recalibrate",  "icon":"🧬","on":False},
    ],
    "narrator": "DNA Analyzer ready. Will learn device behavior.",
    "log":      deque(maxlen=20),
    "lock":     threading.Lock(),
}

_msg_times = deque(maxlen=30)

def dna_analyze(msg: dict) -> dict:
    """Core DNA logic — returns {action, score, reason}."""
    topic   = msg.get("topic","")
    sender  = msg.get("client_id","")
    now     = time.time()

    with dna["lock"]:
        _msg_times.append(now)
        dna["samples"]  += 1
        dna["analyzed"] += 1
        n = dna["samples"]

    # Still learning
    if n <= 10:
        pct = int(n / 10 * 60)
        with dna["lock"]:
            dna["status"]    = "LEARNING"
            dna["match_pct"] = pct
        dna["narrator"] = f"🧬 Learning… sample {n}/10 from {sender}. Topic='{topic}'."
        dna["log"].appendleft({"ts":ts(),"result":"LEARN","topic":topic,"sender":sender,"score":0})
        if n == 10:
            with dna["lock"]: dna["locked"] = True
            dna["narrator"] = "✅ Baseline locked! Normal = topic 'home/temperature', rate ~3s."
        return {"action":"allow","score":0,"reason":"learning"}

    # Analyze
    score = 0.0
    reasons = []

    # Wrong topic?
    if topic != dna["baseline"]["topic"]:
        score += 0.55
        reasons.append(f"Unknown topic '{topic}'")

    # Rate spike?
    recent = [t for t in _msg_times if now - t <= 5]
    rate   = len(recent) / 5.0
    if rate > 2.0:
        score += 0.35
        reasons.append(f"Rate spike {rate:.1f}/s (normal: 0.33/s)")

    # Suspicious sender?
    if "bot" in sender.lower() or "hack" in sender.lower() or "scan" in sender.lower():
        score += 0.40
        reasons.append("Suspicious client ID")

    with dna["lock"]:
        dna["last_score"] = score
        dna["match_pct"]  = max(0, int((1 - score) * 100))

    reason_str = "; ".join(reasons) if reasons else "normal"

    if score >= 0.6:
        with dna["lock"]:
            dna["status"]   = "ALERT"
            dna["anomalies"] += 1
        dna["narrator"] = f"🚨 ANOMALY! Score={score:.2f}. {reason_str}. Telling broker to REDIRECT."
        dna["log"].appendleft({"ts":ts(),"result":"REDIRECT","topic":topic,"sender":sender,"score":score})
        # Trigger self-heal
        threading.Thread(target=self_heal, daemon=True).start()
        return {"action":"redirect","score":score,"reason":reason_str}

    elif score >= 0.3:
        with dna["lock"]: dna["status"] = "WARN"
        dna["narrator"] = f"⚠ Suspicious (score={score:.2f}). {reason_str}. Allowing but watching."
        dna["log"].appendleft({"ts":ts(),"result":"WARN","topic":topic,"sender":sender,"score":score})
        return {"action":"allow","score":score,"reason":reason_str}

    else:
        with dna["lock"]:
            dna["status"]   = "OK"
            dna["match_pct"] = random.randint(88,100)
        dna["narrator"] = f"✅ Normal message from {sender}. Score={score:.2f}. Allowed."
        dna["log"].appendleft({"ts":ts(),"result":"OK","topic":topic,"sender":sender,"score":score})
        return {"action":"allow","score":score,"reason":"normal"}

def self_heal():
    if dna["heal_active"]: return
    dna["heal_active"] = True
    dna["heals"] += 1
    actions = ["IP Blocking","Rate Limiting","Device Isolation"]
    for a in actions:
        dna["narrator"] = f"🔧 Self-Heal: firing '{a}'…"
        time.sleep(0.6)
    dna["narrator"] = f"✅ Self-heal complete — {len(actions)} actions taken. Network safe."
    dna["heal_active"] = False


# ════════════════════════════════════════════════════════
# PART 4 — HACKER + HONEYPOT
# ════════════════════════════════════════════════════════
hacker_state = {
    "active":   False,
    "phase":    "idle",
    "id":       None,
    "ip":       None,
    "msgs_sent": 0,
    "narrator": "Hacker module idle. Click 'Launch Attack' to start.",
    "log":      deque(maxlen=20),
}

honeypot = {
    "total_catches": 0,
    "active_session": False,
    "topics_probed":  [],
    "payloads":       deque(maxlen=15),
    "analysis": {
        "intent":    "—",
        "technique": "—",
        "risk":      "LOW",
    },
    "narrator": "Honeypot armed. Waiting for redirected attackers.",
    "fake_topics": [
        "factory/control/mainpump",
        "security/admin/access",
        "admin/broker/config",
        "power/grid/control",
        "db/credentials/root",
    ],
    "fake_responses": {
        "factory/control/mainpump": '{"status":"OK","pump_speed":2800,"auth":"accepted"}',
        "security/admin/access":    '{"role":"admin","token":"eyJhbGci...","expires":3600}',
        "admin/broker/config":      '{"version":"Mosquitto 2.0","max_clients":1000}',
        "power/grid/control":       '{"zone":"A1","override_available":true}',
        "db/credentials/root":      '{"hint":"try admin:admin"}',
    },
}

def honeypot_receive(msg: dict):
    """Honeypot processes a message from a redirected attacker."""
    topic   = msg.get("topic","?")
    sender  = msg.get("client_id","unknown")
    payload = json.dumps(msg.get("payload",""))

    honeypot["total_catches"]  += 1
    honeypot["active_session"]  = True

    if topic not in honeypot["topics_probed"]:
        honeypot["topics_probed"].append(topic)

    # Classify intent
    tl = topic.lower()
    if "credential" in tl or "db" in tl:
        intent, risk = "Credential Harvesting", "HIGH"
    elif "control" in tl or "override" in tl:
        intent, risk = "System Sabotage / Takeover", "CRITICAL"
    elif "admin" in tl or "config" in tl:
        intent, risk = "Reconnaissance", "HIGH"
    else:
        intent, risk = "Network Scanning", "MEDIUM"

    technique = "Systematic Enumeration" if len(honeypot["topics_probed"]) >= 3 else "Targeted Probe"

    honeypot["analysis"] = {"intent": intent, "technique": technique, "risk": risk}

    fake_resp = honeypot["fake_responses"].get(topic, '{"status":"processing"}')
    honeypot["payloads"].appendleft({
        "ts": ts(), "topic": topic, "payload": payload[:70],
        "intent": intent, "risk": risk, "fake_resp": fake_resp[:50]
    })
    honeypot["narrator"] = (
        f"🔍 CAUGHT: {sender} probed '{topic}'!\n"
        f"Intent={intent} | Risk={risk}\n"
        f"Sent fake response: {fake_resp[:40]}… (attacker thinks it's real!)"
    )

def launch_hacker():
    if hacker_state["active"]: return
    hacker_state["active"]   = True
    hacker_state["msgs_sent"] = 0
    honeypot["topics_probed"] = []
    honeypot["active_session"] = False

    hid = f"HackerBot_{random.randint(100,999)}"
    hip = f"185.{random.randint(100,220)}.{random.randint(0,9)}.{random.randint(1,254)}"
    hacker_state["id"] = hid
    hacker_state["ip"] = hip

    def run():
        def phase(p, narr):
            hacker_state["phase"]    = p
            hacker_state["narrator"] = narr

        # 1. Scan
        phase("scanning", f"🔍 {hid} ({hip}) is scanning the broker for open topics…")
        hacker_state["log"].appendleft({"ts":ts(),"action":"Connected to broker","topic":"—"})
        time.sleep(2)

        # 2. Try normal topic (will be allowed — DNA not locked may not catch it yet)
        phase("probing", f"Trying the real topic to see if it works…")
        post(f"http://localhost:{API_BROKER}/publish", {
            "client_id": hid, "topic": "home/temperature",
            "payload": {"probe": True}
        })
        hacker_state["msgs_sent"] += 1
        hacker_state["log"].appendleft({"ts":ts(),"action":"Probed","topic":"home/temperature"})
        time.sleep(1.5)

        # 3. Escalate — sensitive topics (DNA will flag these)
        sensitive = [
            ("security/admin/access",    {"cmd":"get_users","auth":"admin:admin"}),
            ("factory/control/mainpump", {"cmd":"stop","override":True}),
            ("admin/broker/config",      {"action":"dump_all","passwords":True}),
            ("power/grid/control",       {"zone":"ALL","cmd":"shutdown"}),
            ("db/credentials/root",      {"query":"SELECT * FROM users"}),
        ]

        phase("attacking", f"⚠ Escalating — trying sensitive admin topics…")
        time.sleep(1)

        for topic, payload in sensitive:
            phase("attacking", f"Sending to '{topic}'…")
            post(f"http://localhost:{API_BROKER}/publish", {
                "client_id": hid, "topic": topic, "payload": payload
            })
            hacker_state["msgs_sent"] += 1
            hacker_state["log"].appendleft({"ts":ts(),"action":"Attacked","topic":topic})
            time.sleep(random.uniform(1.2, 2.0))

        # 4. Done
        phase("caught", f"📋 Attack complete. {hacker_state['msgs_sent']} messages sent. "
              f"All sensitive messages were silently redirected to the honeypot. "
              f"The real device never noticed.")
        time.sleep(3)
        hacker_state["active"] = False
        hacker_state["phase"]  = "idle"

    threading.Thread(target=run, daemon=True).start()


# ════════════════════════════════════════════════════════
# HTML TEMPLATES
# ════════════════════════════════════════════════════════

COMMON_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;700&family=Syne:wght@400;700;800&display=swap');
:root{--bg:#060912;--card:#0b1422;--sur:#0f1d30;--brd:#172538;
  --blue:#4da6ff;--cyan:#00ddf5;--green:#1ef090;--red:#ff3d5e;
  --ylw:#ffc93d;--pur:#b87aff;--txt:#94b8d0;--mut:#2e4a60;--wht:#ddeeff;}
*{box-sizing:border-box;margin:0;padding:0;}
body{background:var(--bg);color:var(--txt);font-family:'Syne',sans-serif;
  font-size:13px;line-height:1.55;padding:20px;min-height:100vh;}
body::before{content:'';position:fixed;inset:0;z-index:0;pointer-events:none;
  background-image:linear-gradient(rgba(77,166,255,.016) 1px,transparent 1px),
  linear-gradient(90deg,rgba(77,166,255,.016) 1px,transparent 1px);background-size:48px 48px;}
.wrap{position:relative;z-index:1;max-width:860px;margin:0 auto;}
.part-tag{display:inline-flex;align-items:center;gap:8px;padding:5px 14px;border-radius:20px;
  font-size:10px;font-weight:700;letter-spacing:2px;text-transform:uppercase;
  border:1px solid;margin-bottom:16px;}
h1{font-size:24px;font-weight:800;color:var(--wht);margin-bottom:4px;letter-spacing:-.5px;}
.subtitle{font-size:12px;color:var(--mut);margin-bottom:22px;letter-spacing:1.5px;text-transform:uppercase;}
.narrator{border-radius:12px;padding:16px 20px;border:1px solid;margin-bottom:18px;
  position:relative;overflow:hidden;transition:.4s;}
.narrator::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;}
.n-tag{font-size:9px;font-family:'IBM Plex Mono';font-weight:700;letter-spacing:1.2px;
  padding:2px 8px;border-radius:4px;border:1px solid;display:inline-block;margin-bottom:8px;}
.n-head{font-size:16px;font-weight:800;color:var(--wht);line-height:1.3;margin-bottom:6px;}
.n-body{font-size:12px;color:var(--txt);line-height:1.8;white-space:pre-line;}
.nb{background:rgba(77,166,255,.05);border-color:rgba(77,166,255,.2);}
.nb::before{background:var(--blue);}
.nb .n-tag{color:var(--blue);border-color:rgba(77,166,255,.3);background:rgba(77,166,255,.08);}
.ng{background:rgba(30,240,144,.04);border-color:rgba(30,240,144,.2);}
.ng::before{background:var(--green);}
.ng .n-tag{color:var(--green);border-color:rgba(30,240,144,.3);background:rgba(30,240,144,.07);}
.nr{background:rgba(255,61,94,.05);border-color:rgba(255,61,94,.25);}
.nr::before{background:var(--red);}
.nr .n-tag{color:var(--red);border-color:rgba(255,61,94,.3);background:rgba(255,61,94,.07);}
.ny{background:rgba(255,201,61,.05);border-color:rgba(255,201,61,.2);}
.ny::before{background:var(--ylw);}
.ny .n-tag{color:var(--ylw);border-color:rgba(255,201,61,.3);background:rgba(255,201,61,.07);}
.np{background:rgba(184,122,255,.05);border-color:rgba(184,122,255,.25);}
.np::before{background:var(--pur);}
.np .n-tag{color:var(--pur);border-color:rgba(184,122,255,.3);background:rgba(184,122,255,.07);}
.card{background:var(--card);border:1px solid var(--brd);border-radius:10px;
  overflow:hidden;margin-bottom:14px;}
.ch{padding:11px 15px;border-bottom:1px solid var(--brd);display:flex;
  align-items:center;justify-content:space-between;}
.ct{font-weight:700;font-size:13px;color:var(--wht);display:flex;align-items:center;gap:8px;}
.ctag{font-size:9px;color:var(--mut);padding:2px 7px;border:1px solid var(--brd);
  border-radius:3px;font-family:'IBM Plex Mono';letter-spacing:1px;}
.cb{padding:14px 16px;}
.stat-row{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:14px;}
.stat{background:var(--card);border:1px solid var(--brd);border-radius:9px;padding:12px 14px;
  position:relative;overflow:hidden;}
.stat::after{content:'';position:absolute;top:0;left:0;right:0;height:2px;}
.s1::after{background:var(--blue);}
.s2::after{background:var(--green);}
.s3::after{background:var(--red);}
.s4::after{background:var(--ylw);}
.s5::after{background:var(--pur);}
.sl{font-size:9px;color:var(--mut);letter-spacing:1.2px;text-transform:uppercase;margin-bottom:4px;}
.sv{font-family:'IBM Plex Mono';font-size:22px;font-weight:700;color:var(--wht);}
.row{display:flex;align-items:center;gap:8px;margin-bottom:7px;font-size:12px;}
.lbl{color:var(--mut);width:130px;flex-shrink:0;}
.val{color:var(--wht);font-family:'IBM Plex Mono';font-size:11px;}
.log-item{padding:7px 10px;background:var(--sur);border:1px solid var(--brd);
  border-radius:6px;margin-bottom:5px;animation:fadein .3s;}
@keyframes fadein{from{opacity:0;transform:translateY(-4px)}to{opacity:1;transform:none}}
.li-ts{font-size:9px;color:var(--mut);font-family:'IBM Plex Mono';}
.li-topic{font-size:10px;color:var(--blue);font-family:'IBM Plex Mono';margin:2px 0;}
.li-text{font-size:11px;color:var(--txt);}
.badge{display:inline-block;padding:2px 8px;border-radius:4px;font-size:9px;
  font-weight:700;border:1px solid;}
.b-ok{color:var(--green);border-color:rgba(30,240,144,.3);background:rgba(30,240,144,.08);}
.b-warn{color:var(--ylw);border-color:rgba(255,201,61,.3);background:rgba(255,201,61,.08);}
.b-alert{color:var(--red);border-color:rgba(255,61,94,.3);background:rgba(255,61,94,.08);}
.b-learn{color:var(--ylw);border-color:rgba(255,201,61,.25);background:rgba(255,201,61,.06);}
.b-redir{color:var(--pur);border-color:rgba(184,122,255,.3);background:rgba(184,122,255,.08);}
.dna-wrap{background:var(--brd);border-radius:5px;height:9px;overflow:hidden;margin:8px 0;}
.dna-fill{height:100%;border-radius:5px;transition:width .6s,background .4s;}
.btn{padding:10px 22px;border-radius:8px;border:1px solid;font-family:'Syne';
  font-size:12px;font-weight:700;cursor:pointer;transition:.2s;letter-spacing:.5px;}
.btn:disabled{opacity:.4;pointer-events:none;}
.btn-red{background:rgba(255,61,94,.12);color:var(--red);border-color:rgba(255,61,94,.35);}
.btn-red:hover{background:rgba(255,61,94,.22);transform:translateY(-1px);}
.btn-green{background:rgba(30,240,144,.1);color:var(--green);border-color:rgba(30,240,144,.3);}
.btn-green:hover{background:rgba(30,240,144,.2);}
.nav-links{display:flex;gap:10px;margin-bottom:20px;flex-wrap:wrap;}
.nav-link{padding:6px 14px;border-radius:6px;border:1px solid var(--brd);color:var(--mut);
  font-size:11px;text-decoration:none;transition:.2s;font-weight:700;}
.nav-link:hover{border-color:var(--blue);color:var(--blue);}
.nav-link.active{border-color:var(--blue);color:var(--blue);background:rgba(77,166,255,.08);}
.progress-bar{display:flex;gap:0;margin-bottom:20px;border-radius:8px;overflow:hidden;
  border:1px solid var(--brd);}
.pb-step{flex:1;padding:8px;text-align:center;font-size:10px;font-weight:700;
  letter-spacing:.5px;transition:.3s;cursor:pointer;}
.pb-step:hover{opacity:.85;}
.pb-done{background:rgba(30,240,144,.12);color:var(--green);}
.pb-active{background:rgba(77,166,255,.15);color:var(--blue);}
.pb-idle{background:var(--card);color:var(--mut);}
.connection-line{display:flex;align-items:center;gap:8px;font-size:11px;
  color:var(--mut);margin:6px 0;padding:6px 10px;background:var(--sur);
  border:1px solid var(--brd);border-radius:6px;}
.conn-dot{width:7px;height:7px;border-radius:50%;}
.cd-green{background:var(--green);box-shadow:0 0 8px rgba(30,240,144,.5);}
.cd-red{background:var(--red);box-shadow:0 0 8px rgba(255,61,94,.5);}
.cd-blue{background:var(--blue);}
.cd-mut{background:var(--mut);}
</style>
"""

def html_nav(active):
    links = [
        (8081,"Part 1","🔌 Broker"),
        (8082,"Part 2","🌡️ Device"),
        (8083,"Part 3","🧬 DNA+Heal"),
        (8084,"Part 4","💀 Hacker"),
    ]
    nav = '<div class="nav-links">'
    for port,lbl,icon in links:
        cls = "nav-link active" if port==active else "nav-link"
        nav += f'<a class="{cls}" href="http://localhost:{port}">{icon} {lbl}</a>'
    nav += '</div>'
    return nav

# ─── BROKER HTML ───
def broker_html():
    with broker["lock"]:
        msgs = list(broker["messages"])
        total, allowed, redir, blocked = broker["total"], broker["allowed"], broker["redirected"], broker["blocked"]
        clients = list(broker["clients"])
    narr = broker["narrator"]

    result_badge = {"allow":"b-ok","redirect":"b-redir","block":"b-alert"}
    msg_rows = ""
    for m in msgs[:10]:
        badge = result_badge.get(m["action"],"b-ok")
        msg_rows += f"""<div class="log-item">
          <span class="li-ts">{m['ts']}</span>
          <div class="li-topic">{m['topic']}</div>
          <div class="li-text">from <strong style="color:var(--wht)">{m['from']}</strong>
            &nbsp;<span class="badge {badge}">{m['action'].upper()}</span>
            &nbsp;score={m['score']:.2f}</div>
        </div>"""

    conn_rows = ""
    for c in clients:
        is_hacker = "bot" in c.lower() or "hack" in c.lower()
        dot = "cd-red" if is_hacker else "cd-green"
        conn_rows += f'<div class="connection-line"><div class="conn-dot {dot}"></div>{c}</div>'

    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<title>Part 1 — Broker</title>{COMMON_CSS}
<meta http-equiv="refresh" content="2"></head><body><div class="wrap">
{html_nav(8081)}
<div class="part-tag" style="color:var(--blue);border-color:rgba(77,166,255,.3);background:rgba(77,166,255,.08)">
  ⚡ PART 1 — MQTT BROKER · Port 8081
</div>
<h1>The Message Hub</h1>
<div class="subtitle">receives every message — routes to DNA analyzer — delivers or redirects</div>

<div class="narrator nb" id="narr">
  <div class="n-tag">BROKER STATUS</div>
  <div class="n-head">What the broker is doing right now</div>
  <div class="n-body">{narr}</div>
</div>

<div class="stat-row">
  <div class="stat s1"><div class="sl">Total Received</div><div class="sv">{total}</div></div>
  <div class="stat s2"><div class="sl">Allowed</div><div class="sv">{allowed}</div></div>
  <div class="stat s3"><div class="sl">Redirected</div><div class="sv">{redir}</div></div>
</div>

<div class="card">
  <div class="ch"><div class="ct">🔌 Connected Clients</div><div class="ctag">{len(clients)} CLIENTS</div></div>
  <div class="cb">{conn_rows if conn_rows else '<div style="color:var(--mut);font-size:12px">No clients yet…</div>'}</div>
</div>

<div class="card">
  <div class="ch"><div class="ct">📨 Message Log</div><div class="ctag">LIVE</div></div>
  <div class="cb">{msg_rows if msg_rows else '<div style="color:var(--mut);font-size:12px">No messages yet…</div>'}</div>
</div>

<div class="card">
  <div class="ch"><div class="ct">🔗 How it connects</div></div>
  <div class="cb" style="font-size:12px;line-height:1.9;color:var(--txt)">
    <div>📥 <strong style="color:var(--wht)">Receives</strong> from: Device (Part 2) and Hacker (Part 4)</div>
    <div>📤 <strong style="color:var(--wht)">Sends to</strong>: DNA Analyzer (Part 3) for every message</div>
    <div>🪤 <strong style="color:var(--wht)">Redirects</strong>: flagged messages → Honeypot (Part 4)</div>
    <div style="margin-top:8px;color:var(--mut)">API: POST http://localhost:{API_BROKER}/publish</div>
  </div>
</div>
</div></body></html>"""

# ─── DEVICE HTML ───
def device_html():
    log = list(device["log"])
    log_rows = ""
    for l in log[:8]:
        log_rows += f"""<div class="log-item">
          <span class="li-ts">{l['ts']}</span>
          <div class="li-topic">{l['topic']}</div>
          <div class="li-text">temp={l['temp']}°C</div>
        </div>"""

    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<title>Part 2 — Device</title>{COMMON_CSS}
<meta http-equiv="refresh" content="2"></head><body><div class="wrap">
{html_nav(8082)}
<div class="part-tag" style="color:var(--green);border-color:rgba(30,240,144,.3);background:rgba(30,240,144,.08)">
  🌡️ PART 2 — IoT DEVICE · Port 8082
</div>
<h1>TempSensor01</h1>
<div class="subtitle">legitimate iot device — publishes temperature every 3 seconds</div>

<div class="narrator ng">
  <div class="n-tag">DEVICE STATUS</div>
  <div class="n-head">{device['narrator']}</div>
  <div class="n-body">Publishing to broker on port {API_BROKER}. Each message goes through DNA analysis.</div>
</div>

<div class="stat-row">
  <div class="stat s2"><div class="sl">Sent Total</div><div class="sv">{device['total']}</div></div>
  <div class="stat s1"><div class="sl">Last Temp</div><div class="sv">{device['last_temp']}°C</div></div>
  <div class="stat s2"><div class="sl">Interval</div><div class="sv">3s</div></div>
</div>

<div class="card">
  <div class="ch"><div class="ct">📡 Device Profile</div><div class="ctag">NORMAL</div></div>
  <div class="cb">
    <div class="row"><span class="lbl">Device ID</span><span class="val">TempSensor01</span></div>
    <div class="row"><span class="lbl">Topic</span><span class="val">home/temperature</span></div>
    <div class="row"><span class="lbl">Payload</span><span class="val">{{"temp": {device['last_temp']}, "unit": "C"}}</span></div>
    <div class="row"><span class="lbl">Rate</span><span class="val">1 msg / 3 seconds</span></div>
    <div class="row"><span class="lbl">Broker API</span><span class="val">http://localhost:{API_BROKER}/publish</span></div>
  </div>
</div>

<div class="card">
  <div class="ch"><div class="ct">📤 Message History</div><div class="ctag">LAST 8</div></div>
  <div class="cb">{log_rows if log_rows else '<div style="color:var(--mut);font-size:12px">Sending first messages…</div>'}</div>
</div>

<div class="card">
  <div class="ch"><div class="ct">🔗 How it connects</div></div>
  <div class="cb" style="font-size:12px;line-height:1.9;color:var(--txt)">
    <div>📤 <strong style="color:var(--wht)">Sends to</strong>: Broker Part 1 via POST /publish</div>
    <div>🧬 <strong style="color:var(--wht)">Analyzed by</strong>: DNA Analyzer Part 3 (automatically)</div>
    <div>✅ <strong style="color:var(--wht)">Result</strong>: Always allowed — it's the real, trusted device</div>
  </div>
</div>
</div></body></html>"""

# ─── DNA HTML ───
def dna_html():
    pct  = dna["match_pct"]
    bar_color = {"OK":"var(--green)","WARN":"var(--ylw)","ALERT":"var(--red)","LEARNING":"var(--ylw)"}.get(dna["status"],"var(--mut)")
    badge_cls = {"OK":"b-ok","WARN":"b-warn","ALERT":"b-alert","LEARNING":"b-learn"}.get(dna["status"],"b-learn")

    log_rows = ""
    result_cls = {"OK":"b-ok","WARN":"b-warn","REDIRECT":"b-redir","LEARN":"b-learn"}
    for l in list(dna["log"])[:10]:
        cls = result_cls.get(l["result"],"b-ok")
        log_rows += f"""<div class="log-item">
          <span class="li-ts">{l['ts']}</span>
          <div class="li-topic">{l['topic']}</div>
          <div class="li-text">from {l['sender']} &nbsp;
            <span class="badge {cls}">{l['result']}</span>
            &nbsp;score={l['score']:.2f}</div>
        </div>"""

    modules = ""
    for m in dna["modules"]:
        on = m["on"]
        modules += f"""<div class="connection-line">
          <div class="conn-dot {'cd-green' if on else 'cd-mut'}"></div>
          {m['icon']} {m['name']}
          <span style="margin-left:auto;font-size:10px;color:{'var(--green)' if on else 'var(--mut)'}">{'ON' if on else 'OFF'}</span>
        </div>"""

    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<title>Part 3 — DNA + Healer</title>{COMMON_CSS}
<meta http-equiv="refresh" content="2"></head><body><div class="wrap">
{html_nav(8083)}
<div class="part-tag" style="color:var(--ylw);border-color:rgba(255,201,61,.3);background:rgba(255,201,61,.08)">
  🧬 PART 3 — DNA ANALYZER + SELF-HEALER · Port 8083
</div>
<h1>Behavior Intelligence</h1>
<div class="subtitle">learns normal — flags anomalies — triggers self-heal automatically</div>

<div class="narrator ny">
  <div class="n-tag">DNA STATUS</div>
  <div class="n-head">{dna['narrator']}</div>
  <div class="n-body">Baseline: topic='home/temperature', rate ~0.33/s. Every message scored 0.0–1.0.</div>
</div>

<div class="stat-row">
  <div class="stat s4"><div class="sl">Analyzed</div><div class="sv">{dna['analyzed']}</div></div>
  <div class="stat s3"><div class="sl">Anomalies</div><div class="sv">{dna['anomalies']}</div></div>
  <div class="stat s2"><div class="sl">Self-Heals</div><div class="sv">{dna['heals']}</div></div>
</div>

<div class="card">
  <div class="ch"><div class="ct">🧬 DNA Profile</div>
    <div class="ctag"><span class="badge {badge_cls}">{dna['status']}</span></div>
  </div>
  <div class="cb">
    <div class="row"><span class="lbl">Samples collected</span><span class="val">{dna['samples']}/10</span></div>
    <div class="row"><span class="lbl">Baseline locked</span>
      <span class="val" style="color:{'var(--green)' if dna['locked'] else 'var(--ylw)'}">
        {'✅ YES' if dna['locked'] else '⏳ Learning…'}
      </span>
    </div>
    <div style="margin:10px 0 4px;font-size:10px;color:var(--mut)">MATCH SCORE</div>
    <div class="dna-wrap"><div class="dna-fill" style="width:{pct}%;background:{bar_color}"></div></div>
    <div style="font-size:11px;color:{bar_color}">{pct}% match to baseline</div>
    <div class="row" style="margin-top:10px"><span class="lbl">Last anomaly score</span>
      <span class="val" style="color:{'var(--red)' if dna['last_score']>0.5 else 'var(--green)'}">{dna['last_score']:.3f}</span>
    </div>
  </div>
</div>

<div class="card">
  <div class="ch"><div class="ct">🔧 Self-Heal Modules</div><div class="ctag">AUTO-RESPONSE</div></div>
  <div class="cb">{modules}</div>
</div>

<div class="card">
  <div class="ch"><div class="ct">📊 Analysis Log</div><div class="ctag">LIVE</div></div>
  <div class="cb">{log_rows if log_rows else '<div style="color:var(--mut);font-size:12px">Waiting for messages…</div>'}</div>
</div>

<div class="card">
  <div class="ch"><div class="ct">🔗 How it connects</div></div>
  <div class="cb" style="font-size:12px;line-height:1.9;color:var(--txt)">
    <div>📥 <strong style="color:var(--wht)">Called by</strong>: Broker (Part 1) for every incoming message</div>
    <div>📤 <strong style="color:var(--wht)">Returns verdict</strong>: allow / redirect / block → back to Broker</div>
    <div>🔧 <strong style="color:var(--wht)">Fires self-heal</strong>: automatically when score &gt; 0.6</div>
  </div>
</div>
</div></body></html>"""

# ─── HACKER HTML ───
def hacker_html():
    hp = honeypot
    phase_steps = ["idle","scanning","probing","attacking","caught"]
    phase_idx   = phase_steps.index(hacker_state["phase"]) if hacker_state["phase"] in phase_steps else 0

    progress = '<div class="progress-bar">'
    labels = ["💤 Idle","🔍 Scanning","🕵 Probing","⚡ Attacking","📋 Caught"]
    for i, lbl in enumerate(labels):
        if i < phase_idx:   cls = "pb-step pb-done"
        elif i == phase_idx: cls = "pb-step pb-active"
        else:                cls = "pb-step pb-idle"
        progress += f'<div class="{cls}">{lbl}</div>'
    progress += '</div>'

    topic_rows = ""
    for t in hp["fake_topics"]:
        probed = t in hp["topics_probed"]
        col = "var(--red)" if probed else "var(--mut)"
        icon = "🔥" if probed else "○"
        topic_rows += f"""<div class="connection-line">
          <div class="conn-dot {'cd-red' if probed else 'cd-mut'}"></div>
          <span style="font-family:'IBM Plex Mono';font-size:10px;color:{col}">{t}</span>
          <span style="margin-left:auto;font-size:9px;color:{col}">{icon} {'PROBED' if probed else 'waiting'}</span>
        </div>"""

    payload_rows = ""
    risk_col = {"CRITICAL":"var(--red)","HIGH":"var(--red)","MEDIUM":"var(--ylw)","LOW":"var(--green)"}
    for p in list(hp["payloads"])[:6]:
        col = risk_col.get(p["risk"],"var(--mut)")
        payload_rows += f"""<div class="log-item">
          <span class="li-ts">{p['ts']}</span>
          <div class="li-topic">{p['topic']}</div>
          <div class="li-text" style="color:var(--txt)">{p['payload'][:60]}</div>
          <div style="font-size:10px;margin-top:3px;color:{col}">⚡ {p['intent']} | Risk: {p['risk']}</div>
          <div style="font-size:10px;color:var(--green);margin-top:2px">🎭 Fake reply: {p['fake_resp']}</div>
        </div>"""

    risk_badge_cls = {"CRITICAL":"b-alert","HIGH":"b-alert","MEDIUM":"b-warn","LOW":"b-ok"}
    risk_cls = risk_badge_cls.get(hp["analysis"]["risk"],"b-ok")

    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<title>Part 4 — Hacker + Honeypot</title>{COMMON_CSS}
<meta http-equiv="refresh" content="2"></head><body><div class="wrap">
{html_nav(8084)}
<div class="part-tag" style="color:var(--red);border-color:rgba(255,61,94,.3);background:rgba(255,61,94,.08)">
  💀 PART 4 — HACKER DEMO + HONEYPOT · Port 8084
</div>
<h1>Attack Simulation</h1>
<div class="subtitle">hacker attacks real network → dna flags it → silently moved to honeypot</div>

<div style="margin-bottom:18px">
  <button class="btn btn-red" id="launchBtn"
    onclick="this.disabled=true;fetch('/launch');setTimeout(()=>this.disabled=false,22000)">
    ▶ Launch Hacker Attack
  </button>
  &nbsp;
  <span style="font-size:11px;color:var(--mut)">
    Hacker: <strong style="color:var(--wht)">{hacker_state['id'] or '—'}</strong>
    &nbsp;|&nbsp; IP: <strong style="color:var(--wht)">{hacker_state['ip'] or '—'}</strong>
  </span>
</div>

{progress}

<div class="narrator {'nr' if hacker_state['phase'] in ['attacking','caught'] else 'nb'}">
  <div class="n-tag">HACKER STATUS</div>
  <div class="n-head">{hacker_state['narrator']}</div>
  <div class="n-body">Msgs sent: {hacker_state['msgs_sent']} | Phase: {hacker_state['phase'].upper()}</div>
</div>

<div class="stat-row">
  <div class="stat s3"><div class="sl">Total Catches</div><div class="sv">{hp['total_catches']}</div></div>
  <div class="stat s5"><div class="sl">Topics Probed</div><div class="sv">{len(hp['topics_probed'])}</div></div>
  <div class="stat s4"><div class="sl">Payloads Captured</div><div class="sv">{len(list(hp['payloads']))}</div></div>
</div>

<div style="display:grid;grid-template-columns:1fr 1fr;gap:14px">

  <div class="card">
    <div class="ch"><div class="ct">🪤 Honeypot Topics</div><div class="ctag">FAKE NETWORK</div></div>
    <div class="cb">{topic_rows}</div>
  </div>

  <div class="card">
    <div class="ch"><div class="ct">🔍 Attacker Analysis</div><div class="ctag">LIVE</div></div>
    <div class="cb">
      <div class="row"><span class="lbl">Intent</span>
        <span class="val" style="color:var(--pur)">{hp['analysis']['intent']}</span></div>
      <div class="row"><span class="lbl">Technique</span>
        <span class="val">{hp['analysis']['technique']}</span></div>
      <div class="row"><span class="lbl">Risk Level</span>
        <span class="badge {risk_cls}">{hp['analysis']['risk']}</span></div>
      <div class="row"><span class="lbl">Session active</span>
        <span class="val" style="color:{'var(--red)' if hp['active_session'] else 'var(--mut)'}">
          {'🔴 YES — inside honeypot' if hp['active_session'] else '○ No active session'}
        </span>
      </div>
    </div>
  </div>

</div>

<div class="card" style="margin-top:0">
  <div class="ch"><div class="ct">📦 Captured Payloads</div><div class="ctag">EVIDENCE</div></div>
  <div class="cb">{payload_rows if payload_rows else '<div style="color:var(--mut);font-size:12px">No payloads yet. Launch an attack to see captures.</div>'}</div>
</div>

<div class="card">
  <div class="ch"><div class="ct">🔗 How it connects</div></div>
  <div class="cb" style="font-size:12px;line-height:1.9;color:var(--txt)">
    <div>⚡ <strong style="color:var(--wht)">Hacker</strong>: POSTs to Broker (Part 1) pretending to be a device</div>
    <div>🧬 <strong style="color:var(--wht)">DNA</strong>: Scores the message as anomaly (score &gt; 0.6)</div>
    <div>🔀 <strong style="color:var(--wht)">Broker</strong>: Silently redirects to Honeypot on port {API_HONEYPOT}</div>
    <div>🪤 <strong style="color:var(--wht)">Honeypot</strong>: Sends fake responses — attacker stays engaged</div>
    <div>📋 <strong style="color:var(--wht)">Result</strong>: Full attack profile built, real network untouched</div>
  </div>
</div>
</div></body></html>"""


# ════════════════════════════════════════════════════════
# HTTP SERVERS — one per part
# ════════════════════════════════════════════════════════

def make_handler(html_fn, extra_routes=None):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def do_GET(self):
            path = urlparse(self.path).path
            if extra_routes and path in extra_routes:
                extra_routes[path](self)
                return
            body = html_fn().encode()
            self.send_response(200)
            self.send_header("Content-Type","text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers(); self.wfile.write(body)
        def do_POST(self):
            path = urlparse(self.path).path
            length = int(self.headers.get("Content-Length",0))
            body   = json.loads(self.rfile.read(length)) if length else {}
            if extra_routes and path in extra_routes:
                extra_routes[path](self, body)
                return
            self.send_response(200)
            self.send_header("Content-Type","application/json")
            self.end_headers(); self.wfile.write(b'{"ok":true}')
    return H

def serve(port, handler_cls, label):
    server = HTTPServer(("0.0.0.0", port), handler_cls)
    print(f"  ✓ {label} → http://localhost:{port}")
    server.serve_forever()

# ─── BROKER ROUTES ───
def broker_api_publish(handler, body):
    threading.Thread(target=broker_receive, args=(body,), daemon=True).start()
    handler.send_response(200)
    handler.send_header("Content-Type","application/json")
    handler.end_headers(); handler.wfile.write(b'{"ok":true}')

BrokerDash = make_handler(broker_html)
BrokerAPI  = make_handler(lambda:"", extra_routes={"/publish": broker_api_publish})

# ─── DEVICE ROUTES ───
DeviceDash = make_handler(device_html)

# ─── DNA ROUTES ───
DNADash = make_handler(dna_html)

# ─── HACKER ROUTES ───
def hacker_launch(handler):
    threading.Thread(target=launch_hacker, daemon=True).start()
    body = b'{"ok":true}'
    handler.send_response(200)
    handler.send_header("Content-Type","application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers(); handler.wfile.write(body)

def honeypot_api_receive(handler, body):
    threading.Thread(target=honeypot_receive, args=(body,), daemon=True).start()
    handler.send_response(200)
    handler.send_header("Content-Type","application/json")
    handler.end_headers(); handler.wfile.write(b'{"ok":true}')

HackerDash   = make_handler(hacker_html, extra_routes={"/launch": hacker_launch})
HoneypotAPI  = make_handler(lambda:"",   extra_routes={"/receive": honeypot_api_receive})


# ════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("\n" + "═"*54)
    print("  MQTT SHIELD — 4 Connected Parts")
    print("═"*54)

    parts = [
        (P_BROKER,   BrokerDash,   "Part 1 — Broker Dashboard"),
        (API_BROKER, BrokerAPI,    "Part 1 — Broker API       "),
        (P_DEVICE,   DeviceDash,   "Part 2 — Device Dashboard "),
        (P_DNA,      DNADash,      "Part 3 — DNA Dashboard    "),
        (P_HACKER,   HackerDash,   "Part 4 — Hacker Dashboard "),
        (API_HONEYPOT, HoneypotAPI,"Part 4 — Honeypot API     "),
    ]

    for port, handler, label in parts:
        t = threading.Thread(target=serve, args=(port, handler, label), daemon=True)
        t.start()
        time.sleep(0.1)

    # Start device publishing loop
    threading.Thread(target=device_loop, daemon=True).start()

    print(f"""
  Open all 4 dashboards:
  ┌──────────────────────────────────────────┐
  │  Part 1 — Broker       http://localhost:{P_BROKER}  │
  │  Part 2 — Device       http://localhost:{P_DEVICE}  │
  │  Part 3 — DNA+Healer   http://localhost:{P_DNA}  │
  │  Part 4 — Hacker+Trap  http://localhost:{P_HACKER}  │
  └──────────────────────────────────────────┘

  They are all connected:
  Device → Broker → DNA Analyzer → (allow / redirect to Honeypot)

  Go to Part 4 and click "Launch Hacker Attack" to see
  the full simulation across all 4 dashboards.

  Press Ctrl+C to stop.
""")

    try:
        while True: time.sleep(10)
    except KeyboardInterrupt:
        print("\n  Stopped.")
