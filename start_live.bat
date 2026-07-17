@echo off
REM ============================================
REM   Start the Live Indeed Job Finder Website
REM ============================================
REM This starts the FastAPI app + a public Cloudflare Tunnel.
REM Anyone can access your site via the printed URL.
REM Keep this window open to keep the site running.
REM ============================================

cd /d "%~dp0"

echo Starting Indeed Job Finder...
echo.

REM Pre-populate DB with Indeed jobs (scraped from your residential IP)
echo [1/3] Scraping Indeed jobs from your PC...
call .venv\Scripts\activate.bat
python -c "import json,os; os.path.exists('dist/jobs.json') and print('Using cached Indeed jobs:',
len(json.load(open('dist/jobs.json'))['jobs']))" 2>nul

echo [2/3] Starting web server...
start /b "" .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 > nul 2>&1

timeout /t 4 /nobreak > nul

echo [3/3] Starting public tunnel...
echo.
echo ============================================
echo   YOUR LIVE SITE URL WILL APPEAR BELOW
echo   (share it with anyone!)
echo ============================================
echo.

"C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel --url http://127.0.0.1:8000 --no-autoupdate

pause