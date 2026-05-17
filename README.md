# Financial Track

个人消费与银行流水采集整理辅助工具。当前项目包含几类能力：

- 京东、淘宝订单页面导出为 PDF。
- 通过安卓手机 ADB 截取拼多多、美团订单页面截图，作为后续 OCR 和 AI 结构化识别的输入。
- 调用本地 `llama.cpp` OpenAI 兼容接口，对订单截图做结构化识别。
- 采集银行邮件、解密/解压账单附件，并整理为统一银行流水中间层。

本项目面向个人账号自用，不包含平台逆向接口、抓包或绕过风控逻辑。

## 目录结构

```text
Financial_Track/
  android_order_bot.py       # 安卓订单截图通用入口，支持 pdd/meituan
  pdd_order_bot.py           # 拼多多截图兼容入口
  meituan_order_bot.py       # 美团截图入口
  order_capture/             # ADB 截图基础模块
  jd_pdf_bot.py              # 京东订单 PDF 导出
  taobao_pdf_bot.py          # 淘宝订单 PDF 辅助打印
  bank_email_bot.py          # 银行邮件原始数据采集
  bank_attachment_prepare.py # 银行附件密码匹配与清单生成
  bank_attachment_extract.py # 银行附件解密/解压
  consolidate_bank_transactions.py # 银行流水统一整理
  src/localai/
    entrypoints.py           # 入口脚本公共启动辅助
    logging_config.py        # 统一日志配置
    flows/                   # 场景编排层
    modules/                 # 可复用基础能力模块
  config.yaml                # 项目运行配置
  common.env.example         # 本地环境变量模板
  raw_data/                  # 本地采集数据，已被 git 忽略
  log/                       # 运行日志，已被 git 忽略
```

项目采用“根目录独立入口脚本 + `src/localai/flows` 编排层 + `src/localai/modules` 基础模块”的结构。入口脚本只负责读取配置、初始化日志、创建上下文并调用对应流程，核心处理逻辑应放在 `flows` 或 `modules` 中。

## 环境准备

建议使用 Python 3.11+。

安装 Python 依赖：

```powershell
pip install -r requirements.txt
python -m playwright install chromium
```

如果只运行部分工具，也可以按需安装：

```powershell
pip install playwright pyyaml python-dotenv pyautogui pillow
```

## 配置、日志与本地文件

项目配置入口是根目录 `config.yaml`。本机路径、账号、授权码、服务路径等本地差异放在 `common.env`，仓库只保留 `common.env.example` 作为模板：

```powershell
Copy-Item common.env.example common.env
```

跨 Windows、macOS 或 Linux 同步开发时，不要在源码或 `config.yaml` 中写死本机绝对路径。推荐使用 `${CLOUDSTATION_ROOT}` 占位，并在 `common.env` 中配置平台变量：

```env
CLOUDSTATION_ROOT_WINDOWS=D:\CloudStation
CLOUDSTATION_ROOT_MACOS=~/CloudStation
CLOUDSTATION_ROOT_LINUX=~/CloudStation
```

统一日志配置位于 `src/localai/logging_config.py`，不再放在项目根目录。默认日志写入根目录 `log/`，日志文件名通常对应入口脚本名，例如：

```text
log/ai_self_check.log
log/order_image_ai.log
log/bank_email_bot.log
```

`common.env`、`bank_attachment_passwords.env`、`raw_data/`、`log/`、`vendor/` 等本地文件或运行产物不应提交到 git。

安卓订单截图需要 ADB。可以使用 Android Platform Tools，也可以使用 MuMu 自带的 ADB：

```text
C:\Program Files\Netease\MuMu\nx_device\12.0\shell\adb.exe
```

确认安卓手机已打开 USB 调试，并能被 ADB 识别：

```powershell
adb devices
```

或使用 MuMu 自带 ADB：

```powershell
cd "C:\Program Files\Netease\MuMu\nx_device\12.0\shell"
.\adb.exe devices
```

