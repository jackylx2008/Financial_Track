from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from flows.modules.pdf_table_html import export_pdf_tables, read_cached_pdf_text


class PdfTableHtmlTests(unittest.TestCase):
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

            self.assertEqual(first["converted"], 1)
            self.assertEqual(first["reused"], 0)
            self.assertEqual(first["rows"], 2)
            self.assertEqual(second["converted"], 0)
            self.assertEqual(second["reused"], 1)
            self.assertIn("Sample purchase", html)
            self.assertIn("/open-source", html)
            self.assertIn("SHA-256", html)
            self.assertIn("Sample purchase", read_cached_pdf_text(pdf_path, root) or "")


if __name__ == "__main__":
    unittest.main()
