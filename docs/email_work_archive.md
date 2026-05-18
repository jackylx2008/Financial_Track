# 邮件流水工作归档

更新日期：2026-05-17

本文档归档邮件流水链路阶段性工作记录。当前继续开发时，主入口文档为根目录 `README.md` 和 `TODO.md`。

## 目标和边界

邮件流水链路负责从邮箱附件和邮件正文中获取资金流水，完成附件密码处理、解密/解压、内容读取、统一流水归一和去重。

它不直接承担最终财务分类，也不直接替代订单数据。银行、支付宝、美团等邮件流水先进入 normalized 层，后续再和订单中间层做匹配，并进入最终 ledger 层。

真实邮件、附件、日志、密码和整理后的原始数据只保留在本机 `raw_data/`、`log/` 和本地 env 文件中，不提交到 git。

## 入口和目录

根目录邮件流水入口：

```powershell
python financial_email_bot.py
```

邮件流水工作代码目录：

```text
financial_email_workflow/
  gpu_zip_pdf_cracker.py
  financial_attachment_prepare.py
  financial_attachment_extract.py
  consolidate_bank_transactions.py
```

核心业务模块：

```text
src/localai/flows/
  financial_email_ingest.py
  financial_attachment_prepare.py
  financial_attachment_extract.py
  bank_transaction_consolidate.py

src/localai/modules/
  financial_email_config.py
  financial_email_imap.py
  financial_email_parser.py
  financial_email_record_reader.py
  financial_attachment_inventory.py
  financial_attachment_passwords.py
  financial_attachment_extractor.py
  financial_attachment_reader.py
  bank_transaction_schema.py
  bank_transaction_deduper.py
  bank_transaction_quality_report.py
```

命名已经从 `bank_email` / `bank_attachment` / `email_bank` 收敛为：

```text
financial_email
financial_attachment
raw_data/financial_email
FINANCIAL_EMAIL_*
FINANCIAL_ATTACHMENT_*
```

`bank_transaction_*` 保留，因为它表示归一化后的银行交易流水 schema 和去重逻辑。

## 标准工作流

完整链路：

```powershell
python financial_email_bot.py --stage ingest
python financial_email_bot.py --stage prepare
python financial_email_bot.py --stage crack
python financial_email_bot.py --stage extract
python financial_email_bot.py --stage normalize
```

也可以直接运行：

```powershell
python financial_email_bot.py --stage all
```

常用数据路径：

```text
raw_data/financial_email/financial_email_records.jsonl
raw_data/financial_email/attachment_inventory.json
raw_data/financial_email/extracted_attachments/attachment_extract_manifest.json
processed_data/normalized/bank_transactions.jsonl
processed_data/normalized/bank_transactions.json
processed_data/normalized/bank_transactions_quality_report.md
```

## 附件密码和破解

附件密码保存到：

```text
financial_attachment_passwords.env
```

模板文件：

```text
financial_attachment_passwords.env.example
```

主要配置：

```env
FINANCIAL_ATTACHMENT_PASSWORD_DEFAULT=
FINANCIAL_ATTACHMENT_PASSWORD_BY_BANK_JSON={}
FINANCIAL_ATTACHMENT_PASSWORD_BY_FILENAME_JSON={}
FINANCIAL_ATTACHMENT_PASSWORD_BY_PATTERN_JSON={}
FINANCIAL_ATTACHMENT_PASSWORD_BY_TYPE_JSON={"pdf":[],"zip":[]}
FINANCIAL_ATTACHMENT_PDF_PWD=[]
FINANCIAL_ATTACHMENT_ZIP_PWD=[]
```

已破解成功的 ZIP/PDF 密码会合并保存到 `financial_attachment_passwords.env`。后续运行 `python financial_email_bot.py --stage crack` 会先尝试已保存密码，已经能用保存密码解开的附件不会重复破解。

hashcat / john 工具路径放在 `config.yaml` 的 `financial_attachment_cracker` 下。

## 阶段完成状态

截至 2026-05-17，底层邮件流水链路已经跑通：

- 附件清单阶段：17 个附件，17 个均已匹配密码。
- 附件提取阶段：17 个附件，17 个成功解密/解压，失败 0 个。
- 破解阶段：当前显示“没有需要破解的附件”，说明已知密码可以覆盖现有目标。
- 归一阶段：可正常读取邮件正文候选交易和附件提取结果。

最近一次验证结果：

```text
prepare:
  attachments: 17
  encrypted_or_maybe_encrypted: 17
  password_configured: 17

extract:
  attachments: 17
  success: 17
  failed: 0

normalize:
  raw_transactions: 14350
  deduped_transactions: 11936
  email_transactions: 4140
  attachment_transactions: 10210
```

旧文档中“仍有 6 个附件未解密”的状态已经过期。

## 当前解析能力

已覆盖的来源：

- 邮件正文：读取 `candidate_transactions`，作为低置信度补充来源。
- PDF：已支持部分银行流水 PDF 的文本读取和交易字段提取。
- ZIP：已支持解密/解压后继续读取内部文件。
- XLS：已支持建设银行交易明细类 XLS。
- CSV：已开始支持支付宝、美团等 CSV 明细类附件。

归一化记录包含：

- `transaction_id`
- `bank_key`
- `bank_name`
- `account_key`
- `account_tail`
- `transaction_time`
- `posting_date`
- `direction`
- `amount`
- `signed_amount`
- `currency`
- `merchant`
- `counterparty`
- `summary`
- `balance`
- `channel`
- `transaction_reference`
- `source_records`
- `confidence`
- `warnings`
- `raw_record`

去重策略：

- 有交易参考号时优先按参考号合并。
- 无参考号时按银行、账户、日期、方向、金额、交易对方或摘要合并。
- 合并后保留所有 `source_records`，方便回查原始邮件、附件、PDF 页或表格行。
- 字段冲突写入 `warnings`，进入质量报告。

## 已验证命令

邮件流水链路：

```powershell
python -m py_compile financial_email_bot.py financial_email_workflow\gpu_zip_pdf_cracker.py financial_email_workflow\financial_attachment_prepare.py financial_email_workflow\financial_attachment_extract.py financial_email_workflow\consolidate_bank_transactions.py
python financial_email_bot.py --stage prepare
python financial_email_bot.py --stage crack
python financial_email_bot.py --stage extract
python financial_email_bot.py --stage normalize
```

安卓截图入口：

```powershell
python -m py_compile pdd_order_bot.py meituan_order_bot.py android_order_workflow\android_order_bot.py
python pdd_order_bot.py --help
python meituan_order_bot.py --help
```

## 后续参考

底层邮件流水链路已经完成，剩余工作主要在更上层：

- 扩展更多银行、支付宝、美团等附件格式 parser。
- 提升邮件正文模板解析质量，减少缺交易时间、账户尾号的低置信度记录。
- 将归一化流水和订单中间层做金额、时间、商户匹配。
- 识别账户间转移、信用卡还款、支付宝/微信/银行卡之间的资金中转。
- 识别退款、报销、工资、投资、手续费、利息等财务语义。
- 输出最终账本、消费分类报表和人工复核闭环。

继续分析邮件流水质量时，优先查看：

```text
processed_data/normalized/bank_transactions_quality_report.md
```