正常输出类似：

```text
10CF8C17KP004G0 device
```

## 安卓订单截图

通用入口支持拼多多和美团：

```powershell
python android_order_bot.py pdd capture --device 10CF8C17KP004G0
python android_order_bot.py meituan capture --device 10CF8C17KP004G0
```

也可以使用平台专用入口：

```powershell
python pdd_order_bot.py capture --device 10CF8C17KP004G0
python meituan_order_bot.py capture --device 10CF8C17KP004G0
```

默认输出：

```text
raw_data/pdd/pinduoduo_*.png
raw_data/meituan/meituan_*.png
```

每次启动截图命令时，会先清理对应目录下已有的同平台截图。需要保留已有截图时，加：

```powershell
--keep-existing
```

### 固定页数连续截图

```powershell
python pdd_order_bot.py capture-scroll --device 10CF8C17KP004G0 --pages 5 --wait 1.5
python meituan_order_bot.py capture-scroll --device 10CF8C17KP004G0 --pages 5 --wait 1.5
```

### 自动截图到列表底部

```powershell
python pdd_order_bot.py capture-until-end --device 10CF8C17KP004G0 --max-pages 80 --wait 1.5
python meituan_order_bot.py capture-until-end --device 10CF8C17KP004G0 --max-pages 150 --wait 1.5
```

脚本通过比较相邻截图主体区域判断是否已经到底。美团如果提示“显示更多历史订单”，脚本会暂停；手工点击手机上的按钮后，在终端输入 `c` 继续。直接回车则停止。

拼多多默认使用更短的滑动距离 `--start-y 1700 --end-y 850`，让相邻截图保留更多重叠，避免订单金额刚好被滑过。美团默认仍是 `--start-y 1700 --end-y 500`。

滑动距离不合适时，可以调参数：

```powershell
python pdd_order_bot.py capture-until-end --device 10CF8C17KP004G0 --max-pages 120 --wait 1.5 --start-y 1700 --end-y 950
python meituan_order_bot.py capture-until-end --device 10CF8C17KP004G0 --max-pages 150 --start-y 1800 --end-y 450
```

## 京东订单 PDF

京东脚本使用 Playwright 持久化浏览器配置导出订单页 PDF。

先在 `common.env` 中配置输出目录：

```env
JD_PDF_OUTPUT_DIR=D:\your\pdf\output
```

`config.yaml` 中配置浏览器用户数据目录、等待时间和每年页数：

```yaml
jd_pdf_output_dir: {JD_PDF_OUTPUT_DIR}
jd_browser_user_data_dir: ./raw_data/jd_browser_profile
jd_pdf_headless: false
jd_pdf_wait_seconds: 5
jd_order_pages:
  2024: 4
  2023: 5
```

运行：

```powershell
python jd_pdf_bot.py
```

首次运行建议保持有头模式，手工登录京东。只导出指定 URL：

```powershell
python jd_pdf_bot.py --url "https://order.jd.com/center/list.action?d=2024&s=4096&page=1"
```

## 淘宝订单 PDF

淘宝脚本通过 `pyautogui` 辅助浏览器打印页面。使用前请确认浏览器默认打印目标为“另存为 PDF”，并打开淘宝订单页面。

运行：

```powershell
python taobao_pdf_bot.py
```

启动后把鼠标放在订单页“下一页”按钮上，脚本会循环点击下一页、触发 `Ctrl+P`、保存 PDF。按 `Ctrl+C` 可停止，鼠标移到屏幕左上角可触发 `pyautogui` 紧急停止。

## 本地 AI 自检

本地 AI 运行时用于后续订单截图 OCR 后的结构化识别。当前使用 `llama.cpp` 的 OpenAI 兼容 HTTP API。

配置说明见：

```text
LOCAL_AI_RUNTIME_SETUP.md
```

真实本机路径写入 `common.env`，不要提交到 git。关键变量包括：

