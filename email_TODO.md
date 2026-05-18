# email_TODO：邮件流水后续工作

更新日期：2026-05-17

## 当前状态

底层邮件流水链路已经完成并可重复运行：

```powershell
python financial_email_bot.py --stage prepare
python financial_email_bot.py --stage crack
python financial_email_bot.py --stage extract
python financial_email_bot.py --stage normalize
```

当前验证结果：

- 附件清单：17 个附件，17 个已匹配密码。
- 附件提取：17 个附件，17 个成功，失败 0。
- 破解阶段：已有密码覆盖现有附件，当前无待破解目标。
- 归一输出：`raw_transactions=14350`，`deduped_transactions=11936`。

因此以下内容已经不是 TODO：

- 附件密码准备层。
- ZIP/PDF 解密和密码保存。
- 已知密码跳过重复破解。
- 附件解密/解压清单。
- normalized 层统一流水输出。
- 基础去重和质量报告。

## 数据流

```text
raw_data/financial_email/
  eml/
  body/
  attachments/
  financial_email_records.jsonl
  attachment_inventory.json
  extracted_attachments/attachment_extract_manifest.json
    -> 邮件正文候选交易
    -> 附件 PDF/XLS/CSV 明细
    -> normalized bank transactions
    -> 订单匹配、账户转移识别、财务分类
```

原则：

- 原始 `.eml`、正文文本、附件不删除。
- 去重只发生在 normalized 层。
- 每条 normalized 流水保留 `source_records`，能回查到邮件、附件、PDF 页、表格行或原始候选记录。
- 银行/支付流水不要直接塞进订单 schema；订单和资金流水先分别清洗，再在财务分解阶段匹配。

## 当前统一流水输出

默认命令：

```powershell
python financial_email_bot.py --stage normalize
```

默认输入：

```text
raw_data/financial_email/financial_email_records.jsonl
raw_data/financial_email/extracted_attachments/attachment_extract_manifest.json
```

默认输出：

```text
raw_data/normalized/bank_transactions.jsonl
raw_data/normalized/bank_transactions.json
raw_data/normalized/bank_transactions_quality_report.md
```

当前 schema 重点字段：

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

## 后续 TODO

### 1. 扩展附件 parser 覆盖面

目标：让更多 PDF/XLS/CSV 附件稳定转成高质量流水。

优先级：

1. 根据 `bank_transactions_quality_report.md` 中的 warnings 和低置信度来源，定位最影响结果的附件格式。
2. 补充支付宝 CSV parser 的字段完整度：交易号、商户、对方、交易状态、收支方向、资金渠道。
3. 补充美团账单 CSV parser 的字段完整度：订单号、商户、品类、退款、支付方式。
4. 扩展工商银行 PDF parser，覆盖更多历史明细、电子回单、申请单导出格式。
5. 扩展建设银行 ZIP/XLS parser，覆盖不同导出版本。
6. 根据新增样本补其他银行 PDF/XLS parser。

验收：

- 新增 parser 后 `attachment_transactions` 增加或低置信度记录减少。
- 新 parser 输出的记录包含稳定 `source_records`。
- 质量报告能体现缺字段数量下降。

### 2. 提升邮件正文解析质量

现状：邮件正文候选交易数量多，但缺交易时间、账户尾号、方向和摘要结构，置信度偏低。

工作：

1. 针对稳定邮件模板新增专用 parser。
2. 优先处理交易提醒类邮件，因为它们通常交易时间更准。
3. 将只含金额或标题线索的邮件记录降级为辅助来源，不生成正式强流水。
4. 对邮件正文和附件中的同一笔交易做来源合并，而不是生成重复记录。

验收：

- 邮件正文来源的 `warnings` 减少。
- 缺 `transaction_time`、`account_tail`、`direction` 的记录减少。
- 重复交易合并后保留邮件正文和附件两个来源。

### 3. 银行/支付流水与订单匹配

目标：把资金流水和京东、淘宝、拼多多、美团订单中间层匹配起来。

匹配信号：

- 金额相等或接近。
- 交易时间和订单支付时间接近。
- 商户、平台、摘要、支付渠道相似。
- 退款金额与原订单金额相反或部分相反。

需要识别：

- 一笔订单对应一笔银行卡/支付宝/微信支付。
- 多笔订单合并支付。
- 一笔支付拆成优惠、红包、余额、银行卡等多个资金来源。
- 退款对应原订单或部分退款。

验收：

- 输出匹配结果层，保留流水 ID、订单 ID、匹配分数和匹配原因。
- 无法高置信度匹配的记录进入人工复核清单。

### 4. 账户间转移识别

目标：避免把账户调拨误算成消费。

重点类型：

- 储蓄卡还信用卡。
- 银行卡之间转账。
- 支付宝/微信余额提现或充值。
- 家庭成员账户互转。
- 证券、基金、理财账户转入转出。

规则：

- 同金额、相近时间、一出一入，摘要或对方信息相互指向时，标记为账户间转移。
- 信用卡消费和储蓄卡还信用卡不能合并成同一笔消费；前者是消费，后者是还款/账户转移。

验收：

- 输出转移识别结果。
- 被识别为转移的流水不进入普通消费支出汇总。
- 低置信度转移进入人工复核。

### 5. 财务语义分类

目标：在 normalized 流水和订单匹配结果之上，生成财务分解层。

分类方向：

- 消费支出。
- 退款和冲减支出。
- 工资、报销、奖金等收入。
- 信用卡还款。
- 账户间转移。
- 理财、基金、证券等投资资金流。
- 手续费、利息等金融费用或收入。
- 无法判断的待复核记录。

验收：

- 每条流水有财务分类、分类依据、置信度。
- 退款优先匹配原消费；匹配不上时进入复核。
- 分类汇总能按月份、账户、平台、品类输出。

### 6. 报表和人工复核闭环

目标：从 normalized 数据生成可用的财务报表，并支持人工修正。

需要输出：

- 月度收入/支出/转移汇总。
- 平台消费汇总。
- 账户资金流转表。
- 信用卡还款与消费分离报表。
- 退款复核表。
- 低置信度和字段冲突复核表。

复核闭环：

- 人工确认结果保存为独立本地修正文件。
- 重新运行后应用修正，不直接改原始 raw 数据。
- 修正文件可以按流水 ID、订单 ID 或来源引用定位记录。

## 推荐下一步

下一次继续时先看：

```text
raw_data/normalized/bank_transactions_quality_report.md
```

然后按影响面选择一个最值得补的 parser。建议优先顺序：

1. 低置信度数量最多的附件来源。
2. 金额规模较大的未完整解析来源。
3. 能和订单数据形成闭环的平台来源，例如支付宝、美团。

完成一个 parser 后运行：

```powershell
python financial_email_bot.py --stage extract
python financial_email_bot.py --stage normalize
```

对比 `bank_transactions_quality_report.md` 中的数量、缺字段和 warnings 是否改善。
