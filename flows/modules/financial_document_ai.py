from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any, Mapping

from flows.modules.bank_transaction_schema import make_transaction, parse_decimal
from flows.modules.config_loader import as_bool, as_int
from flows.modules.json_extractor import parse_json_from_text
from flows.modules.llamacpp_client import LlamaCppClient, LlamaCppConfig


logger = logging.getLogger(__name__)


class FinancialDocumentAiFallback:
    """On-demand local-AI fallback for document layouts deterministic parsers cannot handle."""

    def __init__(self, config: Mapping[str, Any], project_root: Path) -> None:
        raw = config.get("financial_document_ai_fallback", {})
        section = raw if isinstance(raw, Mapping) else {}
        self.enabled = as_bool(section.get("enabled", False))
        self.max_documents = max(0, as_int(section.get("max_documents"), 10))
        self.max_chars = max(1000, as_int(section.get("max_chars"), 24000))
        self.max_tokens = max(256, as_int(section.get("max_tokens"), 4096))
        self.ocr_enabled = as_bool(section.get("ocr_enabled", True))
        self.ocr_max_pages = max(1, as_int(section.get("ocr_max_pages"), 20))
        self.ocr_dpi = max(96, as_int(section.get("ocr_dpi"), 144))
        self.client = LlamaCppClient(LlamaCppConfig.from_config(dict(config), project_root))
        self._checked = False
        self._check_attempted = False
        self._check_error = ""
        self.documents_attempted = 0
        self.documents_succeeded = 0
        self.ocr_documents_attempted = 0
        self.ocr_pages_attempted = 0
        self.ocr_pages_succeeded = 0

    def parse(
        self,
        *,
        text: str,
        bank_key: str,
        bank_name: str,
        source_record: dict[str, Any],
        source_label: str,
    ) -> list[dict[str, Any]]:
        if not self.enabled or not text.strip() or self.documents_attempted >= self.max_documents:
            return []
        self.documents_attempted += 1
        self._ensure_available()
        prompt = _build_prompt(text[: self.max_chars], bank_key, bank_name, source_label)
        response = self.client.chat(prompt, max_tokens=self.max_tokens)
        transactions = _response_to_transactions(
            response,
            bank_key,
            bank_name,
            source_record,
        )
        self.documents_succeeded += 1
        logger.info(
            "Local AI fallback parsed document: source=%s bank=%s transactions=%s",
            source_label,
            bank_key,
            len(transactions),
        )
        return transactions

    def parse_pdf(
        self,
        *,
        path: Path,
        text: str,
        bank_key: str,
        bank_name: str,
        source_record: dict[str, Any],
        source_label: str,
    ) -> list[dict[str, Any]]:
        if not self.enabled or self.documents_attempted >= self.max_documents:
            return []
        self.documents_attempted += 1
        self._ensure_available()
        del text  # PDF 的 AI 回退直接走视觉 OCR，避免重复且不稳定的文本请求。
        if not self.ocr_enabled:
            return []

        self.ocr_documents_attempted += 1
        transactions: list[dict[str, Any]] = []
        last_error: Exception | None = None
        successful_pages = 0
        with tempfile.TemporaryDirectory(prefix="financial_pdf_ocr_") as directory:
            images = _render_pdf_pages(
                path,
                Path(directory),
                max_pages=self.ocr_max_pages,
                dpi=self.ocr_dpi,
            )
            for page_number, image_path in enumerate(images, start=1):
                self.ocr_pages_attempted += 1
                try:
                    response = self.client.chat_with_image(
                        _build_ocr_prompt(bank_key, bank_name, source_label, page_number),
                        image_path,
                        max_tokens=self.max_tokens,
                    )
                    page_source = {**source_record, "page_number": page_number}
                    transactions.extend(
                        _response_to_transactions(
                            response,
                            bank_key,
                            bank_name,
                            page_source,
                        )
                    )
                    successful_pages += 1
                    self.ocr_pages_succeeded += 1
                except Exception as exc:
                    last_error = exc
                    logger.warning(
                        "Local AI OCR failed: source=%s page=%s error=%s",
                        path,
                        page_number,
                        type(exc).__name__,
                    )
        if successful_pages:
            self.documents_succeeded += 1
            logger.info(
                "Local AI OCR parsed PDF: source=%s pages=%s transactions=%s",
                path,
                successful_pages,
                len(transactions),
            )
            return transactions
        if last_error is not None:
            raise last_error
        return []

    def stats(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "documents_attempted": self.documents_attempted,
            "documents_succeeded": self.documents_succeeded,
            "ocr_enabled": self.ocr_enabled,
            "ocr_documents_attempted": self.ocr_documents_attempted,
            "ocr_pages_attempted": self.ocr_pages_attempted,
            "ocr_pages_succeeded": self.ocr_pages_succeeded,
        }

    def _ensure_available(self) -> None:
        if self._checked:
            return
        if self._check_attempted:
            raise RuntimeError(self._check_error or "local AI availability check failed")
        self._check_attempted = True
        try:
            _health, models = self.client.ensure_server()
            self.client.assert_model_available(models)
            self._checked = True
        except Exception as exc:
            self._check_error = f"{type(exc).__name__}: {exc}"
            raise


