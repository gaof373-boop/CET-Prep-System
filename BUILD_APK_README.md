# CET 智胜 · 手机 App V2.1 安卓打包操作手册

> 适用版本:V2.1 / buildozer.spec 已经按官方规范生成

## 0. 一次性准备

| 平台 | 一次性操作 |
|---|---|
| **云端 Linux (Ubuntu 22.04+ 推荐)** | `sudo apt update && sudo apt install -y python3-pip build-essential git ffmpeg libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev libportmidi-dev libswscale-dev libavformat-dev libavcodec-dev zlib1g-dev openjdk-17-jdk` |
| **本机 WSL** | `wsl --install -d Ubuntu`,然后同上行 |
| **本机 Docker** | 拉 `kivy/buildozer` 镜像即可 |

把项目压缩成 `CET-Prep-System.zip` 整体发到 Linux 主机,或者在 WSL 里 `cp -r /mnt/d/CET-Prep-System ~/`。

## 1. 一键打包(推荐)

```bash
cd ~/CET-Prep-System
chmod +x build_apk.sh
./build_apk.sh debug      # → bin/cet_zhisheng-2.1.0-armeabi-v7a.apk
```

第一次会**下载约 2-3 GB 的 SDK / NDK / Python-for-Android 工具链**,大约 **5-15 分钟** 出 APK。
**第二次以后** 因为有缓存,只需要 **1-3 分钟** 增量重打包。

## 2. 输出位置

```
CET-Prep-System/
└── bin/
    ├── cet_zhisheng-2.1.0-armeabi-v7a.apk      ← 32 位安卓(老手机)
    ├── cet_zhisheng-2.1.0-arm64-v8a.apk        ← 64 位安卓(主流)
    └── cet_zhisheng-2.1.0-x86_64.apk           ← 模拟器
```

体积参考:
- **arm64 单架构 APK** ≈ 30-40 MB (Kivy + pygame + 我们的 db 16MB + 51 个 mp3)
- 如果觉得太大:在 `buildozer.spec` 里把 `android.archs = arm64-v8a` 改成单架构

## 3. 安装到手机

```bash
# USB 调试模式
adb install -r bin/cet_zhisheng-2.1.0-arm64-v8a.apk
```

或者直接把这个 `.apk` 文件 **发到手机用文件管理器点击安装**(记得开启"未知来源"权限)。

## 4. Windows 本地用户的三条路

| 难度 | 方案 | 命令 |
|---|---|---|
| ⭐ 最快 | **WSL** | `wsl --install` → 重启 → 进入 Ubuntu → 按 §1 走 |
| ⭐⭐ 推荐 | **云端 Linux** | 把 `CET-Prep-System.zip` 上传到阿里云/腾讯云学生机,按 §1 走 |
| ⭐⭐⭐ 退路 | **GitHub Actions** | 见下面 §5 |

## 5. GitHub Actions 自动化(零本地配置)

项目里已有 `buildozer.spec`,在 GitHub 仓库 `.github/workflows/buildozer.yml` 加:

```yaml
name: Build APK
on: [push]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - name: Install system deps
        run: |
          sudo apt update
          sudo apt install -y build-essential git ffmpeg \
            libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev \
            libsdl2-ttf-dev libportmidi-dev libswscale-dev \
            libavformat-dev libavcodec-dev zlib1g-dev openjdk-17-jdk
      - name: Install buildozer
        run: pip install --upgrade buildozer cython
      - name: Build APK
        run: chmod +x build_apk.sh && ./build_apk.sh debug
      - uses: actions/upload-artifact@v4
        with:
          name: cet-zhisheng-apk
          path: bin/*.apk
```

跑完直接去 `Actions → Artifacts` 下载 `cet-zhisheng-apk` 即可。

## 6. 常见问题速查

| 现象 | 修复 |
|---|---|
| `ImportError: No module named kivy` | `pip install --upgrade buildozer cython` |
| `SDL2 compilation error` | `sudo apt install libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev` |
| 第一次很慢 | 正常,会下载 ~2.5GB 工具链,**不要 Ctrl-C** |
| 打包完打开闪退 | 检查手机 logcat:`adb logcat \| grep python`;常见是 `database/cet_exam.db` 路径在 APK 内被解压到 `/data/data/org.zhisheng.cet_zhisheng/files/...`,需要修改 `mobile_main.py` 用 `App.user_data_dir` 路径(下一版) |
| `ANDROID_NDK not found` | 保持默认让 buildozer 自行下载(`android.ndk = 25b`) |
| 提示 `No such file: icon.png` | 注释掉 `buildozer.spec` 里的 `icon.filename` |

## 7. 调试运行(不打包,只跑 Python 检查)

```bash
cd ~/CET-Prep-System
python mobile_main.py     # 弹 390x780 模拟手机窗口
```

## 8. 重新生成 release 签名版(给应用商店)

1. 生成 keystore:
   ```bash
   keytool -genkey -v -keystore cet_zhisheng.keystore -alias cet -keyalg RSA -keysize 2048 -validity 10000
   ```
2. 在 `buildozer.spec` 添加:
   ```ini
   android.keystore = cet_zhisheng.keystore
   android.keyalias = cet
   android.keystore_password = 你的密码
   android.keyalias_password = 你的密码
   ```
3. `./build_apk.sh release`
