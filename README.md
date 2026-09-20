# Financial Track

个人消费与银行流水采集整理辅助工具。当前项目包含几类能力：

- 京东、淘宝等网站页面可导出为 PDF，作为安卓截图数据的校验和归档材料。
- 通过安卓 USB 实体手机 ADB 截取多个 App 的交易流水页面，作为后续 OCR 和 AI 结构化识别的输入。
- 调用外部项目提供的 OpenAI 兼容 AI 服务，对订单截图做结构化识别。
- 采集流水邮件、准备附件密码并解密/解压账单附件，用于校验安卓 App 截图获得的流水。
- 汇总银行流水与订单结构化结果，构建 normalized 中间层、最终 ledger 账本和人工校核 Excel。

本项目面向个人账号自用，不包含平台逆向接口、抓包或绕过风控逻辑。

## 目录结构

```text
Financial_Track/
  main.py                    # 唯一根目录程序入口，启动 Tkinter GUI
  logging_config.py          # 项目统一日志配置
  flows/
    *.py                     # 可独立执行的工作流入口
    workflows/               # 场景编排层
    modules/                 # 财务领域与通用基础模块
    gui/                     # 图形界面实现
    financial_email/         # 邮件与附件分阶段入口
  tests/                     # 单元测试与工作流级测试
  docs/                      # 架构、配置、进度和历史文档
  config.yaml                # 项目运行配置
  common.env.example         # 本地环境变量模板
  raw_data/                  # 本地采集数据、邮件、附件和 AI JSON，已被 git 忽略
  processed_data/            # normalized、ledger、review 和 reports 输出，已被 git 忽略
  logs/                      # 运行日志，已被 git 忽略
```

项目采用“根目录单一 GUI 入口 + `flows/` 工作流入口 + `flows/workflows/` 编排层 +
`flows/modules/` 基础模块”的结构。除 `main.py` 和 `logging_config.py` 外，根目录不再放置 Python 文件。

## 数据来源策略与当前主线

流水获取统一以安卓 App 截图为主来源；通过邮件或网站取得的 PDF、邮件正文和附件只作为校验、对账和原始凭证，不再作为新增流水的权威来源。目标链路为：

```text
安卓 App 交易流水截图 → 图像结构化识别 → normalized → ledger
邮件/网站 PDF ───────────────→ 校验、对账与差异报告
```

安卓截图采集已经统一；银行 App 截图结构化识别和 PDF 差异核验仍是后续工作。现有邮件/PDF 归一化代码暂时保留，用于历史数据兼容和对账开发。

推荐按下面顺序处理完整数据链路：

```powershell
python flows/order_image_ai.py pdd --all --max-tokens 1024
python flows/order_image_ai.py meituan --all --max-tokens 1024
python flows/normalize_transactions.py
python flows/ledger_build.py
python flows/ledger_review_export.py
```

主要数据分层：

```text
raw_data/financial_email/                  # 邮件、PDF、附件等校验对账材料
raw_data/bank/<银行名称>/                  # 解密/解压后的无密码银行原始文件
raw_data/bank/bank_information_summary.html # 已获取银行信息汇总
raw_data/order_json/pdd|meituan/           # 截图 AI 识别后的订单 JSON
processed_data/normalized/                 # bank/orders/financial_transactions/link 中间层
processed_data/ledger/                     # 最终账本 ledger_entries 和质量报告
processed_data/review/ledger_review.xlsx   # 按月份拆分的人工校核表
```

如果已经手工维护好附件密码，可以用 `--skip-crack` 跳过 GPU 破解；需要尝试破解时去掉该参数，并确保 `config.yaml` 中的 hashcat/john 路径可用。

## 图形界面

启动统一桌面控制台：

```powershell
python main.py
```

