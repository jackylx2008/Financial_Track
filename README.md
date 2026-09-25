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
`flows/modules/` 基础模块”的结构。根目录仅保留 `main.py`、独立只读审核入口
`pdf_ocr_review_app.py` 和 `logging_config.py`，其他 Python 入口仍放在 `flows/`。

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

同一工行信用卡账户因不同卡号或重复申请邮件生成多套内容相同的 PDF 时，可点击本页的
“选择工行信用卡 PDF 来源”。本地审核页按原始邮件分组列出全部免密分卷 PDF，并提供原始 EML 与 PDF
打开链接；人工核对后选择一组并保存。选择结果写入配置项
`bank_transaction_review.source_selection_file` 指定的 `raw_data` 本机文件，后续银行归一化只采用所选组，
其他候选组在解析前排除。审核 HTML 位于
`processed_data/normalized/icbc_credit_pdf_source_review.html`；页面及选择文件均已被 Git 忽略。

紧随其后的“邮件数据归一化”页读取上述 `raw_data`，执行交易提取、质量检查并生成完整人工审核 HTML。
第一步默认只执行确定性自动归一化；右侧列出未能自动提取交易的文件。“对未识别 PDF 使用本地 AI/OCR”
默认不勾选，需要时再启用，届时才检查本地 AI 并把 PDF 页面渲染为图片进行 OCR。

第三个页签“PDF 转 HTML 审核”专门预处理 `raw_data/bank` 中的银行流水 PDF。它按原 PDF 的页码、
表格顺序、行列顺序和列宽比例生成一个可筛选的 HTML 审核集，并可从审核页调用本机默认程序打开原 PDF。
每份 PDF 以完整 SHA-256 为键缓存；文件未变化时再次执行只复用缓存，不重复逐页提取。默认产物为：

```text
processed_data/pdf_html_review/bank_pdf_tables_review.html
processed_data/pdf_html_review/pdf_html_manifest.json
processed_data/pdf_html_review/pdf_hash_index.json
processed_data/pdf_html_review/cache/<PDF SHA-256>.json
```

`pdf_hash_index.json` 是持久哈希索引，保存每份本地 PDF 的完整 SHA-256、来源路径、首次/最近发现时间、
提取缓存状态和 OCR 核验状态。GUI 默认只对索引中尚未通过核验的新哈希执行 OCR；文件改名或移动但内容
不变时仍视为同一份文件。也可从命令行执行 `python flows/pdf_to_html.py`；只有表格提取规则更新或需要
重新诊断时才使用 `--force`。HTML 是便于筛选和核对的结构化复刻，原 PDF 仍是版式及内容的最终依据。
工商银行和交通银行 PDF 一旦按 SHA-256 标记为人工审核通过，后续银行归一化直接读取对应表格缓存，
不再调用本地 AI/OCR。人工确认缓存未能解析出交易时，文件进入未解析清单；需要重新使用 AI/OCR 前必须人工确认。
交通银行人工确认的借记卡 PDF 交易表不含本方账号列，因此不再逐行产生账户尾号缺失告警。工商银行信用卡
打印流水与月度 EML 唯一匹配后，因 PDF 换行或“对方户名/交易场所”字段语义不同产生的商户、对方冲突
作为互补来源信息保留，不再列为交易告警；余额或摘要冲突等疑似错误去重仍保留给人工确认。
工行信用卡打印流水按“交易币种”而不是通用缺省币种读取；月度 EML 同时提供交易日和入账日时，可据入账日
与打印流水唯一匹配，并保留邮件中的实际交易日。境外交易的原币金额和入账折算金额分别处理，PDF 币种写为
“其它”时，仅在邮件账单存在唯一同卡、同金额、同商户匹配时采用邮件中的具体币种。
提取器会在进入单元格识别前检查 PDF 字符的旋转矩阵，排除斜向水印文字，同时保留水平正文、垂直正文、
表格线和图片。OCR 对照也会忽略倾斜文本框；本地 AI 视觉提示明确禁止把灰色水印、电子印章、二维码或
防伪标记中的姓名、编号、日期和数字写入交易字段。缓存结构升级后，旧缓存会自动重建并重新执行 OCR 核验。

