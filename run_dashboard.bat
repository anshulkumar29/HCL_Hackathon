@echo off
cd /d "%~dp0"
echo Starting ShopSphere dashboard... (close this window to stop it)
python -m streamlit run dashboard.py
pause

