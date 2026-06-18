# -*- coding: utf-8 -*-
"""一键打包「定制头像」临时版（不改正式图标、源码零留痕）。

用法:
    py -3 scripts/build_custom.py <图片路径> [名字后缀(默认 custom)]
例:
    py -3 scripts/build_custom.py D:\\Pictures\\avatar.jpg
    py -3 scripts/build_custom.py avatar.png laoba

流程:
    1. 图片 -> 居中裁方形 -> 128x128 运行时图标(临时写 src/icon_data.py，先备份 .bak)
       + 多尺寸 _custom_icon.ico(exe 文件图标)
    2. PyInstaller 打包单文件版 -> dist_onefile/CommTool_onefile_v<版本>_<后缀>.exe
    3. 无论成败都还原 src/icon_data.py、删临时 .ico —— 正式图标和源码一点不动
"""
import sys, os, base64, textwrap, subprocess, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "src")

# 与 build_onefile.bat 一致的 Qt 模块裁剪
EXCLUDES = [
    "PyQt5.QtBluetooth", "PyQt5.QtDBus", "PyQt5.QtDesigner", "PyQt5.QtHelp",
    "PyQt5.QtLocation", "PyQt5.QtMultimedia", "PyQt5.QtMultimediaWidgets",
    "PyQt5.QtNfc", "PyQt5.QtOpenGL", "PyQt5.QtPositioning", "PyQt5.QtQml",
    "PyQt5.QtQuick", "PyQt5.QtQuickWidgets", "PyQt5.QtRemoteObjects",
    "PyQt5.QtSensors", "PyQt5.QtSerialPort", "PyQt5.QtSql", "PyQt5.QtTest",
    "PyQt5.QtWebChannel", "PyQt5.QtWebEngine", "PyQt5.QtWebEngineCore",
    "PyQt5.QtWebEngineWidgets", "PyQt5.QtWebSockets", "PyQt5.QtXmlPatterns",
]


def read_version():
    g = {}
    with open(os.path.join(SRC, "version.py"), encoding="utf-8") as f:
        exec(f.read(), g)
    return g.get("__version__", "0.0.0")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    img_path = sys.argv[1]
    suffix = sys.argv[2] if len(sys.argv) > 2 else "custom"
    if not os.path.isfile(img_path):
        print("X 找不到图片:", img_path)
        sys.exit(1)

    from PIL import Image
    ver = read_version()
    name = "CommTool_onefile_v%s_%s" % (ver, suffix)
    icon_data = os.path.join(SRC, "icon_data.py")
    bak = icon_data + ".bak"
    ico = os.path.join(ROOT, "_custom_icon.ico")

    # 残留守卫：上次若被强制中断(finally 没跑)，会留下 bak(=当时的正式图标) +
    # icon_data(=定制版)。先用 bak 还原，避免本次把"定制版"当正式图标备份进去、
    # 导致 finally 还原时把正式图标永久写成定制版。
    if os.path.exists(bak):
        shutil.move(bak, icon_data)
        print("(检测到上次中断的残留，已先还原 src/icon_data.py)")
    shutil.copy(icon_data, bak)          # 备份正式图标
    try:
        img = Image.open(img_path).convert("RGBA")
        w, h = img.size
        s = min(w, h)
        sq = img.crop(((w - s) // 2, (h - s) // 2, (w - s) // 2 + s, (h - s) // 2 + s))

        # 运行时图标：128x128 PNG -> base64 -> icon_data.py
        tmp = os.path.join(ROOT, "_ci_tmp.png")
        sq.resize((128, 128), Image.LANCZOS).save(tmp, "PNG", optimize=True)
        b64 = "\n".join(textwrap.wrap(base64.b64encode(open(tmp, "rb").read()).decode(), 76))
        os.remove(tmp)
        with open(icon_data, "w", encoding="utf-8") as f:
            f.write('# -*- coding: utf-8 -*-\n# custom temp avatar icon\nICON_B64 = """\\\n' + b64 + '\n"""\n')

        # exe 文件图标：多尺寸 .ico
        sq.save(ico, "ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

        args = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                "--windowed", "--onefile", "--name", name, "--icon", ico,
                "--distpath", os.path.join(ROOT, "dist_onefile"),
                "--workpath", os.path.join(ROOT, "build_onefile")]
        for e in EXCLUDES:
            args += ["--exclude-module", e]
        args.append(os.path.join(SRC, "main.py"))

        print(">> 打包中: %s.exe ..." % name)
        subprocess.run(args, cwd=ROOT, check=True)
        print("\nOK 完成: dist_onefile\\%s.exe" % name)
    finally:
        shutil.move(bak, icon_data)       # 还原正式图标（即使打包失败也还原）
        if os.path.exists(ico):
            os.remove(ico)
        print(">> 已还原 src/icon_data.py、清理临时 .ico（源码零留痕）")


if __name__ == "__main__":
    main()
