"""
AIOps Platform – WebSocket Client Example
==========================================
Demonstrates how to subscribe to the monitoring server and receive events.
Run this to test the notification subsystem.

Usage:
    python client_example.py --url ws://localhost:8765 --user my-user
"""

import asyncio
import json
import argparse
import logging
from datetime import datetime

import websockets

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("aiops.client")

SEVERITY_COLORS = {
    "CRITICAL": "\033[91m",  # Red
    "WARNING":  "\033[93m",  # Yellow
    "INFO":     "\033[92m",  # Green
}
RESET = "\033[0m"
DIM   = "\033[2m"


def fmt_event(evt: dict) -> str:
    sev   = evt.get("severity", "INFO")
    color = SEVERITY_COLORS.get(sev, "")
    ts    = evt.get("timestamp", "")
    try:
        ts = datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%H:%M:%S")
    except Exception:
        ts = ts[:19]

    return (
        f"{color}[{sev:8s}]{RESET} "
        f"{DIM}{ts}{RESET} "
        f"{color}{evt.get('reason', '?'):20s}{RESET} "
        f"{evt.get('namespace', '?'):15s}/"
        f"{evt.get('resource_name', '?'):30s}  "
        f"{DIM}{evt.get('message', '')[:80]}{RESET}"
    )


async def run(url: str, user_id: str, role: str, namespaces: list, teams: list):
    log.info("Connecting to %s as %s (%s)…", url, user_id, role)

    async with websockets.connect(url) as ws:
        # ── Subscription handshake ──────────────────────────────────────────
        sub = {
            "user_id":    user_id,
            "role":       role,
            "namespaces": namespaces,
            "teams":      teams,
            "severities": ["INFO", "WARNING", "CRITICAL"],
        }
        await ws.send(json.dumps(sub))
        log.info("Subscription sent: ns=%s teams=%s", namespaces or "*", teams or "*")

        # ── Message loop ────────────────────────────────────────────────────
        async for raw in ws:
            msg = json.loads(raw)
            msg_type = msg.get("type", "")

            if msg_type == "SUBSCRIBED":
                print(f"\n\033[96m✓ Subscribed — receiving events for user={user_id}\033[0m")
                history = msg.get("history", [])
                if history:
                    print(f"\033[2m── {len(history)} historical events ──\033[0m")
                    for evt in history[-10:]:
                        print(fmt_event(evt))
                    print(f"\033[2m── live stream ──\033[0m\n")

            elif msg_type == "PONG":
                pass

            elif msg_type == "HISTORY":
                for evt in msg.get("events", []):
                    print(fmt_event(evt))

            else:
                # Raw event
                print(fmt_event(msg))


def main():
    parser = argparse.ArgumentParser(description="AIOps WebSocket client")
    parser.add_argument("--url",        default="ws://localhost:8765")
    parser.add_argument("--user",       default="operator-1")
    parser.add_argument("--role",       default="operator", choices=["viewer","operator","admin"])
    parser.add_argument("--namespaces", default="", help="Comma-separated list, empty=all")
    parser.add_argument("--teams",      default="", help="Comma-separated list, empty=all")
    args = parser.parse_args()

    namespaces = [n.strip() for n in args.namespaces.split(",") if n.strip()]
    teams      = [t.strip() for t in args.teams.split(",")      if t.strip()]

    asyncio.run(run(args.url, args.user, args.role, namespaces, teams))


if __name__ == "__main__":
    main()
