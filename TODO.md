# TODO：原始订单数据整理

## 下一阶段目标

把四个平台已经获取到的原始数据整理成统一、可校验、可去重的订单级中间数据层。

当前原始数据状态：

- 京东：已获取 PDF。
- 淘宝：已获取 PDF。
- 拼多多：已通过截图和本地 AI 识别生成 JSON。
- 美团：已通过截图和本地 AI 识别生成 JSON。
- 银行邮件：新增 IMAP 采集入口，可保存 `.eml`、正文、附件和候选交易 JSON。

下一阶段不要先做分类、统计或报表。应先完成：

```text
JD/Taobao PDF + PDD/Meituan JSON
  -> 统一订单 schema
  -> 统一订单 JSONL/JSON
  -> 去重和字段清洗
  -> 质量报告

银行邮件流水建议并行建立“统一流水 schema”，不要强行塞入订单 schema：

```text
Bank Email EML/Text/Attachment
  -> 银行邮件 raw record
  -> 候选交易流水 JSONL/JSON
  -> 银行模板校验
  -> 统一流水 schema
```
```

## 推荐执行顺序

### 1. 定义统一订单 schema

先建立所有平台共用的订单结构。

建议字段：

- `platform`
- `source_type`
- `source_file`
- `source_page`
- `source_image`
- `order_id`
- `order_time`
- `merchant`
- `title`
- `spec`
- `quantity`
- `paid_amount`
- `original_amount`
- `shipping_fee`
- `status`
- `logistics`
- `actions`
- `is_partial`
- `confidence`
- `warnings`
- `raw_record`

银行邮件流水建议字段：

- `source_type`
- `source_file`
- `body_text_file`
- `attachment_files`
- `message_uid`
- `message_id`
- `sent_at`
- `from`
- `subject`
- `bank_key`
- `bank_name`
- `account_tail`
- `transaction_time`
- `direction`
- `amount`
- `currency`
- `merchant`
- `counterparty`
- `balance`
- `confidence`
- `warnings`
- `raw_record`

注意：

- 必须保留 `source_file` 和 `raw_record`，方便回查原始 PDF、截图或 AI 输出。
- `source_type` 可先使用 `pdf`、`image_json`。
- 金额、时间、空字段格式要在 schema 或 normalizer 中统一。

### 2. 优先整理拼多多和美团 JSON

拼多多、美团已经是 JSON，最适合先验证统一 schema、清洗和去重逻辑。

需要实现：

- 扫描 `raw_data/order_json/pdd/`。
- 扫描 `raw_data/order_json/meituan/`。
- 读取每张截图对应的 JSON。
- 展开顶层 `orders`。
- 为每条订单补充来源字段。
- 标记异常字段，例如：
  - 缺金额。
  - 缺标题。
  - 缺订单时间。
  - 缺订单号。
  - `is_partial=true`。
  - `confidence` 低于阈值。
  - 原 JSON 中存在 `warnings`。
- 输出统一订单列表。

### 3. 实现订单去重和合并

拼多多、美团截图之间存在重叠，必须先处理重复订单。

去重规则建议：

1. 有 `order_id` 时，使用 `platform + order_id`。
2. 无 `order_id` 时，使用 `platform + merchant + title + paid_amount + order_time`。
3. 如果一条完整记录和一条 `is_partial=true` 记录高度相似，保留完整记录。
4. 如果两条记录互补，可以合并字段。
5. 合并后保留来源列表，便于追踪订单来自哪些截图或 JSON 文件。

### 4. 输出统一结果和质量报告

建议输出目录：

```text
raw_data/normalized/
```

建议输出文件：

```text
raw_data/normalized/orders.jsonl
raw_data/normalized/orders.json
raw_data/normalized/quality_report.md
```

质量报告至少包含：

- 各平台读取的原始文件数量。
- 各平台解析出的订单数量。
- 去重前订单数量。
- 去重后订单数量。
- 缺金额数量。
- 缺标题数量。
- 缺时间数量。
- 缺订单号数量。
- `is_partial=true` 数量。
- 低置信度订单数量。
- 解析失败文件列表。
- 需要人工复核的来源文件列表。

