"""Start uvicorn and a Cloudflare quick tunnel, then print the public URL."""
import subprocess
import sys
import time
import re
import os

PORT = 8000
CFTUNNEL = r"C:\Program Files (x86)\cloudflared\cloudflared.exe"


def main():
    # Start uvicorn (bind all interfaces so the tunnel can reach it)
    uv = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", str(PORT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    print(f"uvicorn started pid={uv.pid} on :{PORT}")
    time.sleep(4)

    # Verify local health
    import httpx
    try:
        r = httpx.get(f"http://127.0.0.1:{PORT}/health", timeout=10)
        print("local health:", r.status_code, r.text)
    except Exception as e:
        print("local health FAILED:", e)

    # Start cloudflare quick tunnel — prints a public trycloudflare URL
    cf = subprocess.Popen(
        [CFTUNNEL, "tunnel", "--url", f"http://127.0.0.1:{PORT}", "--no-autoupdate"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    public_url = None
    deadline = time.time() + 60
    while time.time() < deadline:
        line = cf.stdout.readline()
        if not line:
            if cf.poll() is not None:
                print("cloudflared exited early rc=", cf.returncode)
                break
            time.sleep(0.2)
            continue
        sys.stdout.write(line)
        m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
        if m and not public_url:
            public_url = m.group(0)
            print("\nPUBLIC URL:", public_url, "\n")
            break

    if not public_url:
        print("No trycloudflare URL captured in time.")
        return

    # Test the public URL
    time.sleep(3)
    try:
        r = httpx.get(public_url + "/health", timeout=20, follow_redirects=True)
        print("PUBLIC health:", r.status_code, r.text)
    except Exception as e:
        print("PUBLIC health FAILED:", e)

    print("\n>>> Site is LIVE at:", public_url)
    print(">>> Keep this window open to keep the site running.")
    print(">>> Press Ctrl+C to stop.")

    try:
        cf.wait()
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        cf.terminate()
        uv.terminate()


if __name__ == "__main__":
    main()