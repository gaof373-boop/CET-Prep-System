#!/usr/bin/env bash
# ============================================================
#  CET 智胜 · 安卓 .apk 一键打包脚本 (Linux / WSL / macOS)
# ============================================================
#  Usage:
#     1) 把这个 build_apk.sh 上传到 Linux 服务器 / 启动 WSL
#     2) chmod +x build_apk.sh
#     3) ./build_apk.sh debug      # 生成可安装的 debug 版
#        ./build_apk.sh release    # 生成签名好的 release 版
# ============================================================
set -e

echo "============================================="
echo " CET 智胜 · Kivy Android 打包"
echo "============================================="

# 0. 准备 buildozer
if ! command -v buildozer &> /dev/null; then
    echo "[1/5] 安装 buildozer ..."
    pip install --upgrade buildozer cython
else
    echo "[1/5] buildozer 已安装: $(buildozer --version 2>&1 | head -1)"
fi

# 1. 检查 buildozer.spec
if [ ! -f "buildozer.spec" ]; then
    echo "❌ 未找到 buildozer.spec,请先把它放到当前目录!"
    exit 1
fi
echo "[2/5] buildozer.spec 已就位"

# 2. 安装缺失的 Linux 系统依赖(仅 Debian/Ubuntu 提示)
if command -v apt-get &> /dev/null; then
    echo "[3/5] 提示: 首次运行前请确保已安装系统依赖"
    echo "       sudo apt install -y python3-pip build-essential git \\"
    echo "            python3-dev ffmpeg libsdl2-dev libsdl2-image-dev \\"
    echo "            libsdl2-mixer-dev libsdl2-ttf-dev libportmidi-dev \\"
    echo "            libswscale-dev libavformat-dev libavcodec-dev zlib1g-dev"
fi

# 3. 模式选择
MODE="${1:-debug}"
if [ "$MODE" != "debug" ] && [ "$MODE" != "release" ]; then
    echo "❌ 未知模式 '$MODE',请用 debug 或 release"
    exit 1
fi
echo "[4/5] 模式: $MODE"

# 4. 真正开始打包
echo "[5/5] 启动 buildozer android $MODE"
buildozer android $MODE

# 5. 提示输出位置
echo
echo "============================================="
echo " ✅ 打包完成!"
echo " 📦 APK 输出:  bin/cet_zhisheng-2.1.0-*.apk"
echo "============================================="
ls -lh bin/*.apk 2>/dev/null || true
