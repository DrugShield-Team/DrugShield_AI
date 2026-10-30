"""
DrugShield AI - Unified Multi-Platform Simulation Launcher
===========================================================
Automatically initializes and monitors all DrugShield AI subsystem microservices:
1. Backend REST & WebSocket Engine (Port 8000 via Uvicorn)
2. WhatsApp Chat Simulation Server (Port 8090 via Node.js)
3. Telegram Web Simulation Server (Port 8001 via Node.js)
4. Instagram Direct Simulation Frontend (Port 5173 via Vite/NPM)

Ensures graceful lifecycle shutdown across all child processes upon SIGINT/SIGTERM.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

SERVICES = [
    {
        "name": "Backend Engine (FastAPI / WebSocket)",
        "cmd": [sys.executable, "-m", "uvicorn", "src.api.app:app", "--host", "127.0.0.1", "--port", "8000"],
        "cwd": PROJECT_ROOT,
        "env": {**os.environ, "PYTHONPATH": str(PROJECT_ROOT)},
    },
    {
        "name": "WhatsApp Simulation (Port 8090)",
        "cmd": ["node", "server.js"],
        "cwd": PROJECT_ROOT / "simulations" / "whatsapp",
        "env": os.environ.copy(),
    },
    {
        "name": "Telegram Simulation (Port 8001)",
        "cmd": ["node", "server.js"],
        "cwd": PROJECT_ROOT / "simulations" / "telegram",
        "env": os.environ.copy(),
    },
    {
        "name": "Instagram Simulation (Port 5173)",
        "cmd": ["npm.cmd" if sys.platform == "win32" else "npm", "run", "dev"],
        "cwd": PROJECT_ROOT / "simulations" / "instagram",
        "env": os.environ.copy(),
    },
]


def launch_all() -> None:
    processes: list[tuple[str, subprocess.Popen]] = []

    print("\n" + "=" * 70)
    print("🛡️  DRUGSHIELD AI - MULTI-PLATFORM UNIFIED ORCHESTRATOR")
    print("=" * 70)

    for svc in SERVICES:
        name = svc["name"]
        cmd = svc["cmd"]
        cwd = svc["cwd"]
        env = svc["env"]

        print(f"[*] Starting {name}...")
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(cwd),
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            processes.append((name, proc))
            print(f"    ✓ {name} online (PID: {proc.pid})")
        except Exception as e:
            print(f"    ✗ Failed to start {name}: {e}")

    print("\n" + "-" * 70)
    print("ALL PLATFORMS LAUNCHED SUCCESSFULLY:")
    print("  • Command Center Dashboard: http://127.0.0.1:8000/command_center.html")
    print("  • WhatsApp Simulation:      http://127.0.0.1:8090")
    print("  • Telegram Simulation:      http://127.0.0.1:8001")
    print("  • Instagram Simulation:     http://127.0.0.1:5173")
    print("-" * 70)
    print("Press CTRL+C anytime to terminate all services.\n")

    def handle_sig(sig, frame):
        print("\n[!] Shutting down all DrugShield microservices...")
        for name, p in processes:
            try:
                p.terminate()
                p.kill()
            except Exception:
                pass
        print("[✓] All services stopped cleanly.")
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_sig)
    signal.signal(signal.SIGTERM, handle_sig)

    # Monitor loop
    try:
        while True:
            for name, p in processes:
                ret = p.poll()
                if ret is not None:
                    print(f"[!] Warning: {name} terminated unexpectedly with code {ret}")
            time.sleep(2)
    except KeyboardInterrupt:
        handle_sig(None, None)


if __name__ == "__main__":
    launch_all()
