"""
start.py — Railway Launcher
Runs ai_scout (background worker) + streamlit dashboard (web) in the same process/container
so both share the same scout_brain.db filesystem.
"""
import subprocess
import sys
import os
import signal
import time

PORT = os.getenv("PORT", "8501")

print("🚀 Starting AI Scout System...")

scout_proc = subprocess.Popen(
    [sys.executable, "ai_scout.py"],
    stdout=sys.stdout,
    stderr=sys.stderr
)
print(f"✅ AI Scout bot started (PID: {scout_proc.pid})")

time.sleep(3)

dashboard_proc = subprocess.Popen(
    [
        sys.executable, "-m", "streamlit", "run", "dashboard.py",
        "--server.port", PORT,
        "--server.address", "0.0.0.0",
        "--server.headless", "true",
    ],
    stdout=sys.stdout,
    stderr=sys.stderr
)
print(f"✅ Dashboard started on port {PORT} (PID: {dashboard_proc.pid})")


def shutdown(signum, frame):
    print("\n🛑 Shutting down...")
    scout_proc.terminate()
    dashboard_proc.terminate()
    sys.exit(0)

signal.signal(signal.SIGTERM, shutdown)
signal.signal(signal.SIGINT, shutdown)

dashboard_proc.wait()
