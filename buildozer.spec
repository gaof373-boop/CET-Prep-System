# buildozer.spec — CET 智胜 · 手机 App V2.1 安卓打包工程
# ==========================================================
# Generated for:  mobile_main.py
# Target OS    :  Android (API 21+, arm64-v8a / armeabi-v7a / x86_64)
# Python        :  3.11.x (Kivy default for buildozer)
#
# 如何使用:
#   1. pip install buildozer
#   2. (Linux / WSL / 容器内) buildozer android debug
#   3. 在 bin/ 目录里找到 cet_zhisheng-0.1-armeabi-v7a.apk
# ==========================================================

[app]

# (str) Title of your application
title = CET Zhisheng

# (str) Package name
package.name = cet_zhisheng

# (str) Package domain (needed for android/ios packaging)
package.domain = org.zhisheng

# (str) Source code where the main.py live
source.dir = .

# (list) Source files to include (let empty to include all the files)
source.filename = mobile_main.py

# (list) Source files or python dirs to include (let empty to include all files)
#    ★ 关键: 把 mobile_main.py 入口 + core/ 包 + database/ 主库与音频 全打包进 APK
source.include_patterns = mobile_main.py,
    core/*.py,
    core/**/*.py,
    database/*.db,
    database/audio/*.mp3

# (list) Extensions to include when打包ing (let empty to include all)
#    ★ 极其关键: 必须包含 db (主库) + mp3 (听力音频) 否则手机上读不到
source.include_exts = py,png,jpg,kv,db,mp3

# (str) Application versioning (method 1)
version = 2.1.0

# (str) Application versioning (method 2)
# version.regex =
# version.filename =

# (list) Application requirements
#    显式声明所有运行时需要的 Python 模块
#    kivy     — UI 框架
#    mutagen  — 我们的 edge-tts 音频元数据读取
#    requests — AI / 在线翻译 API 调用
#    NOTE: pygame 已移除 — pygame 2.1.0 与 Python 3.14 不兼容
#          (PyErr API 已废弃),且我们的 mobile_main.py 实际未使用 pygame
requirements = python3,kivy,requests,mutagen

# (str) Presplash background color (hex)
#    启动屏背景 — 用主品牌色 #3B82F6 (蓝)
presplash.backgroundcolor = #3B82F6

# (str) Icon for the application (绝对路径或相对 source.dir)
#    若项目下没放 icon.png,可注释掉,buildozer 会用默认占位
# icon.filename = icon.png

# (list) Supported orientations
#    ★ 锁死 portrait — 手机垂直屏幕,防止横屏导致 StatCard 排版崩掉
orientation = portrait

# (bool) Indicate if the application should be fullscreen or not
fullscreen = 0

# (string) Presplash image used on Android (relative to source.dir)
# presplash.filename = presplash.png

# (str) Supported language (e.g. fr-FR, fr-CA). Use 2-letter ISO 639-1 code.
# android.presplash_languages = en

# (list) List of service to declare
#services = NAME:ENTRYPOINT_TO_PY,NAME2:ENTRYPOINT2_TO_PY

# OSX Specific
#
# (str) Application category
# (list) Application info
# LSApplicationCategoryType = public.app-category.education
# LSEnvironment =

# Android specific
# (bool) Indicate whether the screen should be rotated on small devices
#    True = 允许小尺寸设备旋转(我们已锁 portrait,这里保持默认)
# android.allow_backup = True

# (list) Permissions — 申请运行时权限
#    1. INTERNET             — AI API / 在线翻译
#    2. ACCESS_NETWORK_STATE — 网络状态检测
#    3. READ/WRITE_EXTERNAL_STORAGE — 部分设备需要
android.permissions = INTERNET, ACCESS_NETWORK_STATE, READ_EXTERNAL_STORAGE, WRITE_EXTERNAL_STORAGE

# (int) Target Android API (latest = 33 / 34)
android.api = 33

# (int) Minimum Android API supported (Android 5.0 Lollipop = 21)
android.minapi = 21

# (int) Android SDK version to use
android.sdk = 33

# (int) Android NDK version to use
#   Use 28c (the p4a 2026.05.09 recommended version). NDK 25b
#   fails to compile Kivy's _sdl2 module with Python 3.14 because
#   ``longintrepr.h`` was removed in newer CPython.
android.ndk = 28c

# (int) Android NDK API to use
android.ndk_api = 21

# (str) Android NDK directory (if empty, install automatically)
# android.ndk_path =

# (str) Android SDK directory (if empty, install automatically)
# android.sdk_path =

# (str) ANT directory (if empty, install automatically)
# android.ant_path =

# (str) java directory (if empty, install automatically)
# android.java_path =

# (str) Minimum Android API required to run the app (if android.minapi is not set, this is used)
# android.min_target_api = 21

# (str) Android additional command line arguments
# android.add_aars =
# android.add_activities =
# android.add_gradle_repositories =
# android.add_gradle_dependencies =
# android.add_java_args =
# android.add_jars =
# android.add_packages =
# android.add_src_dirs =
# android.add_res_dirs =
# android.aapt_options =
# android.assets =
# android.bonus_pattern =
# android.branch =
# android.debug = False
# android.exclude_assets =
# android.extra_activities =
# android.extra_jars =
# android.extra_keystore =
# android.extra_keystore_path =
# android.extra_plugins =
# android.extra_providers =
# android.gradle_dependencies =
# android.gradle_repositories =
# android.icons =
# android.intent_filters =
# android.library_repositories =
# android.logcat_filters = *:S python:D
# android.manifest_intent_filters =
# android.manifest_placeholders =
# android.merge_manifests =
# android.min_python_version = 3.7
# android.ndk_path =
# android.presplash_languages = en
# android.pydrive =
# android.reads_assets =
# android.release_artifact = apk
# android.skip_update = False
# android.splash_image = data/splash.png
# android.splash_screen =
# android.start_args =
# android.target_python_version = 3.11
# android.wakelock = False
# android.xpm =

# iOS specific
# (str) iOS title
# ios.kv_application_class =
# ios.kv_container_class =

# (str) iOS bundle name (used in the App Store)
# ios.cocoapods_path = ../ios/Pods

# (str) Bundle ID
# ios.bundle_identifier =

# (str) Apple developer team identifier
# ios.development_team =

# (str) App Store Connect team identifier
# ios.development_team_id =

# (str) Bundle version (used in App Store Connect)
# ios.app_store_icon =

# (str) Apple developer portal team identifier
# ios.codesign_identity =

# (str) Provisioning profile name
# ios.provisioning_profile =

# (str) Provisioning profile file path
# ios.provisioning_profile_filename =

# (str) Provisioning profile suffix
# ios.provisioning_profile_suffix =

# (bool) Enable iOS persistent storage
# ios.enable_reloader =

# (bool) Run `python setup.py sdist` and create a source distribution tarball
# package.create_sdist = False

# (str) Path to an optional .cfg file to fine-tune buildozer's behavior
# buildozer_config = /path/to/buildozer.cfg

# (str) Custom entry point (default: main)
# (str) Entrypoint file to use (default: main.py)
# (str) Entrypoint file to use (default: main.py)
# main_entry_point = mobile_main.py

# (str) List of Python version to use (default: 3.11)
# python_version = 3.11

# (str) List of supported architecture (one or more)
#    单架构方案 C:只打 arm64-v8a(64 位 ARM,覆盖 95% 现代安卓)
#    APK 体积减半(~20-25 MB),编译时间减半
#    后续若需兼容老设备可改回: arm64-v8a, armeabi-v7a
android.archs = arm64-v8a

# (str) python-for-android recipe directory, if empty, we will use the default
# p4a_recipes_dir =

# (str) Use a local p4a install instead of git-cloning kivy/python-for-android.
#   This skips the slow git clone of p4a from GitHub.
#   On GitHub Actions runner, let buildozer do its own clone (just remove
#   the override and let it use its default path inside /home/runner/.buildozer).
# p4a.source_dir =  # commented out to let buildozer auto-clone

# (str) python-for-android recipe to use for the project
# p4a =

# (str) Toolchain.py arguments
# toolchain_py_args =

# (str) Toolchain.py verbosity level
# toolchain_py_verbosity =

# (bool) Display error log in red
# toolchain_py_log =

# (bool) Display info log in green
# toolchain_py_info =

# (bool) Display warning log in yellow
# toolchain_py_warning =

# (bool) Display all log in their default color
# toolchain_py_color =

# (bool) Disable colored toolchain output
# toolchain_py_nocolor =

# (bool) Use colors for toolchain output
# toolchain_py_verbose =

# (bool) Skip toolchain validation
# toolchain_py_skip_check =

# (bool) Print toolchain progress messages
# toolchain_py_print =

# (bool) Use host built-in SDK tools
# toolchain_py_use_host =

# (bool) Set "ANDROID_PYTHONPATH" for your application
# toolchain_py_use_android_pythonpath =

# (str) Blacklist Android archs
# android.blacklist_archs = x86, x86_64

# (str) Blacklist java source files
# android.blacklist_src =

# (str) Blacklist java source files that match a pattern
# android.blacklist_pattern =

# (bool) Whether to copy the android service into the APK
# android.copy_services = True

# (list) Recreate the source code archive
# android.distribution = False

# (bool) Whether to enable SDL2 (disable if you don't use SDL2)
# android.enable_sdl2 = True

# (bool) Whether to enable AAC audio (disable if you don't use SDL2_mixer)
# android.enable_audiomp3 = True

# (list) Put custom files in p4a's dist directory
# android.extra_p4a_args =

# (bool) Use a custom SDL2 image framework
# android.use_custom_sdl2_image = False

# (bool) Use SDL2 in pyjnius
# android.use_pyjnius = True

# (bool) Set "ANDROID_STDERR" to be a file
# android.use_stderr_log =

# (str) Path of the log file for stderr
# android.stderr_log_path =

# (str) Set the log level for stderr
# android.stderr_log_level = ERROR

# (bool) Set "ANDROID_STDOUT" to be a file
# android.use_stdout_log =

# (str) Path of the log file for stdout
# android.stdout_log_path =

# (str) Set the log level for stdout
# android.stdout_log_level = ERROR

# (list) Android logcat filters to use
# android.logcat_filters = *:S python:D

# (bool) Log Android logcat messages
# android.logcat_enable = True

# (str) Logcat log file path
# android.logcat_log_path =

# (str) Use a custom logcat filter prefix
# android.logcat_filter =

# (bool) Use SDL2's haptic feedback API
# android.use_sdl2_haptic = False

# (bool) Use SDL2's game controller API
# android.use_sdl2_controller = False

# (bool) Use SDL2's touch API
# android.use_sdl2_touch = False

# (bool) Use SDL2's power API
# android.use_sdl2_power = False

# (bool) Add an SDL2 hint to enable or disable the touch API
# android.use_sdl2_gl = True

# (bool) Enable the use of SDL2's GL ES 1.x bindings
# android.use_sdl2_es1 = False

# (bool) Enable the use of SDL2's GL ES 2.x bindings
# android.use_sdl2_es2 = False

# (bool) Use SDL2's haptic feedback API
# android.use_sdl2_haptic = False

# (bool) Use SDL2's game controller API
# android.use_sdl2_controller = False

# (bool) Use SDL2's touch API
# android.use_sdl2_touch = False

# (bool) Use SDL2's power API
# android.use_sdl2_power = False

# (bool) Add an SDL2 hint to enable or disable the touch API
# android.use_sdl2_gl = True

# (str) Path to a SDL2 config file
# android.sdl2_config_path =

# (str) Path to a custom p4a directory
# p4a_local_dir =

# (str) Name of the main p4a app
# p4a_app_name =

# (str) Version of the main p4a app
# p4a_app_version =

# (list) Permissions to declare in the AndroidManifest.xml
# android.permissions =

# (bool) Disable automatic patching
# p4a.bootstrap = service

# (bool) Use host pip3 binary
# p4a.use_host_pip3 = False

# (list) Extra files to copy in the dist directory
# p4a.local_recipes =

# (list) Extra args to pass to p4a
# p4a.extra_args =

# (str) The directory to put built apks
# buildozer.bin_dir = bin

[buildozer]
# (int) Log level (0 = error only, 1 = info, 2 = debug (with command output))
log_level = 1

# (int) Display warning if the available used space is lower than specified
warn_on_tools = 0

# (str) Path to a custom spec file (overrides the default)
# spec_path =
