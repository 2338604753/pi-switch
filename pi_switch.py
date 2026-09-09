# -*- coding: utf-8 -*-
"""
Pi-switch
=========
一个为 pi coding agent 设计的小工具 (类似 ccswitch)。
用于快速切换不同的模型 / API Key / BaseUrl，把配置一键写入 pi 的配置文件。

支持的 pi 配置文件 (位于 ~/.pi/agent 下):
  - settings.json  : defaultProvider / defaultModel (启动时用的模型)
  - models.json    : 自定义 provider (含 baseUrl / api / apiKey / models)
  - auth.json      : 内置 provider 的 API key (openai, anthropic, opencode 等)

用法:
  1. 用左侧列表管理和切换"配置文件(profile)"(支持"批量导入"把已有 provider 一次性导入)。
  2. 在右侧表单里编辑某个 profile 的名称 / provider / 地址 / key / 模型 / 思考等级等。
  3. 点 [激活] 会备份并写入 pi 的配置文件；下次启动 pi (或 /model) 生效。

运行:  python pi_switch.py   (或直接双击 启动Pi-switch.bat)
"""

import os
import sys
import copy
import ssl
import json
import shutil
import datetime
import traceback
import threading
import urllib.request
import urllib.error
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# ---------------------------------------------------------------------------
# 路径常量
# ---------------------------------------------------------------------------
AGENT_DIR = os.path.join(os.path.expanduser("~"), ".pi", "agent")
SETTINGS_PATH = os.path.join(AGENT_DIR, "settings.json")
AUTH_PATH = os.path.join(AGENT_DIR, "auth.json")
MODELS_PATH = os.path.join(AGENT_DIR, "models.json")

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
# 若被打包成 PyInstaller exe(_MEIPASS/临时目录)，则把配置写到 exe 旁边，保证能持久保存
if getattr(sys, "frozen", False):
    CURRENT_DIR = os.path.dirname(os.path.abspath(sys.executable))
PROFILES_PATH = os.path.join(CURRENT_DIR, "profiles.json")
BACKUP_DIR = os.path.join(CURRENT_DIR, "backup")

API_CHOICES = [
    "openai-completions",
    "openai-responses",
    "anthropic-messages",
    "google-generative-ai",
]

THINKING_LEVELS = ["off", "minimal", "low", "medium", "high", "xhigh", "max"]

MODEL_TEMPLATE = '[{"id": "my-model", "name": "My Model", "reasoning": false, "input": ["text", "image"]}]'
COMPAT_TEMPLATE = "{}"

# 部分服务商(如 pdai.hi66.cc)用 Cloudflare 按浏览器 User-Agent 拦截非浏览器请求，
# 所以这里伪装成 Chrome，否则 /models 或测试请求会被 403(Error 1010) 拦掉。
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


# ---------------------------------------------------------------------------
# 主题配色：黑色风格 / 白色风格 (极简黑白，无彩色干扰)
# ---------------------------------------------------------------------------
THEMES = {
    "black": {
        "name": "黑色",
        "bg": "#0b0b0d",              # 主背景 (近黑)
        "bg_header": "#000000",       # 顶部标题栏
        "bg_button": "#1c1c1f",       # 按钮背景
        "bg_button_hover": "#2a2a2e",
        "bg_button_pressed": "#333338",
        "bg_input": "#151518",        # 输入框背景
        "border": "#2c2c31",          # 边框
        "accent": "#eaeaec",          # 主色 (白)
        "accent_hover": "#ffffff",
        "accent_pressed": "#cfcfd4",
        "on_accent": "#0b0b0d",       # 主色上的文字
        "text": "#f4f4f6",            # 主文字
        "text_dim": "#8b8b92",        # 次要文字
        "success": "#4ade80",
        "danger": "#f87171",
        "warning": "#fbbf24",
    },
    "white": {
        "name": "白色",
        "bg": "#f4f5f7",              # 主背景 (浅灰)
        "bg_header": "#ffffff",       # 顶部标题栏
        "bg_button": "#e9eaee",       # 按钮背景
        "bg_button_hover": "#dcdee3",
        "bg_button_pressed": "#cfd2d8",
        "bg_input": "#ffffff",        # 输入框背景
        "border": "#d2d6dc",          # 边框
        "accent": "#16181d",          # 主色 (黑)
        "accent_hover": "#2a2d34",
        "accent_pressed": "#000000",
        "on_accent": "#ffffff",       # 主色上的文字
        "text": "#1c1f26",            # 主文字
        "text_dim": "#6b7280",        # 次要文字
        "success": "#16a34a",
        "danger": "#dc2626",
        "warning": "#d97706",
    },
}


def theme_palette(name):
    """返回名为 name 的主题配色字典。"""
    return THEMES.get(name, THEMES["black"])



# ---------------------------------------------------------------------------
# JSON 读写小工具
# ---------------------------------------------------------------------------
def read_json(path, default):
    """安全读取 JSON，失败返回 default。"""
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path, data):
    """写入 JSON (格式化、UTF-8)。"""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def backup_file(path):
    """备份某个配置文件到 backup 目录，带时间戳。"""
    if not os.path.exists(path):
        return None
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        name = os.path.basename(path)
        dest = os.path.join(BACKUP_DIR, f"{stamp}_{name}")
        shutil.copy2(path, dest)
        return dest
    except Exception:
        return None


def parse_json_text(text):
    """解析文本框里的 JSON，出错抛出 ValueError。"""
    text = text.strip()
    if not text:
        return None
    return json.loads(text)


def resource_path(name):
    """返回资源文件的绝对路径（兼容源码运行 & PyInstaller 打包后的 exe）。
    PyInstaller onefile 会把 --add-data 的资源解压到 sys._MEIPASS。
    """
    base = getattr(sys, "_MEIPASS", None)
    if base is None:
        base = CURRENT_DIR
    return os.path.join(base, name)


