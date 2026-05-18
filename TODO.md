# TODO：最终账本层与统计报表

## 当前状态

已完成的数据链路：

- 原始数据目录：`raw_data/`
  - 只保存不同渠道采集到的原始数据、附件、截图、邮件、AI JSON 等。
- 归一化和财务中间层目录：`processed_data/normalized/`
  - `bank_transactions.jsonl/json`
  - `orders.jsonl/json`
  - `financial_transactions.jsonl/json`
  - `financial_transaction_links.jsonl/json`
  - 质量报告和汇总报告。
- 人工审核 Excel：`processed_data/review/financial_transactions_review.xlsx`

当前已有能力：

- 邮件附件、银行流水已经整理为统一银行流水 normalized 层。
- PDD、Meituan 订单截图 AI JSON 已整理为统一订单 normalized 层。
- 已建立 `financial_transactions` 财务事实中间层。
- 已建立订单与银行付款的候选/强关联关系。
- 已导出 Excel 供人工查看强关联、候选关联、未匹配订单、银行付款和财务事实。

当前限制：

- 订单不是所有支出的前提。
- 银行流水中存在收入、转账、还款、退款、医院、餐饮、停车费等无订单场景。
- 最终统计不能只依赖订单匹配，应以银行/支付流水为主账本，订单只用于补充购物或服务明细。

## 当前最新进度

已完成：

- 最终账本构建入口：`ledger_build.py`
- 账本构建 flow：`src/localai/flows/ledger_build.py`
- 账本核心模块：
  - `src/localai/modules/ledger_schema.py`
  - `src/localai/modules/ledger_builder.py`
  - `src/localai/modules/ledger_category_rules.py`
  - `src/localai/modules/ledger_order_enricher.py`
  - `src/localai/modules/ledger_quality_report.py`
- 人工校核 Excel 导出入口：`ledger_review_export.py`
- 人工校核 Excel flow：`src/localai/flows/ledger_review_export.py`
- 人工校核 Excel 模块：`src/localai/modules/ledger_review_workbook.py`
- README 已补充 normalized、ledger 和人工校核流程说明。

已验证：

- `python ledger_build.py` 可以生成最终账本。
- `python ledger_review_export.py` 可以生成按月份分 sheet、每个 sheet 内按日期排序的人工校核 Excel。
- 最终账本以银行/支付流水为主来源，订单只用于补充明细，避免重复统计。
- 强关联订单的商户/标题/摘要会参与分类，例如美团付款关联到药房订单后可归入医疗健康。

待完成的主线：

1. 人工校核回读闭环：
   - 读取人工修改后的 `processed_data/review/ledger_review.xlsx`。
   - 生成 `processed_data/ledger/manual_overrides.json`。
   - 下一次 `ledger_build.py` 构建时优先应用人工修正。
2. 统计报表：
   - 新增 `ledger_report_export.py`。
   - 输出 `processed_data/reports/ledger_report.xlsx`。
   - 基于人工修正后的账本生成总览、按月、按日、分类、人员、项目等统计。
3. 规则继续完善：
   - 根据人工校核结果补充关键词规则。
   - 后续可拆出 `ledger_person_rules.py`，专门维护目标人识别规则。

## 下一阶段目标

建立最终账本层 `ledger`，用于按年月日统计收入、支出和分类明细。

目标输出：

```text
processed_data/ledger/ledger_entries.jsonl
processed_data/ledger/ledger_entries.json
processed_data/ledger/ledger_quality_report.md
processed_data/reports/ledger_report.xlsx
```

最终账本每条记录至少包含：

- 日期
- 年月
- 类型：支出 / 收入 / 转账 / 退款 / 还款 / 未知
- 金额
- 收支方向
- 一级分类
- 二级分类
- 花费项目
- 对应人员
- 具体服务或物品
- 支付渠道
- 商户 / 对方
- 原始摘要
- 是否匹配订单
- 关联订单 ID
- 来源流水 ID
- 置信度
- 是否需要人工复核
- 备注

## 设计原则

1. 银行/支付流水是主账本来源。
2. 订单记录只作为补充信息，用来丰富购物、外卖、平台服务类支出的具体物品或服务。
3. 收入、转账、信用卡还款、账户互转不需要订单。
4. 医院、餐饮、停车费、线下消费等无订单支出直接从银行流水摘要分类。
5. 转账和还款默认不计入真实消费支出，避免统计失真。
6. 自动分类必须保留置信度和复核标记。
7. 所有账本条目必须能回溯到 normalized 层和原始数据。

## 推荐代码结构

新增入口：

```text
ledger_build.py
ledger_review_export.py
ledger_review_import.py
ledger_report_export.py
```

新增 flow：

```text
src/localai/flows/ledger_build.py
src/localai/flows/ledger_review_export.py
src/localai/flows/ledger_review_import.py
src/localai/flows/ledger_report_export.py
```

新增 modules：

```text
src/localai/modules/ledger_schema.py
src/localai/modules/ledger_builder.py
src/localai/modules/ledger_category_rules.py
src/localai/modules/ledger_person_rules.py
src/localai/modules/ledger_order_enricher.py
src/localai/modules/ledger_quality_report.py
src/localai/modules/ledger_review_workbook.py
src/localai/modules/ledger_review_importer.py
src/localai/modules/ledger_report_workbook.py
```

职责：

- `ledger_schema.py`
  - 定义最终账本字段、默认值、金额和日期格式。
- `ledger_builder.py`
  - 从 `financial_transactions` 和 `financial_transaction_links` 生成账本条目。
