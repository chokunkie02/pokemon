"""
start.py — รันทั้ง Backend (uvicorn) และ Frontend (npm run dev) พร้อมกันในหน้าต่างเดียว
กด Ctrl+C เพื่อหยุดทั้งสองพร้อมกัน
"""
import subprocess
import sys
import os
import signal
import threading
import shutil

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

# Python executable ที่ใช้ตอนนี้
PYTHON = sys.executable


def _resolve_backend_python():
    """Pick a Python interpreter that can run backend dependencies reliably."""
    # Priority: BACKEND_PYTHON env -> backend/venv -> current interpreter -> python on PATH.
    # The first one that can import the backend deps wins.
    env_python = os.environ.get("BACKEND_PYTHON", "").strip()
    venv_python = os.path.join(BACKEND_DIR, "venv", "Scripts", "python.exe")
    if env_python:
        return env_python

    candidates = [venv_python, PYTHON, shutil.which("python")]
    existing = [c for c in candidates if c and os.path.exists(c)]
    for candidate in existing:
        if _preflight_backend_python(candidate)[0]:
            return candidate
    return existing[0] if existing else PYTHON


def _preflight_backend_python(python_exe):
    """Return (ok, message). Ensures required backend modules are importable."""
    cmd = [python_exe, "-c", "import uvicorn, llama_cpp; print('ok')"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    except Exception as e:
        return False, f"ไม่สามารถรัน preflight ได้: {e}"

    if proc.returncode == 0:
        return True, "ok"

    detail = (proc.stdout or "") + (proc.stderr or "")
    return False, detail.strip()


def _kill_process_on_port(port):
    """Kill process that is LISTENING on a given TCP port (Windows only)."""
    if sys.platform != "win32":
        return

    try:
        out = subprocess.check_output(["netstat", "-ano", "-p", "tcp"], text=True, encoding="utf-8", errors="ignore")
    except Exception as e:
        print(f"[start.py] ไม่สามารถตรวจพอร์ต {port} ได้: {e}")
        return

    pids = set()
    needle = f":{port}"
    for line in out.splitlines():
        row = line.strip()
        if needle not in row or "LISTENING" not in row:
            continue
        parts = row.split()
        if parts and parts[-1].isdigit():
            pids.add(parts[-1])

    for pid in pids:
        try:
            subprocess.run(["taskkill", "/PID", pid, "/F"], check=False, capture_output=True, text=True)
            print(f"[start.py] ปิด process ค้างบนพอร์ต {port} (PID {pid})")
        except Exception as e:
            print(f"[start.py] ปิด PID {pid} ไม่สำเร็จ: {e}")


def _clear_runtime_cache():
    """Clear stale runtime state/cache so every start is fresh."""
    print("[start.py] กำลังล้างสถานะเก่าก่อนเริ่ม...")

    # 1) Kill stale servers that keep old game state alive.
    for p in [8000, 5173, 5174, 5175]:
        _kill_process_on_port(p)

    # 2) Clear common dev caches.
    cache_dirs = [
        os.path.join(BACKEND_DIR, "__pycache__"),
        os.path.join(FRONTEND_DIR, "node_modules", ".vite"),
    ]
    for cache_dir in cache_dirs:
        if os.path.isdir(cache_dir):
            try:
                shutil.rmtree(cache_dir, ignore_errors=True)
                print(f"[start.py] ล้างแคช: {cache_dir}")
            except Exception as e:
                print(f"[start.py] ล้างแคชไม่สำเร็จ ({cache_dir}): {e}")


def stream_output(process, prefix):
    """อ่าน stdout/stderr แล้วพิมพ์พร้อม prefix"""
    for line in iter(process.stdout.readline, b""):
        text = line.decode("utf-8", errors="replace").rstrip()
        if text:
            print(f"[{prefix}] {text}", flush=True)


def main():
    backend_python = _resolve_backend_python()
    print("=" * 60)
    print("  Pokemon TCG Pocket — Starting Backend + Frontend")
    print("=" * 60)
    print(f"  Backend : {BACKEND_DIR}")
    print(f"  Frontend: {FRONTEND_DIR}")
    print(f"  Python : {backend_python}")
    print("  กด Ctrl+C เพื่อหยุดทั้งสอง")
    print("=" * 60)

    _clear_runtime_cache()

    ok, msg = _preflight_backend_python(backend_python)
    if not ok:
        print("[start.py] Backend preflight failed: Python environment ยังไม่พร้อม")
        print(msg)
        print("[start.py] แนะนำ: ติดตั้ง dependency ด้วย python ที่จะแชร์กับ backend")
        print(f"[start.py] ตัวอย่าง: {backend_python} -m pip install -r backend/requirements.txt")
        sys.exit(1)

    procs = []

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    # --- Backend ---
    backend_proc = subprocess.Popen(
        [backend_python, "-m", "uvicorn", "main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"],
        cwd=BACKEND_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
    )
    procs.append(backend_proc)
    threading.Thread(target=stream_output, args=(backend_proc, "BACKEND"), daemon=True).start()

    # --- Frontend ---
    npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
    frontend_proc = subprocess.Popen(
        [npm_cmd, "run", "dev"],
        cwd=FRONTEND_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    procs.append(frontend_proc)
    threading.Thread(target=stream_output, args=(frontend_proc, "FRONTEND"), daemon=True).start()

    # รอ Ctrl+C
    try:
        for p in procs:
            p.wait()
    except KeyboardInterrupt:
        print("\n[start.py] Ctrl+C — กำลังหยุดทุก process...")
        for p in procs:
            try:
                if sys.platform == "win32":
                    p.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    p.terminate()
            except Exception:
                pass
        for p in procs:
            try:
                p.wait(timeout=5)
            except Exception:
                p.kill()
        print("[start.py] หยุดทุก process แล้ว")


if __name__ == "__main__":
    main()