# ---------------------------------------------------------------------------
# 主程序窗口
# ---------------------------------------------------------------------------
class PiSwitchApp:
    def __init__(self, root):
        self.root = root
        self.root.title("pi-switch")
        self.root.minsize(920, 620)
        # 先设尺寸再居中，打开时正好在屏幕正中间
        self.root.geometry("1080x720")

        self.profiles = read_json(PROFILES_PATH, {"version": 1, "active": None, "profiles": {}})
        self.profiles.setdefault("version", 1)
        self.profiles.setdefault("active", None)
        self.profiles.setdefault("profiles", {})
        # 恢复上次使用的主题 (默认黑色)
        self.current_theme = self.profiles.get("theme", "black")
        if self.current_theme not in THEMES:
            self.current_theme = "black"

        self._apply_theme()
        self.root.update_idletasks()
        PiSwitchApp._center_window(self.root)

        # 当前正在编辑的 profile id (None 表示"新建")
        self.editing_id = None

        self._build_ui()
        self._refresh_list()

        if self.profiles.get("active"):
            self._select_profile(self.profiles["active"])
        else:
            self._capture_current_provider()

    # ------------------------------------------------------------------
    # 现代化主题 (Catppuccin Mocha 风)
    # ------------------------------------------------------------------
    def _apply_theme(self):
        self._theme = theme_palette(self.current_theme)
        C = self._theme
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        # ---- 基础 ----
        style.configure(".", background=C["bg"], foreground=C["text"])
        style.configure("TFrame", background=C["bg"])
        style.configure("TLabel", background=C["bg"], foreground=C["text"])
        style.configure("TLabelframe", background=C["bg"], bordercolor=C["border"])
        style.configure("TLabelframe.Label", background=C["bg"], foreground=C["text"])
        style.configure("TPanedwindow", background=C["bg"], sashwidth=6)

        # ---- 标题 / 次要文字 ----
        style.configure("Title.TLabel", background=C["bg"], foreground=C["text"],
                        font=("Segoe UI", 12, "bold"))
        style.configure("Section.TLabel", background=C["bg"], foreground=C["accent"],
                        font=("Segoe UI", 11, "bold"))
        style.configure("Dim.TLabel", background=C["bg"], foreground=C["text_dim"],
                        font=("Segoe UI", 8))

        # ---- 按钮 ----
        style.configure("TButton", background=C["bg_button"], foreground=C["text"],
                        borderwidth=0, relief="flat", focusthickness=0,
                        padding=(10, 6), font=("Segoe UI", 9))
        style.map("TButton",
                  background=[("pressed", C["bg_button_pressed"]),
                              ("active", C["bg_button_hover"])],
                  foreground=[("disabled", C["text_dim"])])

        style.configure("Accent.TButton", background=C["accent"], foreground=C["on_accent"],
                        borderwidth=0, relief="flat", focusthickness=0,
                        padding=(12, 6), font=("Segoe UI", 9, "bold"))
        style.map("Accent.TButton",
                  background=[("pressed", C["accent_pressed"]),
                              ("active", C["accent_hover"])],
                  foreground=[("disabled", C["text_dim"])])

        # ---- 输入框 ----
        style.configure("TEntry", fieldbackground=C["bg_input"], foreground=C["text"],
                        insertcolor=C["text"], bordercolor=C["border"],
                        lightcolor=C["bg_input"], darkcolor=C["bg_input"],
                        padding=4)
        style.map("TEntry",
                  bordercolor=[("focus", C["accent"])],
                  lightcolor=[("focus", C["accent"])],
                  darkcolor=[("focus", C["accent"])])

        style.configure("TCombobox", fieldbackground=C["bg_input"], background=C["bg_button"],
                        foreground=C["text"], arrowcolor=C["text"],
                        bordercolor=C["border"], padding=4, insertcolor=C["text"])
        style.map("TCombobox",
                  fieldbackground=[("readonly", C["bg_input"])],
                  bordercolor=[("focus", C["accent"])],
                  arrowcolor=[("active", C["accent"])])

        # ---- 单选 / 复选 ----
        style.configure("TRadiobutton", background=C["bg"], foreground=C["text"])
        style.map("TRadiobutton", background=[("active", C["bg"])],
                  foreground=[("active", C["text"])])
        style.configure("TCheckbutton", background=C["bg"], foreground=C["text"])
        style.map("TCheckbutton", background=[("active", C["bg"])])

        # ---- 滚动条 ----
        style.configure("Vertical.TScrollbar", background=C["bg_button"],
                        troughcolor=C["bg"], bordercolor=C["bg"], arrowcolor=C["text"])
        style.configure("Horizontal.TScrollbar", background=C["bg_button"],
                        troughcolor=C["bg"], bordercolor=C["bg"], arrowcolor=C["text"])

        # ---- 将主题同步到已创建的 tk 控件 / 窗口 ----
        self.root.configure(bg=C["bg"])
        if hasattr(self, "_header_frame"):
            self._header_frame.configure(bg=C["bg_header"])
        if hasattr(self, "_header_title_box"):
            self._header_title_box.configure(bg=C["bg_header"])
        if hasattr(self, "_header_title"):
            self._header_title.configure(bg=C["bg_header"], fg=C["text"])
        if hasattr(self, "_header_subtitle"):
            self._header_subtitle.configure(bg=C["bg_header"], fg=C["text_dim"])
        if hasattr(self, "_header_status"):
            self._header_status.configure(bg=C["bg_header"], fg=C["text_dim"])
        if hasattr(self, "_header_divider"):
            self._header_divider.configure(bg=C["border"])
        if hasattr(self, "_theme_btn"):
            self._update_theme_btn()
        if hasattr(self, "listbox"):
            self.listbox.configure(bg=C["bg_input"], fg=C["text"],
                                   selectbackground=C["accent"], selectforeground=C["on_accent"])
        if hasattr(self, "txt_models"):
            self.txt_models.configure(bg=C["bg_input"], fg=C["text"], insertbackground=C["text"],
                                      selectbackground=C["accent"], selectforeground=C["on_accent"])
        if hasattr(self, "txt_compat"):
            self.txt_compat.configure(bg=C["bg_input"], fg=C["text"], insertbackground=C["text"],
                                      selectbackground=C["accent"], selectforeground=C["on_accent"])

    def _toggle_theme(self):
        """在 黑色 / 白色 主题间切换。"""
        self.current_theme = "white" if self.current_theme == "black" else "black"
        self._apply_theme()
        self._save_profiles()

    def _update_theme_btn(self):
        """更新主题切换按钮文案。"""
        if not hasattr(self, "_theme_btn"):
            return
        if self.current_theme == "black":
            self._theme_btn.configure(text="☀ 白色")
        else:
            self._theme_btn.configure(text="🌙 黑色")

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------
    def _build_ui(self):
        # 顶部标题栏
        C = self._theme
        self._header_frame = tk.Frame(self.root, bg=C["bg_header"], padx=16, pady=10)
        self._header_frame.pack(side="top", fill="x")
        bt = ttk.Button(self._header_frame, text="刷新当前配置", command=self._refresh_status, width=14)
        bt.pack(side="right")
        self._theme_btn = ttk.Button(self._header_frame, width=10, command=self._toggle_theme)
        self._theme_btn.pack(side="right", padx=6)
        self.status_var = tk.StringVar(value="查看当前激活配置…")
        self._header_status = tk.Label(self._header_frame, textvariable=self.status_var,
                                       bg=C["bg_header"], fg=C["text_dim"],
                                       font=("Segoe UI", 9), anchor="e")
        self._header_status.pack(side="right", padx=10)
        self._header_title_box = tk.Frame(self._header_frame, bg=C["bg_header"])
        self._header_title_box.pack(side="left", fill="x", expand=True)
        self._header_title = tk.Label(self._header_title_box, text="pi-switch", bg=C["bg_header"], fg=C["text"],
                                      font=("Segoe UI", 18, "bold"), anchor="w")
        self._header_title.pack(anchor="w")
        self._header_subtitle = tk.Label(self._header_title_box, text="pi 模型 · API Key · Base URL 一键切换",
                                         bg=C["bg_header"], fg=C["text_dim"],
                                         font=("Segoe UI", 9), anchor="w")
        self._header_subtitle.pack(anchor="w", pady=(2, 0))
        self._update_theme_btn()

        # 标题栏与内容之间的分隔线
        self._header_divider = tk.Frame(self.root, bg=C["border"], height=1)
        self._header_divider.pack(side="top", fill="x")

        # 主分栏
        paned = ttk.PanedWindow(self.root, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=8, pady=8)

        # ---- 左侧列表 ----
        left = ttk.Frame(paned)
        paned.add(left, weight=1)

        ttk.Label(left, text="配置文件列表", style="Section.TLabel").pack(anchor="w", padx=6, pady=(4, 6))
        lf = ttk.Frame(left)
        lf.pack(fill="both", expand=True, padx=6)
        self.listbox = tk.Listbox(lf, activestyle="none", font=("Consolas", 10), exportselection=False,
                                  bg=C["bg_input"], fg=C["text"], relief="flat", bd=0,
                                  highlightthickness=0,
                                  selectbackground=C["accent"], selectforeground=C["on_accent"])
        sb = ttk.Scrollbar(lf, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=sb.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.listbox.bind("<<ListboxSelect>>", self._on_list_select)

        btns = ttk.Frame(left)
        btns.pack(fill="x", padx=6, pady=6)
        ttk.Button(btns, text="新建", command=self._new_profile, width=7).grid(row=0, column=0, padx=2)
        ttk.Button(btns, text="复制", command=self._copy_selected, width=7).grid(row=0, column=1, padx=2)
        ttk.Button(btns, text="删除", command=self._delete_selected, width=7).grid(row=0, column=2, padx=2)
        ttk.Button(btns, text="激活", command=self._activate_selected, width=23, style="Accent.TButton").grid(row=1, column=0, columnspan=3, sticky="ew", padx=2, pady=(6, 0))
        ttk.Button(btns, text="导入当前", command=self._capture_current_provider, width=9).grid(row=2, column=0, columnspan=2, sticky="ew", padx=2, pady=(4, 0))
        ttk.Button(btns, text="备份管理", command=self._open_backup_dir, width=9).grid(row=2, column=2, sticky="ew", padx=2, pady=(4, 0))
        ttk.Button(btns, text="批量导入", command=self._import_all, width=9).grid(row=3, column=0, columnspan=2, sticky="ew", padx=2, pady=(4, 0))
        ttk.Button(btns, text="打开配置", command=self._open_config_menu, width=9).grid(row=3, column=2, sticky="ew", padx=2, pady=(4, 0))

        # ---- 右侧表单 ----
        right = ttk.Frame(paned)
        paned.add(right, weight=3)

        form = ttk.Frame(right)
        form.pack(fill="both", expand=True, padx=10, pady=6)
        form.columnconfigure(1, weight=1)

        r = 0
        ttk.Label(form, text="名称 (Name)", font=("Segoe UI", 9, "bold")).grid(row=r, column=0, sticky="w", pady=3)
        self.e_name = ttk.Entry(form)
        self.e_name.grid(row=r, column=1, sticky="ew", pady=3)
        r += 1

        ttk.Label(form, text="Provider ID", font=("Segoe UI", 9, "bold")).grid(row=r, column=0, sticky="w", pady=3)
        self.e_provider = ttk.Entry(form)
        self.e_provider.grid(row=r, column=1, sticky="ew", pady=3)
        r += 1

        ttk.Label(form, text="类型 (Kind)", font=("Segoe UI", 9, "bold")).grid(row=r, column=0, sticky="w", pady=3)
        kindf = ttk.Frame(form)
        kindf.grid(row=r, column=1, sticky="w", pady=3)
        self.kind_var = tk.StringVar(value="custom")
        ttk.Radiobutton(kindf, text="自定义 provider (写 models.json)", value="custom", variable=self.kind_var, command=self._toggle_kind).pack(side="left")
        ttk.Radiobutton(kindf, text="内置 provider (写 auth.json)", value="builtin", variable=self.kind_var, command=self._toggle_kind).pack(side="left", padx=8)
        r += 1

        ttk.Label(form, text="Base URL", font=("Segoe UI", 9, "bold")).grid(row=r, column=0, sticky="w", pady=3)
        self.e_baseurl = ttk.Entry(form)
        self.e_baseurl.grid(row=r, column=1, sticky="ew", pady=3)
        r += 1

        ttk.Label(form, text="API 类型", font=("Segoe UI", 9, "bold")).grid(row=r, column=0, sticky="w", pady=3)
        self.cb_api = ttk.Combobox(form, values=API_CHOICES, state="readonly")
        self.cb_api.set(API_CHOICES[0])
        self.cb_api.grid(row=r, column=1, sticky="ew", pady=3)
        r += 1

        ttk.Label(form, text="API Key", font=("Segoe UI", 9, "bold")).grid(row=r, column=0, sticky="w", pady=3)
        kf = ttk.Frame(form)
        kf.grid(row=r, column=1, sticky="ew", pady=3)
        kf.columnconfigure(0, weight=1)
        self.e_key = ttk.Entry(kf, show="*")
        self.e_key.grid(row=0, column=0, sticky="ew")
        self.key_visible = False
        ttk.Button(kf, text="显示", width=5, command=self._toggle_key_visibility).grid(row=0, column=1, padx=4)
        r += 1

        ttk.Label(form, text="默认模型 (defaultModel)", font=("Segoe UI", 9, "bold")).grid(row=r, column=0, sticky="w", pady=3)
        mf = ttk.Frame(form)
        mf.grid(row=r, column=1, sticky="ew", pady=3)
        mf.columnconfigure(0, weight=1)
        self.cb_model = ttk.Combobox(mf, state="normal")
        self.cb_model.grid(row=0, column=0, sticky="ew")
        ttk.Button(mf, text="↻ 从模型列表刷新", width=16, command=self._refresh_model_dropdown).grid(row=0, column=1, padx=4)
        r += 1

        ttk.Label(form, text="思考等级 (thinking)", font=("Segoe UI", 9, "bold")).grid(row=r, column=0, sticky="w", pady=3)
        self.cb_thinking = ttk.Combobox(form, values=THINKING_LEVELS, state="normal", width=10)
        self.cb_thinking.set("")
        self.cb_thinking.grid(row=r, column=1, sticky="w", pady=3)
        ttk.Label(form, text="(可选，写 defaultThinkingLevel；留空则不改)", style="Dim.TLabel").grid(row=r, column=1, sticky="e", padx=4)
        r += 1

        # 模型列表 (JSON)
        mlf = ttk.Frame(form)
        mlf.grid(row=r, column=0, columnspan=2, sticky="ew", pady=(6, 2))
        mlf.columnconfigure(0, weight=1)
        ttk.Label(mlf, text="模型列表 (JSON)", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(mlf, text="(用上方 Key/BaseUrl 一键获取)", style="Dim.TLabel").grid(row=0, column=1, sticky="w", padx=8)
        ttk.Button(mlf, text="⚙ 获取模型", command=self._open_fetch_models, width=12).grid(row=0, column=2, sticky="e")
        r += 1
        modelf = ttk.Frame(form)
        modelf.grid(row=r, column=0, columnspan=2, sticky="nsew")
        form.rowconfigure(r, weight=3)
        modelf.columnconfigure(0, weight=1)
        self.txt_models = tk.Text(modelf, height=8, font=("Consolas", 9), wrap="none", undo=True,
                                  bg=C["bg_input"], fg=C["text"], insertbackground=C["text"],
                                  selectbackground=C["accent"], selectforeground=C["on_accent"],
                                  relief="flat", bd=0, highlightthickness=0)
        sm = ttk.Scrollbar(modelf, orient="vertical", command=self.txt_models.yview)
        self.txt_models.configure(yscrollcommand=sm.set)
        self.txt_models.grid(row=0, column=0, sticky="nsew")
        sm.grid(row=0, column=1, sticky="ns")
        r += 1

        # 兼容设置 (JSON)
        ttk.Label(form, text="兼容设置 compat (JSON, 可选)", font=("Segoe UI", 9, "bold")).grid(row=r, column=0, sticky="nw", pady=(6, 2))
        r += 1
        compatf = ttk.Frame(form)
        compatf.grid(row=r, column=0, columnspan=2, sticky="nsew")
        form.rowconfigure(r, weight=1)
        compatf.columnconfigure(0, weight=1)
        self.txt_compat = tk.Text(compatf, height=4, font=("Consolas", 9), wrap="none", undo=True,
                                  bg=C["bg_input"], fg=C["text"], insertbackground=C["text"],
                                  selectbackground=C["accent"], selectforeground=C["on_accent"],
                                  relief="flat", bd=0, highlightthickness=0)
        sc = ttk.Scrollbar(compatf, orient="vertical", command=self.txt_compat.yview)
        self.txt_compat.configure(yscrollcommand=sc.set)
        self.txt_compat.grid(row=0, column=0, sticky="nsew")
        sc.grid(row=0, column=1, sticky="ns")
        r += 1

        # 底栏按钮
        act = ttk.Frame(form)
        act.grid(row=r, column=0, columnspan=2, sticky="ew", pady=(10, 4))
        ttk.Button(act, text="保存配置 (Save)", command=self._save_editing, width=18).pack(side="left", padx=2)
        ttk.Button(act, text="激活并应用 (Activate)", command=self._activate_editing, width=22, style="Accent.TButton").pack(side="left", padx=2)
        ttk.Button(act, text="重置", command=self._reset_form, width=10).pack(side="right", padx=2)

        self._refresh_status()

    # ------------------------------------------------------------------
    # 状态栏
    # ------------------------------------------------------------------
    def _refresh_status(self):
        st = read_json(SETTINGS_PATH, {})
        provider = st.get("defaultProvider", "?")
        model = st.get("defaultModel", "?")
        active = self.profiles.get("active")
        active_name = ""
        if active and active in self.profiles["profiles"]:
            active_name = self.profiles["profiles"][active].get("name", active)
        self.status_var.set(
            f"当前 pi 激活: {provider} / {model}"
            + (f"    (对应 profile: {active_name})" if active_name else "")
        )

    def _open_backup_dir(self):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        try:
            if sys.platform == "win32":
                os.startfile(BACKUP_DIR)  # type: ignore
            else:
                import subprocess
                subprocess.Popen(["xdg-open", BACKUP_DIR])
        except Exception as e:
            messagebox.showinfo("备份目录", f"{BACKUP_DIR}\n\n(无法自动打开: {e})")

    # ------------------------------------------------------------------
    # 左侧列表
    # ------------------------------------------------------------------
    def _refresh_list(self):
        self.listbox.delete(0, tk.END)
        self._id_by_index = {}
        active = self.profiles.get("active")
        for i, (pid, prof) in enumerate(self.profiles["profiles"].items()):
            name = prof.get("name") or pid
            mark = "● " if pid == active else "   "
            self.listbox.insert(tk.END, f"{mark}{name}   [{pid}]")
            self._id_by_index[i] = pid

    def _on_list_select(self, _event=None):
        sel = self.listbox.curselection()
        if not sel:
            return
        pid = self._id_by_index.get(sel[0])
        if pid:
            self._select_profile(pid)

    def _select_profile(self, pid):
        prof = self.profiles["profiles"].get(pid)
        if not prof:
            return
        self.editing_id = pid
        self._fill_form(prof)

    def _fill_form(self, prof):
        self.e_name.delete(0, tk.END); self.e_name.insert(0, prof.get("name", ""))
        self.e_provider.delete(0, tk.END); self.e_provider.insert(0, prof.get("providerId", ""))
        self.kind_var.set(prof.get("kind", "custom"))
        self.e_baseurl.delete(0, tk.END); self.e_baseurl.insert(0, prof.get("baseUrl", ""))
        self.cb_api.set(prof.get("api", API_CHOICES[0]))
        self.e_key.delete(0, tk.END); self.e_key.insert(0, prof.get("apiKey", ""))
        self.cb_model.set(prof.get("defaultModel", ""))
        self.cb_thinking.set(prof.get("defaultThinkingLevel", ""))
        models = prof.get("models")
        self.txt_models.delete("1.0", tk.END)
        if models:
            self.txt_models.insert("1.0", json.dumps(models, ensure_ascii=False, indent=2))
        else:
            self.txt_models.insert("1.0", MODEL_TEMPLATE)
        compat = prof.get("compat")
        self.txt_compat.delete("1.0", tk.END)
        if compat:
            self.txt_compat.insert("1.0", json.dumps(compat, ensure_ascii=False, indent=2))
        else:
            self.txt_compat.insert("1.0", COMPAT_TEMPLATE)
        self._toggle_kind()
        self._refresh_model_dropdown()

    def _reset_form(self):
        self.editing_id = None
        self.e_name.delete(0, tk.END)
        self.e_provider.delete(0, tk.END)
        self.kind_var.set("custom")
        self.e_baseurl.delete(0, tk.END)
        self.cb_api.set(API_CHOICES[0])
        self.e_key.delete(0, tk.END)
        self.cb_model.set("")
        self.cb_thinking.set("")
        self.txt_models.delete("1.0", tk.END); self.txt_models.insert("1.0", MODEL_TEMPLATE)
        self.txt_compat.delete("1.0", tk.END); self.txt_compat.insert("1.0", COMPAT_TEMPLATE)
        self._toggle_kind()

    def _toggle_key_visibility(self):
        self.key_visible = not self.key_visible
        self.e_key.configure(show="" if self.key_visible else "*")

    def _toggle_kind(self):
        kind = self.kind_var.get()
        state = "normal" if kind == "custom" else "disabled"
        self.e_baseurl.configure(state=state)
        self.cb_api.configure(state="readonly" if kind == "custom" else "disabled")
        self.txt_models.configure(state=state or "disabled")
        self.txt_compat.configure(state=state or "disabled")

    def _refresh_model_dropdown(self):
        try:
            models = parse_json_text(self.txt_models.get("1.0", tk.END))
            ids = [m.get("id") for m in models if isinstance(m, dict) and m.get("id")]
        except Exception:
            ids = []
        self.cb_model.configure(values=ids)

    # ------------------------------------------------------------------
    # 采集表单 -> 字典
    # ------------------------------------------------------------------
    def _collect_form(self):
        kind = self.kind_var.get()
        prof = {
            "name": self.e_name.get().strip() or self.e_provider.get().strip() or "未命名",
            "providerId": self.e_provider.get().strip(),
            "kind": kind,
        }
        # 自定义
        if kind == "custom":
            prof["baseUrl"] = self.e_baseurl.get().strip()
            prof["api"] = self.cb_api.get().strip() or API_CHOICES[0]
            models = self._clean_models(parse_json_text(self.txt_models.get("1.0", tk.END)))
            if models:
                prof["models"] = models
            compat = parse_json_text(self.txt_compat.get("1.0", tk.END))
            if compat is not None:
                prof["compat"] = compat
        # 通用
        prof["apiKey"] = self.e_key.get().strip()
        default_model = self.cb_model.get().strip()
        if default_model and default_model != "my-model":
            prof["defaultModel"] = default_model
        thinking = self.cb_thinking.get().strip()
        if thinking:
            prof["defaultThinkingLevel"] = thinking
        return prof

    # ------------------------------------------------------------------
    # 新建 / 保存 / 删除
    # ------------------------------------------------------------------
    def _new_profile(self):
        self.editing_id = None
        self._reset_form()
        # 预填唯一 provider id
        base = "provider"
        pid = base
        n = 1
        while pid in self.profiles["profiles"]:
            n += 1
            pid = f"{base}{n}"
        self.e_provider.insert(0, pid)
        self.e_name.insert(0, pid)
        self.e_provider.focus_set()

    def _save_with_id(self, pid):
        try:
            prof = self._collect_form()
        except ValueError as e:
            messagebox.showerror("JSON 错误", f"模型列表或 compat 不是合法 JSON：\n\n{e}")
            return False
        if not prof["providerId"]:
            messagebox.showerror("缺少字段", "Provider ID 不能为空。")
            return False
        if prof["kind"] == "custom" and prof.get("baseUrl"):
            if not prof["baseUrl"].startswith(("http://", "https://")):
                messagebox.showerror("字段错误", "Base URL 需要以 http:// 或 https:// 开头。")
                return False
        if not prof.get("apiKey"):
            if not messagebox.askyesno("提示", "API Key 为空，仍要保存吗？"):
                return False
        self.profiles["profiles"][pid] = prof
        self._save_profiles()
        self._refresh_list()
        # 选中刚保存
        for i, p in enumerate(self._id_by_index.values()):
            if p == pid:
                self.listbox.selection_clear(0, tk.END)
                self.listbox.selection_set(i)
                break
        return True

    def _save_editing(self):
        if self.editing_id is None:
            # 新建：用 providerId 作为 id
            pid = self.e_provider.get().strip()
            if not pid:
                messagebox.showerror("缺少字段", "请先填写 Provider ID。")
                return
            if pid in self.profiles["profiles"]:
                messagebox.showerror("重复", f"已存在 Provider ID 为 {pid} 的配置。")
                return
            self.editing_id = pid
        if self._save_with_id(self.editing_id):
            messagebox.showinfo("已保存", f"已保存配置：{self.editing_id}")
            self._refresh_status()

    def _delete_selected(self):
        sel = self.listbox.curselection()
        if not sel:
            messagebox.showinfo("提示", "请先在左侧选择一个配置。")
            return
        pid = self._id_by_index[sel[0]]
        prof = self.profiles["profiles"].get(pid, {})
        if not messagebox.askyesno("确认删除", f"删除配置「{prof.get('name', pid)}」？"):
            return
        del self.profiles["profiles"][pid]
        if self.profiles.get("active") == pid:
            self.profiles["active"] = None
        self._save_profiles()
        self.editing_id = None
        self._reset_form()
        self._refresh_list()
        self._refresh_status()

    def _save_profiles(self):
        self.profiles["theme"] = self.current_theme
        write_json(PROFILES_PATH, self.profiles)

    # ------------------------------------------------------------------
    # 激活 (写入 pi 配置)
    # ------------------------------------------------------------------
    def _do_activate(self, pid, prof):
        """把 profile 写入 pi 配置文件，返回错误列表。"""
        errors = []
        kind = prof.get("kind", "custom")
        provider = prof.get("providerId")
        if not provider:
            return ["Provider ID 为空，无法激活。"]

        # 确保 pi 配置目录存在（对方可能还没运行过 pi，目录不存在会写失败）
        try:
            os.makedirs(AGENT_DIR, exist_ok=True)
        except Exception as e:
            errors.append(f"无法创建 pi 配置目录 {AGENT_DIR}：{e}")

        # 备份将要改的文件
        changed_files = []
        # ---- 自定义 provider：写 models.json ----
        if kind == "custom":
            models = read_json(MODELS_PATH, {})
            models.setdefault("providers", {})
            entry = {
                "name": prof.get("name") or provider,
            }
            if prof.get("baseUrl"):
                entry["baseUrl"] = prof["baseUrl"]
            if prof.get("api"):
                entry["api"] = prof["api"]
            if prof.get("apiKey"):
                entry["apiKey"] = prof["apiKey"]
            if isinstance(prof.get("compat"), dict):
                entry["compat"] = prof["compat"]
            if prof.get("models"):
                entry["models"] = prof["models"]
            models["providers"][provider] = entry
            backup_file(MODELS_PATH)
            try:
                write_json(MODELS_PATH, models)
                changed_files.append("models.json")
            except Exception as e:
                errors.append(f"写入 models.json 失败：{e}")
        # ---- 内置 provider：写 auth.json ----
        else:
            auth = read_json(AUTH_PATH, {})
            auth[provider] = {"type": "api_key", "key": prof.get("apiKey", "")}
            backup_file(AUTH_PATH)
            try:
                write_json(AUTH_PATH, auth)
                changed_files.append("auth.json")
            except Exception as e:
                errors.append(f"写入 auth.json 失败：{e}")

        # ---- 总是写 settings.json (defaultProvider / defaultModel) ----
        st = read_json(SETTINGS_PATH, {})
        st["defaultProvider"] = provider
        default_model = prof.get("defaultModel")
        if default_model:
            st["defaultModel"] = default_model
        thinking = prof.get("defaultThinkingLevel")
        if thinking:
            st["defaultThinkingLevel"] = thinking
        backup_file(SETTINGS_PATH)
        try:
            write_json(SETTINGS_PATH, st)
            changed_files.append("settings.json")
        except Exception as e:
            errors.append(f"写入 settings.json 失败：{e}")

        if not errors:
            self.profiles["active"] = pid
            self._save_profiles()
        return errors

    def _activate_selected(self):
        sel = self.listbox.curselection()
        if not sel:
            messagebox.showinfo("提示", "请先在左侧选择一个配置。")
            return
        pid = self._id_by_index[sel[0]]
        prof = self.profiles["profiles"].get(pid)
        if not prof:
            return
        if not messagebox.askyesno("确认激活", f"将「{prof.get('name', pid)}」应用为 pi 当前配置？\n\n会备份并修改 pi 的配置文件。"):
            return
        errors = self._do_activate(pid, prof)
        if errors:
            messagebox.showerror("激活失败", "\n".join(errors))
        else:
            self._refresh_list()
            self._refresh_status()
            messagebox.showinfo("已激活",
                                f"已激活：{prof.get('name', pid)}\n\n"
                                "修改已写入 pi 配置文件。\n"
                                "下次启动 pi (或打开 /model 选择) 后生效。")

    def _activate_editing(self):
        # 先保存当前编辑内容，再激活
        if self.editing_id is None:
            pid = self.e_provider.get().strip()
            if not pid:
                messagebox.showerror("缺少字段", "请先填写 Provider ID。")
                return
            if pid in self.profiles["profiles"] and \
                    not messagebox.askyesno("覆盖", f"Provider ID「{pid}」已存在，要覆盖并激活吗？"):
                return
            self.editing_id = pid
        if not self._save_with_id(self.editing_id):
            return
        prof = self.profiles["profiles"].get(self.editing_id)
        if not messagebox.askyesno("确认激活", "将当前编辑内容激活并应用？"):
            return
        errors = self._do_activate(self.editing_id, prof)
        if errors:
            messagebox.showerror("激活失败", "\n".join(errors))
        else:
            self._refresh_list()
            self._refresh_status()
            messagebox.showinfo("已激活", "已激活并写入 pi 配置文件。\n下次启动 pi (或 /model) 后生效。")

    # ------------------------------------------------------------------
    # 从 pi 当前配置导入
    # ------------------------------------------------------------------
    def _capture_current_provider(self):
        """读取 pi 当前 defaultProvider/defaultModel，导入成一个 profile。"""
        st = read_json(SETTINGS_PATH, {})
        provider = st.get("defaultProvider")
        if not provider:
            messagebox.showinfo("提示", "pi settings.json 中没有 defaultProvider，无法导入。")
            return
        default_model = st.get("defaultModel", "")

        # 尝试在 models.json 找自定义 provider
        models = read_json(MODELS_PATH, {})
        prov = models.get("providers", {}).get(provider)
        if prov and prov.get("baseUrl"):
            prof = {
                "name": prov.get("name") or provider,
                "providerId": provider,
                "kind": "custom",
                "baseUrl": prov.get("baseUrl", ""),
                "api": prov.get("api", API_CHOICES[0]),
                "apiKey": prov.get("apiKey", ""),
                "compat": prov.get("compat") if isinstance(prov.get("compat"), dict) else None,
                "models": prov.get("models") if isinstance(prov.get("models"), list) else None,
                "defaultModel": default_model,
            }
        else:
            # 内置 provider，从 auth.json 取 key
            auth = read_json(AUTH_PATH, {})
            entry = auth.get(provider, {})
            prof = {
                "name": provider,
                "providerId": provider,
                "kind": "builtin",
                "apiKey": (entry.get("key") if isinstance(entry, dict) else "") or "",
                "defaultModel": default_model,
            }

        self.profiles["profiles"][provider] = prof
        self._save_profiles()
        self._refresh_list()
        self.editing_id = provider
        self._fill_form(prof)
        # 选中
        for i, p in enumerate(self._id_by_index.values()):
            if p == provider:
                self.listbox.selection_clear(0, tk.END)
                self.listbox.selection_set(i)
                break
        self.status_var.set(f"已从 pi 导入当前配置：{provider} / {default_model}")

    # ------------------------------------------------------------------
    # 批量导入 / 打开配置文件 / 模型清理
    # ------------------------------------------------------------------
    def _clean_models(self, models):
        """去掉占位模板 / 空列表，避免把示例模型写进 pi 配置。"""
        if not isinstance(models, list):
            return None
        real = []
        for m in models:
            if not isinstance(m, dict):
                continue
            if m.get("id") == "my-model":  # 占位模板
                continue
            real.append(m)
        return real or None

    def _import_all(self):
        """扫描 models.json 全部自定义 provider + auth.json 全部内置 provider，批量生成 profiles。"""
        added = []
        # 自定义 providers (models.json)
        models = read_json(MODELS_PATH, {})
        for pid, prov in models.get("providers", {}).items():
            if not isinstance(prov, dict):
                continue
            prof = {
                "name": prov.get("name") or pid,
                "providerId": pid,
                "kind": "custom",
                "baseUrl": prov.get("baseUrl", ""),
                "api": prov.get("api", API_CHOICES[0]),
                "apiKey": prov.get("apiKey", ""),
                "compat": prov.get("compat") if isinstance(prov.get("compat"), dict) else None,
                "models": prov.get("models") if isinstance(prov.get("models"), list) else None,
                "defaultModel": "",
            }
            self.profiles["profiles"][pid] = prof
            added.append(f"[custom]  {pid}")
        # 内置 providers (auth.json)
        auth = read_json(AUTH_PATH, {})
        for pid, cred in auth.items():
            if not isinstance(cred, dict):
                continue  # 跳过 auth.json 里的非凭据/杂项键
            if cred.get("type") != "api_key":
                continue
            # 若已存在同名自定义配置，不覆盖
            if pid in self.profiles["profiles"] and self.profiles["profiles"][pid].get("kind") == "custom":
                continue
            if pid not in self.profiles["profiles"]:
                prof = {
                    "name": pid,
                    "providerId": pid,
                    "kind": "builtin",
                    "apiKey": cred.get("key", ""),
                    "defaultModel": "",
                }
                self.profiles["profiles"][pid] = prof
                added.append(f"[builtin] {pid}")
        if not added:
            messagebox.showinfo("批量导入", "没有发现可导入的 provider。")
            return
        self._save_profiles()
        self._refresh_list()
        messagebox.showinfo("批量导入", f"已导入 {len(added)} 个 provider：\n\n" + "\n".join(added))
        self._refresh_status()

    def _open_config_menu(self):
        """右键/点击打开 pi 相关配置文件。"""
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="settings.json", command=lambda: self._open_file(SETTINGS_PATH))
        menu.add_command(label="models.json", command=lambda: self._open_file(MODELS_PATH))
        menu.add_command(label="auth.json", command=lambda: self._open_file(AUTH_PATH))
        menu.add_command(label="profiles.json (本工具)", command=lambda: self._open_file(PROFILES_PATH))
        menu.add_separator()
        menu.add_command(label="打开备份目录", command=self._open_backup_dir)
        try:
            x = self.root.winfo_pointerx()
            y = self.root.winfo_pointery()
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def _open_file(self, path):
        if not os.path.exists(path):
            messagebox.showinfo("打开配置", f"文件不存在：\n{path}")
            return
        try:
            if sys.platform == "win32":
                os.startfile(path)  # type: ignore
            else:
                import subprocess
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            messagebox.showerror("打开配置", str(e))

    # ------------------------------------------------------------------
    # 复制配置
    # ------------------------------------------------------------------
    def _copy_selected(self):
        """把左侧选中的配置复制一份，作为新的配置（可在此基础上修改）。"""
        sel = self.listbox.curselection()
        if not sel:
            messagebox.showinfo("提示", "请先在左侧选择一个配置。")
            return
        pid = self._id_by_index[sel[0]]
        prof = self.profiles["profiles"].get(pid)
        if not prof:
            return
        new_prof = copy.deepcopy(prof)
        base = pid
        new_id = f"{base} (副本)"
        n = 1
        while new_id in self.profiles["profiles"]:
            n += 1
            new_id = f"{base} (副本{n})"
        new_prof["providerId"] = new_id
        new_prof["name"] = f"{prof.get('name') or pid} (副本{n})"
        self.profiles["profiles"][new_id] = new_prof
        self._save_profiles()
        self._refresh_list()
        self.editing_id = new_id
        self._fill_form(new_prof)
        for i, p in enumerate(self._id_by_index.values()):
            if p == new_id:
                self.listbox.selection_clear(0, tk.END)
                self.listbox.selection_set(i)
                break
        messagebox.showinfo("已复制",
                            f"已复制「{prof.get('name', pid)}」为「{new_prof['name']}」。\n\n"
                            "可在右侧修改，然后点「保存配置」或「激活并应用」。")

    # ------------------------------------------------------------------
    # 获取模型 / 测试模型
    # ------------------------------------------------------------------
    def _ssl_ctx(self):
        """返回一个不校验证书的 ssl context（部分自建代理无有效证书时也能连）。"""
        try:
            return ssl._create_unverified_context()
        except Exception:
            return None

    @staticmethod
    def _center_window(win):
        """把窗口居中显示在主屏幕正中间。"""
        try:
            win.update_idletasks()
        except Exception:
            pass
        w = win.winfo_width() or 640
        h = win.winfo_height() or 460
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        win.geometry(f"+{x}+{y}")

    def _open_fetch_models(self):
        """用表单里的 Base URL + API Key 去 /models 拉取模型列表，并弹出窗口展示。"""
        baseurl = self.e_baseurl.get().strip()
        apikey = self.e_key.get().strip()
        api = self.cb_api.get().strip()
        if self.kind_var.get() != "custom":
            messagebox.showinfo("获取模型", "请把类型先设为「自定义 provider」，才能获取模型。")
            return
        if not baseurl:
            messagebox.showinfo("获取模型", "请先填写 Base URL（例如 https://xxx/v1）。")
            return
        if not apikey:
            messagebox.showinfo("获取模型", "请先填写 API Key。")
            return

        win = tk.Toplevel(self.root)
        win.title("获取模型")
        win.geometry("640x460")
        win.minsize(480, 340)
        win.configure(bg=self._theme["bg"])
        win.transient(self.root)
        self._center_window(win)
        win.grab_set()
        win.protocol("WM_DELETE_WINDOW", win.destroy)

        loading = ttk.Frame(win)
        loading.pack(fill="both", expand=True)
        ttk.Label(loading, text="正在获取模型…", font=("Segoe UI", 12, "bold")).pack(pady=24)
        ttk.Label(loading, text=f"{baseurl.rstrip('/')}/models", font=("Consolas", 9), foreground=self._theme["text_dim"]).pack()
        ttk.Button(loading, text="关闭", command=win.destroy).pack(pady=16)

        threading.Thread(target=self._fetch_models_worker,
                         args=(win, baseurl, apikey, api), daemon=True).start()

    def _fetch_models_worker(self, win, baseurl, apikey, api):
        try:
            models = self._request_models(baseurl, apikey, api)
            err = None
        except Exception as e:
            models = None
            err = str(e)
        self.root.after(0, self._show_models_result, win, models, err, baseurl, apikey, api)

    @staticmethod
    def _http_error_msg(e):
        """把 HTTP 错误转成更可读的消息，尽量带上服务器返回的 message。"""
        try:
            body = e.read().decode("utf-8", "replace")
        except Exception:
            body = ""
        if body:
            try:
                j = json.loads(body)
                msg = j.get("message") or j.get("detail") or j.get("error") or body
            except Exception:
                msg = body
            return f"HTTP {e.code}: {msg}"
        return f"HTTP {e.code}: {e.reason}"

    def _request_models(self, baseurl, apikey, api):
        baseurl = baseurl.rstrip("/")
        headers = {"Accept": "application/json", "User-Agent": BROWSER_UA}
        if api == "anthropic-messages":
            headers["x-api-key"] = apikey
            headers["anthropic-version"] = "2023-06-01"
        else:
            headers["Authorization"] = f"Bearer {apikey}"
        req = urllib.request.Request(f"{baseurl}/models", headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=20, context=self._ssl_ctx()) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise RuntimeError(self._http_error_msg(e))
        return self._parse_models(data)

    @staticmethod
    def _parse_models(data):
        """兼容多种 /models 返回结构，统一成 [{'id':..., 'name':...}]。"""
        items = []
        if isinstance(data, dict):
            for key in ("data", "models", "items"):
                v = data.get(key)
                if isinstance(v, list):
                    items = v
                    break
        elif isinstance(data, list):
            items = data
        models = []
        for it in items:
            if isinstance(it, str):
                models.append({"id": it, "name": it})
            elif isinstance(it, dict):
                mid = it.get("id") or it.get("name")
                if mid:
                    models.append({"id": mid, "name": it.get("name") or mid})
        return models

    def _show_models_result(self, win, models, err, baseurl, apikey, api):
        for w in win.winfo_children():
            w.destroy()
        if err:
            ttk.Label(win, text="获取模型失败", font=("Segoe UI", 12, "bold"), foreground=self._theme["danger"]).pack(pady=12)
            ttk.Label(win, text=err, wraplength=580, justify="left").pack(padx=14)
            ttk.Button(win, text="关闭", command=win.destroy).pack(pady=12)
            return
        if not models:
            ttk.Label(win, text="接口未返回任何模型", font=("Segoe UI", 12, "bold"), foreground=self._theme["warning"]).pack(pady=12)
            ttk.Label(win, text="可能该端点不支持 /models，或需要不同的鉴权方式。", foreground=self._theme["text_dim"]).pack()
            ttk.Button(win, text="关闭", command=win.destroy).pack(pady=12)
            return

        self._last_fetched_models = models
        self._last_fetch_meta = (baseurl, apikey, api)

        hdr = ttk.Frame(win)
        hdr.pack(fill="x", padx=10, pady=(8, 4))
        ttk.Label(hdr, text=f"共 {len(models)} 个模型", font=("Segoe UI", 11, "bold")).pack(side="left")
        ttk.Button(hdr, text="⬇ 全部导入到模型列表", command=self._import_fetched_models).pack(side="right")

        lf = ttk.Frame(win)
        lf.pack(fill="both", expand=True, padx=10, pady=4)
        canvas = tk.Canvas(lf, highlightthickness=0, bg=self._theme["bg"])
        vsb = ttk.Scrollbar(lf, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        for m in models:
            self._make_model_row(inner, m, baseurl, apikey, api, win)

    def _make_model_row(self, parent, m, baseurl, apikey, api, win):
        mid = m.get("id")
        name = m.get("name") or mid
        row = ttk.Frame(parent)
        row.pack(fill="x", padx=4, pady=2)
        row.columnconfigure(0, weight=1)

        left = ttk.Frame(row)
        left.grid(row=0, column=0, sticky="ew", rowspan=2)
        left.columnconfigure(0, weight=1)
        ttk.Label(left, text=mid, font=("Consolas", 9, "bold"), anchor="w").grid(row=0, column=0, sticky="ew")
        ttk.Label(left, text=name, font=("Segoe UI", 8), foreground=self._theme["text_dim"], anchor="w").grid(row=1, column=0, sticky="ew")

        copybtn = ttk.Button(row, text="复制", width=6)
        copybtn.grid(row=0, column=1, padx=4)
        copybtn.configure(command=lambda b=copybtn, mm=mid: self._copy_model(win, mm, b))

        btn = ttk.Button(row, text="测试", width=6)
        btn.grid(row=0, column=2)
        st = ttk.Label(row, text="", width=14, foreground=self._theme["text_dim"], anchor="w")
        st.grid(row=0, column=3, padx=4)
        btn.configure(command=lambda b=btn, s=st, mm=mid: self._run_model_test(baseurl, apikey, api, mm, b, s, win))

    def _copy_model(self, win, mid, btn):
        """复制模型 ID 到剪贴板，按钮临时显示“已复制”。"""
        win.clipboard_clear()
        win.clipboard_append(mid)
        orig = btn.cget("text")
        btn.configure(text="已复制")
        win.after(1000, lambda b=btn, o=orig: b.configure(text=o))
        self.status_var.set(f"已复制模型 ID：{mid}")

    def _run_model_test(self, baseurl, apikey, api, mid, btn, st, win):
        btn.configure(state="disabled")
        st.configure(text="测试中…", foreground=self._theme["warning"])
        threading.Thread(target=self._model_test_worker,
                         args=(baseurl, apikey, api, mid, btn, st, win), daemon=True).start()

    def _model_test_worker(self, baseurl, apikey, api, mid, btn, st, win):
        try:
            self._request_test(baseurl, apikey, api, mid)
            ok, msg = True, ""
        except Exception as e:
            ok, msg = False, str(e)
        self.root.after(0, self._model_test_done, btn, st, win, ok, msg, mid)

    def _request_test(self, baseurl, apikey, api, mid):
        """发出最简请求，2xx 即视为通；否则抛异常（含错误信息）。"""
        baseurl = baseurl.rstrip("/")
        headers = {"Content-Type": "application/json", "User-Agent": BROWSER_UA}
        payload = None
        if api == "anthropic-messages":
            url = f"{baseurl}/messages"
            headers["x-api-key"] = apikey
            headers["anthropic-version"] = "2023-06-01"
            payload = {"model": mid, "max_tokens": 16,
                       "messages": [{"role": "user", "content": "Hello"}]}
        elif api == "openai-responses":
            url = f"{baseurl}/responses"
            headers["Authorization"] = f"Bearer {apikey}"
            payload = {"model": mid, "input": "Hello", "max_output_tokens": 16}
        elif api == "google-generative-ai":
            url = f"{baseurl}/models/{mid}:generateContent"
            headers["Authorization"] = f"Bearer {apikey}"
            payload = {"contents": [{"parts": [{"text": "Hello"}]}]}
        else:  # openai-completions
            url = f"{baseurl}/chat/completions"
            headers["Authorization"] = f"Bearer {apikey}"
            payload = {"model": mid, "messages": [{"role": "user", "content": "Hello"}],
                       "max_tokens": 16}
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30, context=self._ssl_ctx()) as resp:
                resp.read()
        except urllib.error.HTTPError as e:
            raise RuntimeError(self._http_error_msg(e))

    def _model_test_done(self, btn, st, win, ok, msg, mid):
        btn.configure(state="normal")
        if ok:
            st.configure(text="✓ 正常", foreground=self._theme["success"])
            btn.configure(text="测试")
        else:
            st.configure(text="✗ 失败", foreground=self._theme["danger"])
            btn.configure(text="重试")
            messagebox.showinfo("测试结果", f"模型「{mid}」测试失败：\n\n{msg}")

    def _import_fetched_models(self):
        """把获取到的模型转成 pi 的 models 格式，填入右侧表单。"""
        models = getattr(self, "_last_fetched_models", None)
        if not models:
            return
        rows = []
        for m in models:
            mid = m.get("id")
            if not mid:
                continue
            rows.append({
                "id": mid,
                "name": m.get("name") or mid,
                "reasoning": False,
                "input": ["text", "image"],
                "contextWindow": 1048576,
                "maxTokens": 16384,
                "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
            })
        if not rows:
            messagebox.showinfo("导入", "没有可导入的模型。")
            return
        if not messagebox.askyesno("导入模型",
                                   f"将 {len(rows)} 个模型写入右侧「模型列表」？\n\n（会替换当前模型列表内容）"):
            return
        self.txt_models.delete("1.0", tk.END)
        self.txt_models.insert("1.0", json.dumps(rows, ensure_ascii=False, indent=2))
        self._refresh_model_dropdown()
        # 自动把默认模型设置为接口返回的第一个模型
        self.cb_model.set(rows[0]["id"])
        messagebox.showinfo("导入完成", f"已导入 {len(rows)} 个模型到「模型列表」。\n默认模型已自动设为：{rows[0]['id']}")


# ---------------------------------------------------------------------------
def main():
    root = tk.Tk()
    # 现代化主题在 _apply_theme 里统一设置
    # 设置窗口图标（标题栏/任务栏），找不到就忽略
    try:
        root.iconbitmap(resource_path("app.ico"))
    except Exception:
        pass
    PiSwitchApp(root)
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # 出错时把堆栈写到日志，避免窗口闪退后毫无提示
        try:
            log_path = os.path.join(CURRENT_DIR, "error.log")
            with open(log_path, "w", encoding="utf-8") as f:
                f.write(traceback.format_exc())
        except Exception:
            pass
        # 打包成 exe 后（无控制台）不要再裸抛，静默退出即可
        sys.exit(1)
