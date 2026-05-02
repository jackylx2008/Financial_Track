# Financial Track

个人消费订单采集辅助工具。当前项目包含两类能力：

- 京东、淘宝订单页面导出为 PDF。
- 通过安卓手机 ADB 截取拼多多、美团订单页面截图，作为后续 OCR 和 AI 结构化识别的输入。

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
  config.yaml                # 京东 PDF 导出配置
  common.env                 # 本地环境变量
  raw_data/                  # 本地采集数据，已被 git 忽略
```

## 环境准备

建议使用 Python 3.11+。

安装 Python 依赖：

```powershell
pip install playwright pyyaml python-dotenv pyautogui pillow
python -m playwright install chromium
```

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

## 数据与隐私

`raw_data/`、`log/`、环境文件和输出目录已在 `.gitignore` 中排除。订单截图、浏览器登录状态、PDF 输出等本地隐私数据不应提交到 git。

当前安卓截图只是采集阶段，后续 OCR、AI 识别和订单级去重应基于这些截图继续扩展。
