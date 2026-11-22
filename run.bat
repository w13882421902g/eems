@echo off
chcp 65001 >nul
cd /d "%~dp0"

REM ===== 大模型环境变量（Key 在此处填写；不写进 Python 代码）=====
REM 硅基流动：https://siliconflow.cn 控制台「API 密钥」创建 sk- 开头密钥
set "AI_API_KEY=sk-cfhohvoajcyfixxsmaawlzznxvutkwrusuixubzgayliuqqt"
set "AI_BASE_URL=https://api.siliconflow.cn/v1"
set "AI_MODEL=Qwen/Qwen2.5-7B-Instruct"

REM ===== 直接使用项目 .venv 解释器，避免误用系统 Python =====
.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
pause