界面从上到下固定为工作流选项卡、当前参数、共享实时日志、总体进度与状态栏。底部显示外部 AI 的
配置模型和本机接口，但 GUI 启动后不会执行心跳、模型列表查询或“你好”测试。只有实际执行 AI
功能时才检查服务和模型是否可用，并在不可用时报告错误。
所有耗时流程通过后台
CLI 子进程运行，不阻塞 Tk 主线程；同一时间只允许一个任务。GUI 不保存或展示邮箱授权码及附件密码；
`common.env` 只配置附件密码文件路径，破解密码按附件文件名保存在该路径对应的专用密码文件。详细规范见
[`docs/GUI_DESIGN_REQUIREMENTS.md`](docs/GUI_DESIGN_REQUIREMENTS.md)。

在 GUI 中获取 126 邮箱账单时，进入“邮件获取账单”页签。该页只采集并整理原始资料，不生成交易；如需扫描邮箱内
全部历史银行账单，勾选“扫描邮箱全部历史邮件（忽略日期/数量限制）”后执行。全量扫描
会读取整个邮箱，按发件人、主题、正文和附件名称初步判断财务相关性，并仅将匹配邮件、正文和附件写入
本机 `raw_data/financial_email/`，耗时取决于邮箱邮件数量。无论初判是否匹配，本次检查范围内的全部邮件
都会列入 `raw_data/financial_email/financial_email_review.html`，用于人工审核误判和漏判。
“检查起始日期”默认为 `2015-01-01`，起止日期运行前可直接修改；邮箱目录固定使用配置中的 `INBOX`，邮件、
清单和解压路径均使用配置或 CLI 默认值。主配置文件统一在“全局配置”页选择并重新加载。
“破解邮件附件”默认勾选，使用本地 GPU 枚举六位数字密码；取消勾选只跳过破解步骤，不影响使用已保存密码解压。

紧随其后的“邮件数据归一化”页读取上述 `raw_data`，执行交易提取、质量检查并生成完整人工审核 HTML。
第一步默认只执行确定性自动归一化；右侧列出未能自动提取交易的文件。“对未识别 PDF 使用本地 AI/OCR”
默认不勾选，需要时再启用，届时才检查本地 AI 并把 PDF 页面渲染为图片进行 OCR。

## 环境准备

建议使用 Python 3.11+。

安装 Python 依赖：

```powershell
pip install -r requirements.txt
python -m playwright install chromium
```

如果只运行部分工具，也可以按需安装：

```powershell
pip install playwright pyyaml pyautogui pillow
```

## 配置、日志与本地文件

项目配置入口是根目录 `config.yaml`。本机路径、账号、授权码和外部服务地址等本地差异放在 `common.env`，仓库只保留 `common.env.example` 作为模板：

```powershell
Copy-Item common.env.example common.env
```

跨 Windows、macOS 或 Linux 同步开发时，不要在源码或 `config.yaml` 中写死本机绝对路径。推荐使用 `${CLOUDSTATION_ROOT}` 占位，并在 `common.env` 中配置平台变量：

```env
CLOUDSTATION_ROOT_WINDOWS=D:\CloudStation
CLOUDSTATION_ROOT_MACOS=~/SynologyDrive
CLOUDSTATION_ROOT_LINUX=~/CloudStation
```

统一日志配置仅位于项目根目录 `logging_config.py`。默认日志写入项目根目录 `logs/`，不会写入 `flows/logs/`。日志文件名通常对应入口脚本名，例如：

```text
logs/main.log
logs/ai_self_check.log
logs/order_image_ai.log
logs/financial_email_bot.log
logs/android_capture_macos.log
logs/android_capture_windows.log
```

GUI 启动后会创建 `logs/main.log`，界面“运行日志与实时输出”中显示的工作流输出也会同步写入该文件；
各 CLI 子进程仍保留自己的入口日志，例如邮件流程写入 `logs/financial_email_bot.log`。

`common.env`、`financial_attachment_passwords.env`、`raw_data/`、`processed_data/`、`logs/`、`vendor/` 等本地文件或运行产物不应提交到 git。

## 开发检查

项目使用标准库 `unittest`，测试数据均为临时目录或脱敏的最小样本：

```powershell
$env:PYTHONPATH='.'
python -m unittest discover -s tests -v
python -m compileall -q -f -x 'vendor|raw_data|processed_data|logs?|__pycache__' .
python -m flake8 .
git diff --check
```

