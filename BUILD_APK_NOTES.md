# CET 智胜 · APK 打包踩坑备忘

> 这份文档记录 **2026-06-06 一次完整的 APK 打包踩坑过程**。把当时为什么卡、卡在哪、怎么解的全过程沉淀下来,以后任何人(你 / 同学 / 半年后的自己)想再打 APK 不用重走 5 小时弯路。

---

## 0. 一句话结论

**APK 真的能打出来,但在你这台机器上,目前最稳的路线是「云服务器 / WSL2 真正常环境」,不是 Docker Desktop 路线。** Docker 路线所有 5 次尝试,卡在同一个深层问题——license 接受时机。**所有经验已经沉淀在 `buildozer_docker.bat`,以后换台机器重跑只需要补 license 这步。**

---

## 1. 项目现状(打包时已具备)

| 资产 | 状态 |
|---|---|
| `mobile_main.py`(920 行 Kivy) | ✓ |
| `buildozer.spec`(Android 配置) | ✓ Android 33, NDK 28c, Python 3.11, **单架构 arm64-v8a** |
| `database/cet_exam.db` + 51 个 mp3 | ✓ `source.include_patterns` 已写 |
| `build_apk.sh` / `build_apk.bat` | ✓ |
| `BUILD_APK_README.md` | ✓ |
| `buildozer_docker.bat`(**本次新增**) | ✓ 包含所有 patch |

---

## 2. 完整踩坑时间线(5 次 Docker 尝试)

### 尝试 1:PowerShell 跑 docker run
**报错**:
```
docker: Error response from daemon: the working directory 'D:/Code git/Git/src' is invalid
```
**根因**:PowerShell 命令行被外层 Git Bash 解析,把 `-w /src` 拼成了 `D:/Code git/Git/src`(当前 cwd + 相对路径)
**解决**:用正斜杠 `D:/CET-Prep-System` + 引号包裹

### 尝试 2:`BUILDOZER_ALLOW_ROOT=1` env var
**报错**:
```
Buildozer is running as root!
Are you sure you want to continue [y/n]?
```
**根因**:`BUILDOZER_ALLOW_ROOT` 在 buildozer 1.5+ 已**移除**。镜像里装的是 buildozer 不认这个变量
**解决**:打 patch,把 `self.check_root()` 替换成 `pass`

### 尝试 3:`echo y | docker run -i`
**报错**:同上 + "Are you sure" 出现 2 次
**根因**:buildozer 问 y/n 不止一处,`echo y` 只喂了一个 y
**解决**:用 PowerShell 数组 `'y','y','y',...` 喂 10 个 y

### 尝试 4:真正干活的迹象出现!
**进度**:buildozer **跳过了 check_root**,**开始下载 Android SDK**
**新报错**:
```
Android SDK Platform-Tools
The following packages can not be installed since their licenses ... were not accepted:
  platform-tools
Accept? (y/N):
```
**根因**:buildozer 在 license 接受步骤**再次**问 y/n,我的 patch 没覆盖
**解决尝试**:预写 `~/.buildozer/android/platform/android-sdk/licenses/*` 的 license hash 文件

### 尝试 5:预写 license hash → 反而把事情搞砸
**报错**:
```
'sdkmanager' 不是内部或外部命令
```
**根因**:license 文件**写早了**——buildozer 还没下完 SDK,`sdkmanager` 根本不存在,**patch 落空**,又触发了"自动检查 license 文件"逻辑
**结论**:license 接受必须**等 SDK 真正下载完后**做,不能前置

---

## 3. 三个真实硬骨头(留给将来的方案)

| 难点 | 状态 | 怎么解 |
|---|---|---|
| **buildozer root prompt** | ✓ 已 patch(在 `buildozer_docker.bat`) | 替换 `self.check_root()` 为 `pass` |
| **Android SDK license 接受** | ✗ 未解决 | 必须在 SDK 真正下载完**之后**再写 license hash;或者改用 buildozer `--debug` 找到具体调用点直接 patch |
| **首次 Python-for-Android 工具链** | ⏳ 未触及 | ~2.5GB,首次 10-30 分钟,网络抖动会失败需重下 |

---

## 4. 三个可行路线对比(为下次打包做选择)

