@echo off
chcp 65001 >nul
cd /d "%~dp0"
REM 使用项目内置虚拟环境，避免系统 Python 缺少 Django/openai 依赖
.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
pause