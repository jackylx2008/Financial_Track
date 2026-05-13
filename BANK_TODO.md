# BANK_TODO：银行邮件流水整理与去重

## 目标

通过 `bank_email_bot.py` 已经可以从 126 邮箱读取银行邮件，并保存 `.eml`、正文、附件和候选交易信息。下一阶段目标是把这些邮件来源的银行流水整理成统一、可追溯、可去重、适合财务分解的银行交易中间层。

银行流水不要直接塞进平台订单 schema。订单是消费明细来源，银行流水是资金账户变动来源；两者应先分别清洗，再在后续财务分解阶段做匹配。

## 推荐数据流

```text
raw_data/email_bank/
  eml/ body/ attachments/ bank_email_records.jsonl
    -> 邮件/PDF/ZIP 解析结果 raw records
    -> 统一银行流水 schema
    -> 去重合并
    -> 财务分解、分类、订单匹配
```

原则：

- 原始 `.eml`、正文文本、附件不删除。
- 去重只发生在 normalized 层。
- 每条去重后的流水都必须保留 `source_records`，能回查到邮件、附件、PDF 页或原始候选记录。

## 统一银行流水 Schema

建议字段：

- `transaction_id`：内部生成的稳定 ID。
- `bank_key`：银行标识，例如 `cmb`、`icbc`、`ccb`。
- `bank_name`
- `account_key`：`bank_key + account_tail/account_alias` 派生出的账户标识。
- `account_tail`：卡号或账号后四位。
- `transaction_time`：实际交易时间。
- `posting_date`：入账/记账日期，可空。
- `direction`：`inflow`、`outflow`、`unknown`。
- `amount`：正数金额。
- `signed_amount`：支出为负，收入为正。
- `currency`：默认 `CNY`。
- `merchant`
- `counterparty`
- `summary`：银行原始摘要。
- `balance`
- `channel`：支付宝、微信、POS、网银、ATM 等。
- `transaction_reference`：银行交易流水号、回单编号、参考号，可空。
- `source_records`：多个来源引用。
- `confidence`
- `warnings`
- `raw_record`

`source_records` 示例：

```json
[
  {
    "source_type": "email_body",
    "source_file": "raw_data/email_bank/eml/xxx.eml",
    "message_id": "...",
    "message_uid": "..."
  },
  {
    "source_type": "email_attachment_pdf",
    "source_file": "raw_data/email_bank/attachments/xxx/statement.pdf",
    "page": 2
  }
]
```

## 去重策略

按优先级生成去重 key。

### 1. 强唯一键

如果存在银行交易流水号、回单编号、参考号：

```text
bank_key + account_key + transaction_reference
```

### 2. 强匹配键

没有流水号时，使用：

```text
bank_key + account_key + transaction_date + amount + direction + normalized_party
```

其中 `normalized_party` 来自商户、对方户名、摘要中的主要名称。

### 3. 模糊匹配键

时间不精确或来源口径不一致时：

```text
同银行
同账户
同金额
同方向
交易时间相差 <= 1 天
摘要/商户/对方名称高度相似
```

### 4. 邮件正文与附件重复

同一笔流水可能同时出现在：

- 实时交易提醒邮件正文。
- 月度账单 PDF。
- 电子回单 PDF。
- 银行流水 PDF。
- ZIP 附件中的 PDF 或 Excel。

这种情况应合并为一条交易，并保留多个来源。

## 合并规则

同一笔交易重复出现时，不是简单保留第一条，而是字段互补合并。

建议优先级：

- 实时交易提醒邮件：交易时间通常更准，商户信息可能更及时。
- 月度账单 PDF：金额、入账日、账单期通常更权威。
- 电子回单 PDF：交易编号、对方账户、对方户名通常更权威。
- 银行流水 PDF/Excel：余额、账户维度、正式摘要通常更完整。

合并时：

- 保留最完整字段。
- 冲突字段写入 `warnings`。
- 所有来源写入 `source_records`。
- 如果一个来源只有邮件标题或摘要，没有金额，不应生成正式交易，只作为辅助来源或质量报告项。

## 财务分解注意事项

去重后的银行流水再进入财务分解，不要在原始解析阶段直接分类。

建议分解类型：

- 消费支出：尝试匹配京东、淘宝、拼多多、美团订单。
- 转账：个人往来、家庭转账、账户间调拨。
- 信用卡还款：账户间转移，不算消费。
- 工资、报销、退款：收入或冲减支出。
- 理财、基金、证券：投资账户变动。
- 手续费、利息：金融费用或收入。

重要边界：

- 信用卡消费和储蓄卡还信用卡不是同一笔消费。前者是消费，后者是账户间转移。
- 支付宝、微信、银行卡可能都出现同一消费链路，后续需要订单匹配和账户转移识别。
- 退款应优先匹配原消费；匹配不上时作为独立收入或冲减支出待人工复核。

## 建议新增代码结构

沿用当前项目“入口脚本 + flows + modules”的结构。

```text
consolidate_bank_transactions.py
src/localai/flows/bank_transaction_consolidate.py
src/localai/modules/bank_transaction_schema.py
src/localai/modules/bank_email_record_reader.py
src/localai/modules/bank_attachment_reader.py
src/localai/modules/bank_transaction_normalizer.py
src/localai/modules/bank_transaction_deduper.py
src/localai/modules/bank_transaction_quality_report.py
```