跨平台协作规范见 [`AGENTS.md`](AGENTS.md)，详细项目文档集中存放在 [`docs/`](docs/)。

## 安卓 App 交易流水截图

安卓采集只支持 macOS/Windows 连接的 USB 实体手机，不使用模拟器。先确认手机已启用 USB 调试并授权：

```bash
adb devices -l
```

App 名称、输出目录和参考滑动参数通过本机 `common.env` 的 `ANDROID_CAPTURE_APPS_JSON` 维护，不放入 `config.yaml`，增加 App 不需要增加入口脚本。本机当前配置了拼多多、美团和光大银行；启动 `python main.py` 后，在统一“安卓 App 采集”页签选择 App 和采集模式即可。

GUI 是正式入口，底层统一调试入口为：

```bash
python flows/android_transaction_capture.py check --app sample_wallet
python flows/android_transaction_capture.py capture-scroll --app sample_wallet --pages 5 --wait 1.5
```

程序自动读取实际屏幕尺寸，并把 App 的参考滑动坐标换算到当前设备。连接、脱敏设备信息、屏幕尺寸、截图和滑动结果写入根目录 `logs/android_capture_macos.log` 或 `logs/android_capture_windows.log`。完整说明见 [`docs/ORDER_CAPTURE.md`](docs/ORDER_CAPTURE.md)。

## 京东订单 PDF 校验归档

京东脚本使用 Playwright 持久化浏览器配置导出订单页 PDF。

先在 `common.env` 中配置输出目录：

```env
JD_PDF_OUTPUT_DIR=<pdf_output_dir>
```

`config.yaml` 中配置浏览器用户数据目录、等待时间和每年页数：

```yaml
flows:
  jd_pdf:
    output_dir: ${JD_PDF_OUTPUT_DIR:-./raw_data/jd_pdf}
    browser_user_data_dir: ./raw_data/jd_browser_profile
    headless: false
    wait_seconds: 5
    order_pages:
      2024: 4
      2023: 5
```

运行：

```powershell
python flows/jd_pdf_bot.py
```

首次运行建议保持有头模式，手工登录京东。只导出指定 URL：

```powershell
python flows/jd_pdf_bot.py --url "https://order.jd.com/center/list.action?d=2024&s=4096&page=1"
```

## 淘宝订单 PDF 校验归档

淘宝脚本通过 `pyautogui` 辅助浏览器打印页面。使用前请确认浏览器默认打印目标为“另存为 PDF”，并打开淘宝订单页面。

运行：

```powershell
python flows/taobao_pdf_bot.py
```

启动后把鼠标放在订单页“下一页”按钮上，脚本会循环点击下一页、触发 `Ctrl+P`、保存 PDF。按 `Ctrl+C` 可停止，鼠标移到屏幕左上角可触发 `pyautogui` 紧急停止。

## 外部 AI 服务自检

本项目只调用其他项目已启动的 OpenAI 兼容 AI 服务，不负责安装模型、启动服务、管理 CUDA
运行时或结束服务进程。连接默认值保留在 `config.yaml`；需要覆盖时，可由启动本项目的外部运行环境注入
`LLAMACPP_*` 进程变量，或写入被 Git 忽略的本机 `common.env`。GUI 会异步读取健康接口和模型列表；模型
接口需要鉴权时，应仅在本机设置 `LLAMACPP_API_KEY`。
详细接口约定见 [`docs/EXTERNAL_AI_SERVICE.md`](docs/EXTERNAL_AI_SERVICE.md)。

外部服务需提供 `/health`、`/v1/models` 和 `/v1/chat/completions` 接口。

只检查服务健康状态和模型列表：

```powershell
python flows/ai_self_check.py --no-chat
```

完整对话测试：

```powershell
python flows/ai_self_check.py --prompt "请直接回答两个字：可用" --max-tokens 32
```

如果服务不可用，脚本会提示先在专用运行时项目中启动服务，不会尝试创建或关闭服务进程。

### 订单截图 AI 识别

识别最新一张拼多多截图：

```powershell
python flows/order_image_ai.py pdd --max-tokens 1024
```

识别整个拼多多截图目录，默认会在终端显示进度条：

