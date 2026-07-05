# -*- coding: utf-8 -*-
"""
KeyboardWizard · 按键精灵 入口
运行： python main.py
依赖： pip install -r requirements.txt
跨平台支持：Windows / macOS / Linux
"""
from __future__ import annotations

import os
import sys

# macOS 下抑制系统 Tk 弃用警告
if sys.platform == "darwin":
    os.environ.setdefault("TK_SILENCE_DEPRECATION", "1")


def _check_deps():
    """启动前做一次依赖检查，给出友好提示。"""
    missing = []
    for mod in ("customtkinter", "pyautogui", "PIL", "pyperclip"):
        try:
            __import__(mod)
        except Exception:
            missing.append(mod)
    has_hotkey = False
    try:
        __import__("pynput")
        has_hotkey = True
    except Exception:
        try:
            __import__("keyboard")
            has_hotkey = True
        except Exception:
            pass
    if not has_hotkey:
        missing.append("pynput (或 keyboard)")
    has_window = False
    try:
        __import__("pygetwindow")
        has_window = True
    except Exception:
        try:
            __import__("pywinctl")
            has_window = True
        except Exception:
            pass
    if not has_window:
        missing.append("pygetwindow (或 pywinctl)")
    if missing:
        print("=" * 60)
        print("缺少依赖：" + ", ".join(missing))
        print("请先执行： pip install -r requirements.txt")
        print()
        print("如果已执行仍报此错，说明 pip 与运行时用的 Python 不一致。")
        print("请确认 VSCode 右下角选择的解释器与下面一致后，重新安装：")
        print()
        print("  当前 Python 解释器：")
        print("  " + sys.executable)
        print()
        print("  请用此解释器安装依赖（复制下面命令执行）：")
        print()
        print(f'  "{sys.executable}" -m pip install -r requirements.txt')
        print("=" * 60)
        try:
            from tkinter import messagebox, Tk
            root = Tk()
            root.withdraw()
            messagebox.showerror(
                "缺少依赖",
                "缺少：" + ", ".join(missing) +
                "\n\n当前 Python 解释器：\n" + sys.executable +
                "\n\n如已执行 pip install 仍报错，说明解释器不一致。\n"
                "请在终端执行：\n"
                f'"{sys.executable}" -m pip install -r requirements.txt',
            )
        except Exception:
            pass
        sys.exit(1)


def main():
    _check_deps()
    # 捕获所有异常写入日志文件，方便排查打包后的崩溃
    import traceback
    try:
        from app import App
        app = App()
        app.mainloop()
    except Exception:
        log_path = _write_crash_log(traceback.format_exc())
        try:
            from tkinter import messagebox, Tk
            root = Tk()
            root.withdraw()
            messagebox.showerror(
                "启动失败",
                f"程序启动时发生错误：\n\n{traceback.format_exc()[:500]}\n\n"
                f"完整日志已保存到：\n{log_path}",
            )
        except Exception:
            pass
        raise


def _write_crash_log(content: str) -> str:
    """将崩溃日志写入应用数据目录，返回日志文件路径。"""
    import time
    try:
        from platform_utils import get_app_dir
        log_dir = get_app_dir()
    except Exception:
        log_dir = os.path.expanduser("~")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "crash.log")
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(f"时间：{time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Python：{sys.version}\n")
        f.write(f"平台：{sys.platform}\n")
        f.write(f"可执行文件：{sys.executable}\n")
        f.write("-" * 60 + "\n")
        f.write(content)
    return log_path


if __name__ == "__main__":
    main()
