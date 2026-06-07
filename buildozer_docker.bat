@echo off
REM Build APK via Docker, with the buildozer root-prompt patched.
REM This wraps the docker run so the inner buildozer never asks y/n.

set "SRC=%~dp0"

docker run --rm -i -v "%SRC%:/src" -w /src ^
  --entrypoint bash ^
  kivy/buildozer ^
  -c "python -c \"\nimport buildozer, os, re\np = buildozer.__file__\ns = open(p).read()\n# 1) Skip the buildozer-is-root y/n prompt\ns = s.replace('self.check_root()', 'pass  # patched: no y/n prompt')\n# 2) Pre-accept Android SDK licenses by stubbing the sdkmanager\n#    'cat .../licenses/*' and 'yes | sdkmanager --licenses' paths.\n#    The simplest universal patch: in target func that does\n#    'sdkmanager --licenses', force stdin='y\\n'.\n#    Buildozer runs sdkmanager via subprocess; we pre-accept by writing\n#    accepted license hashes into the licenses dir, which is what\n#    'yes | sdkmanager --licenses' ultimately does.\nlicdir = os.path.expanduser('~/.buildozer/android/platform/android-sdk/licenses')\nos.makedirs(licdir, exist_ok=True)\n# These are the well-known license hashes for SDK platform-tools +\n# build-tools + platform; copying from a real install lets sdkmanager\n# skip the y/n prompt entirely.\nfor h in [\n    'android-sdk-license', 'android-sdk-preview-license',\n    'intel-android-extra-license', 'android-googletv-license',\n    'mips-android-sysimage-license', 'android-sdk-arm-dbt-license',\n]:\n    open(os.path.join(licdir, h), 'w').write('\\n8933bad161af4178b1185d1a37fbf41ea5269c55\\n')\nopen(p, 'w').write(s)\nprint('patched:', p)\nprint('licenses pre-accepted in:', licdir)\n\" && buildozer android debug"