```powershell
python flows/order_image_ai.py pdd --all --max-tokens 1024
```

关闭终端进度条：

```powershell
python flows/order_image_ai.py pdd --all --max-tokens 1024 --no-progress
```

识别结果默认输出到：

```text
raw_data/order_json/pdd
raw_data/order_json/meituan
```

运行日志写入：

```text
logs/order_image_ai.log
```

日志会记录任务参数、图片总数、每张图片的开始/完成、输出 JSON 路径、订单数量、告警和最终汇总。终端进度条本身不会逐帧写入日志。

## 数据与隐私

`raw_data/`、`processed_data/`、`logs/`、环境文件和输出目录已在 `.gitignore` 中排除。订单截图、浏览器登录状态、PDF 输出等本地隐私数据不应提交到 git。

安卓截图已经可以通过外部 AI 服务识别并整理为订单 JSON；最终账本仍以银行/支付流水为主来源，订单只作为购物、外卖、平台服务等场景的明细补充，避免重复统计。

## 邮件/PDF 校验对账材料采集

银行交易提醒、信用卡账单、支付平台账单等邮件可以作为另一类底层原始数据。项目提供
`flows/financial_email_bot.py`，通过 IMAP 读取邮箱，把匹配到的流水邮件保存为本地原始产物：

```text
raw_data/financial_email/eml/                  # 邮件原文 .eml
raw_data/financial_email/body/                 # 抽取后的正文文本
raw_data/financial_email/attachments/          # 邮件附件
raw_data/financial_email/financial_email_records.jsonl
raw_data/financial_email/financial_email_records.json
raw_data/financial_email/financial_email_summary.md
raw_data/financial_email/financial_email_review.json     # 本次检查的全部邮件条目
raw_data/financial_email/financial_email_review.html     # 可搜索、可筛选的人工审核页
```

先在 `common.env` 中配置邮箱 IMAP 信息。网易 126 邮箱使用 `imap.126.com:993`，密码应填写客户端授权码，不要使用网页登录密码：

```env
FINANCIAL_EMAIL_IMAP_HOST=imap.126.com
FINANCIAL_EMAIL_IMAP_PORT=993
FINANCIAL_EMAIL_IMAP_USER=your-account@126.com
FINANCIAL_EMAIL_IMAP_PASSWORD=your-126-authorization-code
FINANCIAL_EMAIL_CLIENT_SUPPORT_EMAIL=support@example.invalid
FINANCIAL_EMAIL_SINCE=2015-01-01
FINANCIAL_EMAIL_MAX_MESSAGES=200
FINANCIAL_EMAIL_SUBJECT_KEYWORDS_JSON=["银行","账单","流水","交易","动账","入账","扣款","信用卡","借记卡","电子回单","对账单"]
```

网易邮箱在第三方客户端登录后还要求发送 IMAP `ID` 客户端身份信息。项目会自动发送 `FinancialTrack` 的 `ID` 信息，以避免 `Unsafe Login. Please contact kefu@188.com for help` 这类 `SELECT/EXAMINE INBOX` 阶段拦截。

运行：

```powershell
python flows/financial_email_bot.py --since 2024-01-01 --max-messages 500
```

只验证 126 IMAP 登录和邮箱目录选择，不下载邮件：

```powershell
python flows/financial_email_bot.py --stage check
```

忽略日期和数量限制，扫描邮箱全部历史邮件：

```powershell
python flows/financial_email_bot.py --stage ingest --all-history
```

也可以先解析已经导出的 `.eml` 文件，避免直接连接邮箱：

```powershell
python flows/financial_email_bot.py --eml-dir raw_data/email_export
```

当前邮件解析会根据发件人、主题、正文以及附件名称初步判断财务相关性。只有财务相关邮件会保存 EML、正文和附件；全部受检邮件的日期、发件人、主题、附件、判断依据和保存状态都会进入同目录 HTML 供人工复核。这些产物定位为校验对账材料，不再作为新增流水的权威来源。

### 邮件附件密码准备

银行账单 PDF 或 ZIP 附件通常带密码。根目录下被 Git 忽略的 `common.env` 只配置密码文件路径：