def _build_prompt(text: str, bank_key: str, bank_name: str, source_label: str) -> str:
    return f"""你是本机财务文档解析器。只提取逐笔交易，不得把余额、信用额度、可用额度、账单合计、
本期应还或最低还款额当成交易。无法确认的字段使用空字符串，不要猜测。
返回严格 JSON 对象：
{{"transactions":[{{"transaction_time":"YYYY-MM-DD HH:MM:SS 或 YYYY-MM-DD","posting_date":"YYYY-MM-DD 或空",
"amount":"绝对金额","direction":"inflow|outflow|unknown","merchant":"商户名称或空","counterparty":"对方户名或空",
"counterparty_account":"对方账号或空","channel":"交易渠道或空","summary":"",
"account_full_name":"完整账户名称或号码，原文没有则为空","account_tail":"仅四位或空","currency":"CNY","transaction_reference":""}}]}}
银行代码：{bank_key}；银行名称：{bank_name}；来源类型：{source_label}
文档内容：
---
{text}
---"""


def _build_ocr_prompt(
    bank_key: str,
    bank_name: str,
    source_label: str,
    page_number: int,
) -> str:
    return f"""请直接读取这张银行文档页面图片并提取逐笔交易。不要把余额、额度、账单合计、
本期应还或最低还款额当成交易。无法确认的字段使用空字符串，不要猜测。
返回严格 JSON 对象，不要 Markdown：
{{"transactions":[{{"transaction_time":"YYYY-MM-DD HH:MM:SS 或 YYYY-MM-DD","posting_date":"YYYY-MM-DD 或空",
"amount":"绝对金额","direction":"inflow|outflow|unknown","merchant":"商户名称或空","counterparty":"对方户名或空",
"counterparty_account":"对方账号或空","channel":"交易渠道或空","summary":"",
"account_full_name":"完整账户名称或号码，原图没有则为空","account_tail":"仅四位或空","currency":"CNY","transaction_reference":""}}]}}
银行代码：{bank_key}；银行名称：{bank_name}；来源类型：{source_label}；PDF 页码：{page_number}
"""


def _render_pdf_pages(
    path: Path,
    output_dir: Path,
    *,
    max_pages: int,
    dpi: int,
) -> list[Path]:
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PyMuPDF is required for local AI PDF OCR") from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    scale = dpi / 72
    images: list[Path] = []
    with fitz.open(path) as document:
        for index, page in enumerate(document):
            if index >= max_pages:
                break
            pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            image_path = output_dir / f"page_{index + 1:04d}.png"
            pixmap.save(image_path)
            images.append(image_path)
    return images


def _response_to_transactions(
    response: str,
    bank_key: str,
    bank_name: str,
    source_record: dict[str, Any],
) -> list[dict[str, Any]]:
    payload = parse_json_from_text(response)
    rows = payload.get("transactions", [])
    if not isinstance(rows, list):
        raise ValueError("AI financial document response must contain a transactions list")
    transactions = [
        _row_to_transaction(row, bank_key, bank_name, source_record)
        for row in rows
        if isinstance(row, dict)
    ]
    return [item for item in transactions if item is not None]


def _row_to_transaction(
    row: dict[str, Any],
    bank_key: str,
    bank_name: str,
    source_record: dict[str, Any],
) -> dict[str, Any] | None:
    amount = parse_decimal(str(row.get("amount", "")))
    if amount is None or amount == 0:
        return None
    direction = str(row.get("direction", "unknown"))
    if direction not in {"inflow", "outflow", "unknown"}:
        direction = "unknown"
    account_tail = "".join(char for char in str(row.get("account_tail", "")) if char.isdigit())[-4:]
    return make_transaction(
        bank_key=bank_key,
        bank_name=bank_name,
        account_full_name=str(row.get("account_full_name", "")).strip(),
        account_tail=account_tail,
        transaction_time=str(row.get("transaction_time", "")).strip(),
        posting_date=str(row.get("posting_date", "")).strip(),
        direction=direction,
        amount=amount,
        currency=str(row.get("currency", "CNY")).strip() or "CNY",
        merchant=str(row.get("merchant", "")).strip(),
        counterparty=str(row.get("counterparty", "")).strip(),
        counterparty_account=str(row.get("counterparty_account", "")).strip(),
        summary=str(row.get("summary", "")).strip(),
        channel=str(row.get("channel", "")).strip(),
        transaction_reference=str(row.get("transaction_reference", "")).strip(),
        source_records=[source_record],
        confidence=0.68,
        warnings=["parsed_by_local_ai", "requires_human_review"],
        raw_record={"parser": "local_ai_fallback"},
    )
