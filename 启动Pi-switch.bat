@echo off
chcp 65001 >nul
title Pi-switch
cd /d "%~dp0"

REM 优先用"无窗口版"Python (pythonw)，启动后黑框自动关闭、不留控制台
set "PYW="
where pythonw >nul 2>nul && set "PYW=pythonw"
if not defined PYW where pyw >nul 2>nul && set "PYW=pyw"

if defined PYW (
    start "" %PYW% pi_switch.py
    exit /b 0
)

REM 没有窗口版，退回控制台版 (py/python)，会保留一个黑框
set "PY="
where py >nul 2>nul && set "PY=py"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
    echo.
    echo  [错误] 未找到 Python。请安装 Python 3 并勾选 "Add to PATH"。
    echo.
    pause
    exit /b 1
)

"%PY%" pi_switch.py
if errorlevel 1 (
    echo.
    echo  [错误] 程序异常退出。错误日志见同目录 error.log
    pause
)