```env
LLAMACPP_BASE_URL=http://127.0.0.1:8080/v1
LLAMACPP_MODEL=local-model
LLAMACPP_AUTOSTART=true
LLAMACPP_SERVER_PATH=
LLAMACPP_MODEL_PATH=
LLAMACPP_MMPROJ_PATH=
LLAMACPP_EXTRA_DLL_DIRS=./vendor/cuda12
LLAMACPP_N_GPU_LAYERS=999
LLAMACPP_CTX_SIZE=8192
```

`vendor/cuda12/` 只放本机运行需要的 CUDA runtime DLL，不提交到 git。需要的 DLL 从 NVIDIA 官方 CUDA Toolkit 获取：

```text
https://developer.nvidia.com/cuda-toolkit-archive
```

安装或解压 CUDA Toolkit 12.x 后，复制以下文件到 `vendor/cuda12/`：

```text
cudart64_12.dll
cublas64_12.dll
cublasLt64_12.dll
```

只检查 CUDA、服务健康状态和模型列表：

```powershell
python ai_self_check.py --no-chat
```

完整对话测试：

```powershell
python ai_self_check.py --prompt "请直接回答两个字：可用" --max-tokens 32
```

脚本会在需要时自动启动 `llama-server`，并在本次流程结束时关闭由它启动的服务以释放显存。

### 订单截图 AI 识别

识别最新一张拼多多截图：

```powershell
python order_image_ai.py pdd --max-tokens 1024
```

识别整个拼多多截图目录，默认会在终端显示进度条：

```powershell
python order_image_ai.py pdd --all --max-tokens 1024
```

关闭终端进度条：

```powershell
python order_image_ai.py pdd --all --max-tokens 1024 --no-progress
```

识别结果默认输出到：

```text
raw_data/order_json/pdd
raw_data/order_json/meituan
```

运行日志写入：

```text
log/order_image_ai.log
```

日志会记录任务参数、图片总数、每张图片的开始/完成、输出 JSON 路径、订单数量、告警和最终汇总。终端进度条本身不会逐帧写入日志。

## 数据与隐私

`raw_data/`、`log/`、环境文件和输出目录已在 `.gitignore` 中排除。订单截图、浏览器登录状态、PDF 输出等本地隐私数据不应提交到 git。

当前安卓截图只是采集阶段，后续 OCR、AI 识别和订单级去重应基于这些截图继续扩展。

## 银行邮件流水采集

银行交易提醒、信用卡账单等邮件可以作为另一类底层原始数据。项目提供 `bank_email_bot.py`，通过 IMAP 读取邮箱，把匹配到的银行邮件保存为本地原始产物：

```text
raw_data/email_bank/eml/                  # 邮件原文 .eml
raw_data/email_bank/body/                 # 抽取后的正文文本
raw_data/email_bank/attachments/          # 邮件附件
raw_data/email_bank/bank_email_records.jsonl
raw_data/email_bank/bank_email_records.json
raw_data/email_bank/bank_email_summary.md
```

先在 `common.env` 中配置邮箱 IMAP 信息。网易 126 邮箱使用 `imap.126.com:993`，密码应填写客户端授权码，不要使用网页登录密码：

```env
BANK_EMAIL_IMAP_HOST=imap.126.com
BANK_EMAIL_IMAP_PORT=993
BANK_EMAIL_IMAP_USER=your-account@126.com
BANK_EMAIL_IMAP_PASSWORD=your-126-authorization-code
BANK_EMAIL_CLIENT_SUPPORT_EMAIL=support@example.invalid
BANK_EMAIL_SINCE=2024-01-01
BANK_EMAIL_MAX_MESSAGES=200
BANK_EMAIL_SUBJECT_KEYWORDS_JSON=["银行","账单","流水","交易","动账","入账","扣款","信用卡","借记卡","电子回单","对账单"]
```

网易邮箱在第三方客户端登录后还要求发送 IMAP `ID` 客户端身份信息。项目会自动发送 `FinancialTrack` 的 `ID` 信息，以避免 `Unsafe Login. Please contact kefu@188.com for help` 这类 `SELECT/EXAMINE INBOX` 阶段拦截。

