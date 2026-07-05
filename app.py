# -*- coding: utf-8 -*-
"""
主界面
基于 customtkinter 的简洁美观界面，包含：
  - 指令列表（增删改查、上下移动、启用/禁用）
  - 开始 / 停止 / 暂停 按钮
  - 自定义全局快捷键设置
  - 全局监控规则配置（系统提示/杀毒弹窗等）
  - 文件保存/加载（JSON）
  - 运行日志
"""
from __future__ import annotations

import json
import os
import sys
import threading

import customtkinter as ctk
from tkinter import filedialog, messagebox, ttk

import commands as C
from executor import Executor
from monitor import GlobalMonitor
from platform_utils import (
    get_ui_font, get_mono_font, get_app_icon, set_window_icon,
    HotkeyManager, resource_path, get_app_dir
)

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

DEFAULT_START_HOTKEY = "f6"
DEFAULT_STOP_HOTKEY = "f7"
VERSION = "1.2.5"

CONFIG_FILE = os.path.join(get_app_dir(), "config.json")

# 全局监控动作选项
MONITOR_ACTIONS = ["enter", "esc", "close_window", "click_image", "custom_key"]
MONITOR_ACTION_NAMES = {
    "enter": "回车",
    "esc": "ESC",
    "close_window": "关闭窗口",
    "click_image": "点击图片",
    "custom_key": "自定义按键",
}


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("KeyboardWizard")
        self.geometry("1000x680")
        self.minsize(900, 600)
        self._try_set_icon()

        self.commands = []            # 命令列表
        self.executor = None
        self.monitor = GlobalMonitor(rules=[], on_log=self._log)
        self.start_hotkey = DEFAULT_START_HOTKEY
        self.stop_hotkey = DEFAULT_STOP_HOTKEY
        self.monitor_rules = []

        self._build_menu()
        self._build_layout()
        self._load_config()
        self._refresh_list()
        self._warmup_macos()
        self._setup_hotkeys()
        self._check_macos_permissions()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------ macOS 预热
    def _warmup_macos(self):
        """macOS 启动预热：在主线程加载 Quartz/CoreFoundation 等 pyobjc 框架。

        macOS 26+ 要求 HIToolbox TSM API 在主线程调用。pynput/pyautogui 在后台
        线程调用这些 API 会崩溃。提前在主线程导入并触发初始化，让模块级缓存生效。
        """
        if not sys.platform == "darwin":
            return
        try:
            # 在主线程预导入 Quartz / CoreFoundation（触发 pyobjc 框架初始化）
            import Quartz
            import CoreFoundation
            # 预热 HIToolbox：在主线程获取当前输入源（安全）
            try:
                import ctypes
                import ctypes.util
                carbon = ctypes.CDLL(ctypes.util.find_library('Carbon'))
                carbon.TISGetCurrentInputSource.restype = ctypes.c_void_p
                _ = carbon.TISGetCurrentInputSource()
            except Exception:
                pass
        except Exception:
            pass

    # ------------------------------------------------------------------ macOS 权限检查
    def _check_macos_permissions(self):
        """macOS 启动时检查辅助功能权限，缺失则弹窗引导用户授权。"""
        if sys.platform != "darwin":
            return
        from platform_utils import has_accessibility_permission
        if has_accessibility_permission():
            return
        # 没有权限 → 弹窗提示（不阻塞主界面，用 after 延迟显示）
        self.after(300, self._show_accessibility_prompt)

    def _show_accessibility_prompt(self):
        from platform_utils import open_accessibility_settings
        result = messagebox.askyesno(
            "需要辅助功能权限",
            "KeyboardWizard 需要「辅助功能」权限才能使用全局快捷键和鼠标控制。\n\n"
            "请在系统设置中授予权限：\n"
            "  系统设置 → 隐私与安全性 → 辅助功能\n"
            "  勾选 KeyboardWizard\n\n"
            "⚠️ 重要：授权后必须重启 KeyboardWizard 才能生效！\n\n"
            "是否现在打开系统设置？",
        )
        if result:
            open_accessibility_settings()
        self._log("提示：未授予辅助功能权限，全局快捷键和鼠标操作不可用", "warn")
        self._log("请在「系统设置 → 隐私与安全性 → 辅助功能」中授权并重启应用", "warn")

    # ------------------------------------------------------------------ 图标
    def _try_set_icon(self):
        """尝试设置窗口图标，失败则静默跳过（不影响使用）。"""
        try:
            assets = resource_path("assets")
            icon_path = get_app_icon(assets)
            if icon_path:
                set_window_icon(self, icon_path)
        except Exception:
            pass

    # ------------------------------------------------------------------ 菜单
    def _build_menu(self):
        menubar = ctk.CTkFrame(self, height=30, fg_color=("#e8e8e8", "#2b2b2b"))
        menubar.pack(fill="x", side="top")
        ctk.CTkButton(menubar, text="新建", width=70, height=26,
                      command=self._new_file).pack(side="left", padx=4, pady=2)
        ctk.CTkButton(menubar, text="打开", width=70, height=26,
                      command=self._open_file).pack(side="left", padx=4, pady=2)
        ctk.CTkButton(menubar, text="保存", width=70, height=26,
                      command=self._save_file).pack(side="left", padx=4, pady=2)
        ctk.CTkButton(menubar, text="全局监控设置", width=120, height=26,
                      command=self._open_monitor_settings).pack(side="left", padx=4, pady=2)
        ctk.CTkButton(menubar, text="快捷键设置", width=100, height=26,
                      command=self._open_hotkey_settings).pack(side="left", padx=4, pady=2)

    # ------------------------------------------------------------------ 布局
    def _build_layout(self):
        # 左侧：指令列表 + 操作按钮
        left = ctk.CTkFrame(self, width=620)
        left.pack(fill="both", expand=True, side="left", padx=(8, 4), pady=8)
        left.pack_propagate(False)

        top_bar = ctk.CTkFrame(left, fg_color="transparent")
        top_bar.pack(fill="x", padx=8, pady=(8, 4))
        ctk.CTkLabel(top_bar, text="指令列表", font=ctk.CTkFont(size=15, weight="bold")).pack(side="left")
        ctk.CTkLabel(top_bar, text="", text_color="gray").pack(side="left", padx=8)

        # 使用 ttk.Treeview 展示列表（支持选中、滚动）
        tree_frame = ctk.CTkFrame(left)
        tree_frame.pack(fill="both", expand=True, padx=8, pady=4)
        style = ttk.Style()
        style.theme_use("default")
        ui_font = get_ui_font(11)
        ui_font_bold = get_ui_font(11, bold=True)
        style.configure("Treeview", rowheight=26, font=ui_font)
        style.configure("Treeview.Heading", font=ui_font_bold)

        self.tree = ttk.Treeview(tree_frame,
                                 columns=("idx", "type", "desc", "comment", "enabled"),
                                 show="headings", selectmode="browse")
        self.tree.heading("idx", text="#")
        self.tree.heading("type", text="类型")
        self.tree.heading("desc", text="参数")
        self.tree.heading("comment", text="备注")
        self.tree.heading("enabled", text="启用")
        self.tree.column("idx", width=40, anchor="center")
        self.tree.column("type", width=100, anchor="center")
        self.tree.column("desc", width=280)
        self.tree.column("comment", width=120)
        self.tree.column("enabled", width=50, anchor="center")
        self.tree.pack(fill="both", expand=True, side="left")
        vsb = ctk.CTkScrollbar(tree_frame, command=self.tree.yview)
        vsb.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.bind("<Double-1>", lambda e: self._edit_selected())

        # 操作按钮行
        btn_bar = ctk.CTkFrame(left, fg_color="transparent")
        btn_bar.pack(fill="x", padx=8, pady=4)
        ctk.CTkButton(btn_bar, text="添加", width=70, command=self._add_cmd).pack(side="left", padx=2)
        ctk.CTkButton(btn_bar, text="编辑", width=70, command=self._edit_selected).pack(side="left", padx=2)
        ctk.CTkButton(btn_bar, text="删除", width=70, fg_color="#c0392b",
                      hover_color="#922b21", command=self._delete_cmd).pack(side="left", padx=2)
        ctk.CTkButton(btn_bar, text="上移", width=60, command=lambda: self._move(-1)).pack(side="left", padx=2)
        ctk.CTkButton(btn_bar, text="下移", width=60, command=lambda: self._move(1)).pack(side="left", padx=2)
        ctk.CTkButton(btn_bar, text="复制", width=60, command=self._duplicate_cmd).pack(side="left", padx=2)

        # 运行控制行
        run_bar = ctk.CTkFrame(left, fg_color="transparent")
        run_bar.pack(fill="x", padx=8, pady=(4, 8))
        self.btn_start = ctk.CTkButton(run_bar, text="▶ 开始 (F6)", width=130,
                                       fg_color="#27ae60", hover_color="#1e8449",
                                       command=self._start)
        self.btn_start.pack(side="left", padx=2)
        self.btn_pause = ctk.CTkButton(run_bar, text="⏸ 暂停", width=90,
                                       command=self._pause, state="disabled")
        self.btn_pause.pack(side="left", padx=2)
        self.btn_stop = ctk.CTkButton(run_bar, text="■ 停止 (F7)", width=130,
                                      fg_color="#e74c3c", hover_color="#cb3728",
                                      command=self._stop, state="disabled")
        self.btn_stop.pack(side="left", padx=2)
        self.lbl_status = ctk.CTkLabel(run_bar, text="状态：就绪", text_color="gray")
        self.lbl_status.pack(side="left", padx=12)
        ctk.CTkLabel(run_bar, text=f"v{VERSION}", text_color="#666666",
                     font=ctk.CTkFont(size=10)).pack(side="right", padx=8)

        # 右侧：日志 + 全局监控状态
        right = ctk.CTkFrame(self, width=360)
        right.pack(fill="both", expand=True, side="right", padx=(4, 8), pady=8)
        right.pack_propagate(False)

        ctk.CTkLabel(right, text="运行日志", font=ctk.CTkFont(size=15, weight="bold")).pack(anchor="w", padx=12, pady=(12, 4))
        mono_font = get_mono_font(11)
        self.log_box = ctk.CTkTextbox(right, font=mono_font, wrap="word")
        self.log_box.pack(fill="both", expand=True, padx=8, pady=4)
        self.log_box.configure(state="disabled")

        log_bar = ctk.CTkFrame(right, fg_color="transparent")
        log_bar.pack(fill="x", padx=8, pady=(0, 8))
        ctk.CTkButton(log_bar, text="清空日志", width=90, command=self._clear_log).pack(side="left")
        self.monitor_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(log_bar, text="启用全局监控", variable=self.monitor_var,
                        command=self._toggle_monitor).pack(side="left", padx=12)

    # ------------------------------------------------------------------ 列表操作
    def _refresh_list(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for i, cmd in enumerate(self.commands):
            self.tree.insert("", "end", iid=str(i),
                             values=(i + 1,
                                     C.TYPE_NAMES.get(cmd["type"], cmd["type"]),
                                     C.describe(cmd),
                                     cmd.get("comment", ""),
                                     "√" if cmd.get("enabled", True) else "×"))
        # 行高亮：禁用项灰色
        self.tree.tag_configure("off", foreground="#999999")
        for i, cmd in enumerate(self.commands):
            if not cmd.get("enabled", True):
                self.tree.item(str(i), tags=("off",))

    def _selected_index(self):
        sel = self.tree.selection()
        if not sel:
            return None
        return int(sel[0])

    def _labels(self):
        return [c["params"].get("name", "") for c in self.commands if c["type"] == C.LABEL]

    def _add_cmd(self):
        from command_dialog import edit_command
        result = edit_command(self, cmd=None, labels=self._labels())
        if result:
            self.commands.append(result)
            self._refresh_list()
            self._select(len(self.commands) - 1)

    def _edit_selected(self):
        idx = self._selected_index()
        if idx is None:
            messagebox.showinfo("提示", "请先选择一条指令")
            return
        from command_dialog import edit_command
        result = edit_command(self, cmd=self.commands[idx], labels=self._labels())
        if result:
            self.commands[idx] = result
            self._refresh_list()
            self._select(idx)

    def _delete_cmd(self):
        idx = self._selected_index()
        if idx is None:
            return
        del self.commands[idx]
        self._refresh_list()

    def _duplicate_cmd(self):
        idx = self._selected_index()
        if idx is None:
            return
        import copy
        self.commands.insert(idx + 1, copy.deepcopy(self.commands[idx]))
        self._refresh_list()
        self._select(idx + 1)

    def _move(self, delta):
        idx = self._selected_index()
        if idx is None:
            return
        new = idx + delta
        if 0 <= new < len(self.commands):
            self.commands[idx], self.commands[new] = self.commands[new], self.commands[idx]
            self._refresh_list()
            self._select(new)

    def _select(self, idx):
        if 0 <= idx < len(self.commands):
            self.tree.selection_set(str(idx))
            self.tree.focus(str(idx))
            self.tree.see(str(idx))

    # ------------------------------------------------------------------ 运行控制
    def _start(self):
        if not self.commands:
            messagebox.showwarning("提示", "指令列表为空")
            return
        if self.executor and self.executor.is_running():
            return
        # 保存配置（包含命令列表），便于下次恢复
        self._save_config()
        self.executor = Executor(
            commands=self.commands,
            on_log=self._log,
            on_state=self._on_state,
            on_step=self._on_step,
        )
        self._set_running_ui(True)
        self.executor.start()

    def _stop(self):
        if self.executor:
            self.executor.stop()
        self._set_running_ui(False)

    def _pause(self):
        if not self.executor:
            return
        if self.executor._pause_flag.is_set():
            self.executor.pause()
            self.btn_pause.configure(text="▶ 继续")
        else:
            self.executor.resume()
            self.btn_pause.configure(text="⏸ 暂停")

    def _on_state(self, state):
        def upd():
            text_map = {"running": "运行中", "paused": "已暂停", "stopped": "已停止",
                        "finished": "已完成", "error": "出错"}
            self.lbl_status.configure(text=f"状态：{text_map.get(state, state)}")
            if state in ("stopped", "finished", "error"):
                self._set_running_ui(False)
        self.after(0, upd)

    def _on_step(self, idx):
        def upd():
            if idx < 0:
                for iid in self.tree.get_children():
                    self.tree.item(iid, tags=())
            else:
                # 高亮当前行
                for iid in self.tree.get_children():
                    tags = list(self.tree.item(iid, "tags"))
                    tags = [t for t in tags if t != "cur"]
                    self.tree.item(iid, tags=tags)
                cur_tags = list(self.tree.item(str(idx), "tags"))
                if "cur" not in cur_tags:
                    cur_tags.append("cur")
                self.tree.item(str(idx), tags=cur_tags)
                self.tree.see(str(idx))
        self.after(0, upd)

    def _set_running_ui(self, running):
        self.btn_start.configure(state="disabled" if running else "normal")
        self.btn_stop.configure(state="normal" if running else "disabled")
        self.btn_pause.configure(state="normal" if running else "disabled")
        if not running:
            self.btn_pause.configure(text="⏸ 暂停")

    # ------------------------------------------------------------------ 日志
    def _log(self, msg, level="info"):
        color = {"info": "", "warn": "#d68910", "error": "#c0392b"}.get(level, "")
        def upd():
            self.log_box.configure(state="normal")
            tag = f"lvl_{level}"
            self.log_box.tag_config(tag, foreground=color) if color else None
            import time as _t
            line = f"[{_t.strftime('%H:%M:%S')}] {msg}\n"
            if color:
                self.log_box.insert("end", line, tag)
            else:
                self.log_box.insert("end", line)
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        self.after(0, upd)

    def _clear_log(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    # ------------------------------------------------------------------ 全局监控
    def _toggle_monitor(self):
        if self.monitor_var.get():
            self.monitor.update_rules(self.monitor_rules)
            self.monitor.start()
        else:
            self.monitor.stop()

    def _open_monitor_settings(self):
        MonitorDialog(self, self.monitor_rules, on_save=self._save_monitor_rules)

    def _save_monitor_rules(self, rules):
        self.monitor_rules = rules
        self.monitor.update_rules(rules)
        self._save_config()

    # ------------------------------------------------------------------ 快捷键设置
    def _open_hotkey_settings(self):
        HotkeyDialog(self, self.start_hotkey, self.stop_hotkey, on_save=self._save_hotkeys)

    def _save_hotkeys(self, start, stop):
        self.start_hotkey = start
        self.stop_hotkey = stop
        self.btn_start.configure(text=f"▶ 开始 ({start.upper()})")
        self.btn_stop.configure(text=f"■ 停止 ({stop.upper()})")
        self._setup_hotkeys()
        self._save_config()

    def _setup_hotkeys(self):
        if not hasattr(self, "_hotkey_mgr"):
            self._hotkey_mgr = HotkeyManager()
        if not self._hotkey_mgr.available:
            self._log("未安装可用的全局快捷键库（pynput / keyboard），全局快捷键不可用", "warn")
            return
        self._hotkey_mgr.remove_all()
        try:
            ok1 = self._hotkey_mgr.add_hotkey(self.start_hotkey, self._on_start_hotkey)
            ok2 = self._hotkey_mgr.add_hotkey(self.stop_hotkey, self._on_stop_hotkey)
            if not ok1 or not ok2:
                self._log("注册快捷键失败", "error")
        except Exception as e:
            self._log(f"注册快捷键失败：{e}", "error")

    def _on_start_hotkey(self):
        self.after(0, self._start)

    def _on_stop_hotkey(self):
        self.after(0, self._stop)

    # ------------------------------------------------------------------ 文件操作
    def _new_file(self):
        if self.executor and self.executor.is_running():
            messagebox.showwarning("提示", "请先停止运行")
            return
        self.commands = []
        self._refresh_list()

    def _open_file(self):
        path = filedialog.askopenfilename(
            defaultextension=".json",
            filetypes=[("按键脚本", "*.json"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.commands = [C.from_dict(c) for c in data.get("commands", [])]
            self._refresh_list()
            self._log(f"已加载 {len(self.commands)} 条指令", "info")
        except Exception as e:
            messagebox.showerror("加载失败", str(e))

    def _save_file(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("按键脚本", "*.json"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            data = {"commands": [C.to_dict(c) for c in self.commands]}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self._log(f"已保存到 {path}", "info")
        except Exception as e:
            messagebox.showerror("保存失败", str(e))

    # ------------------------------------------------------------------ 配置持久化
    def _save_config(self):
        data = {
            "start_hotkey": self.start_hotkey,
            "stop_hotkey": self.stop_hotkey,
            "monitor_enabled": self.monitor_var.get(),
            "monitor_rules": self.monitor_rules,
            "commands": [C.to_dict(c) for c in self.commands],
        }
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_config(self):
        if not os.path.exists(CONFIG_FILE):
            return
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.start_hotkey = data.get("start_hotkey", DEFAULT_START_HOTKEY)
            self.stop_hotkey = data.get("stop_hotkey", DEFAULT_STOP_HOTKEY)
            self.monitor_rules = data.get("monitor_rules", [])
            self.commands = [C.from_dict(c) for c in data.get("commands", [])]
            self.monitor.update_rules(self.monitor_rules)
            self.btn_start.configure(text=f"▶ 开始 ({self.start_hotkey.upper()})")
            self.btn_stop.configure(text=f"■ 停止 ({self.stop_hotkey.upper()})")
            if data.get("monitor_enabled"):
                self.monitor_var.set(True)
                self._toggle_monitor()
        except Exception as e:
            print("加载配置失败：", e)

    # ------------------------------------------------------------------ 关闭
    def _on_close(self):
        if self.executor and self.executor.is_running():
            self.executor.stop()
        self.monitor.stop()
        self._save_config()
        if hasattr(self, "_hotkey_mgr"):
            self._hotkey_mgr.remove_all()
        self.destroy()


# ===========================================================================
# 快捷键设置对话框
# ===========================================================================
class HotkeyDialog(ctk.CTkToplevel):
    def __init__(self, master, start, stop, on_save):
        super().__init__(master)
        self.title("快捷键设置")
        self.geometry("380x220")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        self.on_save = on_save
        self.start_var = ctk.StringVar(value=start)
        self.stop_var = ctk.StringVar(value=stop)

        ctk.CTkLabel(self, text="设置开始/停止的全局快捷键\n（输入按键名，如 f6 / ctrl+f6 / ctrl+shift+s）",
                    justify="left").pack(padx=16, pady=(16, 8), anchor="w")

        f1 = ctk.CTkFrame(self, fg_color="transparent")
        f1.pack(fill="x", padx=16, pady=4)
        ctk.CTkLabel(f1, text="开始：", width=60).pack(side="left")
        ctk.CTkEntry(f1, textvariable=self.start_var).pack(side="left", fill="x", expand=True)

        f2 = ctk.CTkFrame(self, fg_color="transparent")
        f2.pack(fill="x", padx=16, pady=4)
        ctk.CTkLabel(f2, text="停止：", width=60).pack(side="left")
        ctk.CTkEntry(f2, textvariable=self.stop_var).pack(side="left", fill="x", expand=True)

        bf = ctk.CTkFrame(self, fg_color="transparent")
        bf.pack(fill="x", padx=16, pady=12)
        ctk.CTkButton(bf, text="取消", width=80, command=self.destroy).pack(side="right", padx=(8, 0))
        ctk.CTkButton(bf, text="保存", width=80, command=self._save).pack(side="right")
        self.focus_force()

    def _save(self):
        self.on_save(self.start_var.get().strip().lower(), self.stop_var.get().strip().lower())
        self.destroy()


# ===========================================================================
# 全局监控设置对话框
# ===========================================================================
class MonitorDialog(ctk.CTkToplevel):
    def __init__(self, master, rules, on_save):
        super().__init__(master)
        self.title("全局监控设置")
        self.geometry("780x520")
        self.transient(master)
        self.grab_set()

        self.on_save = on_save
        import copy
        self.rules = copy.deepcopy(rules) if rules else []

        ctk.CTkLabel(self, text="全局监控规则\n当屏幕出现系统提示、杀毒弹窗等匹配项时自动执行动作（无需在指令列表中编写）",
                    justify="left").pack(padx=16, pady=(12, 4), anchor="w")

        # 规则列表
        tree_frame = ctk.CTkFrame(self)
        tree_frame.pack(fill="both", expand=True, padx=12, pady=4)
        style = ttk.Style()
        mono_font_small = get_ui_font(10)
        style.configure("Treeview", rowheight=24, font=mono_font_small)
        self.tree = ttk.Treeview(tree_frame,
                                 columns=("name", "type", "target", "action", "enabled"),
                                 show="headings")
        self.tree.heading("name", text="名称")
        self.tree.heading("type", text="匹配方式")
        self.tree.heading("target", text="目标")
        self.tree.heading("action", text="动作")
        self.tree.heading("enabled", text="启用")
        self.tree.column("name", width=120)
        self.tree.column("type", width=90, anchor="center")
        self.tree.column("target", width=240)
        self.tree.column("action", width=120, anchor="center")
        self.tree.column("enabled", width=50, anchor="center")
        self.tree.pack(fill="both", expand=True, side="left")
        vsb = ctk.CTkScrollbar(tree_frame, command=self.tree.yview)
        vsb.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.bind("<Double-1>", lambda e: self._edit_rule())

        self._refresh()
        bf = ctk.CTkFrame(self, fg_color="transparent")
        bf.pack(fill="x", padx=12, pady=8)
        ctk.CTkButton(bf, text="添加规则", width=100, command=self._add_rule).pack(side="left")
        ctk.CTkButton(bf, text="编辑", width=80, command=self._edit_rule).pack(side="left", padx=4)
        ctk.CTkButton(bf, text="删除", width=80, fg_color="#c0392b",
                      command=self._del_rule).pack(side="left", padx=4)
        ctk.CTkButton(bf, text="保存并关闭", width=120, command=self._save).pack(side="right")

        self.focus_force()

    def _refresh(self):
        for it in self.tree.get_children():
            self.tree.delete(it)
        for i, r in enumerate(self.rules):
            t = r.get("type", "window")
            target = r.get("title") or r.get("image", "") or ""
            target = os.path.basename(target) if t == "image" else target
            act = MONITOR_ACTION_NAMES.get(r.get("action", "enter"), r.get("action", ""))
            self.tree.insert("", "end", iid=str(i),
                             values=(r.get("name", ""), "窗口" if t == "window" else "图片",
                                     target, act, "√" if r.get("enabled", True) else "×"))

    def _sel(self):
        s = self.tree.selection()
        return int(s[0]) if s else None

    def _add_rule(self):
        r = MonitorRuleDialog(self, None)
        if r:
            self.rules.append(r)
            self._refresh()

    def _edit_rule(self):
        idx = self._sel()
        if idx is None:
            return
        r = MonitorRuleDialog(self, self.rules[idx])
        if r:
            self.rules[idx] = r
            self._refresh()

    def _del_rule(self):
        idx = self._sel()
        if idx is None:
            return
        del self.rules[idx]
        self._refresh()

    def _save(self):
        self.on_save(self.rules)
        self.destroy()


class MonitorRuleDialog(ctk.CTkToplevel):
    def __init__(self, master, rule):
        super().__init__(master)
        self.title("监控规则")
        self.geometry("500x480")
        self.transient(master)
        self.grab_set()

        self.result = None
        if rule is None:
            rule = {"name": "规则1", "type": "window", "title": "",
                    "image": "", "confidence": 0.8, "action": "enter",
                    "action_key": "enter", "action_image": "",
                    "enabled": True}

        self.name_var = ctk.StringVar(value=rule.get("name", ""))
        self.type_var = ctk.StringVar(value=rule.get("type", "window"))
        self.title_var = ctk.StringVar(value=rule.get("title", ""))
        self.image_var = ctk.StringVar(value=rule.get("image", ""))
        self.conf_var = ctk.StringVar(value=str(rule.get("confidence", 0.8)))
        self.action_var = ctk.StringVar(value=rule.get("action", "enter"))
        self.action_key_var = ctk.StringVar(value=rule.get("action_key", "enter"))
        self.action_image_var = ctk.StringVar(value=rule.get("action_image", ""))
        self.enabled_var = ctk.BooleanVar(value=rule.get("enabled", True))

        # 参数容器：每次切换类型/动作时重建，避免 pack 顺序混乱
        self._param_box = ctk.CTkFrame(self, fg_color="transparent")
        self._param_box.pack(fill="both", expand=True, padx=12, pady=4)
        self._rebuild_params()

        ctk.CTkCheckBox(self, text="启用", variable=self.enabled_var).pack(anchor="w", padx=108, pady=4)

        bf = ctk.CTkFrame(self, fg_color="transparent")
        bf.pack(fill="x", padx=12, pady=10)
        ctk.CTkButton(bf, text="取消", width=80, command=self.destroy).pack(side="right", padx=(8, 0))
        ctk.CTkButton(bf, text="确定", width=80, command=self._ok).pack(side="right")
        self.focus_force()

    def _row(self, label, widget):
        f = ctk.CTkFrame(self._param_box, fg_color="transparent")
        f.pack(fill="x", padx=4, pady=4)
        ctk.CTkLabel(f, text=label, width=90, anchor="e").pack(side="left")
        widget.pack(side="left", fill="x", expand=True, padx=(8, 0))
        return f

    def _image_row(self, label, var):
        f = ctk.CTkFrame(self._param_box, fg_color="transparent")
        f.pack(fill="x", padx=4, pady=4)
        ctk.CTkLabel(f, text=label, width=90, anchor="e").pack(side="left")
        ctk.CTkEntry(f, textvariable=var).pack(side="left", fill="x", expand=True, padx=(8, 4))
        ctk.CTkButton(f, text="截图", width=60, command=lambda: self._capture(var)).pack(side="left")
        ctk.CTkButton(f, text="文件", width=60, command=lambda: self._pick_file(var)).pack(side="left", padx=4)
        return f

    def _rebuild_params(self):
        for w in self._param_box.winfo_children():
            w.destroy()
        self._row("名称：", ctk.CTkEntry(self._param_box, textvariable=self.name_var))
        self._row("匹配方式：", ctk.CTkOptionMenu(
            self._param_box, variable=self.type_var, values=["window", "image"],
            width=120, command=lambda v: self._rebuild_params()))
        if self.type_var.get() == "window":
            self._row("窗口标题：", ctk.CTkEntry(self._param_box, textvariable=self.title_var))
            ctk.CTkLabel(self._param_box, text="（模糊匹配，包含关键词即触发）",
                         text_color="gray").pack(anchor="w", padx=108)
        else:
            self._image_row("图片：", self.image_var)
            self._row("置信度：", ctk.CTkEntry(self._param_box, textvariable=self.conf_var, width=80))
        self._row("动作：", ctk.CTkOptionMenu(
            self._param_box, variable=self.action_var, values=MONITOR_ACTIONS,
            width=140, command=lambda v: self._rebuild_params()))
        act = self.action_var.get()
        if act == "custom_key":
            self._row("动作按键：", ctk.CTkEntry(self._param_box, textvariable=self.action_key_var, width=120))
            ctk.CTkLabel(self._param_box, text="（组合键用 + 连接，如 ctrl+s）",
                         text_color="gray").pack(anchor="w", padx=108)
        elif act == "click_image":
            self._image_row("动作图片：", self.action_image_var)

    def _pick_file(self, var):
        p = filedialog.askopenfilename(filetypes=[("图片", "*.png *.jpg *.bmp")])
        if p:
            var.set(p)

    def _capture(self, var):
        self.withdraw()
        try:
            from image_capture import RegionCapture
            p = RegionCapture().capture()
            if p:
                var.set(p)
        except Exception as e:
            messagebox.showerror("截图失败", str(e))
        finally:
            self.deiconify()
            self.focus_force()

    def _ok(self):
        try:
            conf = float(self.conf_var.get())
        except Exception:
            conf = 0.8
        self.result = {
            "name": self.name_var.get(),
            "type": self.type_var.get(),
            "title": self.title_var.get(),
            "image": self.image_var.get(),
            "confidence": conf,
            "action": self.action_var.get(),
            "action_key": self.action_key_var.get(),
            "action_image": self.action_image_var.get(),
            "enabled": self.enabled_var.get(),
        }
        self.destroy()


def edit_rule(master, rule=None):
    dlg = MonitorRuleDialog(master, rule)
    master.wait_window(dlg)
    return dlg.result