生成后可执行独立一致性核验：

```powershell
python flows/pdf_html_ocr_compare.py
```

核验分为两层：先逐页、逐表格、逐单元格检查缓存矩阵与 HTML 内嵌数据完全相同；再分别渲染每份 PDF
的首、中、末代表页和对应 HTML 表格，通过 RapidOCR 独立识别并比较字符及数字。默认字符相似度门槛为
90%，数字相似度门槛为 95%；200 DPI 未通过的原 PDF 小字号页面自动以 300 DPI 复核。结果写入
`processed_data/pdf_html_review/pdf_html_ocr_comparison.json`，任一结构或 OCR 检查不通过时命令返回非零状态。
已经通过 OCR 的哈希默认跳过；需要重新核验全部历史文件时使用
`python flows/pdf_html_ocr_compare.py --force`。

归一化读取 PDF 时也按完整 SHA-256 查找同一缓存。旧哈希直接使用人工审核 PDF 阶段保存的原始解析文本，
不重新打开或扫描 PDF；只有没有缓存的新哈希才回退读取源 PDF。缓存文本保存自身 SHA-256，确保内容未被
静默改写。

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
processed_data/normalized/payment_transactions_full_review.html
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
银行流水去重还会比较交易后的余额：两条记录即使交易日期时间、方向、金额和交易双方完全一致，只要两者均有余额
且余额不同，就视为连续发生的两笔独立交易，分别保留各自的来源页码和行号。该规则用于同类银行流水记录，
不阻断工商银行信用卡打印流水与月度邮件账单之间的跨来源核对合并，因为两类来源的余额字段口径可能不同。
工行月度信用卡账单逐笔保存交易卡尾号及“主卡/副卡”角色；邮件只提供卡号后四位时，同时将该尾号写入
归一化账户尾号，避免邮件独有记录缺少卡片身份，也避免同日同金额的主卡、副卡交易互相合并。账单与信用卡打印流水按银行、日期、方向、金额、
交易卡尾号和商户进行比对；同一卡片同日存在多笔相同金额时，月度邮件保留每一行及其出现次数，再按原币金额、
人民币入账金额和邮件/PDF 出现顺序与打印流水一对一匹配。PDF 中精确交易时间和不同余额用于保留各笔独立流水，
不会把同日同额消费合并；匹配后同时保留月账单和 PDF 来源。信用卡还款摘要优先使用
邮件中的完整信息，打印流水的精确时间、账户尾号和来源定位继续保留。招商银行电子月账单按交易块解析消费和还款。
当前个人数据中的交通银行 PDF 和建设银行活期明细均明确保存为借记卡，不再根据账号长度或摘要中的“信用卡还款”
文字误判卡片类型。
放在 `raw_data/` 根目录的 `中国光大银行账户明细查询清单.xls` 会在银行归一化时自动读取为光大银行借记卡流水；
支出金额和存入金额分别映射为支出和收入，对方账号（包括星号）、对方户名、摘要、余额、工作表及行号均予以保留。
该清单原始列不包含本方账号或卡号，因此账户尾号为空属于来源文件的正常结构，不生成
`missing_account_tail` 告警；其他银行及其他来源仍执行账户尾号完整性检查。
该文件是光大银行直接出具的权威流水，每个工作表数据行均代表一笔独立交易；即使时间、金额和对方完全
相同，也按工作表及行号分别保存，不使用通用字段组合将相邻行合并。
`raw_data/taobao/csv/` 下的支付宝 CSV 和 `raw_data/weixin/csv/` 下的微信支付 XLSX 也会自动读取，
标记为支付账户流水。保存交易时间、方向、金额、交易对方、商品全名、支付方式、状态和订单号；支付宝退款
按收入处理，平台标为“不计收支”的普通内部划转以及微信中性交易不进入归一化流水。
首次实际调用前检查服务和模型，不执行 GUI 心跳。
质量报告写入 `bank_transactions_quality_report.md`。
未自动提取文件写入 `email_normalization_unresolved.json`，并在 GUI 页面右侧自动刷新显示。GUI 分别提供
“打开个人银行交易完整流水清单”和“打开支付审核 HTML”：`bank_transactions_full_review.html` 只汇总各银行流水，
`payment_transactions_full_review.html` 合并支付宝和微信支付流水，两类数据不再混排。
“个人银行交易完整流水清单”按“银行 + 卡片类型”展示机构，标题自动附加所读流水的最早至最新日期。
主表包含账户尾号、卡号后4位、主/副卡、交易/入账日期、方向、精确金额、币种和来源定位；商户/对方全名、
对方账号、未脱敏摘要和渠道保留在页面数据中，通过全文搜索统一检索，不再单独占列。银行归一化记录不再保存“交易类型”；工行借记卡的序号、地区代码仅保留在
`raw_record` 原始行中，不映射为归一化字段或渠道。对方账号按账单原文保存，包括中间四位为星号的账号。
审核页的交易金额统一保留两位小数，并按每三位整数添加千位分隔逗号；该格式仅用于显示，不改变底层金额、
哈希、筛选、排序或汇总计算。
主表另设“交易场所”列：信用卡/贷记卡优先显示账单原始交易场所、交易地点或商户名称，原始专用字段缺失时
回退到归一化商户；借记卡没有交易场所，固定显示短横线“—”。
页面支持机构/卡片类型、主副卡、卡号尾号、年度、月度、日期范围、方向、金额区间、币种、来源及
“有告警/无告警”筛选；账户全名不再显示。通过 GUI 的“打开个人银行交易完整流水清单”进入页面后，来源
PDF、Excel、CSV 或邮件文件可以点击并交给本机默认程序打开。对于带密码的邮件 PDF，审核页只链接附件提取阶段生成并验证为可直接读取的
免密副本；对于带密码的 ZIP，只链接解压后的 Excel、CSV 或 PDF，不链接 ZIP 本身。原附件路径和完整 SHA-256
仍保留在归一化数据中供追溯。本地桥接只监听回环地址，使用随机会话令牌，
且只允许访问项目 `raw_data/` 下的文件。
来源链接不使用浏览器的 `file://` 导航，而是由 Windows 系统注册的 `open` 文件关联打开；同一流水会分别列出
可直接阅读的 PDF/Excel/CSV、EML 邮件、图片和解析来源。必须从 GUI 打开审核 HTML 才能使用该本机桥接。
银行审核页还可按工商银行信用卡的“主卡/副卡”、年度、月度及币种筛选；顶部按钮可切换为交易金额从大到小排序，
初始状态保持原始顺序，再次点击恢复。页面底部按币种实时汇总当前筛选结果的笔数、收入金额和支出金额，
不再显示收入与支出的合计金额，也不跨币种直接相加。底层归一化数据继续使用 ISO 4217 代码，人民币、`RMB`、
人民币元及人民币符号统一保存为 `CNY`；审核页的筛选项、明细和汇总统一显示中文币种名称：人民币、英镑、
日元、新加坡元和美元。
信用卡/贷记卡中，同一机构、同一卡片、同币种和同金额的先支出后收入记录，间隔不超过配置项
`bank_transaction_review.credit_card_refund_window_days` 时按一组
“交易取消退款”进行一对一匹配。页面在两条流水的整行所有单元格上显示半透明斜线阴影，底部笔数仍包含两条流水，但收入、支出金额
均不计入汇总；借记卡以及超过配置天数的同金额交易不适用此规则。默认值为 31 天，也可通过环境变量
`BANK_TRANSACTION_REVIEW_REFUND_WINDOW_DAYS` 覆盖。
对于金额略小于原支出的退款，系统要求同一机构、同一卡片、同币种、同一商户，且收入摘要明确包含退款、
退货、退单、撤销或冲正语义。差额同时不超过
`bank_transaction_review.partial_refund_max_difference`（默认 200 元）和
`bank_transaction_review.partial_refund_max_difference_ratio`（默认原支出的 5%）时，审核页以浅黄色斜线标记两条
“差额退款”流水，保留原金额，并在详情中显示“原支出 − 退款 = 净支出”；底部金额汇总只把这笔净差额计入
支出，不把退款收入重复计入。超过阈值的普通部分退款以浅蓝色标记，提示人工确认差额性质，收入和支出仍按
各自原金额分别汇总。匹配固定按“全额退款 → 小差额退款 → 普通部分退款”的顺序执行，金额最接近的候选优先，
避免低置信度的普通部分退款抢占正确关系。两个差额阈值可分别通过
`BANK_TRANSACTION_REVIEW_PARTIAL_REFUND_MAX_DIFFERENCE` 和
`BANK_TRANSACTION_REVIEW_PARTIAL_REFUND_MAX_DIFFERENCE_RATIO` 覆盖。
人工确认某组邮件或附件属于重复信息源时，可在被 Git 忽略的
`raw_data/bank_source_selection.local.txt` 中登记 `excluded_source_tokens`。归一化会在去重前排除匹配来源，
原始 EML/PDF 仍保留在 `raw_data`；权威来源和被排除来源的路径、SHA-256及人工决定也可记录在同一文件中。
配置项 `bank_transaction_review.source_selection_file` 可修改该本机清单的位置。
完整审核集含个人财务信息，只能保存在被 Git 忽略的 `processed_data/` 中。