运行：

```powershell
python bank_email_bot.py --since 2024-01-01 --max-messages 500
```

也可以先解析已经导出的 `.eml` 文件，避免直接连接邮箱：

```powershell
python bank_email_bot.py --eml-dir raw_data/email_export
```

当前邮件解析会先按 `config.yaml` 中的 `bank_email.rules` 匹配银行邮件；如果没有命中银行规则，则使用 `BANK_EMAIL_SUBJECT_KEYWORDS_JSON` 中的标题关键字兜底捕捉银行账单/流水邮件。解析器会递归保存邮件中的 PDF 等附件，再用通用金额、时间、卡尾号正则抽取 `candidate_transactions`。这一步是“原始数据层”，不是最终账本；后续应按具体银行邮件模板增加专用 parser，并把候选交易合并进统一流水 schema。

### 银行附件密码准备

银行账单 PDF 或 ZIP 附件通常带密码。真实密码放在独立文件 `bank_attachment_passwords.env`，不要放进 `common.env`，也不要提交到版本库。先复制模板：

```powershell
Copy-Item bank_attachment_passwords.env.example bank_attachment_passwords.env
```

可配置项：

```env
BANK_ATTACHMENT_PASSWORD_DEFAULT=
BANK_ATTACHMENT_PASSWORD_BY_BANK_JSON={"cmb":"password-for-cmb"}
BANK_ATTACHMENT_PASSWORD_BY_FILENAME_JSON={"statement.pdf":"password-for-this-file"}
BANK_ATTACHMENT_PASSWORD_BY_PATTERN_JSON={"招商":"password-for-filename-containing-this-text"}
BANK_ATTACHMENT_PASSWORD_BY_TYPE_JSON={"pdf":["pdf-password-1","pdf-password-2"],"zip":["zip-password-1","zip-password-2"]}
BANK_ATTACHMENT_PDF_PWD=["pdf-password-1","pdf-password-2"]
BANK_ATTACHMENT_ZIP_PWD=["zip-password-1","zip-password-2"]
```

生成附件清单并检查哪些附件还缺密码：

```powershell
python bank_attachment_prepare.py
```

默认输出：

```text
raw_data/email_bank/attachment_inventory.json
raw_data/email_bank/attachment_inventory.md
```

`BANK_ATTACHMENT_PASSWORD_BY_TYPE_JSON` 是标准的按文件类型配置方式；`BANK_ATTACHMENT_PDF_PWD` 和 `BANK_ATTACHMENT_ZIP_PWD` 是按类型配置的简写。清单只记录是否已匹配到密码、匹配来源和候选密码数量，不输出真实密码。

尝试解密/解压附件：

```powershell
python bank_attachment_extract.py
```

默认输出：

```text
raw_data/email_bank/extracted_attachments/attachment_extract_manifest.json
raw_data/email_bank/extracted_attachments/attachment_extract_failures.md
```

日志会记录每个附件的解密/解压结果、密码来源和候选数量，不记录真实密码。

### 银行流水统一整理

已下载的邮件正文候选交易和已成功解密/解压的 PDF、ZIP 内部文件可以整理为统一银行流水中间层：

```powershell
python consolidate_bank_transactions.py
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

整理过程会按统一 schema 标准化金额、方向、账户尾号、来源引用等字段，并在 normalized 层做去重合并。每条去重后的记录会保留 `source_records`，用于回查原始邮件、附件、PDF 或 Excel 行。邮件正文候选通常缺交易时间和账户信息，当前按低置信度来源进入质量报告；已成功解密的 PDF/XLS 附件是第一阶段更可靠的流水来源。

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

提交前重点确认不要提交本地隐私数据、真实账单、浏览器 profile、授权码、token、密码、附件、订单截图、账单 PDF、`common.env` 或 `bank_attachment_passwords.env`：

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
