# MQTT Shield — README

## Overview
MQTT Shield is an intelligent, self-defending IoT security framework built for real-time threat detection and deception-based defense on MQTT networks. It monitors all broker traffic, learns each connected device's normal behavioral pattern (its "DNA"), and silently redirects attackers into a virtual honeypot — feeding them convincing fake responses while the real IoT network continues operating completely undisturbed. When a threat is detected, the system autonomously self-heals without any human intervention.

---

## Problem Statement
MQTT is the most widely used protocol for IoT communication, yet it ships with zero built-in security. Any device on the internet can connect to an MQTT broker, subscribe to any topic, publish malicious commands to industrial sensors, smart grids, or medical devices, and cause real-world damage. Existing defenses either block attackers outright (immediately tipping them off) or rely on static ACL rules that are trivially bypassed by changing a topic name. No current solution dynamically learns device behavior, silently traps attackers, captures forensic intelligence, and self-heals — all simultaneously.

---

## Solution
MQTT Shield solves this with three layered mechanisms working together:

**1. Communication DNA Engine** — The system watches the first 10 messages from any connected device and builds a behavioral fingerprint: which topics it uses, how frequently it publishes, what its payload structure looks like. Once locked, every subsequent message is scored from 0.0 to 1.0 against this baseline. A score above 0.65 triggers a threat response.

**2. Deception Network (Honeypot)** — Instead of blocking the attacker (which reveals detection), the broker silently mirrors all their traffic to a fake virtual network. The honeypot returns convincing fake responses — "auth granted", "command accepted", "admin access confirmed" — while the real devices are completely isolated from the attack.

**3. Self-Healing Controller** — The moment a threat is confirmed, four automated responses fire in sequence: rate limiting is applied, the client is removed from the ACL whitelist, the IP is blocked at the firewall level, and all future traffic is permanently redirected to the honeypot. Zero human action required.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        MACHINE 1                            │
│                                                             │
│   Mosquitto MQTT Broker  (port 1883)                        │
│         │                                                   │
│   MQTTShield Monitor  ──► DNA Analyser                      │
│         │                      │                            │
│         │              verdict: allow / warn / threat       │
│         │                      │                            │
│         ├── allow ─────────────► Real Network (untouched)   │
│         │                                                   │
│         └── threat ────────────► Honeypot Engine            │
│                                       │                     │
│                                 Fake reply sent back        │
│                                       │                     │
│                                 Self-Heal fires:            │
│                                   Rate Limit                │
│                                   ACL Blacklist             │
│                                   IP Block                  │
│                                   Permanent Redirect        │
│                                                             │
│   Live Dashboard  →  http://localhost:8080                  │
└─────────────────────────────────────────────────────────────┘
                              │
                          LAN / Wi-Fi
                              │
┌─────────────────────────────────────────────────────────────┐
│                        MACHINE 2                            │
│                                                             │
│   TempSensor01  ──► publishes temp/humidity/CO₂ every 5s   │
│                                                             │
│   AttackerBot   ──► recon → inject → flood → brute-force   │
│                                                             │
│   Interactive Browser UI  →  http://localhost:8081          │
│     Left panel  : live sensor gauges + DNA progress        │
│     Right panel : attack buttons + honeypot replies        │
└─────────────────────────────────────────────────────────────┘
```

---

## Features

- **Real-time DNA fingerprinting** — automatically learns each device's behavioral baseline with zero pre-configuration
- **Anomaly scoring** — every message scored 0.0–1.0 in real time against the locked baseline
- **Silent deception** — attackers are never blocked or disconnected; they are redirected without any indication
- **Honeypot intelligence** — fake responses tailored per topic (admin, control, config, shell, OTA, etc.)
- **Forensic capture** — every attacker payload, topic, timestamp, and fake reply logged and available as a downloadable report
- **Autonomous self-healing** — four-stage automatic response fires without human input
- **Fully interactive HTML UI** — no terminal needed for the demo; everything runs in the browser
- **Cross-machine real network communication** — real MQTT packets flow over LAN/Wi-Fi between machines
- **Zero external Python dependencies beyond paho-mqtt and Flask**

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.7+ |
| MQTT Broker | Mosquitto |
| MQTT Client | paho-mqtt |
| Web Framework | Flask |
| Real-time Updates | Server-Sent Events (SSE) |
| Frontend | Pure HTML / CSS / JavaScript |
| DNA Algorithm | Statistical baseline + EMA anomaly scoring |
| Honeypot | In-process fake topic mirror with per-topic fake response templates |
| Self-Heal | Threaded automated response engine |
| Network | Direct LAN or Wi-Fi (two-machine setup) |

---

## File Structure

```
mqtt_shield_live/
│
├── server.py          # Machine 1 — DNA engine, honeypot, self-heal, dashboard
├── client_ui.py       # Machine 2 — interactive browser UI, device + attacker
├── config.py          # Shared config — set BROKER_IP here on Machine 2
├── mosquitto.conf     # Broker config — copy to C:\Program Files\mosquitto\
│
├── start_broker.bat   # Machine 1 — starts Mosquitto on port 1883
├── start_server.bat   # Machine 1 — starts server.py + opens browser
├── start_client.bat   # Machine 2 — starts client_ui.py + opens browser
│
└── CHEAT_SHEET.txt    # Stage demo script with exact words to say
```

---

## Setup

### Machine 1
1. Install Mosquitto from mosquitto.org/download
2. Copy `mosquitto.conf` to `C:\Program Files\mosquitto\`
3. Run `pip install flask paho-mqtt`
4. Run `start_broker.bat` → wait for "Opening ipv4 listen socket on port 1883"
5. Run `start_server.bat` → open `http://localhost:8080` → press F11