每个原始数据源行、PDF 页/行、Excel/CSV 行或邮件候选均保存独立的 `source_record_sha256`；每条银行、
支付宝、微信及购物订单流水均保存唯一的 64 位 `flow_hash_sha256`，对应类型还保存
`transaction_hash_sha256` 或 `order_hash_sha256`。来源记录中的原始 EML、原始加密附件、解密后解析文件等均记录
64 位文件 SHA-256；`record_fingerprint_sha256` 是归一化记录的完整规范化指纹；`record_version`、
`supersedes_record_ids` 和 `supersedes_record_fingerprints_sha256` 连接修正前后的版本。被替代的旧版本
追加保存在 `bank_transactions_history.jsonl` 或 `financial_transactions_history.jsonl`，原有 PDF 页码、
Excel/CSV 行号、工作表和邮件 UID 定位字段继续保留。

### PDF 原页与识别数据双栏审核

根目录独立入口 `pdf_ocr_review_app.py` 只用于人工核对已经生成过哈希缓存的 PDF，不重新执行交易提取 OCR、
不执行归一化，也不把数据再次计入财务统计（首次打开时只用 OCR 定位左右边框）：

```powershell
python pdf_ocr_review_app.py
```

程序默认选择交通银行案例。左侧按页渲染原始 PDF，右侧使用同一 SHA-256 缓存中的逐页识别表格，
两侧保持完全相同的页面高度和纵向滚动位置；左右分别提供横向滚动条。可以切换机构、PDF、页码和缩放比例，
鼠标位于任一审核画布时可按住 `Ctrl` 滚动滚轮逐级放大或缩小，并保留当前审核位置。
按住 `Ctrl` 和鼠标左键左右拖动任一画布时，左右两页会同步横向移动；一侧先到边界时，另一侧仍可继续移动，
方便核对超出窗口宽度的列。
左侧原始 PDF 默认按 175% 显示，较初版提高两档，便于直接核对小字号流水。
右侧识别表格字体在原有缩放规则上整体增加两个字号，便于与原 PDF 逐行核对。
首次打开一个 PDF 时，程序仅对第一页执行一次 OCR，用文字范围识别左右空白边框；裁剪后的内容宽度作为
左侧 PDF 和右侧识别表格共同的初始显示范围。裁边位置按完整 PDF SHA-256 保存到根目录本地文件
`pdf_ocr_crop_positions.local.json`，同一文件以后直接复用，不重复 OCR；内容变化导致哈希变化时才重新识别。
该本地缓存已加入 Git 忽略规则，不提交到仓库。
也可以选择任意已有缓存的 PDF。每页可标记“待审核”“一致”或“存在问题”并填写备注，结论独立保存到：
“确认通过”按钮会把当前页直接标记为“一致”并立即保存；不会自动跳转到下一页。

