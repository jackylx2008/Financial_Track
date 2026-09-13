# Financial Track 项目进度

更新时间：2026-05-25

## 当前定位

Financial Track 是个人消费与银行流水的本地化采集、整理和账本构建工具。项目坚持本地优先：真实账单、订单截图、邮箱授权码、附件密码、浏览器登录态和模型路径都留在本机，不进入版本库。

## 已完成能力

- 京东订单页通过 Playwright 导出 PDF，保留浏览器登录态复用能力。
- 淘宝订单页通过 `pyautogui` 半自动打印 PDF，适合人工可控的批量归档。
- 拼多多、美团通过 ADB 截图，支持单张、固定页数滚动和自动滚动到底。
- 拼多多、美团截图可调用外部项目提供的 OpenAI 兼容视觉模型识别为订单 JSON。
- 邮件流水可通过 IMAP 或本地 `.eml` 导入，保存原文、正文、附件和候选交易。
- 邮件附件支持密码清单准备、按密码规则解密/解压，以及可选 GPU 破解阶段。
- 银行流水和订单 JSON 已汇总到 `processed_data/normalized/` 中间层。
- 已建立 `financial_transactions` 财务事实层和 `financial_transaction_links` 订单/付款关联层。
- 已实现最终账本 `ledger` 构建，账本以银行/支付流水为主，订单只补充消费明细。
- 已实现按月份拆分的人工校核 Excel：`processed_data/review/ledger_review.xlsx`。

## 主要入口

```text
flows/financial_email_bot.py         # 邮件流水采集、附件处理、银行流水归一化
flows/order_image_ai.py              # 订单截图 AI 识别
flows/normalize_transactions.py      # 统一 normalized 中间层
flows/ledger_build.py                 # 最终账本构建
flows/ledger_review_export.py         # 人工校核 Excel 导出
```

## 推荐运行顺序

```powershell
python flows/financial_email_bot.py --stage all --skip-crack
python flows/order_image_ai.py pdd --all --max-tokens 1024
python flows/order_image_ai.py meituan --all --max-tokens 1024
python flows/normalize_transactions.py
python flows/ledger_build.py
python flows/ledger_review_export.py
```

需要破解账单附件密码时，先确认 `config.yaml` 中的 hashcat/john 路径，再运行：

```powershell
python flows/financial_email_bot.py --stage crack
python flows/financial_email_bot.py --stage prepare
python flows/financial_email_bot.py --stage extract
python flows/financial_email_bot.py --stage normalize
```

## 当前数据产物

```text
raw_data/financial_email/financial_email_records.jsonl
raw_data/financial_email/attachment_inventory.json
raw_data/financial_email/extracted_attachments/attachment_extract_manifest.json
raw_data/order_json/pdd/
raw_data/order_json/meituan/
processed_data/normalized/bank_transactions.jsonl
processed_data/normalized/orders.jsonl
processed_data/normalized/financial_transactions.jsonl
processed_data/normalized/financial_transaction_links.jsonl
processed_data/ledger/ledger_entries.jsonl
processed_data/ledger/ledger_entries.json
processed_data/ledger/ledger_quality_report.md
processed_data/review/ledger_review.xlsx
```

## 已知限制

- 京东、淘宝目前以 PDF 归档为主，尚未完成订单级结构化解析。
- 视觉模型识别订单截图时仍可能漏读金额、订单号或截断内容，需要抽样复核。
- 银行邮件正文候选交易通常字段不完整，附件解析结果比正文正则候选更可靠。
- 最终账本分类仍以规则为主，复杂场景需要人工校核或后续补充规则。
- 人工校核 Excel 已能导出，但人工修正回读为 `manual_overrides.json` 的闭环仍未完成。
- 统计报表 `flows/ledger_report_export.py` 尚未实现。

## 下一步

1. 实现 `ledger_review_import.py`，读取人工校核 Excel 并生成 `processed_data/ledger/manual_overrides.json`。
2. 在 `flows/ledger_build.py` 中优先应用人工修正，形成可迭代的账本校核闭环。
3. 实现 `flows/ledger_report_export.py`，输出总览、按月、按日、分类、人员、项目等统计报表。
4. 持续根据人工校核结果完善分类关键词和目标人识别规则。
5. 推进京东、淘宝 PDF 的订单级结构化解析，并接入统一订单 schema。

## Git 同步注意

提交前必须确认不会包含以下本地隐私数据：

```text
common.env
financial_attachment_passwords.env
raw_data/
processed_data/
logs/
vendor/
浏览器 profile、订单截图、账单 PDF、邮箱附件、授权码和密码
```

本次文档同步目标是让 README 和项目进度文件反映当前代码实际能力，便于后续继续实现人工校核回读和统计报表。
