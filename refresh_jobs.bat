@echo off
REM Daily Indeed refresh — run this from your PC (residential IP).
REM Scrapes Indeed, commits the updated dist/, and pushes to publish via GitHub Pages.
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python generate_static.py
git add dist/
git commit -m "chore: refresh Indeed jobs (%date% %time%)"
git push origin main
echo Done. Site will auto-publish via GitHub Actions.
pause