```dotenv
FINANCIAL_ATTACHMENT_PASSWORD_ENV_FILE=./financial_attachment_passwords.env
```

实际密码保存在该路径对应且同样被 Git 忽略的 `financial_attachment_passwords.env` 中。先复制模板：

```powershell
Copy-Item financial_attachment_passwords.env.example financial_attachment_passwords.env
```

可配置项：

```env
FINANCIAL_ATTACHMENT_PASSWORD_DEFAULT=
FINANCIAL_ATTACHMENT_PASSWORD_BY_BANK_JSON={"cmb":"password-for-cmb"}
FINANCIAL_ATTACHMENT_PASSWORD_BY_FILENAME_JSON={"statement.pdf":"password-for-this-file"}
FINANCIAL_ATTACHMENT_PASSWORD_BY_PATTERN_JSON={"招商":"password-for-filename-containing-this-text"}
FINANCIAL_ATTACHMENT_PASSWORD_BY_TYPE_JSON={"pdf":["pdf-password-1","pdf-password-2"],"zip":["zip-password-1","zip-password-2"]}
FINANCIAL_ATTACHMENT_PDF_PWD=["pdf-password-1","pdf-password-2"]
FINANCIAL_ATTACHMENT_ZIP_PWD=["zip-password-1","zip-password-2"]
```

生成附件清单并检查哪些附件还缺密码：

```powershell
python flows/financial_email_bot.py --stage prepare
```

默认输出：

```text
raw_data/financial_email/attachment_inventory.json
raw_data/financial_email/attachment_inventory.md
```

破解成功后仅写入 `FINANCIAL_ATTACHMENT_PASSWORD_BY_FILENAME_JSON`，使每个附件文件名与自己的密码一一对应。清单只记录是否已匹配到密码、匹配来源和候选密码数量，不输出真实密码。

尝试解密/解压附件：

```powershell
python flows/financial_email_bot.py --stage extract
```

默认输出：

```text
raw_data/financial_email/extracted_attachments/attachment_extract_manifest.json
raw_data/financial_email/extracted_attachments/attachment_extract_failures.md
raw_data/bank/<银行名称>/
raw_data/bank/bank_information_summary.html
```

无法正确解压的 ZIP 或无法读取的 PDF 不会中断其他附件及后续阶段。流程结束时，失败日志和
`attachment_extract_failures.md` 只列出附件名称、收件日期和邮件标题，不输出密码、完整路径或复杂的技术错误。

### 使用 GPU 暴力破解邮件附件

GUI 已将破解功能合并到“邮件获取账单”页；“破解邮件附件”默认勾选。完整流程会先尝试提取并生成失败清单，
再只破解其中密码错误的 PDF/ZIP（包括 ZIP 内仍加密的 PDF），随后重新提取。执行时固定
使用 6 位数字掩码 `?d?d?d?d?d?d`（即 `000000`–`999999`），关闭候选密码和 CPU 数字枚举回退，并通过
Hashcat `-D 2` 限定为本地 GPU 设备。破解结果按文件名写回 `FINANCIAL_ATTACHMENT_PASSWORD_ENV_FILE`
指向的本地密码文件，日志默认不显示真实密码。随后自动重新提取，将无密码文件按银行写入 `raw_data/bank/`。

命令行等价调用为：

```powershell
python flows/financial_attachment_crack.py --target failed --mask "?d?d?d?d?d?d" --candidate-profile none --gpu-only
```

### 邮件数据归一化与人工审核

GUI 第二个页签“邮件数据归一化”读取已下载的邮件正文和已成功解密/解压的 PDF、ZIP 内部文件：

```powershell
python flows/normalize_transactions.py --source bank
```

默认读取：

```text
raw_data/financial_email/financial_email_records.jsonl
raw_data/financial_email/extracted_attachments/attachment_extract_manifest.json
```

默认输出：

```text
processed_data/normalized/bank_transactions.jsonl
processed_data/normalized/bank_transactions.json
processed_data/normalized/bank_transactions_quality_report.md
processed_data/normalized/bank_transactions_full_review.html
processed_data/normalized/bank_transactions_history.jsonl
processed_data/normalized/email_normalization_unresolved.json
```