- `ledger_category_rules.py`
  - 关键词分类规则。
- `ledger_person_rules.py`
  - 对应人员识别规则，第一版可默认空或 `unknown`。
- `ledger_order_enricher.py`
  - 使用已匹配订单补充具体物品/服务。
- `ledger_quality_report.py`
  - 输出缺分类、缺人员、未知类型、低置信度、需复核统计。
- `ledger_review_workbook.py`
  - 输出按月份分 sheet 的人工校核 Excel，预留人工修正列。
- `ledger_review_importer.py`
  - 读取人工校核 Excel，生成 manual overrides。
- `ledger_report_workbook.py`
  - 输出最终 Excel 报表。

## 第一阶段实现范围

先实现规则分类，不接入 AI。

输入：

```text
processed_data/normalized/financial_transactions.jsonl
processed_data/normalized/financial_transaction_links.jsonl
```

输出：

```text
processed_data/ledger/ledger_entries.jsonl
processed_data/ledger/ledger_entries.json
processed_data/ledger/ledger_quality_report.md
```

第一版分类规则：

- 医疗
  - 关键词：医院、门诊、挂号、药房、药店、医保、体检、诊所。
- 餐饮
  - 关键词：餐饮、饭店、餐厅、咖啡、奶茶、美团外卖、饿了么、麦当劳、肯德基。
- 停车 / 交通
  - 关键词：停车、停车场、ETCP、高速、地铁、公交、打车、滴滴。
- 购物
  - 关键词：淘宝、天猫、拼多多、京东、抖音商城、支付宝-商户、财付通-平台商户。
- 生活服务
  - 关键词：物业、水费、电费、燃气、话费、宽带、充值。
- 住房
  - 关键词：房租、租金、物业费、供暖。
- 收入
  - 关键词：工资、薪资、奖金、报销、入账、利息。
- 退款
  - 关键词：退款、退货、返现、冲正。
- 转账 / 还款
  - 关键词：转账、账户互转、信用卡还款、还款、借记卡还款。
- 未分类
  - 无规则命中或冲突时进入人工复核。

## 第二阶段 Excel 报表

状态：未完成。

新增：

```text
python ledger_report_export.py
```

输出：

```text
processed_data/reports/ledger_report.xlsx
```

Excel sheet 建议：

- `总览`
- `按月收支`
- `按日收支`
- `支出分类汇总`
- `收入分类汇总`
- `人员汇总`
- `账本明细`
- `需人工复核`
- `转账还款`
- `订单补充明细`

格式要求：

- 自动列宽。
- 首行冻结。
- 自动筛选。
- 金额列可排序求和。
- 支出、收入、转账、退款用不同底色。
- `需人工复核` sheet 重点列出未分类、低置信度、疑似转账误判、金额或时间缺失记录。

## 第三阶段人工复核闭环

状态：部分完成。

已完成：

- `python ledger_review_export.py`
- 输出：`processed_data/review/ledger_review.xlsx`
- Excel 按月份分 sheet，每个 sheet 内按日期升序排列。
- 缺日期记录单独进入 `缺日期` sheet。
- 已预留人工修正列。

在 Excel 中预留人工修正列：

- 人工类型
- 人工一级分类
- 人工二级分类
- 人工对应人员
- 人工花费项目
- 人工具体服务或物品
- 人工备注

后续新增回读脚本：

```text
ledger_review_import.py
```

目标：

- 读取人工修正后的 Excel。
- 生成 `processed_data/ledger/manual_overrides.json`。
- 下一次构建账本时优先应用人工修正。

建议实现细节：

- 以 `ledger_entry_id` 为主键读取人工修正。
- 只导入至少填写了一个 `人工...` 字段的行。
- 空人工字段不覆盖机器字段。
- 输出时保留：
  - 原始 `ledger_entry_id`
  - 人工修正字段
  - 人工备注
  - 导入时间
- `ledger_build.py` 下次构建时增加参数：

```powershell
python ledger_build.py --manual-overrides processed_data/ledger/manual_overrides.json
```

- 默认也可以自动读取：

```text
processed_data/ledger/manual_overrides.json
```

- 应用人工修正后，在 ledger entry 中标记：

```text
override_applied: true
override_source: manual_overrides
```

## 下一步建议执行顺序

1. 实现 `ledger_review_import.py`
   - 先完成人工校核闭环。
   - 让人工修正能回流到 `manual_overrides.json`。
2. 修改 `ledger_build.py`
   - 支持读取并应用 `manual_overrides.json`。
3. 再实现 `ledger_report_export.py`
   - 统计报表应基于已经应用人工修正后的账本。
4. 根据人工校核结果补充分类规则
   - 优先补高频未分类商户、高金额收入、疑似转账/还款误判。

## 验收标准

第一阶段完成后：

- 可以运行：

```powershell
python ledger_build.py
```

- 能生成 `processed_data/ledger/ledger_entries.jsonl`。
- 银行收入、支出、转账、退款能够分开。
- 没有订单的医院、餐饮、停车费等支出也能进入账本。
- 已匹配订单的购物/服务支出能补充具体物品或服务。
- 转账和还款不计入消费支出统计。
- 所有条目保留来源 ID，可回查到 `financial_transactions` 和原始流水。

第二阶段完成后：

- 可以运行：

```powershell
python ledger_report_export.py
```

- 能生成 `processed_data/reports/ledger_report.xlsx`。
- Excel 可以直接按年月日、分类、人员、项目查看收入和支出。
- `需人工复核` sheet 能明确列出需要人工处理的记录。
