@echo off
REM ============================================================
REM  CET 智胜 · 安卓 .apk 一键打包脚本 (Windows 本地)
REM ============================================================
REM  注意: Buildozer 在 Windows 原生环境无法直接打包安卓 APK。
REM  推荐方案:
REM     A) WSL (推荐):  在 Windows 上装 WSL,进入 WSL 后跑 build_apk.sh
REM     B) Docker:     使用本目录下 build_apk_docker.bat
REM     C) 云端 Linux: 把整个项目上传到 Linux 服务器跑 build_apk.sh
REM ============================================================

setlocal

echo ===============================================
echo  CET 智胜 - 安卓 APK 打包引导
echo ===============================================

if not exist "buildozer.spec" (
    echo [ERROR] 未找到 buildozer.spec
    pause
    exit /b 1
)

echo.
echo 当前项目结构:
dir /b *.py core database 2^>nul | findstr /v "^$"
echo.

echo ===============================================
echo  请选择打包方式:
echo ===============================================
echo  [1] 自动启动 WSL 并调用 build_apk.sh  (推荐)
echo  [2] 仅打印准备步骤 (手工执行)
echo  [3] 检查本机环境
echo  [Q] 退出
echo.

set /p CHOICE=请输入选项 (1/2/3/Q):

if "%CHOICE%"=="1" goto WSL_RUN
if "%CHOICE%"=="2" goto PRINT_STEPS
if "%CHOICE%"=="3" goto CHECK_ENV
if /i "%CHOICE%"=="Q" exit /b 0

:WSL_RUN
echo.
echo [INFO] 启动 WSL ...
wsl --status >nul 2>&1
if errorlevel 1 (
    echo [ERROR] 未检测到 WSL,请先安装 WSL: wsl --install
    pause
    exit /b 1
)
wsl -- bash -ic "cd $(wslpath '%~dp0' | sed 's:\\\\:/:g') && ./build_apk.sh debug"
goto END

:PRINT_STEPS
echo.
echo [手工执行步骤]
echo   1) 启动 WSL:                 wsl
echo   2) 切到项目盘:              cd /mnt/d/CET-Prep-System
echo   3) 第一次打包前装系统依赖:  sudo apt update ^&^& sudo apt install -y python3-pip build-essential git ffmpeg libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev libportmidi-dev libswscale-dev libavformat-dev libavcodec-dev zlib1g-dev
echo   4) 安装 buildozer:           pip install --upgrade buildozer cython
echo   5) 给脚本加可执行权限:       chmod +x build_apk.sh
echo   6) 开始打包:                 ./build_apk.sh debug
echo   7) 等待 5-15 分钟,APK 输出在 bin/ 目录
goto END

:CHECK_ENV
echo.
echo [环境检查]
echo   Python:   %PYTHON_VERSION%  (Windows 本机 Python)
where python 2>nul
where wsl 2>nul && echo   WSL:    OK || echo   WSL:    NOT FOUND
where docker 2>nul && echo   Docker: OK || echo   Docker: NOT FOUND
where adb 2>nul && echo   adb:    OK || echo   adb:    NOT FOUND (无需,装到手机后用文件管理器打开)

:END
echo.
pause
endlocal
