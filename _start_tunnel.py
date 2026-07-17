"""Start uvicorn + cloudflare tunnel, write the public URL to _live_url.txt."""
import subprocess
import sys
import time
import re
import os

PORT = 8000
CFTUNNEL = r"C:\Program Files (x86)\cloudflared\cloudflared.exe"
OUT = "_tunnel.log"
URL_FILE = "_live_url.txt"


def main():
    # Start uvicorn
    uv = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", str(PORT)],
        stdout=open("_uvicorn.log", "w"),
        stderr=subprocess.STDOUT,
    )

    time.sleep(5)

    # Clear log
    open(OUT, "w").close()

    # Start cloudflare quick tunnel
    cf = subprocess.Popen(
        [CFTUNNEL, "tunnel", "--url", f"http://127.0.0.1:{PORT}", "--no-autoupdate"],
        stdout=open(OUT, "w"),
        stderr=subprocess.STDOUT,
        text=False,
    )

    # Wait for URL in the log file
    public_url = None
    deadline = time.time() + 45
    while time.time() < deadline:
        if cf.poll() is not None:
            break
        try:
            content = open(OUT, "r", encoding="utf-8", errors="replace").read()
            m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", content)
            if m:
                public_url = m.group(0)
                break
        except Exception:
            pass
        time.sleep(1)

    if public_url:
        open(URL_FILE, "w").write(public_url)
        # Test it
        time.sleep(3)
        import httpx
        try:
            r = httpx.get(public_url + "/health", timeout=20, follow_redirects=True)
            result = f"LIVE:{r.status_code}"
        except Exception as e:
            result = f"TEST_FAILED:{e}"
        print(f"URL={public_url}")
        print(f"HEALTH={result}")
        print(f"UVICORN_PID={uv.pid}")
        print(f"CF_PID={cf.pid}")
    else:
        print("NO_URL")
        # dump log
        print(open(OUT, "r", encoding="utf-8", errors="replace").read()[-2000:])
        uv.terminate()
        cf.terminate()


if __name__ == "__main__":
    main()