### Machine 2
1. Run `pip install paho-mqtt flask`
2. Open `config.py` → set `BROKER_IP` to Machine 1's IP address
3. Run `start_client.bat` → open `http://localhost:8081`

### Finding Machine 1's IP
Open CMD on Machine 1 and run `ipconfig`. Look for **IPv4 Address** under your Wi-Fi or Ethernet adapter. For a direct LAN cable connection, set both machines to static IPs — Machine 1 to `192.168.10.1` and Machine 2 to `192.168.10.2`.

---

## Demo Flow

| Step | Action | Working |
|------|--------|----------------|
| 1 | Click START DEVICE on Machine 2 | Sensor gauges come alive — temp, humidity, CO₂ updating every 5s |
| 2 | Watch DNA bar fill | Machine 1 dashboard shows baseline learning progress |
| 3 | DNA bar turns green | "DNA LOCKED" — detection mode active |
| 4 | Click CONNECT ATTACKER | Attack buttons unlock on Machine 2 |
| 5 | Click FULL AUTO SEQUENCE | 5-phase attack runs automatically with narration |
| 6 | Watch Machine 1 | Score spikes to 95%, THREAT fires, honeypot activates, self-heal fires |
| 7 | Watch Machine 2 | Honeypot reply box flashes — attacker sees fake "admin granted" data |
| 8 | Open /report | Full forensic capture of every attacker payload |

---

## Attack Phases

**Phase 1 — Reconnaissance** — Attacker subscribes to common topic patterns to map the IoT network topology. Equivalent to port scanning in traditional hacking.

**Phase 2 — Control Injection** — Attacker publishes malicious commands to actuator topics (pumps, valves, HVAC, reboot). These topics are completely outside TempSensor01's baseline — DNA score spikes immediately.

**Phase 3 — Payload Injection** — Attacker embeds shell commands, SQL injection strings, path traversal, and base64-encoded malware inside MQTT payloads hoping the IoT backend will execute them.

**Phase 4 — Rate Flood** — Attacker sends 20 messages in rapid succession — far above the normal baseline rate — triggering the rate-spike detector in the DNA engine.

**Phase 5 — Credential Brute-Force** — Attacker rapidly reconnects with 10 common username/password combinations hoping to gain authenticated access to the broker.

---

## Key Innovation

The critical insight behind MQTT Shield is that **blocking is the wrong response**. When an attacker gets blocked or disconnected, they immediately know they have been detected. They stop, change their approach, and try again from a different angle.

MQTT Shield never blocks. Instead, it silently moves the attacker into a parallel fake universe — a honeypot that mirrors every real topic but returns fabricated data. The attacker continues probing, believing they are making progress, while every payload they send is captured as forensic evidence. By the time they realize something is wrong, the real network has already self-healed and a complete attack profile has been built.

---

## Team
**Tech Hunters** — Cyberthon '26, SRM Institute of Science and Technology, Ramapuram Campus

**Problem Statement** — PS10: Security Analysis and Vulnerability Detection in MQTT-Based IoT Systems
