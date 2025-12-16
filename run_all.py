#!/usr/bin/env python3
"""Run all services (ingestion, analytics, api, dashboard) from one command.

Usage:
    python run_all.py

This script is cross-platform and writes stdout/stderr of each service to
`logs/*.log`. Press Ctrl+C to stop all services.
"""
import os
import sys
import time
import subprocess


ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)


def ensure_dirs():
    for d in ("storage", "logs"):
        os.makedirs(d, exist_ok=True)


def start_process(name, cmd, logpath):
    logf = open(logpath, "a", buffering=1, encoding="utf-8")
    logf.write(f"=== Starting {name}: {' '.join(cmd)}\n")
    try:
        proc = subprocess.Popen(cmd, stdout=logf, stderr=subprocess.STDOUT)
    except Exception:
        logf.write("Failed to start process\n")
        logf.close()
        raise
    return proc, logf


def main():
    ensure_dirs()

    python = sys.executable or "python"

    services = [
        ("ingestion", [python, "-m", "ingestion.ws_ingest"], os.path.join("logs", "ingestion.log")),
        ("analytics", [python, "-m", "analytics.engine"], os.path.join("logs", "analytics.log")),
        ("api", [python, "-m", "api.server"], os.path.join("logs", "api.log")),
        ("dashboard", [python, "-m", "streamlit", "run", "dashboard/app.py"], os.path.join("logs", "dashboard.log")),
    ]

    procs = []
    try:
        for name, cmd, log in services:
            print(f"Starting {name} -> logging to {log}")
            proc, logf = start_process(name, cmd, log)
            procs.append((name, proc, logf))

        print("\nAll services started. Press Ctrl+C to stop.")
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nStopping services...")
    finally:
        for name, proc, logf in procs:
            print(f"Stopping {name} (pid={getattr(proc, 'pid', None)})")
            try:
                proc.terminate()
            except Exception:
                pass
        # give processes a moment to exit
        time.sleep(1.5)
        for name, proc, logf in procs:
            ret = None
            try:
                ret = proc.poll()
            except Exception:
                pass
            if ret is None:
                try:
                    proc.kill()
                except Exception:
                    pass
            try:
                logf.write(f"=== Stopped {name}\n")
                logf.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