```text
processed_data/pdf_html_review/pdf_ocr_manual_review.json
```

该审核文件和识别缓存均含本地个人数据，已处于 Git 忽略目录。

## 归一化、账本与人工校核

银行流水、订单截图 AI JSON 等结构化结果可以统一汇总到 normalized 中间层：

```powershell
python flows/normalize_transactions.py
```

默认输出：

```text
processed_data/normalized/bank_transactions.jsonl
processed_data/normalized/orders.jsonl
processed_data/normalized/orders.json
processed_data/normalized/orders_full_review.html
processed_data/normalized/orders_history.jsonl
processed_data/normalized/financial_transactions.jsonl
processed_data/normalized/financial_transactions_history.jsonl
processed_data/normalized/financial_transaction_links.jsonl
processed_data/normalized/payment_chain_links.jsonl
processed_data/normalized/normalized_quality_report.md
```

订单归一化会自动发现 `raw_data/pdd/*.png`、`raw_data/meituan/*.png` 和
`raw_data/jd/*.pdf`。拼多多和美团截图优先复用 `raw_data/order_json/<platform>/` 中的
已识别 JSON，仅对尚无同名 JSON 的截图调用本地视觉模型，因此支持断点续跑。
京东 PDF 优先使用自带文本层解析，只对字体编码异常的页面按需 OCR。
三个平台目录中的 CSV、XLS 或 XLSX 订单表也会根据中文列名自动映射，并保留工作表与行号定位。
归一化订单保存平台、下单时间、实付金额、商户、商品全名、规格、数量、状态、
订单号、原始 PDF 页码或截图定位。记录指纹、版本关系与原始文件 SHA-256 和银行流水采用同一追溯规则。
`orders_full_review.html` 支持平台、日期、金额区间、商户、商品、状态及“有告警/无告警”筛选，
在 GUI“交易归一”页可直接打开，并可调用本机默认程序打开原始 PDF 或截图。

