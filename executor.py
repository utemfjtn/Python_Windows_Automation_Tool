# -*- coding: utf-8 -*-
"""
执行引擎模块
负责按顺序执行命令列表，支持：
  - 程序计数器（pc）推进
  - 重复/结束重复（repeat/end_repeat）—— 使用栈实现嵌套
  - 条件判断（if_image/if_not_image/if_window ... end_if）—— 支持嵌套
  - 跳转（goto/label）
  - 可中途停止（stop 标志）
执行在独立线程中运行，通过回调向 UI 报告状态与日志。
"""
from __future__ import annotations

import threading
import time
import traceback
import sys


class Executor:
    def __init__(self, commands, on_log=None, on_state=None, on_step=None):
        """
        :param commands: 命令列表（list[dict]）
        :param on_log:   日志回调 (msg: str, level: str) -> None
        :param on_state: 状态回调 (state: str) -> None, state in {running, stopped, finished, error}
        :param on_step:  步进回调 (index: int) -> None, 当前正在执行的行号
        """
        self.commands = commands
        self.on_log = on_log or (lambda m, l="info": None)
        self.on_state = on_state or (lambda s: None)
        self.on_step = on_step or (lambda i: None)

        self._stop_flag = threading.Event()
        self._pause_flag = threading.Event()
        self._pause_flag.set()  # 默认不暂停
        self._thread = None
        self.pc = 0

    # ------------------------------------------------------------------ 控制
    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_flag.clear()
        self._pause_flag.set()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_flag.set()
        self._pause_flag.set()  # 释放暂停
        self.on_state("stopped")
        self.on_log("已停止", "warn")

    def pause(self):
        self._pause_flag.clear()
        self.on_state("paused")
        self.on_log("已暂停", "info")

    def resume(self):
        self._pause_flag.set()
        self.on_state("running")
        self.on_log("继续运行", "info")

    def is_running(self):
        return self._thread is not None and self._thread.is_alive()

    # ------------------------------------------------------------------ 内部
    def _sleep(self, seconds):
        """可被停止中断的 sleep。"""
        self._stop_flag.wait(seconds)

    def _check_pause(self):
        """等待暂停解除，同时响应停止。"""
        while not self._pause_flag.is_set():
            if self._stop_flag.is_set():
                return
            time.sleep(0.05)

    def _check_macos_permissions(self):
        """macOS 运行前检查辅助功能权限，缺失则警告。
        
        pyautogui 的模拟操作（鼠标点击、按键）需要辅助功能权限，
        没有权限时操作会静默失败（不抛异常），导致用户以为程序没反应。
        """
        if sys.platform != "darwin":
            return
        try:
            from platform_utils import has_accessibility_permission
            if not has_accessibility_permission():
                self.on_log("警告：未授予辅助功能权限", "warn")
                self.on_log("鼠标点击和按键操作将无法生效", "warn")
                self.on_log("请在「系统设置 → 隐私与安全性 → 辅助功能」中授权", "warn")
                self.on_log("⚠️ 授权后必须重启 KeyboardWizard 才能生效！", "warn")
        except Exception:
            pass

    def _run(self):
        self.on_state("running")
        self.on_log("开始运行", "info")
        try:
            self._check_macos_permissions()
            self.pc = 0
            repeat_stack = []  # 元素: {"start": pc_of_repeat, "remaining": int}
            n = len(self.commands)
            while not self._stop_flag.is_set() and self.pc < n:
                self._check_pause()
                if self._stop_flag.is_set():
                    break
                cmd = self.commands[self.pc]
                if not cmd.get("enabled", True):
                    self.pc += 1
                    continue

                self.on_step(self.pc)
                t = cmd["type"]
                p = cmd.get("params", {})

                if t == "delay":
                    self.on_log(f"延时 {p.get('ms',0)}ms", "info")
                    self._sleep(p.get("ms", 0) / 1000.0)
                    self.pc += 1

                elif t == "key":
                    self._do_key(p)
                    self.pc += 1

                elif t == "input_text":
                    self._do_input_text(p)
                    self.pc += 1

                elif t == "click":
                    self._do_click(p)
                    self.pc += 1

                elif t == "image_click":
                    self._do_image_click(p)
                    self.pc += 1

                elif t == "image_wait":
                    self._do_image_wait(p)
                    self.pc += 1

                elif t == "repeat":
                    count = int(p.get("count", 1))
                    repeat_stack.append({"start": self.pc, "remaining": count})
                    self.on_log(f"重复开始 ×{count}", "info")
                    self.pc += 1

                elif t == "end_repeat":
                    if repeat_stack:
                        top = repeat_stack[-1]
                        top["remaining"] -= 1
                        if top["remaining"] > 0 and not self._stop_flag.is_set():
                            self.on_log(f"剩余重复 {top['remaining']} 次", "info")
                            self.pc = top["start"] + 1
                        else:
                            repeat_stack.pop()
                            self.pc += 1
                    else:
                        self.on_log("end_repeat 无匹配的 repeat，跳过", "warn")
                        self.pc += 1

                elif t in ("if_image", "if_not_image", "if_window"):
                    ok = self._eval_condition(t, p)
                    if ok:
                        self.pc += 1  # 进入分支
                    else:
                        # 跳到匹配的 end_if 之后
                        end = self._find_matching(self.pc, t, "end_if")
                        if end is None:
                            self.on_log("未找到匹配的 end_if", "error")
                            break
                        self.pc = end + 1

                elif t == "end_if":
                    self.pc += 1

                elif t == "label":
                    self.pc += 1

                elif t == "goto":
                    name = p.get("name", "")
                    idx = self._find_label(name)
                    if idx is None:
                        self.on_log(f"未找到标签 {name}", "error")
                        break
                    self.on_log(f"跳转到 {name}", "info")
                    self.pc = idx

                else:
                    self.on_log(f"未知指令类型 {t}", "warn")
                    self.pc += 1

            if not self._stop_flag.is_set():
                self.on_state("finished")
                self.on_log("运行结束", "info")
            self.on_step(-1)
        except Exception as e:
            self.on_state("error")
            self.on_log(f"运行出错：{e}\n{traceback.format_exc()}", "error")
            self.on_step(-1)

    # ------------------------------------------------------------------ 指令实现
    def _do_key(self, p):
        import pyautogui
        key = p.get("key", "enter")
        hold = float(p.get("hold", 0) or 0)
        self.on_log(f"按键 {key}", "info")
        if hold > 0:
            pyautogui.keyDown(key)
            self._sleep(hold)
            pyautogui.keyUp(key)
        else:
            # 支持组合键，如 "ctrl+s"
            if "+" in key:
                keys = [k.strip() for k in key.split("+")]
                pyautogui.hotkey(*keys)
            else:
                pyautogui.press(key)

    def _do_input_text(self, p):
        import pyautogui
        from platform_utils import input_text_via_clipboard
        text = p.get("text", "")
        interval = float(p.get("interval", 0) or 0)
        self.on_log(f"输入文本 {len(text)} 字符", "info")
        try:
            text.encode("ascii")
            pyautogui.write(text, interval=interval)
        except UnicodeEncodeError:
            if not input_text_via_clipboard(text):
                self.on_log("文本含非 ASCII 字符且剪贴板操作失败，已跳过", "warn")

    def _do_click(self, p):
        import pyautogui
        x = int(p.get("x", 0))
        y = int(p.get("y", 0))
        button = p.get("button", "left")
        clicks = int(p.get("clicks", 1))
        interval = float(p.get("interval", 0) or 0)
        self.on_log(f"点击 ({x},{y}) {button}×{clicks}", "info")
        pyautogui.click(x=x, y=y, button=button, clicks=clicks, interval=interval)

    def _do_image_click(self, p):
        import pyautogui
        image = p.get("image", "")
        if not image:
            self.on_log("点击图片：未设置图片", "warn")
            return
        confidence = float(p.get("confidence", 0.8))
        button = p.get("button", "left")
        clicks = int(p.get("clicks", 1))
        region = p.get("region")
        ox = int(p.get("offset_x", 0))
        oy = int(p.get("offset_y", 0))
        try:
            pos = pyautogui.locateCenterOnScreen(image, confidence=confidence, region=region)
        except Exception as e:
            self.on_log(f"图片识别异常：{e}", "error")
            return
        if pos is None:
            self.on_log(f"未找到图片 {image}", "warn")
            return
        x, y = pos.x + ox, pos.y + oy
        self.on_log(f"点击图片于 ({x},{y})", "info")
        pyautogui.click(x=x, y=y, button=button, clicks=clicks)

    def _do_image_wait(self, p):
        import pyautogui
        image = p.get("image", "")
        if not image:
            return
        confidence = float(p.get("confidence", 0.8))
        timeout = float(p.get("timeout", 10))
        region = p.get("region")
        self.on_log(f"等待图片出现（超时 {timeout}s）", "info")
        end_time = time.time() + timeout
        while not self._stop_flag.is_set():
            try:
                pos = pyautogui.locateCenterOnScreen(image, confidence=confidence, region=region)
            except Exception:
                pos = None
            if pos:
                self.on_log("图片已出现", "info")
                return
            if time.time() > end_time:
                self.on_log("等待图片超时", "warn")
                return
            self._sleep(0.3)

    # ------------------------------------------------------------------ 条件/跳转辅助
    def _eval_condition(self, t, p):
        if t == "if_window":
            return self._window_exists(p.get("title", ""))
        # if_image / if_not_image
        found = self._find_image(p)
        return found if t == "if_image" else (not found)

    def _find_image(self, p):
        import pyautogui
        image = p.get("image", "")
        if not image:
            return False
        confidence = float(p.get("confidence", 0.8))
        region = p.get("region")
        try:
            pos = pyautogui.locateCenterOnScreen(image, confidence=confidence, region=region)
        except Exception:
            pos = None
        return pos is not None

    def _window_exists(self, title):
        """模糊匹配窗口标题。"""
        from platform_utils import window_exists
        return window_exists(title)

    def _find_matching(self, start, open_type, close_type):
        """从 start（open 指令）开始，找到对应的 close 指令索引，支持嵌套。"""
        depth = 0
        for i in range(start, len(self.commands)):
            t = self.commands[i].get("type")
            if t in ("if_image", "if_not_image", "if_window"):
                depth += 1
            elif t == "end_if":
                depth -= 1
                if depth == 0:
                    return i
        return None

    def _find_label(self, name):
        for i, c in enumerate(self.commands):
            if c.get("type") == "label" and c.get("params", {}).get("name") == name:
                return i
        return None
