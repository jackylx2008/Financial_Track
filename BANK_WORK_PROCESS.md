# 银行邮件流水整理工作过程

日期：2026-05-13

## 工作目标

本轮工作围绕两件事推进：

- 将银行邮件附件密码、解密/解压、失败统计流程固化，方便后续补充密码后继续跑。
- 基于已经成功解出的 PDF、ZIP 内部文件和邮件正文候选交易，开始生成统一去重的银行流水中间层。

真实邮件、附件、日志、密码和整理后的原始数据都保留在本机 `raw_data/`、`log/` 和本地 env 文件中，不提交到 git。

## 已完成工程

### 1. 邮件与附件准备链路

保留并整理了银行邮件采集入口：

```powershell
python bank_email_bot.py --since 2016-01-01 --max-messages 800
```

采集结果进入：

```text
raw_data/email_bank/
```

其中包括 `.eml` 原文、正文文本、附件、候选交易 JSONL/JSON 和摘要报告。

### 2. 附件密码配置

附件密码使用独立文件：

```text
bank_attachment_passwords.env
```

模板文件：

```text
bank_attachment_passwords.env.example
```

当前代码只读取新前缀配置，不兼容旧的 `PDF_PWD` / `ZIP_PWD`：

```env
BANK_ATTACHMENT_PDF_PWD=[]
BANK_ATTACHMENT_ZIP_PWD=[]
```

也支持更精细的匹配方式：

```env
BANK_ATTACHMENT_PASSWORD_DEFAULT=
BANK_ATTACHMENT_PASSWORD_BY_BANK_JSON={}
BANK_ATTACHMENT_PASSWORD_BY_FILENAME_JSON={}
BANK_ATTACHMENT_PASSWORD_BY_PATTERN_JSON={}
BANK_ATTACHMENT_PASSWORD_BY_TYPE_JSON={"pdf":[],"zip":[]}
```

日志和报告只记录候选密码数量与匹配来源，不输出真实密码。

### 3. 附件清单与解密/解压

准备附件清单：

```powershell
python bank_attachment_prepare.py
```

尝试解密/解压：

```powershell
python bank_attachment_extract.py
```

本轮测试结果：

- 附件总数：14
- 成功解密/解压：8
- 因密码不匹配失败：6

成功产物包括 PDF 和 ZIP 内部解出的 XLS 文件。失败附件已写入：

```text
raw_data/email_bank/extracted_attachments/attachment_extract_failures.md
```

该报告包含无法解密附件对应的银行、文件名、邮件标题、邮件日期等信息，后续补密码时优先看这个文件。

### 4. 统一银行流水整理链路

新增统一整理入口：

```powershell
python consolidate_bank_transactions.py
```

新增模块结构：

```text
src/localai/flows/bank_transaction_consolidate.py
src/localai/modules/bank_transaction_schema.py
src/localai/modules/bank_email_record_reader.py
src/localai/modules/bank_attachment_reader.py
src/localai/modules/bank_transaction_deduper.py
src/localai/modules/bank_transaction_quality_report.py
```

默认读取：

```text
raw_data/email_bank/bank_email_records.jsonl
raw_data/email_bank/extracted_attachments/attachment_extract_manifest.json
```

默认输出：

```text
raw_data/normalized/bank_transactions.jsonl
raw_data/normalized/bank_transactions.json
raw_data/normalized/bank_transactions_quality_report.md
```

统一流水记录包含：

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

### 5. 当前解析能力

当前第一版已经开始读取已成功解出的附件内容：

- PDF：解析工商银行流水类 PDF 的日期、时间、金额、余额、摘要、渠道和对方信息。
- XLS：解析建设银行 ZIP 中解出的交易明细 XLS。
- 邮件正文：读取 `candidate_transactions`，作为低置信度补充来源。

去重策略：

- 有交易参考号时按参考号合并。
- 无参考号时按银行、账户、日期、方向、金额、交易对方或摘要合并。
- 合并后保留所有 `source_records`。
- 字段冲突写入 `warnings`。

## 本轮验证结果

语法检查：

```powershell
python -m compileall consolidate_bank_transactions.py src\localai\flows\bank_transaction_consolidate.py src\localai\modules\bank_transaction_schema.py src\localai\modules\bank_email_record_reader.py src\localai\modules\bank_attachment_reader.py src\localai\modules\bank_transaction_deduper.py src\localai\modules\bank_transaction_quality_report.py
```

运行整理：

```powershell
python consolidate_bank_transactions.py
```

本轮输出摘要：

- 邮件候选转流水：4140
- 附件转流水：5521
- 去重前流水：9661
- 去重后流水：8399
- 合并重复：1262
- 附件读取文件数：8

质量报告显示：附件解析出的记录质量更高；邮件正文候选大多缺交易时间和账户尾号，当前应作为低置信度来源和人工复核线索，不应直接当成最终账本。

## 当前限制

- 仍有 6 个附件因为密码不匹配没有解出，待补充密码后可重新运行 `bank_attachment_extract.py`。
- 邮件正文候选交易的结构化程度有限，缺交易时间和账户尾号较多。
- PDF parser 当前先覆盖已经成功解析出的工商银行流水格式，其他银行 PDF 需要根据实际样本继续增加专用 parser。
- XLS parser 当前覆盖已经解出的建设银行交易明细格式。
- 当前还没有做订单流水匹配、账户间转移识别、信用卡还款归并和财务分类。

## 下一步建议

1. 补充失败附件对应密码，重新运行：

```powershell
python bank_attachment_prepare.py
python bank_attachment_extract.py
python consolidate_bank_transactions.py
```

2. 优先查看：

```text
raw_data/normalized/bank_transactions_quality_report.md
```

3. 对失败最多、金额较大的银行附件增加专用 parser。

4. 在统一银行流水稳定后，再与京东、淘宝、拼多多、美团订单中间层做金额、时间、商户匹配。
