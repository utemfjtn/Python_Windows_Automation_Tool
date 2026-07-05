# -*- coding: utf-8 -*-
"""
平台适配层
封装 Windows / macOS / Linux 之间的差异，上层模块只调用本模块的统一接口。
包括：全局快捷键、窗口操作、剪贴板粘贴、字体、图标、资源路径等。
"""
from __future__ import annotations

import os
import sys
import platform


# ---------------------------------------------------------------------------
# 平台检测
# ---------------------------------------------------------------------------
IS_WINDOWS = sys.platform.startswith("win")
IS_MACOS = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")


# ---------------------------------------------------------------------------
# 路径工具：兼容 PyInstaller 打包后的资源路径
# ---------------------------------------------------------------------------
def resource_path(relative_path: str) -> str:
    """获取资源文件的绝对路径，兼容 PyInstaller 打包后的环境。

    PyInstaller 打包后会将资源解压到临时目录 _MEIPASS，
    此时 __file__ 指向的路径不正确，需要用 sys._MEIPASS。
    """
    base_path = getattr(sys, "_MEIPASS",
                        os.path.dirname(os.path.abspath(sys.argv[0])))
    return os.path.join(base_path, relative_path)


def get_app_dir() -> str:
    """获取应用程序目录（用户数据存储位置）。

    - Windows: %APPDATA%/KeyboardWizard
    - macOS: ~/Library/Application Support/KeyboardWizard
    - Linux: ~/.local/share/KeyboardWizard

    目录不存在会自动创建。
    """
    app_name = "KeyboardWizard"
    if IS_WINDOWS:
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
        path = os.path.join(base, app_name)
    elif IS_MACOS:
        path = os.path.join(os.path.expanduser("~"), "Library",
                            "Application Support", app_name)
    else:
        base = os.environ.get("XDG_DATA_HOME",
                              os.path.join(os.path.expanduser("~"),
                                           ".local", "share"))
        path = os.path.join(base, app_name)
    os.makedirs(path, exist_ok=True)
    return path


def current_os() -> str:
    """返回平台名称：windows / macos / linux"""
    if IS_WINDOWS:
        return "windows"
    if IS_MACOS:
        return "macos"
    if IS_LINUX:
        return "linux"
    return sys.platform


# ---------------------------------------------------------------------------
# 字体：根据平台选择合适的中文字体
# ---------------------------------------------------------------------------
def get_ui_font(size: int = 11, bold: bool = False) -> tuple:
    """返回适合当前平台的 UI 字体配置。"""
    if IS_WINDOWS:
        name = "Microsoft YaHei"
    elif IS_MACOS:
        name = "PingFang SC"
    else:
        name = "Noto Sans CJK SC"
    weight = "bold" if bold else "normal"
    return (name, size, weight)


def get_mono_font(size: int = 11) -> tuple:
    """返回适合当前平台的等宽字体配置。"""
    if IS_WINDOWS:
        name = "Consolas"
    elif IS_MACOS:
        name = "Menlo"
    else:
        name = "Monospace"
    return (name, size)


# ---------------------------------------------------------------------------
# 图标：根据平台选择合适的图标格式
# ---------------------------------------------------------------------------
def get_app_icon(assets_dir: str) -> str | None:
    """返回适合当前平台的图标文件路径，不存在则返回 None。"""
    import os
    if IS_WINDOWS:
        p = os.path.join(assets_dir, "app.ico")
    elif IS_MACOS:
        p = os.path.join(assets_dir, "app.icns")
    else:
        p = os.path.join(assets_dir, "app.png")
    return p if os.path.exists(p) else None


