from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from flows.modules.order_document_reader import (
    _requires_visual_fallback,
    parse_jd_pdf_page,
    parse_order_rows,
)
from flows.modules.order_json_reader import read_order_json_records
from flows.modules.order_review_html import write_order_review_html


class OrderDocumentReaderTests(unittest.TestCase):
    def test_visual_fallback_skips_footer_but_accepts_unreadable_page(self) -> None:
        self.assertFalse(_requires_visual_fallback("购物指南 售后服务 Copyright 2026"))
        self.assertTrue(_requires_visual_fallback(""))
        self.assertTrue(_requires_visual_fallback("2026-01-02 10:11:12 订单文本乱码"))

    def test_parses_jd_pdf_order_and_split_parent(self) -> None:
        text = """
2025-01-02 10:11:12  订单号： 12345678901  京东
资产中心                 示例商品全名  红色  x2       示例收货人   ¥88.50  已完成
2025-01-03 11:12:13  订单号： 12345678902  您订单中的商品在不同库房
收货人：示例      订单金额：¥128.00      支付方式: 在线支付  订单状态：已拆分
"""

        orders = parse_jd_pdf_page(Path("sample.pdf"), 3, text)

        self.assertEqual(len(orders), 2)
        self.assertEqual(orders[0]["title"], "示例商品全名 红色")
        self.assertEqual(orders[0]["paid_amount"], "88.50")
        self.assertEqual(orders[0]["quantity"], "2")
        self.assertEqual(orders[0]["source_records"][0]["page_number"], 3)
        self.assertEqual(orders[1]["title"], "拆分订单")
        self.assertEqual(orders[1]["status"], "已拆分")
        self.assertTrue(orders[1]["is_container"])

    def test_order_json_resolves_original_image_for_hashing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            raw_root = Path(directory)
            json_root = raw_root / "order_json"
            platform_dir = json_root / "pdd"
            image_dir = raw_root / "pdd"
            platform_dir.mkdir(parents=True)
            image_dir.mkdir()
            image = image_dir / "sample.png"
            image.write_bytes(b"sample-image")
            (platform_dir / "sample.json").write_text(
                json.dumps(
                    {
                        "platform": "pdd",
                        "source_image": "sample.png",
                        "orders": [{"title": "示例商品", "paid_amount": "10.00"}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            orders, _stats = read_order_json_records(json_root, ["pdd"])

        self.assertEqual(len(orders), 1)
        self.assertEqual(Path(orders[0]["source_image"]), image)
        self.assertEqual(Path(orders[0]["source_records"][0]["source_image"]), image)

    def test_parses_generic_order_spreadsheet_rows(self) -> None:
        orders = parse_order_rows(
            Path("sample.xlsx"),
            "meituan",
            [
                {
                    "下单时间": "2025-02-03 09:10:11",
                    "订单号": "demo-1",
                    "店铺名称": "示例店铺",
                    "商品全名": "示例套餐",
                    "实付金额": "36.80",
                    "数量": "1",
                    "订单状态": "已完成",
                }
            ],
            "Orders",
            4,
        )

        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0]["platform"], "meituan")
        self.assertEqual(orders[0]["paid_amount"], "36.80")
        self.assertEqual(orders[0]["source_records"][0]["sheet"], "Orders")
        self.assertEqual(orders[0]["source_records"][0]["row"], 4)

    def test_order_review_html_contains_filters_and_source_opening(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "orders_full_review.html"
            write_order_review_html(
                [
                    {
                        "order_record_id": "order_demo",
                        "platform": "jd",
                        "order_time": "2025-01-02 10:11:12",
                        "paid_amount": "88.50",
                        "merchant": "示例商户",
                        "title": "示例商品",
                        "status": "已完成",
                        "source_records": [
                            {"source_type": "order_pdf", "source_file": "sample.pdf", "page_number": 3}
                        ],
                    }
                ],
                output,
            )
            html = output.read_text(encoding="utf-8")

        self.assertIn("购物订单完整人工审核集", html)
        self.assertIn("实付金额", html)
        self.assertIn("/open-source", html)
        self.assertIn("示例商品", html)


if __name__ == "__main__":
    unittest.main()