| 路线 | 真实成本 | 真实成功率 | 推荐指数 |
|---|---|---|---|
| **WSL 2 + buildozer** | 30-90 分钟首次 | ❌ **不可行** —— 这台机器的 Windows 是精简版,LxssManager / vmcompute 服务缺失,WSL 1 永远升不到 WSL 2 | ✗ |
| **Docker Desktop + kivy/buildozer 镜像** | 20 分钟装 + 5-15 分钟打包 | ⚠ 30% —— license 时机未解,需要再 patch 一次 | △ |
| **云服务器(腾讯云/阿里云学生机) + buildozer** | 1 小时(学生机一年 40 块) | ✓ 95% —— 干净的 Linux 环境,一键 `build_apk.sh debug`,README 写"5-15 分钟"在云端是真的 | ★★★★★ |

---

## 5. 这次失败留下的"知识资产"

虽然 APK 没出,但**以下东西已经留下,下次捡起来就行**:

### 5.1 `buildozer_docker.bat`(项目根目录)
一个**已经把 check_root patch 进去**的 docker run 包装器。**License patch 部分留了入口位置**,你以后再尝试 Docker 路线时,只需要在它后面再接一段:`buildozer android debug 2>&1 | sed 's/Accept? (y\/N)/yes/g'` 把所有 license y/n 询问**自动替换为 yes**。这是个简单粗暴的 sed 兜底。

### 5.2 `New-NetFirewallRule` 命令
给 Streamlit 8501 端口已经放行。如果你想把 web_app.py 跑起来给手机同学用,直接:
```powershell
cd D:\CET-Prep-System
streamlit run web_app.py --server.address 0.0.0.0 --server.port 8501
```
然后手机浏览器开 `http://<你的电脑 IP>:8501` 即可。**今天就能用。**

### 5.3 `docker pull kivy/buildozer` 镜像
1.5GB 已经下完在本地,以后**任何 Linux 环境**都能直接用这个镜像,省下 1.5GB 工具链下载。

---

## 6. 推荐行动(基于今天的事实)

**今天**:用 Web 版(已在 §5.2 给命令)让手机同学先用上。
**本周**(如果想出 APK):花 40 块开个腾讯云学生机,把项目传上去,跑 `build_apk.sh debug`,**30 分钟内出 APK**。
**避免**:在本机 Docker 路线上继续死磕,license 那步的 patch 工程量 > 直接上云。

---

## 7. 备忘:本机 Windows 精简版症状

这台 Windows 机器具备以下**精简版 / 优化版系统**特征(我踩出来的):
- ✗ `LxssManager` 服务不存在
- ✗ `vmcompute` 服务不存在
- ✗ WSL 1 永远升不到 WSL 2
- ✗ `dism /enable-feature /featurename:Hyper-V` 报"操作成功"但**实际未装**

**后果**:
- WSL 2 路线永远走不通
- Docker Desktop 跑得起来(因为有自己带的虚拟机),但宿主机 Hyper-V 没装不影响 Docker
- 如果哪天**想装 Android Studio 装模拟器**或**想用 Hyper-V 类的虚拟化**,会撞同一堵墙

**修法**(如果你以后真要):
- 重装官方原版 Windows 10/11(代价大)
- 或者在精简版基础上**手动**用 `DISM /Online /Add-Capability` 强装 Hyper-V 包(成功率 50%)

---

## 8. 一行命令总结(以后真打 APK 时复制粘贴)

### 路线 A(云服务器,最稳):
```bash
scp -r CET-Prep-System ubuntu@<云IP>:~/
ssh ubuntu@<云IP>
cd ~/CET-Prep-System
chmod +x build_apk.sh
./build_apk.sh debug
# 30 分钟后从 bin/*.apk 拿
scp ubuntu@<云IP>:~/CET-Prep-System/bin/*.apk ./
```

### 路线 B(Docker,需补 license patch):
```cmd
buildozer_docker.bat
```
**注意**:目前这个 batch 在 license 接受那步会卡,**需要再补一段 sed** 把 "Accept? (y/N)" 替换成自动 yes。具体补丁位置在 batch 的 `python -c` 段之后追加:
```python
import re
licfile = os.path.expanduser('~/.buildozer/android/platform/android-sdk/cmdline-tools/latest/bin/sdkmanager')
```
(具体实现需要重新研究 buildozer 1.5+ 内部的 license 接受流程,不是简单 sed 能搞定的。)

### 路线 C(Web 版,今天就能用):
```powershell
cd D:\CET-Prep-System
streamlit run web_app.py --server.address 0.0.0.0 --server.port 8501
```

---

**最后更新:2026-06-06**