### 5. 再处理京东 PDF

京东 PDF 先尝试文本解析。

建议路线：

1. 使用 `PyMuPDF` 或 `pdfplumber` 提取 PDF 文本。
2. 判断京东 PDF 文本是否包含稳定的订单字段。
3. 如果文本稳定，写京东 PDF parser。
4. 如果文本不稳定，把 PDF 页面渲染成图片，复用本地 AI 视觉识别流程。
5. 输出同一套统一订单 schema。

### 6. 最后处理淘宝 PDF

淘宝 PDF 可能更依赖浏览器打印版式，稳定性可能弱于京东。

建议路线：

1. 先尝试文本解析。
2. 如果字段顺序或版式不稳定，走 PDF 页面转图片。
3. 复用本地 AI 视觉识别流程识别页面中的订单。
4. 输出同一套统一订单 schema。

## 建议新增代码结构

沿用当前项目“入口脚本 + flows + modules”的结构。

建议新增：

```text
consolidate_orders.py
src/localai/flows/order_raw_consolidate.py
src/localai/modules/order_schema.py
src/localai/modules/order_json_reader.py
src/localai/modules/pdf_order_extractor.py
src/localai/modules/order_normalizer.py
src/localai/modules/order_deduper.py
src/localai/modules/order_quality_report.py
```

职责划分：

- `consolidate_orders.py`
  - 根目录入口脚本。
  - 负责读取命令行参数、加载配置、调用 flow、打印结果摘要。
- `order_raw_consolidate.py`
  - 负责组织“读取 -> 标准化 -> 去重 -> 输出 -> 报告”的完整流程。
- `order_schema.py`
  - 定义统一订单字段、默认值和必要的类型转换。
- `order_json_reader.py`
  - 读取拼多多、美团 AI JSON，转换为标准订单草稿。
- `pdf_order_extractor.py`
  - 后续承接京东、淘宝 PDF 解析或 PDF 转图片识别。
- `order_normalizer.py`
  - 统一金额、时间、空字段、warnings、source 信息。
- `order_deduper.py`
  - 负责订单级去重、相似记录合并、来源追踪。
- `order_quality_report.py`
  - 生成 Markdown 质量报告和统计摘要。

## 第一轮实现范围

第一轮不要一次性处理四个平台 PDF 和 JSON。建议范围收窄为：

1. 新增统一 schema。
2. 读取拼多多 JSON。
3. 读取美团 JSON。
4. 标准化字段。
5. 去重。
6. 输出 `orders.jsonl`。
7. 输出 `quality_report.md`。

第一轮暂不实现：

- 京东 PDF 解析。
- 淘宝 PDF 解析。
- 订单分类。
- Excel 写入。
- 报表统计。

## 验收标准

第一轮完成时应满足：

- 可以运行：

```powershell
python consolidate_orders.py --platform pdd --platform meituan
```

- 能从默认目录读取：

```text
raw_data/order_json/pdd/
raw_data/order_json/meituan/
```

- 能输出：

```text
raw_data/normalized/orders.jsonl
raw_data/normalized/orders.json
raw_data/normalized/quality_report.md
```

- 输出订单中每条记录都包含统一 schema 字段。
- 每条记录都能回溯到原始 JSON 文件和截图名。
- 去重前后数量清楚。
- 缺字段、低置信度、截断订单会进入质量报告。
- 不读取或提交任何真实隐私数据到版本库。

## 后续扩展顺序

完成第一轮后，再继续：

1. 为京东 PDF 增加解析能力。
2. 为淘宝 PDF 增加解析能力。
3. 为银行邮件增加具体银行模板 parser，把 `candidate_transactions` 转成统一流水 schema。
4. 如果 PDF 文本解析不稳定，则实现 PDF 转图片并复用本地 AI 视觉识别。
5. 四个平台订单和银行流水全部进入统一 JSONL 后，再做消费分类、汇总统计和 Excel 输出。
