@echo off
chcp 65001 >nul
title AutoSRT 启动器

echo ==========================================
echo       AutoSRT WebUI 一键启动脚本
echo ==========================================
echo.

echo [*] 正在启动后端 API 服务 (端口 8000)...
start "AutoSRT 后端 (FastAPI)" cmd /k "call venv\Scripts\activate.bat && python app.py"

echo [*] 正在启动前端 Web 服务 (端口 8080)...
start "AutoSRT 前端 (WebUI)" cmd /k "cd frontend && python -m http.server 8080"

echo.
echo [*] 服务已启动，正在为你打开浏览器...
:: 等待 2 秒钟，确保本地服务器已经完全跑起来再打开网页
timeout /t 2 /nobreak >nul
start http://127.0.0.1:8080