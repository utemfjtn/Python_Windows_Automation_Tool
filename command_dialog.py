# -*- coding: utf-8 -*-
"""
命令编辑对话框
根据指令类型动态显示对应的参数输入控件。
"""
from __future__ import annotations

import os

import customtkinter as ctk
from tkinter import filedialog, messagebox

import commands as C


ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


class CommandDialog(ctk.CTkToplevel):
    def __init__(self, master, cmd=None, labels=None):
        """
        :param cmd: 待编辑命令；为 None 则新建
        :param labels: 当前列表中已有的标签名，用于跳转目标下拉
        """
        super().__init__(master)
        self.title("编辑指令")
        self.geometry("520x560")
        self.resizable(False, True)
        self.transient(master)
        self.grab_set()

        self.result = None
        self.labels = labels or []
        self._widgets = {}

        if cmd is None:
            cmd = C.make_command(C.KEY)
        self._cmd_type = cmd["type"]
        self._data = {k: v for k, v in cmd.items()}

        self._build_type_selector()
        self._params_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._params_frame.pack(fill="both", expand=True, padx=16, pady=(4, 8))

        self._build_common()
        self._rebuild_params()

        # 底部按钮
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=16, pady=(0, 12))
        ctk.CTkButton(btn_frame, text="取消", width=100,
                      command=self._cancel).pack(side="right", padx=(8, 0))
        ctk.CTkButton(btn_frame, text="确定", width=100,
                      command=self._ok).pack(side="right")

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.after(50, lambda: self.focus_force())

    # ------------------------------------------------------------------ 类型选择
    def _build_type_selector(self):
        f = ctk.CTkFrame(self, fg_color="transparent")
        f.pack(fill="x", padx=16, pady=(12, 4))
        ctk.CTkLabel(f, text="指令类型：").pack(side="left")
        names = [C.TYPE_NAMES[t] for t in C.ALL_TYPES]
        cur = C.TYPE_NAMES[self._cmd_type]
        self._type_var = ctk.StringVar(value=cur)
        combo = ctk.CTkOptionMenu(
            f, variable=self._type_var, values=names,
            command=self._on_type_change, width=180)
        combo.pack(side="left", padx=8)

    def _on_type_change(self, selected_name):
        # 反查类型
        t = None
        for k, v in C.TYPE_NAMES.items():
            if v == selected_name:
                t = k
                break
        if t and t != self._cmd_type:
            self._cmd_type = t
            # 切换类型时保留可复用参数，其余用默认
            new_cmd = C.make_command(t)
            self._data = new_cmd
            self._rebuild_params()

    # ------------------------------------------------------------------ 通用字段
    def _build_common(self):
        f = ctk.CTkFrame(self, fg_color="transparent")
        f.pack(fill="x", padx=16, pady=(0, 4))
        self._enabled_var = ctk.BooleanVar(value=self._data.get("enabled", True))
        ctk.CTkCheckBox(f, text="启用", variable=self._enabled_var).pack(side="left")
        ctk.CTkLabel(f, text="备注：").pack(side="left", padx=(16, 4))
        self._comment_var = ctk.StringVar(value=self._data.get("comment", ""))
        ctk.CTkEntry(f, textvariable=self._comment_var, width=200).pack(side="left")

    # ------------------------------------------------------------------ 参数区
    def _clear_params(self):
        for w in self._params_frame.winfo_children():
            w.destroy()
        self._widgets = {}

    def _rebuild_params(self):
        self._clear_params()
        t = self._cmd_type
        p = self._data.get("params", {})
        b = self._params_frame

        def row(label_text, widget):
            f = ctk.CTkFrame(b, fg_color="transparent")
            f.pack(fill="x", padx=8, pady=4)
            lbl = ctk.CTkLabel(f, text=label_text)
            lbl.pack(side="left", padx=(0, 8), anchor="e")
            widget.pack(side="left", fill="x", expand=True)
            return widget

        if t == C.KEY:
            v = ctk.StringVar(value=p.get("key", ""))
            e = ctk.CTkEntry(b, textvariable=v)
            self._widgets["key"] = v
            row("按键：", e)
            ctk.CTkLabel(b, text="（组合键用 + 连接，如 ctrl+s / ctrl+shift+s）",
                         text_color="gray").pack(anchor="w", padx=8, pady=(0, 4))
            hv = ctk.StringVar(value=str(p.get("hold", 0)))
            he = ctk.CTkEntry(b, textvariable=hv, width=100)
            self._widgets["hold"] = hv
            row("按住(秒,0为点按)：", he)

        elif t == C.CLICK:
            xv = ctk.StringVar(value=str(p.get("x", 0)))
            yv = ctk.StringVar(value=str(p.get("y", 0)))
            bv = ctk.StringVar(value=p.get("button", "left"))
            cv = ctk.StringVar(value=str(p.get("clicks", 1)))

            f1 = ctk.CTkFrame(b, fg_color="transparent")
            f1.pack(fill="x", padx=8, pady=4)
            ctk.CTkLabel(f1, text="X：").pack(side="left", padx=(0, 8))
            ctk.CTkEntry(f1, textvariable=xv, width=100).pack(side="left", padx=(0, 16))
            ctk.CTkLabel(f1, text="Y：").pack(side="left", padx=(0, 8))
            ctk.CTkEntry(f1, textvariable=yv, width=100).pack(side="left")
            self._widgets["x"] = xv
            self._widgets["y"] = yv

            f2 = ctk.CTkFrame(b, fg_color="transparent")
            f2.pack(fill="x", padx=8, pady=4)
            ctk.CTkLabel(f2, text="按键：").pack(side="left", padx=(0, 8))
            ctk.CTkOptionMenu(f2, variable=bv, values=C.MOUSE_BUTTONS, width=120).pack(side="left", padx=(0, 16))
            ctk.CTkLabel(f2, text="点击次数：").pack(side="left", padx=(0, 8))
            ctk.CTkEntry(f2, textvariable=cv, width=60).pack(side="left")
            self._widgets["button"] = bv
            self._widgets["clicks"] = cv

            ctk.CTkButton(b, text="拾取屏幕坐标", command=self._pick_pos).pack(anchor="w", padx=8, pady=4)

        elif t == C.IMAGE_CLICK:
            self._build_image_picker(p, with_click_opts=True)

        elif t == C.IMAGE_WAIT:
            self._build_image_picker(p, with_timeout=True)

        elif t == C.INPUT_TEXT:
            tv = ctk.StringVar(value=p.get("text", ""))
            iv = ctk.StringVar(value=str(p.get("interval", 0)))

            f = ctk.CTkFrame(b, fg_color="transparent")
            f.pack(fill="x", padx=8, pady=4)
            ctk.CTkLabel(f, text="文本：").pack(side="left", padx=(0, 8))
            ctk.CTkEntry(f, textvariable=tv).pack(side="left", fill="x", expand=True, padx=(0, 16))
            ctk.CTkLabel(f, text="字符间隔(秒)：").pack(side="left", padx=(0, 8))
            ctk.CTkEntry(f, textvariable=iv, width=60).pack(side="left")
            self._widgets["text"] = tv
            self._widgets["interval"] = iv

        elif t == C.DELAY:
            mv = ctk.StringVar(value=str(p.get("ms", 1000)))
            row("延时(毫秒)：", ctk.CTkEntry(b, textvariable=mv, width=120))
            self._widgets["ms"] = mv

        elif t == C.REPEAT:
            cv = ctk.StringVar(value=str(p.get("count", 3)))
            row("重复次数：", ctk.CTkEntry(b, textvariable=cv, width=100))
            self._widgets["count"] = cv
            ctk.CTkLabel(b, text="（需与“重复结束”配对使用）", text_color="gray").pack(anchor="w", padx=8, pady=(0, 4))

        elif t in (C.IF_IMAGE, C.IF_NOT_IMAGE):
            self._build_image_picker(p, condition=True)

        elif t == C.IF_WINDOW:
            tv = ctk.StringVar(value=p.get("title", ""))
            row("窗口标题：", ctk.CTkEntry(b, textvariable=tv))
            self._widgets["title"] = tv
            ctk.CTkLabel(b, text="（模糊匹配，包含该关键词即成立）", text_color="gray").pack(anchor="w", padx=8, pady=(0, 4))

        elif t == C.LABEL:
            nv = ctk.StringVar(value=p.get("name", "label1"))
            row("标签名：", ctk.CTkEntry(b, textvariable=nv))
            self._widgets["name"] = nv

        elif t == C.GOTO:
            opts = self.labels if self.labels else ["label1"]
            nv = ctk.StringVar(value=p.get("name", opts[0]))
            row("目标标签：", ctk.CTkOptionMenu(b, variable=nv, values=opts))
            self._widgets["name"] = nv

        elif t in (C.END_REPEAT, C.END_IF):
            ctk.CTkLabel(b, text="该指令无需参数", text_color="gray").pack(pady=20)

    def _build_image_picker(self, p, with_click_opts=False, with_timeout=False, condition=False):
        b = self._params_frame
        iv = ctk.StringVar(value=p.get("image", ""))
        self._widgets["image"] = iv

        def row(label_text, widget):
            f = ctk.CTkFrame(b, fg_color="transparent")
            f.pack(fill="x", padx=8, pady=4)
            ctk.CTkLabel(f, text=label_text).pack(side="left", padx=(0, 8))
            widget.pack(side="left", fill="x", expand=True)

        ent = ctk.CTkEntry(b, textvariable=iv)
        row("图片：", ent)

        bf = ctk.CTkFrame(b, fg_color="transparent")
        bf.pack(fill="x", padx=8, pady=2)
        ctk.CTkButton(bf, text="选择文件", width=100, command=lambda: self._pick_file(iv)).pack(side="left", padx=(0, 4))
        ctk.CTkButton(bf, text="截图区域", width=100, command=lambda: self._capture_region(iv)).pack(side="left")

        cv = ctk.StringVar(value=str(p.get("confidence", 0.8)))
        row("置信度(0~1)：", ctk.CTkEntry(b, textvariable=cv, width=100))
        self._widgets["confidence"] = cv

        if with_click_opts:
            bv = ctk.StringVar(value=p.get("button", "left"))
            clv = ctk.StringVar(value=str(p.get("clicks", 1)))

            f1 = ctk.CTkFrame(b, fg_color="transparent")
            f1.pack(fill="x", padx=8, pady=4)
            ctk.CTkLabel(f1, text="鼠标按键：").pack(side="left", padx=(0, 8))
            ctk.CTkOptionMenu(f1, variable=bv, values=C.MOUSE_BUTTONS, width=120).pack(side="left", padx=(0, 16))
            ctk.CTkLabel(f1, text="点击次数：").pack(side="left", padx=(0, 8))
            ctk.CTkEntry(f1, textvariable=clv, width=60).pack(side="left")
            self._widgets["button"] = bv
            self._widgets["clicks"] = clv

            f2 = ctk.CTkFrame(b, fg_color="transparent")
            f2.pack(fill="x", padx=8, pady=4)
            ctk.CTkLabel(f2, text="偏移X：").pack(side="left", padx=(0, 8))
            oxv = ctk.StringVar(value=str(p.get("offset_x", 0)))
            ctk.CTkEntry(f2, textvariable=oxv, width=80).pack(side="left", padx=(0, 16))
            ctk.CTkLabel(f2, text="偏移Y：").pack(side="left", padx=(0, 8))
            oyv = ctk.StringVar(value=str(p.get("offset_y", 0)))
            ctk.CTkEntry(f2, textvariable=oyv, width=80).pack(side="left")
            self._widgets["offset_x"] = oxv
            self._widgets["offset_y"] = oyv

        if with_timeout:
            tv = ctk.StringVar(value=str(p.get("timeout", 10)))
            row("超时(秒)：", ctk.CTkEntry(b, textvariable=tv, width=100))
            self._widgets["timeout"] = tv

    # ------------------------------------------------------------------ 选择器回调
    def _pick_file(self, var):
        path = filedialog.askopenfilename(
            filetypes=[("图片", "*.png *.jpg *.jpeg *.bmp"), ("所有文件", "*.*")])
        if path:
            var.set(path)

    def _capture_region(self, var):
        self.withdraw()
        try:
            from image_capture import RegionCapture
            path = RegionCapture().capture()
            if path:
                var.set(path)
        except Exception as e:
            messagebox.showerror("截图失败", str(e))
        finally:
            self.deiconify()
            self.focus_force()

    def _pick_pos(self):
        self.withdraw()
        try:
            from image_capture import pick_position
            pos = pick_position()
            if pos:
                self._widgets["x"].set(str(pos[0]))
                self._widgets["y"].set(str(pos[1]))
        except Exception as e:
            messagebox.showerror("拾取失败", str(e))
        finally:
            self.deiconify()
            self.focus_force()

    # ------------------------------------------------------------------ 确定/取消
    def _collect(self):
        t = self._cmd_type
        params = dict(C.PARAM_SCHEMA.get(t, {}))
        for key, var in self._widgets.items():
            val = var.get()
            # 类型转换
            if key in ("x", "y", "clicks", "ms", "count", "offset_x", "offset_y"):
                try:
                    params[key] = int(float(val))
                except Exception:
                    params[key] = 0
            elif key in ("hold", "confidence", "timeout", "interval"):
                try:
                    params[key] = float(val)
                except Exception:
                    params[key] = 0.0
            else:
                params[key] = val
        return {
            "type": t,
            "params": params,
            "enabled": self._enabled_var.get(),
            "comment": self._comment_var.get(),
        }

    def _ok(self):
        self.result = self._collect()
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


def edit_command(master, cmd=None, labels=None):
    """弹出编辑对话框，返回编辑后的命令或 None（取消）。"""
    dlg = CommandDialog(master, cmd=cmd, labels=labels)
    master.wait_window(dlg)
    return dlg.result
