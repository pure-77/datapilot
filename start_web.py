"""
DataPilot 一键启动脚本

    .venv\\Scripts\\python.exe start_web.py

启动两个服务并自动打开浏览器：
    backend  : uvicorn app.main:app  http://127.0.0.1:8001
    frontend : http.server            http://127.0.0.1:5500/index.html

按 Ctrl+C 停止。
"""
from __future__ import annotations

import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"
BACKEND_PORT = 8001
FRONTEND_PORT = 5500


def get_python() -> str:
    """优先使用项目 .venv 解释器"""
    for candidate in (ROOT / ".venv" / "Scripts" / "python.exe", ROOT / ".venv" / "bin" / "python"):
        if candidate.exists():
            return str(candidate)
    return sys.executable


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def wait_for_backend(port: int, timeout: int = 30) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            time.sleep(1)
    return False


def main() -> int:
    py = get_python()

    print("=" * 54)
    print("  DataPilot")
    print(f"    backend   : http://127.0.0.1:{BACKEND_PORT}")
    print(f"    frontend  : http://127.0.0.1:{FRONTEND_PORT}/index.html")
    print(f"    interpreter: {py}")
    print("=" * 54)

    procs: list[subprocess.Popen] = []

    if port_in_use(BACKEND_PORT):
        print(f"[1/3] 端口 {BACKEND_PORT} 已被占用，跳过后端启动")
    else:
        print(f"[1/3] 启动后端 ...")
        procs.append(subprocess.Popen(
            [py, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(BACKEND_PORT)],
            cwd=str(BACKEND_DIR),
        ))

    if port_in_use(FRONTEND_PORT):
        print(f"[2/3] 端口 {FRONTEND_PORT} 已被占用，跳过前端启动")
    else:
        print(f"[2/3] 启动前端 ...")
        procs.append(subprocess.Popen(
            [py, "-m", "http.server", str(FRONTEND_PORT), "--bind", "127.0.0.1"],
            cwd=str(FRONTEND_DIR),
        ))

    print("[3/3] 等待后端就绪 ...")
    if wait_for_backend(BACKEND_PORT):
        print("      后端已就绪")
        webbrowser.open(f"http://127.0.0.1:{FRONTEND_PORT}/index.html")
    else:
        print("      [警告] 后端 30 秒内未就绪，请查看上方日志")

    print("\n服务运行中，按 Ctrl+C 停止。")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n正在停止服务 ...")
    finally:
        for p in procs:
            if p.poll() is None:
                p.terminate()
        for p in procs:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
        print("已停止。")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