职责划分：

- `consolidate_bank_transactions.py`
  - 根目录入口脚本。
  - 读取命令行参数、加载配置、调用 flow、打印摘要。
- `bank_transaction_consolidate.py`
  - 编排读取、标准化、去重、输出、质量报告。
- `bank_transaction_schema.py`
  - 定义统一流水字段、默认值、类型转换。
- `bank_email_record_reader.py`
  - 读取 `raw_data/email_bank/bank_email_records.jsonl`。
  - 将 `candidate_transactions` 转为流水草稿。
- `bank_attachment_reader.py`
  - 后续解析 PDF、ZIP、Excel 附件。
- `bank_transaction_normalizer.py`
  - 统一金额、时间、方向、账户、摘要、来源字段。
- `bank_transaction_deduper.py`
  - 实现强唯一键、强匹配键、模糊匹配和字段合并。
- `bank_transaction_quality_report.py`
  - 输出 Markdown 质量报告。

## 第一版实现范围

第一版先不要解析 PDF 附件内容，先基于 `bank_email_records.jsonl` 中已有 `candidate_transactions` 做统一和去重。

范围：

1. 新增统一银行流水 schema。
2. 读取 `raw_data/email_bank/bank_email_records.jsonl`。
3. 展开每条邮件的 `candidate_transactions`。
4. 标准化金额、方向、交易时间、卡尾号、银行、来源。
5. 去重合并。
6. 输出 JSONL/JSON。
7. 输出质量报告。

第一版暂不实现：

- PDF 账单解析。
- ZIP 解压和附件内部解析。
- AI 读取 PDF。
- 和电商订单匹配。
- 最终财务分类报表。

## 建议输出

```text
raw_data/normalized/bank_transactions.jsonl
raw_data/normalized/bank_transactions.json
raw_data/normalized/bank_transactions_quality_report.md
```

质量报告至少包含：

- 读取的邮件记录数。
- 候选交易数。
- 标准化成功数。
- 去重前流水数。
- 去重后流水数。
- 按银行统计数量。
- 按账户尾号统计数量。
- 缺金额数量。
- 缺方向数量。
- 缺交易时间数量。
- 缺账户尾号数量。
- 合并来源数量分布。
- 字段冲突记录列表。
- 需要人工复核记录列表。

## 第一版验收标准

可以运行：

```powershell
python consolidate_bank_transactions.py
```

默认读取：

```text
raw_data/email_bank/bank_email_records.jsonl
```

默认输出：

```text
raw_data/normalized/bank_transactions.jsonl
raw_data/normalized/bank_transactions.json
raw_data/normalized/bank_transactions_quality_report.md
```

输出要求：

- 每条记录包含统一 schema 字段。
- 每条记录能追溯到原始邮件和候选交易。
- 去重前后数量清楚。
- 重复交易合并后保留所有来源。
- 缺字段、冲突字段、低质量交易进入质量报告。
- 不提交任何真实银行数据、邮件、附件或日志到版本库。

## 后续扩展顺序

1. 完成第一版 `candidate_transactions` 标准化与去重。
2. 增加附件密码准备层：独立 `bank_attachment_passwords.env`、附件清单、密码匹配检查。
3. 增加 ZIP 附件解压与附件清单索引。
4. 增加 PDF 文本解析和密码解密能力。
5. 对重点银行增加专用账单 parser。
6. 将银行流水与订单中间层做金额、时间、商户匹配。
7. 增加账户间转移识别，尤其是信用卡还款。
8. 输出财务分解层和消费分类报表。

## 附件密码准备

银行邮件附件中的 ZIP、PDF 通常带密码。密码不能写入代码、日志或普通数据产物，建议放在独立本地文件：

```text
bank_attachment_passwords.env
```

该文件应被 `.gitignore` 排除。模板文件：

```text
bank_attachment_passwords.env.example
```

支持的密码配置：

```env
BANK_ATTACHMENT_PASSWORD_DEFAULT=
BANK_ATTACHMENT_PASSWORD_BY_BANK_JSON={"cmb":"password"}
BANK_ATTACHMENT_PASSWORD_BY_FILENAME_JSON={"statement.pdf":"password"}
BANK_ATTACHMENT_PASSWORD_BY_PATTERN_JSON={"招商":"password","账单":"password"}
BANK_ATTACHMENT_PASSWORD_BY_TYPE_JSON={"pdf":["password1","password2"],"zip":["password1","password2"]}
BANK_ATTACHMENT_PDF_PWD=["password1","password2"]
BANK_ATTACHMENT_ZIP_PWD=["password1","password2"]
```

准备命令：

```powershell
python bank_attachment_prepare.py
```

输出：

```text
raw_data/email_bank/attachment_inventory.json
raw_data/email_bank/attachment_inventory.md
```

清单只输出：

- 附件路径。
- 附件类型。
- 是否存在。
- ZIP 是否加密。
- PDF 是否可能加密。
- 是否已配置可匹配密码。
- 密码匹配来源，例如 `bank:cmb`、`filename`、`pattern:招商`、`default`。
- 候选密码数量。

清单不得输出真实密码。
