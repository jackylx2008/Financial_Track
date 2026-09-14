"""Financial Track Tkinter 主窗口。"""

from __future__ import annotations

import platform
import os
import re
import time
import tkinter as tk
from pathlib import Path
from queue import Empty
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from flows.gui.task_runner import TaskEvent, TaskRunner
from flows.gui.workflows import FieldSpec, WorkflowSpec, build_command, format_command, workflows_for_android_apps
from flows.modules.android_capture_config import load_android_app_configs
from flows.modules.config_loader import get_cloudstation_root, load_config


LOG_LINE_LIMIT = 2500
PROGRESS_PATTERN = re.compile(r"(?:\[)?(\d+)\s*/\s*(\d+)")


class WorkflowPanel(ttk.Frame):
    """根据声明式工作流定义生成参数控件。"""

    def __init__(self, parent: ttk.Notebook, app: "FinancialTrackApp", spec: WorkflowSpec) -> None:
        super().__init__(parent, padding=(14, 10))
        self.app = app
        self.spec = spec
        self.variables: dict[str, tk.StringVar | tk.BooleanVar] = {}
        self.input_widgets: list[tk.Widget] = []

        self.columnconfigure(0, weight=1)
        description = ttk.Label(self, text=spec.description, style="Description.TLabel", wraplength=1100)
        description.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        form = ttk.LabelFrame(self, text="参数设置", padding=10)
        form.grid(row=1, column=0, sticky="nsew")
        form.columnconfigure(0, weight=1)
        form.columnconfigure(1, weight=1)
        for index, field in enumerate(spec.fields):
            self._build_field(form, field, index // 2, index % 2)

        button_row = ttk.Frame(self)
        button_row.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        button_row.columnconfigure(0, weight=1)
        self.preview_button = ttk.Button(button_row, text="参数预览", command=self.preview)
        self.preview_button.grid(row=0, column=1, padx=(0, 8))
        self.start_button = ttk.Button(button_row, text="开始执行", style="Accent.TButton", command=self.start)
        self.start_button.grid(row=0, column=2, padx=(0, 8))
        self.cancel_button = ttk.Button(button_row, text="取消任务", command=self.app.cancel_task, state="disabled")
        self.cancel_button.grid(row=0, column=3)

    def _build_field(self, parent: ttk.LabelFrame, field: FieldSpec, row: int, column: int) -> None:
        container = ttk.Frame(parent, padding=(4, 3))
        container.grid(row=row, column=column, sticky="ew", padx=4, pady=2)
        container.columnconfigure(1, weight=1)
        if field.kind == "bool":
            variable = tk.BooleanVar(value=bool(self.app.initial_value(self.spec.key, field)))
            widget = ttk.Checkbutton(container, text=field.label, variable=variable)
            widget.grid(row=0, column=0, columnspan=3, sticky="w")
        else:
            variable = tk.StringVar(value=str(self.app.initial_value(self.spec.key, field)))
            ttk.Label(container, text=field.label, width=16).grid(row=0, column=0, sticky="w", padx=(0, 6))
            if field.kind == "choice":
                widget = ttk.Combobox(container, textvariable=variable, values=field.choices, state="readonly")
            else:
                widget = ttk.Entry(container, textvariable=variable)
            widget.grid(row=0, column=1, sticky="ew")
            if field.kind in {"file", "save_file", "directory"}:
                browse = ttk.Button(container, text="浏览…", width=8, command=lambda: self._browse(field))
                browse.grid(row=0, column=2, padx=(6, 0))
                self.input_widgets.append(browse)
            if field.help_text:
                ttk.Label(container, text=field.help_text, style="Hint.TLabel").grid(
                    row=1,
                    column=1,
                    columnspan=2,
                    sticky="w",
                    pady=(2, 0),
                )
        self.variables[field.key] = variable
        self.input_widgets.append(widget)

    def _browse(self, field: FieldSpec) -> None:
        current = str(self.variables[field.key].get()).strip()
        current_path = Path(current).expanduser() if current else self.app.project_root
        if not current_path.is_absolute():
            current_path = self.app.project_root / current_path
        initial_dir = current_path if current_path.is_dir() else current_path.parent
        if field.kind == "directory":
            selected = filedialog.askdirectory(parent=self, initialdir=initial_dir)
        elif field.kind == "save_file":
            selected = filedialog.asksaveasfilename(
                parent=self,
                initialdir=initial_dir,
                initialfile=current_path.name if current else "",
                defaultextension=".xlsx",
                filetypes=(("Excel 工作簿", "*.xlsx"), ("所有文件", "*.*")),
            )
        else:
            selected = filedialog.askopenfilename(parent=self, initialdir=initial_dir)
        if selected:
            self.variables[field.key].set(selected)

    def values(self) -> dict[str, str | bool]:
        return {key: variable.get() for key, variable in self.variables.items()}

    def preview(self) -> None:
        self.app.preview_workflow(self)

    def start(self) -> None:
        self.app.start_workflow(self)

    def set_running(self, running: bool, active: bool = False) -> None:
        for widget in self.input_widgets:
            if isinstance(widget, ttk.Combobox):
                widget.configure(state="disabled" if running else "readonly")
            else:
                widget.configure(state="disabled" if running else "normal")
        self.preview_button.configure(state="disabled" if running else "normal")
        self.start_button.configure(state="disabled" if running else "normal")
        self.cancel_button.configure(state="normal" if running and active else "disabled")


class ConfigPanel(ttk.Frame):
    """只展示安全的全局路径和运行环境，不显示 env 中的秘密值。"""

    def __init__(self, parent: ttk.Notebook, app: "FinancialTrackApp") -> None:
        super().__init__(parent, padding=(14, 10))
        self.app = app
        self.columnconfigure(1, weight=1)
        rows = (
            ("项目根目录", str(app.project_root)),
            ("主配置文件", str(app.project_root / "config.yaml")),
            ("本地环境文件", str(app.project_root / "common.env")),
            ("日志目录", str(app.project_root / "logs")),
            ("CloudStation 根目录", str(get_cloudstation_root())),
            ("Python", platform.python_version()),
            ("Tk", str(tk.TkVersion)),
        )
        for row, (label, value) in enumerate(rows):
            ttk.Label(self, text=label, width=20).grid(row=row, column=0, sticky="nw", padx=(0, 8), pady=5)
            entry = ttk.Entry(self)
            entry.insert(0, value)
            entry.configure(state="readonly")
            entry.grid(row=row, column=1, sticky="ew", pady=5)

        note = (
            "界面只读取配置，不在这里保存账号、授权码或附件密码。请在被 Git 忽略的 common.env 和"
            " financial_attachment_passwords.env 中维护本机秘密信息。"
        )
        ttk.Label(self, text=note, style="Hint.TLabel", wraplength=1000).grid(
            row=len(rows), column=0, columnspan=2, sticky="w", pady=(12, 8)
        )
        self.reload_button = ttk.Button(
            self,
            text="重新加载并检查配置",
            command=self.check_config,
        )
        self.reload_button.grid(row=len(rows) + 1, column=1, sticky="e")

    def check_config(self) -> None:
        try:
            config = load_config(self.app.project_root / "config.yaml")
        except Exception as exc:
            self.app.append_log(f"配置检查失败：{exc}", "error")
            messagebox.showerror("配置检查失败", str(exc), parent=self)
            return
        self.app.config = config
        self.app.apply_config_defaults()
        sections = "、".join(sorted(config))
        self.app.append_log(f"配置检查成功；已加载顶层配置：{sections}", "success")

    def set_running(self, running: bool) -> None:
        """Prevent configuration changes while a subprocess is active."""
        self.reload_button.configure(state="disabled" if running else "normal")


class FinancialTrackApp:
    """单窗口财务流程控制台。"""

    def __init__(self, root: tk.Tk, project_root: Path) -> None:
        self.root = root
        self.project_root = project_root.resolve()
        self.runner = TaskRunner()
        self.config = self._load_initial_config()
        self.panels: list[WorkflowPanel] = []
        self.active_panel: WorkflowPanel | None = None
        self.started_at: float | None = None
        self.closing = False

        self.status_var = tk.StringVar(value="就绪")
        self.current_var = tk.StringVar(value="当前对象：—")
        self.elapsed_var = tk.StringVar(value="耗时：00:00:00")

        self._configure_window()
        self._build_layout()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(100, self._poll_events)
        self.root.after(250, self._update_elapsed)

    def _load_initial_config(self) -> dict[str, object]:
        try:
            return load_config(self.project_root / "config.yaml")
        except Exception:
            return {}

    def initial_value(self, workflow_key: str, field: FieldSpec) -> str | bool:
        """优先从 config.yaml 读取 GUI 可安全展示的工作流默认值。"""
        if workflow_key == "email":
            section = self.config.get("financial_email", {})
            if isinstance(section, dict):
                mapping = {
                    "since": "since",
                    "before": "before",
                    "max_messages": "max_messages",
                    "output_dir": "output_dir",
                }
                config_key = mapping.get(field.key)
                if config_key and section.get(config_key) not in {None, ""}:
                    return str(section[config_key])
        if workflow_key == "attachment" and field.key == "password_env":
            section = self.config.get("financial_attachments", {})
            if isinstance(section, dict) and section.get("password_env_file"):
                return str(section["password_env_file"])
        return field.default

    def apply_config_defaults(self) -> None:
        """用户主动重新加载配置时，将安全默认值同步到工作流表单。"""
        if self.runner.running:
            return
        for panel in self.panels:
            for field in panel.spec.fields:
                panel.variables[field.key].set(self.initial_value(panel.spec.key, field))

    def _configure_window(self) -> None:
        self.root.title("Financial Track · 个人财务信息追溯")
        self.root.geometry("1320x900")
        self.root.minsize(1080, 720)
        style = ttk.Style(self.root)
        style.configure("Description.TLabel", font=("TkDefaultFont", 10))
        style.configure("Hint.TLabel", foreground="#5f6b7a")
        style.configure("Status.TLabel", padding=(6, 3))
        style.configure("Accent.TButton", font=("TkDefaultFont", 9, "bold"))

    def _build_layout(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=3)
        self.root.rowconfigure(1, weight=2)

        self.notebook = ttk.Notebook(self.root)
        self.notebook.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 4))
        try:
            android_apps = load_android_app_configs(os.environ)
            app_names = tuple(item.name for item in android_apps)
        except ValueError as exc:
            app_names = ()
            self.root.after(0, lambda message=str(exc): self.append_log(f"安卓 App 配置错误：{message}", "error"))
        for spec in workflows_for_android_apps(app_names):
            panel = WorkflowPanel(self.notebook, self, spec)
            self.panels.append(panel)
            self.notebook.add(panel, text=spec.title)
        self.config_panel = ConfigPanel(self.notebook, self)
        self.notebook.add(self.config_panel, text="全局配置")

        log_frame = ttk.LabelFrame(self.root, text="运行日志与实时输出", padding=(8, 6))
        log_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=4)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(1, weight=1)
        toolbar = ttk.Frame(log_frame)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        toolbar.columnconfigure(0, weight=1)
        ttk.Label(toolbar, text="所有工作流共用此区域；磁盘日志保存在 logs/。", style="Hint.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Button(toolbar, text="清空日志", command=self.clear_log).grid(row=0, column=1, sticky="e")
        self.log_text = ScrolledText(
            log_frame,
            height=14,
            wrap="word",
            state="disabled",
            font=("TkFixedFont", 9),
            background="#111827",
            foreground="#e5e7eb",
            insertbackground="#e5e7eb",
        )
        self.log_text.grid(row=1, column=0, sticky="nsew")
        self.log_text.tag_configure("info", foreground="#e5e7eb")
        self.log_text.tag_configure("warning", foreground="#fbbf24")
        self.log_text.tag_configure("error", foreground="#f87171")
        self.log_text.tag_configure("success", foreground="#4ade80")
        self.log_text.tag_configure("command", foreground="#93c5fd")

        status_area = ttk.Frame(self.root, padding=(10, 3))
        status_area.grid(row=2, column=0, sticky="ew")
        status_area.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(status_area, mode="determinate", maximum=100)
        self.progress.grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 3))
        ttk.Label(status_area, textvariable=self.status_var, style="Status.TLabel", width=14).grid(
            row=1, column=0, sticky="w"
        )
        ttk.Label(status_area, textvariable=self.current_var, style="Status.TLabel").grid(
            row=1, column=1, sticky="w", padx=(8, 0)
        )
        ttk.Label(status_area, textvariable=self.elapsed_var, style="Status.TLabel", width=18).grid(
            row=1, column=2, sticky="e"
        )
        environment = f"Python {platform.python_version()} · Tk {tk.TkVersion}"
        ttk.Label(status_area, text=environment, style="Status.TLabel").grid(row=1, column=3, sticky="e")

    def preview_workflow(self, panel: WorkflowPanel) -> None:
        try:
            command = build_command(panel.spec, panel.values(), self.project_root)
        except ValueError as exc:
            messagebox.showerror("参数错误", str(exc), parent=panel)
            return
        self.append_log(f"[{panel.spec.title}] 参数预览：\n{format_command(command)}", "command")

    def start_workflow(self, panel: WorkflowPanel) -> None:
        if self.runner.running:
            messagebox.showwarning("任务正在运行", "同一时间只能运行一个工作流。", parent=panel)
            return
        try:
            command = build_command(panel.spec, panel.values(), self.project_root)
        except ValueError as exc:
            self.notebook.select(panel)
            messagebox.showerror("参数错误", str(exc), parent=panel)
            return

        self.active_panel = panel
        self.started_at = time.monotonic()
        self.status_var.set("运行")
        self.current_var.set(f"当前工作流：{panel.spec.title}")
        self.elapsed_var.set("耗时：00:00:00")
        self.progress.configure(mode="indeterminate", maximum=100, value=0)
        self.progress.start(12)
        self._set_running_state(True)
        self.append_log("─" * 72, "info")
        self.append_log(f"开始执行 [{panel.spec.title}]", "success")
        self.append_log(format_command(command), "command")
        try:
            self.runner.start(command, self.project_root)
        except RuntimeError as exc:
            self._finish_ui("失败", 0)
            messagebox.showerror("无法启动", str(exc), parent=panel)

    def cancel_task(self) -> None:
        if self.runner.request_cancel():
            self.status_var.set("正在取消")
        elif self.runner.running:
            self.append_log("任务正在启动，请稍后再次取消。", "warning")

    def _set_running_state(self, running: bool) -> None:
        for panel in self.panels:
            panel.set_running(running, active=panel is self.active_panel)
        self.config_panel.set_running(running)

    def _poll_events(self) -> None:
        try:
            while True:
                self._handle_event(self.runner.events.get_nowait())
        except Empty:
            pass
        if self.closing and not self.runner.running:
            self.root.destroy()
            return
        self.root.after(100, self._poll_events)

    def _handle_event(self, event: TaskEvent) -> None:
        if event.kind == "output":
            tag = self._log_tag(event.message)
            self.append_log(event.message, tag)
            self.current_var.set(f"当前对象：{self._shorten(event.message, 90)}")
            self._update_progress_from_line(event.message)
        elif event.kind == "error":
            self.append_log(event.message, "error")
        elif event.kind == "cancelling":
            self.status_var.set("正在取消")
            self.append_log(event.message, "warning")
        elif event.kind == "finished":
            cancelled = event.message == "任务已取消"
            if cancelled:
                status, tag = "已取消", "warning"
            elif event.returncode == 0:
                status, tag = "完成", "success"
            else:
                status, tag = "失败", "error"
            self.append_log(f"{event.message}；耗时 {self._format_elapsed(event.elapsed_seconds)}", tag)
            self._finish_ui(status, event.elapsed_seconds, success=event.returncode == 0 and not cancelled)
            if event.returncode not in {0, None} and not cancelled and not self.closing:
                messagebox.showerror("工作流执行失败", event.message, parent=self.root)

    def _finish_ui(self, status: str, elapsed: float, success: bool = False) -> None:
        self.progress.stop()
        self.progress.configure(mode="determinate", maximum=100, value=100 if success else 0)
        self.status_var.set(status)
        self.elapsed_var.set(f"耗时：{self._format_elapsed(elapsed)}")
        self._set_running_state(False)
        self.active_panel = None
        self.started_at = None

    def _update_progress_from_line(self, line: str) -> None:
        match = PROGRESS_PATTERN.search(line)
        if not match:
            return
        current, total = (int(match.group(1)), int(match.group(2)))
        if total <= 0:
            return
        if str(self.progress.cget("mode")) == "indeterminate":
            self.progress.stop()
            self.progress.configure(mode="determinate")
        self.progress.configure(maximum=total, value=min(current, total))

    def _update_elapsed(self) -> None:
        if self.started_at is not None:
            self.elapsed_var.set(f"耗时：{self._format_elapsed(time.monotonic() - self.started_at)}")
        self.root.after(250, self._update_elapsed)

    def append_log(self, message: str, tag: str = "info") -> None:
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"{timestamp}  {message}\n", tag)
        line_count = int(self.log_text.index("end-1c").split(".")[0])
        if line_count > LOG_LINE_LIMIT:
            self.log_text.delete("1.0", f"{line_count - LOG_LINE_LIMIT + 1}.0")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def on_close(self) -> None:
        if not self.runner.running:
            self.root.destroy()
            return
        if not messagebox.askyesno(
            "任务仍在运行",
            "是否请求当前任务安全取消？窗口将在任务退出后关闭。",
            parent=self.root,
        ):
            return
        self.closing = True
        self.cancel_task()

    @staticmethod
    def _format_elapsed(seconds: float) -> str:
        total = max(0, int(seconds))
        hours, remainder = divmod(total, 3600)
        minutes, secs = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    @staticmethod
    def _shorten(value: str, length: int) -> str:
        return value if len(value) <= length else value[: length - 3] + "..."

    @staticmethod
    def _log_tag(line: str) -> str:
        lowered = line.lower()
        if any(token in lowered for token in ("error", "failed", "traceback", "错误", "失败")):
            return "error"
        if any(token in lowered for token in ("warning", "warn", "警告", "跳过")):
            return "warning"
        if any(token in lowered for token in ("success", "completed", "saved", "成功", "完成", "已保存")):
            return "success"
        return "info"


def run(project_root: Path) -> int:
    root = tk.Tk()
    FinancialTrackApp(root, project_root)
    root.mainloop()
    return 0
