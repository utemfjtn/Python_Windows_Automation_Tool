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
        super().__init__(master)
        self.title("编辑指令")
        self.geometry("500x560")
        self.resizable(False, True)
        self.transient(master)
        self.grab_set()

        self.result = None
        self.labels = labels or []
        self._widgets = {}
        self._row = 0

        if cmd is None:
            cmd = C.make_command(C.KEY)
        self._cmd_type = cmd["type"]
        self._data = {k: v for k, v in cmd.items()}

        self._build_type_selector()

        self._scroll_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._scroll_frame.pack(fill="both", expand=True, padx=16, pady=(4, 8))
        self._grid_parent = self._scroll_frame

        self._rebuild_params()

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=16, pady=(0, 12))
        ctk.CTkButton(btn_frame, text="取消", width=100,
                      command=self._cancel).pack(side="right", padx=(8, 0))
        ctk.CTkButton(btn_frame, text="确定", width=100,
                      command=self._ok).pack(side="right")

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.after(50, lambda: self.focus_force())

    def _build_type_selector(self):
        f = ctk.CTkFrame(self, fg_color="transparent")
        f.pack(fill="x", padx=16, pady=(12, 4))
        ctk.CTkLabel(f, text="指令类型：", width=80, anchor="e").pack(side="left")
        names = [C.TYPE_NAMES[t] for t in C.ALL_TYPES]
        cur = C.TYPE_NAMES[self._cmd_type]
        self._type_var = ctk.StringVar(value=cur)
        combo = ctk.CTkOptionMenu(
            f, variable=self._type_var, values=names,
            command=self._on_type_change, width=220)
        combo.pack(side="left", padx=8)

    def _on_type_change(self, selected_name):
        t = None
        for k, v in C.TYPE_NAMES.items():
            if v == selected_name:
                t = k
                break
        if t and t != self._cmd_type:
            self._cmd_type = t
            new_cmd = C.make_command(t)
            self._data = new_cmd
            self._rebuild_params()

    def _add_row(self, label_text, widget_cls, **kwargs):
        parent = self._grid_parent
        ctk.CTkLabel(parent, text=label_text, width=110, anchor="e").grid(
            row=self._row, column=0, sticky="e", pady=4, padx=(0, 8))
        widget = widget_cls(parent, **kwargs)
        widget.grid(row=self._row, column=1, sticky="ew", pady=4)
        self._row += 1
        return widget

    def _add_hint(self, text):
        ctk.CTkLabel(self._grid_parent, text=text, text_color="gray",
                     anchor="w").grid(row=self._row, column=1, sticky="w",
                                      padx=(0, 0), pady=(0, 4))
        self._row += 1

    def _add_button_row(self, *buttons):
        bf = ctk.CTkFrame(self._grid_parent, fg_color="transparent")
        bf.grid(row=self._row, column=1, sticky="w", pady=(0, 4))
        self._row += 1
        for i, btn in enumerate(buttons):
            text, cmd = btn
            pad = (0, 4) if i < len(buttons) - 1 else 0
            ctk.CTkButton(bf, text=text, width=90, command=cmd).pack(
                side="left", padx=pad)

    def _rebuild_params(self):
        for w in list(self._grid_parent.winfo_children()):
            w.destroy()
        self._widgets = {}
        self._row = 0

        self._build_common()

        t = self._cmd_type
        p = self._data.get("params", {})
        gp = self._grid_parent

        gp.grid_columnconfigure(1, weight=1)

        if t == C.KEY:
            v = ctk.StringVar(value=p.get("key", ""))
            self._widgets["key"] = v
            self._add_row("按键：", ctk.CTkEntry, textvariable=v)
            self._add_hint("组合键用 + 连接，如 ctrl+s / ctrl+shift+s")
            hv = ctk.StringVar(value=str(p.get("hold", 0)))
            self._widgets["hold"] = hv
            self._add_row("按住时间(秒)：", ctk.CTkEntry,
                          textvariable=hv, width=120)
            self._add_hint("0 表示点按，大于 0 表示按住指定秒数")

        elif t == C.CLICK:
            xv = ctk.StringVar(value=str(p.get("x", 0)))
            yv = ctk.StringVar(value=str(p.get("y", 0)))
            self._widgets["x"] = xv
            self._widgets["y"] = yv
            self._add_row("X 坐标：", ctk.CTkEntry, textvariable=xv, width=120)
            self._add_row("Y 坐标：", ctk.CTkEntry, textvariable=yv, width=120)
            bv = ctk.StringVar(value=p.get("button", "left"))
            self._widgets["button"] = bv
            self._add_row("鼠标按键：", ctk.CTkOptionMenu,
                          variable=bv, values=C.MOUSE_BUTTONS, width=120)
            cv = ctk.StringVar(value=str(p.get("clicks", 1)))
            self._widgets["clicks"] = cv
            self._add_row("点击次数：", ctk.CTkEntry, textvariable=cv, width=120)
            self._add_button_row(("拾取屏幕坐标", self._pick_pos))

        elif t == C.IMAGE_CLICK:
            self._build_image_picker(p, with_click_opts=True)

        elif t == C.IMAGE_WAIT:
            self._build_image_picker(p, with_timeout=True)

        elif t == C.INPUT_TEXT:
            tv = ctk.StringVar(value=p.get("text", ""))
            self._widgets["text"] = tv
            self._add_row("输入文本：", ctk.CTkEntry, textvariable=tv)
            iv = ctk.StringVar(value=str(p.get("interval", 0)))
            self._widgets["interval"] = iv
            self._add_row("字符间隔(秒)：", ctk.CTkEntry,
                          textvariable=iv, width=120)
            self._add_hint("每个字符之间的输入间隔，0 表示最快（剪贴板粘贴）")

        elif t == C.DELAY:
            mv = ctk.StringVar(value=str(p.get("ms", 1000)))
            self._widgets["ms"] = mv
            self._add_row("延时(毫秒)：", ctk.CTkEntry, textvariable=mv, width=120)
            self._add_hint("1000 毫秒 = 1 秒")

        elif t == C.REPEAT:
            cv = ctk.StringVar(value=str(p.get("count", 3)))
            self._widgets["count"] = cv
            self._add_row("重复次数：", ctk.CTkEntry, textvariable=cv, width=120)
            self._add_hint("需与「重复结束」指令配对使用")

        elif t in (C.IF_IMAGE, C.IF_NOT_IMAGE):
            self._build_image_picker(p, condition=True)

        elif t == C.IF_WINDOW:
            tv = ctk.StringVar(value=p.get("title", ""))
            self._widgets["title"] = tv
            self._add_row("窗口标题：", ctk.CTkEntry, textvariable=tv)
            self._add_hint("模糊匹配，窗口标题包含该关键词即成立")

        elif t == C.LABEL:
            nv = ctk.StringVar(value=p.get("name", "label1"))
            self._widgets["name"] = nv
            self._add_row("标签名：", ctk.CTkEntry, textvariable=nv)
            self._add_hint("供「跳转」指令引用，同一脚本中标签名不能重复")

        elif t == C.GOTO:
            opts = self.labels if self.labels else ["label1"]
            nv = ctk.StringVar(value=p.get("name", opts[0]))
            self._widgets["name"] = nv
            self._add_row("目标标签：", ctk.CTkOptionMenu,
                          variable=nv, values=opts)
            self._add_hint("跳转到指定标签处继续执行")

        elif t in (C.END_REPEAT, C.END_IF):
            ctk.CTkLabel(gp, text="该指令无需参数", text_color="gray").grid(
                row=self._row, column=0, columnspan=2, pady=20)
            self._row += 1

        ctk.CTkFrame(gp, height=8, fg_color="transparent").grid(
            row=self._row, column=0, columnspan=2)
        self._row += 1

    def _build_common(self):
        gp = self._grid_parent
        self._enabled_var = ctk.BooleanVar(value=self._data.get("enabled", True))
        ctk.CTkCheckBox(gp, text="启用", variable=self._enabled_var).grid(
            row=self._row, column=0, sticky="w", pady=(4, 8))
        self._row += 1

        ctk.CTkLabel(gp, text="备注：", width=110, anchor="e").grid(
            row=self._row, column=0, sticky="e", pady=4, padx=(0, 8))
        self._comment_var = ctk.StringVar(value=self._data.get("comment", ""))
        ctk.CTkEntry(gp, textvariable=self._comment_var).grid(
            row=self._row, column=1, sticky="ew", pady=4)
        self._row += 1

        sep = ctk.CTkFrame(gp, height=2)
        sep.grid(row=self._row, column=0, columnspan=2, sticky="ew",
                 pady=(4, 8))
        self._row += 1

    def _build_image_picker(self, p, with_click_opts=False, with_timeout=False, condition=False):
        gp = self._grid_parent
        iv = ctk.StringVar(value=p.get("image", ""))
        self._widgets["image"] = iv

        self._add_row("图片路径：", ctk.CTkEntry, textvariable=iv)
        self._add_button_row(
            ("选择文件", lambda: self._pick_file(iv)),
            ("截图区域", lambda: self._capture_region(iv)),
        )

        cv = ctk.StringVar(value=str(p.get("confidence", 0.8)))
        self._widgets["confidence"] = cv
        self._add_row("置信度(0~1)：", ctk.CTkEntry,
                      textvariable=cv, width=120)
        self._add_hint("数值越高匹配越严格，建议 0.7~0.9")

        if with_click_opts:
            bv = ctk.StringVar(value=p.get("button", "left"))
            self._widgets["button"] = bv
            self._add_row("鼠标按键：", ctk.CTkOptionMenu,
                          variable=bv, values=C.MOUSE_BUTTONS, width=120)
            clv = ctk.StringVar(value=str(p.get("clicks", 1)))
            self._widgets["clicks"] = clv
            self._add_row("点击次数：", ctk.CTkEntry,
                          textvariable=clv, width=120)
            oxv = ctk.StringVar(value=str(p.get("offset_x", 0)))
            oyv = ctk.StringVar(value=str(p.get("offset_y", 0)))
            self._widgets["offset_x"] = oxv
            self._widgets["offset_y"] = oyv
            self._add_row("偏移 X：", ctk.CTkEntry,
                          textvariable=oxv, width=120)
            self._add_row("偏移 Y：", ctk.CTkEntry,
                          textvariable=oyv, width=120)
            self._add_hint("相对于图片中心的偏移像素，正数向右/下")

        if with_timeout:
            tv = ctk.StringVar(value=str(p.get("timeout", 10)))
            self._widgets["timeout"] = tv
            self._add_row("超时(秒)：", ctk.CTkEntry,
                          textvariable=tv, width=120)
            self._add_hint("等待超过该时间仍未出现图片则继续向下执行")

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

    def _collect(self):
        t = self._cmd_type
        params = dict(C.PARAM_SCHEMA.get(t, {}))
        for key, var in self._widgets.items():
            val = var.get()
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
    dlg = CommandDialog(master, cmd=cmd, labels=labels)
    master.wait_window(dlg)
    return dlg.result