整理过程会保留金额、方向、账户尾号和来源引用，方便回查邮件、附件、PDF 或 Excel 行。迁移完成后，这些记录应标记为 `reconciliation` 来源，只参与校验，不直接生成权威账本流水。

邮件正文优先使用工商、招商、建设银行专用规则；银行身份优先按发件人和机构专名判断，避免通用的“信用卡/账单”
关键词把工行月账单误归为招商银行。附件按 PDF、XLS/XLSX、CSV 分派解析。余额、额度、
本期应还和合计行会在去重前过滤。只有确定性解析器无法识别文档时，才会按
`financial_document_ai_fallback` 配置调用本地 AI；PDF 文本解析仍无结果时可直接渲染页面并调用视觉接口 OCR。
工商银行 PDF 会区分借记账户和信用卡版式：借记账户使用带 `+/-` 的收入/支出金额；信用卡使用“借/贷”
判断方向，并读取“交易金额”列，账户余额仅作为余额保存，不参与交易金额计算。
同一工商银行共享额度信用卡账户可能为不同卡尾号分别生成账单；当交易日期和信用卡 PDF 原始交易行完全一致时，
归一化层将其合并为一笔交易，同时在 `account_tails` 中保留全部相关卡尾号和两份来源定位。仅凭金额或商户相同
不会触发跨卡合并。
工行月度信用卡账单逐笔保存交易卡尾号及“主卡/副卡”角色，并与信用卡打印流水按银行、日期、方向、金额、
交易卡尾号和商户进行比对；唯一匹配后合并为一笔，同时保留月账单和全部 PDF 来源。信用卡还款摘要优先使用
邮件中的完整信息，打印流水的精确时间、账户尾号和来源定位继续保留。招商银行电子月账单按交易块解析消费和还款。
当前个人数据中的交通银行 PDF 和建设银行活期明细均明确保存为借记卡，不再根据账号长度或摘要中的“信用卡还款”
文字误判卡片类型。
放在 `raw_data/` 根目录的 `中国光大银行账户明细查询清单.xls` 会在银行归一化时自动读取为光大银行借记卡流水；
支出金额和存入金额分别映射为支出和收入，对方账号（包括星号）、对方户名、摘要、余额、工作表及行号均予以保留。
`raw_data/taobao/csv/` 下的支付宝 CSV 和 `raw_data/weixin/csv/` 下的微信支付 XLSX 也会自动读取，
标记为支付账户流水。保存交易时间、方向、金额、交易对方、商品全名、支付方式、状态和订单号；支付宝退款
按收入处理，平台标为“不计收支”的普通内部划转以及微信中性交易不进入归一化流水。
首次实际调用前检查服务和模型，不执行 GUI 心跳。
质量报告写入 `bank_transactions_quality_report.md`。
未自动提取文件写入 `email_normalization_unresolved.json`，并在 GUI 页面右侧自动刷新显示；完整交易审核结果可由
页面上的“打开审核 HTML”按钮查看。
完整人工审核集写入 `bank_transactions_full_review.html`，按“银行 + 卡片类型”展示机构，主表包含账户尾号、
交易卡尾号、主/副卡、交易/入账日期、方向、精确金额、币种、统一后的商户/对方全名、对方账号、
未脱敏摘要、渠道和来源定位。银行归一化记录不再保存“交易类型”；工行借记卡的序号、地区代码仅保留在
`raw_record` 原始行中，不映射为归一化字段或渠道。对方账号按账单原文保存，包括中间四位为星号的账号。
页面支持上述字段、日期范围及金额区间筛选；账户全名不再显示。通过 GUI 的“打开审核 HTML”进入页面后，来源
PDF、Excel、CSV 或邮件文件可以点击并交给本机默认程序打开；本地桥接只监听回环地址，使用随机会话令牌，
且只允许访问项目 `raw_data/` 下的文件。
完整审核集含个人财务信息，只能保存在被 Git 忽略的 `processed_data/` 中。

