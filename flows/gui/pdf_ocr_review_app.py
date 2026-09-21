from __future__ import annotations

import logging
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from flows.gui.review_file_server import open_with_default_application
from flows.modules.pdf_ocr_review_data import (
    default_document_index,
    find_document_for_pdf,
    load_cached_pages,
    load_manual_reviews,
    load_review_documents,
    review_key,
    save_manual_review,
)


logger = logging.getLogger(__name__)
ZOOM_VALUES = (100, 125, 150, 175, 200)


class PdfOcrReviewApp:
    def __init__(self, root: tk.Tk, project_root: Path) -> None:
        self.root = root
        self.project_root = project_root.resolve()
        self.output_dir = self.project_root / "processed_data" / "pdf_html_review"
        self.manifest_path = self.output_dir / "pdf_html_manifest.json"
        self.review_path = self.output_dir / "pdf_ocr_manual_review.json"
        self.documents = load_review_documents(self.manifest_path)
        if not self.documents:
            raise RuntimeError("没有可审核的 PDF 缓存，请先在主 GUI 执行“PDF 转 HTML 审核”。")
        self.reviews = load_manual_reviews(self.review_path)
        self.document: dict[str, Any] = {}
        self.pages: list[dict[str, Any]] = []
        self.pdf_document: Any | None = None
        self.page_index = 0
        self.pdf_photo: Any | None = None
        self._syncing_scroll = False

        self.root.title("PDF 原页与识别数据人工审核")
        self.root.geometry("1680x980")
        self.root.minsize(1100, 700)
        self._configure_styles()
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        index = default_document_index(self.documents)
        self.institution_var.set(str(self.documents[index].get("institution", "")))
        self._refresh_document_choices(preferred_index=index)

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 16, "bold"))
        style.configure("Hint.TLabel", foreground="#5a6874")
        style.configure("Status.TLabel", foreground="#174d7a", font=("Microsoft YaHei UI", 10, "bold"))

    def _build_ui(self) -> None:
        shell = ttk.Frame(self.root, padding=10)
        shell.pack(fill="both", expand=True)
        ttk.Label(shell, text="PDF 原页与识别数据人工审核", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            shell,
            text="只读取 PDF 哈希缓存和识别结果；人工结论独立保存，不进入归一化或财务统计。",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(2, 8))

        toolbar = ttk.Frame(shell)
        toolbar.pack(fill="x", pady=(0, 8))
        ttk.Label(toolbar, text="机构").grid(row=0, column=0, padx=(0, 4))
        self.institution_var = tk.StringVar()
        self.institution_box = ttk.Combobox(
            toolbar,
            textvariable=self.institution_var,
            state="readonly",
            width=12,
            values=sorted({str(item.get("institution", "")) for item in self.documents}),
        )
        self.institution_box.grid(row=0, column=1, padx=(0, 10))
        self.institution_box.bind("<<ComboboxSelected>>", lambda _: self._refresh_document_choices())
        ttk.Label(toolbar, text="PDF").grid(row=0, column=2, padx=(0, 4))
        self.document_var = tk.StringVar()
        self.document_box = ttk.Combobox(toolbar, textvariable=self.document_var, state="readonly", width=72)
        self.document_box.grid(row=0, column=3, sticky="ew", padx=(0, 6))
        self.document_box.bind("<<ComboboxSelected>>", lambda _: self._load_selected_document())
        ttk.Button(toolbar, text="选择其他 PDF…", command=self.choose_pdf).grid(row=0, column=4, padx=(0, 6))
        ttk.Button(toolbar, text="默认程序打开 PDF", command=self.open_pdf).grid(row=0, column=5)
        toolbar.columnconfigure(3, weight=1)

        pagebar = ttk.Frame(shell)
        pagebar.pack(fill="x", pady=(0, 8))
        ttk.Button(pagebar, text="上一页", command=self.previous_page).pack(side="left")
        ttk.Button(pagebar, text="下一页", command=self.next_page).pack(side="left", padx=(6, 12))
        ttk.Label(pagebar, text="页码").pack(side="left")
        self.page_var = tk.StringVar()
        self.page_box = ttk.Combobox(pagebar, textvariable=self.page_var, state="readonly", width=8)
        self.page_box.pack(side="left", padx=(4, 12))
        self.page_box.bind("<<ComboboxSelected>>", lambda _: self._select_page_number())
        ttk.Label(pagebar, text="缩放").pack(side="left")
        self.zoom_var = tk.IntVar(value=125)
        zoom_box = ttk.Combobox(
            pagebar,
            textvariable=self.zoom_var,
            state="readonly",
            width=7,
            values=ZOOM_VALUES,
        )
        zoom_box.pack(side="left", padx=(4, 12))
        zoom_box.bind("<<ComboboxSelected>>", lambda _: self.render_page())
        self.status_var = tk.StringVar()
        ttk.Label(pagebar, textvariable=self.status_var, style="Status.TLabel").pack(side="left", fill="x", expand=True)

        headings = ttk.Frame(shell)
        headings.pack(fill="x")
        headings.columnconfigure(0, weight=1)
        headings.columnconfigure(1, weight=1)
        ttk.Label(headings, text="左侧：原始 PDF 页面", anchor="center").grid(row=0, column=0, sticky="ew")
        ttk.Label(headings, text="右侧：缓存中的识别表格", anchor="center").grid(row=0, column=1, sticky="ew")

        viewer = ttk.Frame(shell)
        viewer.pack(fill="both", expand=True)
        viewer.rowconfigure(0, weight=1)
        viewer.columnconfigure(0, weight=1)
        viewer.columnconfigure(2, weight=1)
        self.left_canvas = tk.Canvas(viewer, background="#4d555c", highlightthickness=0)
        self.right_canvas = tk.Canvas(viewer, background="#e8edf1", highlightthickness=0)
        self.left_canvas.grid(row=0, column=0, sticky="nsew")
        ttk.Separator(viewer, orient="vertical").grid(row=0, column=1, sticky="ns", padx=3)
        self.right_canvas.grid(row=0, column=2, sticky="nsew")
        self.vertical_scrollbar = ttk.Scrollbar(viewer, orient="vertical", command=self._scroll_both)
        self.vertical_scrollbar.grid(row=0, column=3, sticky="ns")
        self.left_hscroll = ttk.Scrollbar(viewer, orient="horizontal", command=self.left_canvas.xview)
        self.left_hscroll.grid(row=1, column=0, sticky="ew")
        self.right_hscroll = ttk.Scrollbar(viewer, orient="horizontal", command=self.right_canvas.xview)
        self.right_hscroll.grid(row=1, column=2, sticky="ew")
        self.left_canvas.configure(xscrollcommand=self.left_hscroll.set)
        self.right_canvas.configure(xscrollcommand=self.right_hscroll.set)
        for widget in (self.left_canvas, self.right_canvas):
            widget.bind("<MouseWheel>", self._on_mousewheel)
            widget.bind("<Button-4>", self._on_mousewheel)
            widget.bind("<Button-5>", self._on_mousewheel)

        review = ttk.LabelFrame(shell, text="本页人工审核结论", padding=8)
        review.pack(fill="x", pady=(8, 0))
        self.review_status_var = tk.StringVar(value="pending")
        ttk.Radiobutton(review, text="待审核", variable=self.review_status_var, value="pending").grid(row=0, column=0)
        ttk.Radiobutton(review, text="一致", variable=self.review_status_var, value="approved").grid(row=0, column=1, padx=8)
        ttk.Radiobutton(review, text="存在问题", variable=self.review_status_var, value="issue").grid(row=0, column=2)
        ttk.Label(review, text="备注").grid(row=0, column=3, padx=(18, 4))
        self.note_var = tk.StringVar()
        ttk.Entry(review, textvariable=self.note_var).grid(row=0, column=4, sticky="ew")
        ttk.Button(review, text="保存本页结论", command=self.save_review).grid(row=0, column=5, padx=(8, 0))
        review.columnconfigure(4, weight=1)

    def _refresh_document_choices(self, preferred_index: int | None = None) -> None:
        institution = self.institution_var.get()
        choices = [
            (index, item)
            for index, item in enumerate(self.documents)
            if not institution or item.get("institution") == institution
        ]
        self._document_indices = [index for index, _ in choices]
        labels = [str(item.get("relative_file") or Path(item["source_file"]).name) for _, item in choices]
        self.document_box.configure(values=labels)
        if not choices:
            return
        selected = self._document_indices.index(preferred_index) if preferred_index in self._document_indices else 0
        self.document_box.current(selected)
        self._load_selected_document()

    def _load_selected_document(self) -> None:
        selection = self.document_box.current()
        if selection < 0:
            return
        self._set_document(self.documents[self._document_indices[selection]])

    def _set_document(self, document: dict[str, Any]) -> None:
        import fitz

        if self.pdf_document is not None:
            self.pdf_document.close()
        self.document = document
        self.pages = load_cached_pages(document)
        self.pdf_document = fitz.open(document["source_file"])
        if len(self.pages) != self.pdf_document.page_count:
            raise ValueError("PDF 页数与识别缓存页数不一致，不能进行逐页审核。")
        self.page_box.configure(values=[str(index) for index in range(1, len(self.pages) + 1)])
        self.page_index = 0
        self.page_box.current(0)
        self.render_page()

    def choose_pdf(self) -> None:
        value = filedialog.askopenfilename(
            title="选择已有识别缓存的 PDF",
            initialdir=self.project_root / "raw_data" / "bank",
            filetypes=[("PDF 文件", "*.pdf")],
        )
        if not value:
            return
        try:
            self._set_document(find_document_for_pdf(Path(value), self.output_dir))
        except (OSError, ValueError, FileNotFoundError) as exc:
            messagebox.showerror("无法载入 PDF", str(exc), parent=self.root)

    def render_page(self) -> None:
        if self.pdf_document is None or not self.pages:
            return
        import fitz
        from PIL import Image, ImageTk

        page = self.pdf_document.load_page(self.page_index)
        scale = self.zoom_var.get() / 100.0
        pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
        self.pdf_photo = ImageTk.PhotoImage(image)
        width, height = pixmap.width, pixmap.height

        self.left_canvas.delete("all")
        self.left_canvas.create_image(12, 12, anchor="nw", image=self.pdf_photo)
        self.left_canvas.configure(scrollregion=(0, 0, width + 24, height + 24))
        self._draw_recognized_page(self.pages[self.page_index], width, height, scale)
        self.left_canvas.yview_moveto(0)
        self.right_canvas.yview_moveto(0)
        self.vertical_scrollbar.set(0, min(1.0, self.left_canvas.winfo_height() / max(1, height + 24)))
        self._load_review_state()
        self._update_status()

    def _draw_recognized_page(self, page: dict[str, Any], width: int, height: int, scale: float) -> None:
        canvas = self.right_canvas
        canvas.delete("all")
        horizontal_scale = scale * 1.65
        recognized_width = int(width * 1.65)
        canvas.create_rectangle(12, 12, recognized_width + 12, height + 12, fill="white", outline="#9aa8b4")
        tables = page.get("tables", [])
        if not tables:
            canvas.create_text(
                28,
                28,
                anchor="nw",
                text=page.get("text") or "本页没有识别表格",
                width=recognized_width - 32,
            )
        for table in tables:
            self._draw_table(canvas, table, horizontal_scale, scale, page)
        canvas.configure(scrollregion=(0, 0, recognized_width + 24, height + 24))

    def _draw_table(
        self,
        canvas: tk.Canvas,
        table: dict[str, Any],
        horizontal_scale: float,
        vertical_scale: float,
        page: dict[str, Any],
    ) -> None:
        bbox = table.get("bbox", [0, 0, page.get("width", 1), page.get("height", 1)])
        x0 = float(bbox[0]) * horizontal_scale + 12
        x1 = float(bbox[2]) * horizontal_scale + 12
        y0 = float(bbox[1]) * vertical_scale + 12
        y1 = float(bbox[3]) * vertical_scale + 12
        rows = table.get("rows", [])
        if not rows:
            return
        widths = [float(value) for value in table.get("column_widths", [])]
        columns = max(len(widths), max((len(row) for row in rows), default=0))
        if columns <= 0:
            return
        if len(widths) != columns or sum(widths) <= 0:
            widths = [1.0] * columns
        total_width = sum(widths)
        row_height = max(1.0, (y1 - y0) / len(rows))
        font_size = max(6, min(8, int(5 * vertical_scale)))
        for row_index, row in enumerate(rows):
            top = y0 + row_index * row_height
            bottom = y0 + (row_index + 1) * row_height
            left = x0
            for column in range(columns):
                cell_width = (x1 - x0) * widths[column] / total_width
                right = left + cell_width
                canvas.create_rectangle(left, top, right, bottom, outline="#66798a", fill="#f1f5f8" if row_index == 0 else "white")
                text = str(row[column] if column < len(row) else "")
                canvas.create_text(
                    left + 2,
                    top + 2,
                    anchor="nw",
                    text=text,
                    width=max(1, cell_width - 4),
                    font=("Microsoft YaHei UI", font_size, "bold" if row_index == 0 else "normal"),
                    fill="#16232e",
                )
                left = right

    def _scroll_both(self, *args: str) -> None:
        self.left_canvas.yview(*args)
        self.right_canvas.yview(*args)
        self.vertical_scrollbar.set(*self.left_canvas.yview())

    def _on_mousewheel(self, event: tk.Event[Any]) -> str:
        if getattr(event, "num", None) == 4:
            units = -3
        elif getattr(event, "num", None) == 5:
            units = 3
        else:
            units = -max(-3, min(3, int(event.delta / 120))) * 3
        self.left_canvas.yview_scroll(units, "units")
        self.right_canvas.yview_scroll(units, "units")
        self.vertical_scrollbar.set(*self.left_canvas.yview())
        return "break"

    def _select_page_number(self) -> None:
        try:
            self.page_index = int(self.page_var.get()) - 1
        except ValueError:
            return
        self.render_page()

    def previous_page(self) -> None:
        if self.page_index > 0:
            self.page_index -= 1
            self.page_box.current(self.page_index)
            self.render_page()

    def next_page(self) -> None:
        if self.page_index + 1 < len(self.pages):
            self.page_index += 1
            self.page_box.current(self.page_index)
            self.render_page()

    def open_pdf(self) -> None:
        if self.document:
            try:
                open_with_default_application(Path(self.document["source_file"]))
            except OSError as exc:
                messagebox.showerror("打开 PDF 失败", str(exc), parent=self.root)

    def save_review(self) -> None:
        entry = save_manual_review(
            self.review_path,
            self.reviews,
            pdf_sha256=str(self.document.get("sha256", "")),
            page_number=self.page_index + 1,
            status=self.review_status_var.get(),
            note=self.note_var.get(),
        )
        self.status_var.set(f"本页结论已保存：{self._status_label(entry['status'])} · {entry['updated_at']}")

    def _load_review_state(self) -> None:
        key = review_key(str(self.document.get("sha256", "")), self.page_index + 1)
        entry = self.reviews.get("reviews", {}).get(key, {})
        self.review_status_var.set(str(entry.get("status", "pending")))
        self.note_var.set(str(entry.get("note", "")))

    def _update_status(self) -> None:
        digest = str(self.document.get("sha256", ""))
        self.status_var.set(
            f"第 {self.page_index + 1}/{len(self.pages)} 页 · OCR {self.document.get('ocr_status', 'unknown')} · SHA-256 {digest[:16]}…"
        )

    @staticmethod
    def _status_label(status: str) -> str:
        return {"approved": "一致", "issue": "存在问题", "pending": "待审核"}.get(status, status)

    def close(self) -> None:
        if self.pdf_document is not None:
            self.pdf_document.close()
        self.root.destroy()


def run(project_root: Path) -> int:
    root = tk.Tk()
    try:
        PdfOcrReviewApp(root, project_root)
    except Exception as exc:
        logger.exception("Failed to start PDF OCR review app")
        messagebox.showerror("PDF OCR 审核程序启动失败", str(exc), parent=root)
        root.destroy()
        return 1
    root.mainloop()
    return 0