def set_window_icon(tk_window, icon_path: str | None) -> bool:
    """为 tk 窗口设置图标，成功返回 True。"""
    if not icon_path:
        return False
    try:
        if IS_WINDOWS:
            tk_window.iconbitmap(icon_path)
        else:
            from PIL import Image, ImageTk
            img = Image.open(icon_path)
            photo = ImageTk.PhotoImage(img)
            tk_window.iconphoto(True, photo)
            tk_window._icon_photo_ref = photo
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# 全局快捷键
# 优先使用 pynput（跨平台），Windows 下回退到 keyboard 库
# ---------------------------------------------------------------------------
class HotkeyManager:
    """跨平台全局快捷键管理器。

    用法：
        mgr = HotkeyManager()
        mgr.add_hotkey("f6", callback)
        mgr.add_hotkey("ctrl+shift+s", callback)
        mgr.remove_all()
    """

    def __init__(self):
        self._hooks = []
        self._listener = None
        self._backend = None
        self._init_backend()

    def _init_backend(self):
        """尝试初始化后端，优先 pynput，失败则尝试 keyboard。"""
        try:
            from pynput import keyboard as pynput_kb
            self._backend = "pynput"
            self._pynput_kb = pynput_kb
            return
        except Exception:
            pass
        try:
            import keyboard as kb_lib
            self._backend = "keyboard"
            self._kb_lib = kb_lib
            return
        except Exception:
            pass
        self._backend = None

    @property
    def available(self) -> bool:
        return self._backend is not None

    def _parse_hotkey(self, hotkey: str):
        """将 'ctrl+shift+f6' 解析为 pynput 所需的按键集合。"""
        parts = [p.strip().lower() for p in hotkey.split("+") if p.strip()]
        keys = []
        for p in parts:
            if p in ("ctrl", "control"):
                keys.append(self._pynput_kb.Key.ctrl)
            elif p == "alt":
                keys.append(self._pynput_kb.Key.alt)
            elif p == "shift":
                keys.append(self._pynput_kb.Key.shift)
            elif p == "cmd" or p == "command" or p == "win" or p == "super":
                keys.append(self._pynput_kb.Key.cmd)
            elif len(p) == 1:
                keys.append(p)
            else:
                try:
                    keys.append(self._pynput_kb.Key[p])
                except Exception:
                    keys.append(p)
        return frozenset(keys)

    def add_hotkey(self, hotkey: str, callback) -> bool:
        """注册一个全局热键，成功返回 True。"""
        if not self.available:
            return False

        if self._backend == "keyboard":
            try:
                hook = self._kb_lib.add_hotkey(hotkey, callback, suppress=False)
                self._hooks.append(hook)
                return True
            except Exception:
                return False

        if self._backend == "pynput":
            try:
                target = self._parse_hotkey(hotkey)
                current = set()

                def on_press(key):
                    try:
                        k = key.char if hasattr(key, "char") and key.char else key
                    except Exception:
                        k = key
                    current.add(k)
                    if all(k in current for k in target):
                        callback()

                def on_release(key):
                    try:
                        k = key.char if hasattr(key, "char") and key.char else key
                    except Exception:
                        k = key
                    current.discard(k)

                if self._listener is None:
                    self._listener = self._pynput_kb.Listener(
                        on_press=on_press, on_release=on_release
                    )
                    self._listener.daemon = True
                    self._listener.start()
                self._hooks.append(hotkey)
                return True
            except Exception:
                return False

        return False

    def remove_all(self):
        """移除所有已注册的热键。"""
        if self._backend == "keyboard":
            for h in self._hooks:
                try:
                    self._kb_lib.remove_hotkey(h)
                except Exception:
                    pass
            self._hooks = []
        elif self._backend == "pynput":
            if self._listener:
                try:
                    self._listener.stop()
                except Exception:
                    pass
                self._listener = None
            self._hooks = []


# ---------------------------------------------------------------------------
# 窗口操作
# ---------------------------------------------------------------------------
def get_all_window_titles() -> list[str]:
    """获取所有窗口标题列表。"""
    titles = []
    try:
        try:
            import pygetwindow as gw
            titles = gw.getAllTitles()
        except Exception:
            try:
                import pywinctl as pwc
                wins = pwc.getAllWindows()
                titles = [w.title for w in wins]
            except Exception:
                pass
    except Exception:
        pass
    return titles or []


def close_windows_by_title(title: str) -> bool:
    """按标题模糊匹配关闭窗口，成功返回 True。"""
    if not title:
        return False
    try:
        try:
            import pygetwindow as gw
            wins = gw.getWindowsWithTitle(title)
            for w in wins:
                try:
                    w.close()
                except Exception:
                    pass
            return len(wins) > 0
        except Exception:
            try:
                import pywinctl as pwc
                wins = pwc.getWindowsWithTitle(title)
                for w in wins:
                    try:
                        w.close()
                    except Exception:
                        pass
                return len(wins) > 0
            except Exception:
                pass
    except Exception:
        pass
    return False


def window_exists(title: str) -> bool:
    """按标题模糊匹配判断窗口是否存在。"""
    if not title:
        return False
    titles = get_all_window_titles()
    return any(title.lower() in (w or "").lower() for w in titles)


# ---------------------------------------------------------------------------
# 粘贴快捷键
# ---------------------------------------------------------------------------
def get_paste_modifiers() -> list[str]:
    """返回粘贴快捷键的修饰键列表。Windows/Linux 用 ctrl，macOS 用 cmd。"""
    if IS_MACOS:
        return ["command", "v"]
    return ["ctrl", "v"]


def press_paste():
    """执行粘贴操作（ctrl+v 或 cmd+v）。"""
    try:
        import pyautogui
        mods = get_paste_modifiers()
        pyautogui.hotkey(*mods)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 中文输入（剪贴板 + 粘贴）
# ---------------------------------------------------------------------------
def copy_text_to_clipboard(text: str) -> bool:
    """将文本复制到剪贴板，成功返回 True。"""
    try:
        import pyperclip
        pyperclip.copy(text)
        return True
    except Exception:
        return False


def input_text_via_clipboard(text: str) -> bool:
    """通过剪贴板粘贴方式输入文本（用于中文等非 ASCII 文本）。"""
    if copy_text_to_clipboard(text):
        import time
        time.sleep(0.05)
        press_paste()
        return True
    return False