每条归一化流水还保存完整追溯信息：来源记录中的原始 EML、原始加密附件、解密后解析文件等均记录
64 位 SHA-256；`record_fingerprint_sha256` 是归一化记录的完整规范化指纹；`record_version`、
`supersedes_record_ids` 和 `supersedes_record_fingerprints_sha256` 连接修正前后的版本。被替代的旧版本
追加保存在 `bank_transactions_history.jsonl` 或 `financial_transactions_history.jsonl`，原有 PDF 页码、
Excel/CSV 行号、工作表和邮件 UID 定位字段继续保留。

## 归一化、账本与人工校核

银行流水、订单截图 AI JSON 等结构化结果可以统一汇总到 normalized 中间层：

```powershell
python flows/normalize_transactions.py
```

默认输出：

```text
processed_data/normalized/bank_transactions.jsonl
processed_data/normalized/orders.jsonl
processed_data/normalized/financial_transactions.jsonl
processed_data/normalized/financial_transactions_history.jsonl
processed_data/normalized/financial_transaction_links.jsonl
processed_data/normalized/normalized_quality_report.md
```

其中 `financial_transactions` 是财务事实中间层，包含银行/支付流水事实和订单事实；`financial_transaction_links` 保存订单与付款流水的强关联或候选关联。最终账本以银行/支付流水为主来源，订单只用于补充购物、外卖、平台服务等明细，避免同一笔消费重复统计。

构建最终账本：

```powershell
python flows/ledger_build.py
```

默认读取：

```text
processed_data/normalized/financial_transactions.jsonl
processed_data/normalized/financial_transaction_links.jsonl
```

默认输出：

```text
processed_data/ledger/ledger_entries.jsonl
processed_data/ledger/ledger_entries.json
processed_data/ledger/ledger_quality_report.md
```

账本字段包含日期、年月、收支类型、金额、一级/二级/三级分类、目标人、项目、标签、商户/对象、支付方式、原始摘要、订单补充明细、来源流水 ID、置信度和人工复核标记。信用卡还款、账户互转、投资买卖等会进入账本明细，但默认不计入普通消费支出统计。

导出人工校核 Excel：

```powershell
python flows/ledger_review_export.py
```

默认输出：

```text
processed_data/review/ledger_review.xlsx
```

Excel 按月份分 sheet，每个 sheet 内按日期升序排列；缺日期记录会单独进入 `缺日期` sheet。每行保留机器分类、分类理由、问题提示和订单补充明细，并预留人工修正列：

```text
人工收支类型
人工一级分类
人工二级分类
人工三级分类
人工目标人
人工项目
人工标签
人工是否报销
人工预算状态
人工备注
```

人工校核时建议只填写 `人工...` 列，不直接覆盖机器分类列。后续可通过导入脚本读取这些人工修正，生成 `processed_data/ledger/manual_overrides.json`，并在下一次构建账本时优先应用人工修正。

## GitHub 同步

推荐使用 SSH remote，避免 HTTPS 凭据和部分网络环境下的 443 连接问题。先检查当前仓库状态和远端：

```powershell
git status -sb
git remote -v
```

如果 `origin` 还是 HTTPS，可切换为 SSH：

```powershell
git remote set-url origin git@github.com:<owner>/<repo>.git
```

提交前重点确认不要提交本地隐私数据、真实账单、浏览器 profile、授权码、token、密码、附件、订单截图、账单 PDF、`common.env` 或 `financial_attachment_passwords.env`：

```powershell
git status --short --ignored
```

日常同步建议先拉取远端主分支，再提交和推送：

```powershell
$env:GIT_SSH_COMMAND='ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new'
git pull --rebase origin main
git add .
git commit -m "简短说明本次改动"
git push origin main
```

如果当前分支不是 `main`，用实际分支名替换：

```powershell
git branch --show-current
git push origin <branch-name>
```

推送后验证本地和远端是否同步：

```powershell
$env:GIT_SSH_COMMAND='ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new'
git fetch origin
git status -sb
```

如果遇到 `Permission denied (publickey).`，说明本机 SSH key 未被 GitHub 接受，需要确认公钥已添加到 GitHub，并检查：

```powershell
ssh -T git@github.com
```
