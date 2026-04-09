"""Memonexus Server Starter"""

import subprocess
import time
import os
import signal
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(BASE_DIR, "\u8bb0\u5fc6\u5e93")
FRONTEND_DIR = os.path.join(BASE_DIR, "web-app")

PORTS = {8000: "Backend", 5173: "Frontend"}
processes = []


def kill_port(port):
    """Kill process using specified port on Windows."""
    try:
        result = subprocess.run(["netstat", "-ano"], capture_output=True, text=True)
        for line in result.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                parts = line.split()
                for p in parts:
                    if p.isdigit() and int(p) > 0:
                        pid = int(p)
                        subprocess.run(
                            ["taskkill", "/PID", str(pid), "/F"], capture_output=True
                        )
                        print(f"  [Killed] PID {pid} on port {port}")
                        break
    except Exception:
        pass


def start():
    print("[Memonexus] Starting servers...\n")

    # Kill existing processes
    for port in PORTS:
        kill_port(port)

    time.sleep(2)

    # Start backend
    print("[Memonexus] Starting backend on port 8000...")
    backend_cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "src.api.server:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
    ]
    p_backend = subprocess.Popen(
        backend_cmd,
        cwd=BACKEND_DIR,
    )
    processes.append(p_backend)
    print(f"  [Backend] PID {p_backend.pid}")

    time.sleep(2)

    # Install frontend deps if needed
    if not os.path.exists(os.path.join(FRONTEND_DIR, "node_modules")):
        print("[Memonexus] Installing frontend dependencies...")
        subprocess.run([npm_cmd, "install"], cwd=FRONTEND_DIR)

    # Start frontend
    print("[Memonexus] Starting frontend on port 5173...")
    npm_cmd = r"C:\Program Files\nodejs\npm.cmd"
    p_frontend = subprocess.Popen(
        [npm_cmd, "run", "dev"],
        cwd=FRONTEND_DIR,
    )
    processes.append(p_frontend)
    print(f"  [Frontend] PID {p_frontend.pid}")

    print("\n[Memonexus] Done.")
    print("  Backend:  http://localhost:8000")
    print("  Frontend: http://localhost:5173\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[Memonexus] Shutting down...")
        for p in processes:
            try:
                p.terminate()
            except Exception:
                pass


if __name__ == "__main__":
    start()
