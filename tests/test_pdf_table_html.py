from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from flows.modules.pdf_hash_registry import update_ocr_status
from flows.modules.pdf_html_ocr_verifier import verify_pdf_html_ocr
from flows.modules.pdf_table_html import export_pdf_tables, read_cached_pdf_text


class PdfTableHtmlTests(unittest.TestCase):
    def test_diagonal_watermark_is_removed_before_table_extraction(self) -> None:
        from reportlab.pdfgen import canvas

        with tempfile.TemporaryDirectory() as directory:
            pdf_path = Path(directory) / "watermarked.pdf"
            document = canvas.Canvas(str(pdf_path), pagesize=(500, 240))
            x_positions = (30, 180, 320, 470)
            y_positions = (40, 90, 140, 190)
            for x in x_positions:
                document.line(x, y_positions[0], x, y_positions[-1])
            for y in y_positions:
                document.line(x_positions[0], y, x_positions[-1], y)
            rows = (
                ("Date", "Amount", "Summary"),
                ("2026-01-02", "12.34", "Sample"),
                ("2026-01-03", "56.78", "Other"),
            )
            for row_index, row in enumerate(rows):
                for column, value in enumerate(row):
                    document.drawString(x_positions[column] + 5, 165 - row_index * 50, value)
            document.saveState()
            document.setFillGray(0.75)
            document.translate(70, 60)
            document.rotate(30)
            document.setFont("Helvetica", 22)
            document.drawString(0, 0, "WATERMARK 123456")
            document.restoreState()
            document.save()

            result = export_pdf_tables(
                Path(directory), Path(directory), Path(directory) / "review"
            )
            cache_path = next((Path(directory) / "review" / "cache").glob("*.json"))
            cached = json.loads(cache_path.read_text(encoding="utf-8"))

            self.assertEqual(result["rows"], 3)
            self.assertEqual(cached["pages"][0]["tables"][0]["rows"], [list(row) for row in rows])
            self.assertNotIn("WATERMARK", cached["parser_text"])
            self.assertNotIn("123456", cached["parser_text"])

    def test_exports_tables_and_reuses_sha256_cache(self) -> None:
        import fitz

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_root = root / "raw_data" / "bank" / "sample_bank"
            output_dir = root / "processed_data" / "pdf_html_review"
            input_root.mkdir(parents=True)
            pdf_path = input_root / "sample.pdf"
            document = fitz.open()
            page = document.new_page(width=500, height=200)
            x_positions = (30, 150, 250, 470)
            y_positions = (30, 70, 110)
            for x in x_positions:
                page.draw_line((x, y_positions[0]), (x, y_positions[-1]))
            for y in y_positions:
                page.draw_line((x_positions[0], y), (x_positions[-1], y))
            cells = (
                ("Date", "Amount", "Summary"),
                ("2026-01-02", "12.34", "Sample purchase"),
            )
            for row, values in enumerate(cells):
                for column, value in enumerate(values):
                    page.insert_text((x_positions[column] + 4, y_positions[row] + 24), value, fontsize=9)
            document.save(pdf_path)
            document.close()

            first = export_pdf_tables(root, root / "raw_data" / "bank", output_dir)
            second = export_pdf_tables(root, root / "raw_data" / "bank", output_dir)
            html = (output_dir / "bank_pdf_tables_review.html").read_text(encoding="utf-8")
            registry = json.loads((output_dir / "pdf_hash_index.json").read_text(encoding="utf-8"))

            self.assertEqual(first["converted"], 1)
            self.assertEqual(first["reused"], 0)
            self.assertEqual(first["rows"], 2)
            self.assertEqual(second["converted"], 0)
            self.assertEqual(second["reused"], 1)
            self.assertEqual(second["upgraded"], 0)
            self.assertEqual(first["hash_entries"], 1)
            self.assertIn("Sample purchase", html)
            self.assertIn("/open-source", html)
            self.assertIn("SHA-256", html)
            self.assertIn("Sample purchase", read_cached_pdf_text(pdf_path, root) or "")
            digest = next(iter(registry["documents"]))
            self.assertTrue(registry["documents"][digest]["parser_text_cached"])

            update_ocr_status(output_dir, {digest: "passed"})
            result = verify_pdf_html_ocr(output_dir, ocr=lambda _: self.fail("old hash was OCRed"))
            self.assertTrue(result["passed"])
            self.assertEqual(result["documents_ocr_checked"], 0)
            self.assertEqual(result["documents_ocr_skipped"], 1)

            cache_path = output_dir / "cache" / f"{digest}.json"
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
            cache["parser_text"] += "tampered"
            cache_path.write_text(json.dumps(cache), encoding="utf-8")
            self.assertIsNone(read_cached_pdf_text(pdf_path, root))


if __name__ == "__main__":
    unittest.main()
