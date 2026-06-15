@echo off
REM ============================================================
REM run.bat — Windows 一键启动脚本
REM ============================================================
REM 论文-研报工作流 跨平台启动入口
REM   Linux/macOS:    ./run.sh
REM   Windows:        run.bat
REM ============================================================

setlocal enabledelayedexpansion

REM ── 颜色（Windows 10+ 支持 ANSI）────────────────────────
for /F "tokens=*" %%i in ('echo prompt $E ^| cmd') do set "ESC=%%i"
set "GREEN=%ESC%[92m"
set "YELLOW=%ESC%[93m"
set "RED=%ESC%[91m"
set "RESET=%ESC%[0m"

echo %GREEN%============================================================%RESET%
echo %GREEN%  论文-研报工作流 · FinResearch Agent (Windows)%RESET%
echo %GREEN%============================================================%RESET%
echo.

REM ── 1) Python 检查 ───────────────────────────────────
where python >nul 2>nul
if errorlevel 1 (
    echo %RED%[X] Python 未安装。请先安装 Python 3.10+ (勾选 Add to PATH)%RESET%
    echo     下载: https://www.python.org/downloads/
    exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo %GREEN%[OK]%RESET% Python !PYVER!

REM ── 2) venv 创建/激活 ────────────────────────────────
if not exist ".venv\Scripts\activate.bat" (
    echo %YELLOW%[*]%RESET% 创建虚拟环境 .venv ...
    python -m venv .venv
    if errorlevel 1 (
        echo %RED%[X] 虚拟环境创建失败%RESET%
        exit /b 1
    )
)
call .venv\Scripts\activate.bat
echo %GREEN%[OK]%RESET% 已激活 venv

REM ── 3) 依赖安装 ──────────────────────────────────────
if not exist ".venv\.installed" (
    echo %YELLOW%[*]%RESET% 安装依赖 (首次较慢，约 2-5 分钟) ...
    python -m pip install --upgrade pip
    python -m pip install -e .
    if errorlevel 1 (
        echo %YELLOW%[!] 核心依赖安装失败，尝试 requirements.txt ...%RESET%
        python -m pip install -r requirements.txt
    )
    type nul > .venv\.installed
    echo %GREEN%[OK]%RESET% 依赖安装完成
) else (
    echo %GREEN%[OK]%RESET% 依赖已安装（跳过）
)

REM ── 4) Keychain 检查（Windows 用 Credential Manager）──
echo.
echo %YELLOW%[?] 是否配置 API Key？%RESET%
echo     1) 是 - 打开配置向导
echo     2) 否 - 使用默认 / fallback
set /p CHOICE=
if "!CHOICE!"=="1" (
    python scripts\keychain_setup.py
)

REM ── 5) 健康检查 ──────────────────────────────────────
echo.
echo %YELLOW%[*]%RESET% 系统健康检查 ...
python scripts\health_check.py
if errorlevel 1 (
    echo %YELLOW%[!] 健康检查有警告，但可继续%RESET%
)

REM ── 6) MCP 注册（可选）──────────────────────────────
if exist "%USERPROFILE%\.cursor\mcp.json" (
    echo.
    echo %YELLOW%[?] 是否注册 MCP 服务器到 Cursor？%RESET%
    echo     1) 是 - 注册全部 44 个
    echo     2) 是 - 注册 academic profile (18 个，推荐)
    echo     3) 是 - 注册 minimal profile (5 个，演示)
    echo     4) 否
    set /p MCP=
    if "!MCP!"=="1" python scripts\register_mcp_servers.py
    if "!MCP!"=="2" python scripts\register_mcp_servers.py --profile academic
    if "!MCP!"=="3" python scripts\register_mcp_servers.py --profile minimal
)

echo.
echo %GREEN%============================================================%RESET%
echo %GREEN%  启动完成！%RESET%
echo.
echo   快速开始:
echo     python scripts\demo_research_report.py     # 演示研报
echo     python scripts\agent_pipeline.py --topic "..."  # 完整流水线
echo.
echo   文档: README.md / 使用指南.md
echo %GREEN%============================================================%RESET%

endlocal
