@echo off
title 10kinM AI Launcher
echo ==================================================
echo   🚀 STARTING 10KINM AI DIGITAL WORKER
echo ==================================================
echo.
echo 1) Starting AI Scout Engine (Data Farming & Synapse)...
start "AI Scout Engine" cmd /k "python ai_scout.py"

echo 2) Starting Web Dashboard...
start "AI Knowledge Dashboard" cmd /k "streamlit run dashboard.py"

echo.
echo ✅ All systems launched! 
echo You can close this small window now.
timeout /t 3
exit
