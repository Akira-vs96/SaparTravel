"""Apply the schema and supervise the API and durable worker in one container."""
import os
import signal
import subprocess
import sys
import time


def supervise(commands):
    children = []
    stopping = False

    def stop(signum, frame):
        nonlocal stopping
        stopping = True

    previous = {sig: signal.signal(sig, stop) for sig in (signal.SIGTERM, signal.SIGINT)}
    try:
        for command in commands:
            if stopping:
                return 0
            children.append(subprocess.Popen(command))
        while not stopping:
            for child in children:
                result = child.poll()
                if result is not None:
                    # A missing worker is a failed service even if the API lives.
                    return result or 1
            time.sleep(.25)
        return 0
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        deadline = time.monotonic() + 20
        for child in children:
            try:
                child.wait(timeout=max(.01, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def main():
    public_url = os.environ.get("RENDER_EXTERNAL_URL")
    if public_url:
        os.environ.setdefault("PUBLIC_WEB_URL", public_url)
        os.environ.setdefault("CORS_ORIGINS", public_url)
    port = int(os.environ.get("PORT", "10000"))
    if not 1 <= port <= 65535:
        raise SystemExit("PORT must be between 1 and 65535")
    # Settings hide secret inputs in validation errors. Never print the env.
    from app.core.config import get_settings
    get_settings()
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)
    subprocess.run([sys.executable, "-m", "app.seed"], check=True)
    raise SystemExit(supervise([
        [sys.executable, "-m", "uvicorn", "app.public:app", "--host", "0.0.0.0", "--port", str(port), "--no-access-log"],
        [sys.executable, "-m", "app.worker", "--interval", "10"],
    ]))


if __name__ == "__main__":
    main()