### 根目录人工审核快捷入口

Windows 下可直接双击根目录批处理文件：

- `open_bank_review.bat` 打开 `bank_transactions_full_review.html` 银行流水审核页。
- `open_consumption_review.bat` 同时打开 `orders_full_review.html`（美团、拼多多、京东）和
  `payment_transactions_full_review.html`（淘宝 CSV 流水所在审核页）。

批处理使用项目相对路径，不依赖当前盘符或 CloudStation 的绝对目录；审核 HTML 尚未生成时会显示提示，
不会打开备份目录中的旧页面。

macOS 下可双击对应的 `.command` 文件：

- `open_bank_review.command` 打开银行流水审核页。
- `open_consumption_review.command` 同时打开美团/拼多多/京东订单审核页和包含淘宝流水的支付审核页。

macOS 脚本根据自身所在目录定位项目，不写死 Windows 的 `D:\CloudStation` 或 macOS 的
`~/SynologyDrive/`。因此项目在不同系统使用不同 CloudStation 目录名称时无需修改脚本。
如果首次双击被 macOS 拒绝执行，可在项目根目录运行一次
`chmod +x open_bank_review.command open_consumption_review.command`。

当前完整审核页是独立于银行流水审核页的购物订单审核集。本轮实测读取拼多多截图 147 张、
美团截图 292 张以及京东 PDF 45 份（152 页），由 2,590 条页面级候选合并为 2,380 条：
拼多多 438 条、美团 1,155 条、京东 787 条。所有审核记录均保存归一化指纹和原始来源
SHA-256；京东无文本层的 3 页按需调用本地 AI/OCR，其余 PDF 使用文本层解析。
拼多多订单列表截图本身不显示订单日期，程序不会根据截图文件名推测日期，审核时应结合
可点击的原始截图确认。

其中 `financial_transactions` 是财务事实中间层，明确区分银行流水、支付宝/微信支付账户流水和订单事实；
每条事实也保存唯一的 `flow_hash_sha256`。`financial_transaction_links` 保持订单到付款流水的兼容关联，
`payment_chain_links` 进一步汇总“订单 → 支付账户/银行卡”和“支付宝/微信 → 银行卡”的带哈希关系。
支付账户到银行卡只在金额完全相同、日期相近且银行渠道明确匹配时建立；多候选情况标记为 `candidate`，
不自动认定唯一链路。最终账本仍以资金流水为主来源，订单只补充购物、外卖、平台服务等明细，避免重复统计。

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
