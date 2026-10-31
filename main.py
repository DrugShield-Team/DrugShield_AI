"""
DrugShield AI - Unified Subsystem Launcher
==========================================
Runs the DrugShield AI FastAPI analysis backend and concurrently orchestrates
the simulation subprocesses (WhatsApp on 8090, Telegram on 8001, Instagram on 8080).
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent


def spawn_simulation_subprocesses() -> list[subprocess.Popen]:
    """Start WhatsApp (8090), Telegram (8001), and Instagram (8080) in background."""
    processes = []
    npm_bin = "npm.cmd" if sys.platform == "win32" else "npm"

    sims = [
        ("WhatsApp Simulation (Port 8090)", ["node", "server.js"], PROJECT_ROOT / "simulations" / "whatsapp"),
        ("Telegram Simulation (Port 8001)", ["node", "server.js"], PROJECT_ROOT / "simulations" / "telegram"),
        ("Instagram Simulation (Port 8080)", [npm_bin, "run", "dev"], PROJECT_ROOT / "simulations" / "instagram"),
    ]

    for name, cmd, cwd in sims:
        if cwd.exists():
            try:
                p = subprocess.Popen(
                    cmd,
                    cwd=str(cwd),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                processes.append(p)
                print(f"[Orchestrator] Launched {name} (PID: {p.pid})")
            except Exception as e:
                print(f"[Orchestrator] Notice: Could not launch {name}: {e}")

    return processes


def main() -> None:
    import uvicorn

    sim_procs = spawn_simulation_subprocesses()

    def cleanup(sig=None, frame=None):
        print("\n[Orchestrator] Stopping child simulation processes...")
        for p in sim_procs:
            try:
                p.terminate()
                p.kill()
            except Exception:
                pass
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    try:
        uvicorn.run("src.api.app:app", host="127.0.0.1", port=8000, reload=False)
    finally:
        cleanup()


if __name__ == "__main__":
    main()
