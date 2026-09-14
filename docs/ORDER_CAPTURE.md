# 安卓交易流水截图采集

## 目标与边界

用户先在 USB 安卓实体机上打开目标 App 和交易流水页面，项目负责连接检查、屏幕尺寸读取、截图、坐标换算、滑动和到底判断。项目不会启动 App，不处理登录，也不自动跳转页面。

当前支持 macOS 和 Windows：

- macOS：依次使用 GUI 指定的 ADB 和系统 `PATH` 中的 `adb`。
- Windows：依次使用 GUI 指定的 ADB、系统 `PATH`、`ANDROID_SDK_ROOT`、`ANDROID_HOME` 和标准 Android SDK 目录。
- 仅支持 USB 实体手机，不探测或适配 MuMu 等安卓模拟器。

## 本机 App 配置

App 名称、输出目录、参考屏幕尺寸和默认滑动参数只放在被 Git 忽略的 `common.env`，不放在 `config.yaml`。配置格式如下：

```dotenv
ANDROID_CAPTURE_APPS_JSON=[{"key":"sample_wallet","name":"示例钱包","output_dir":"./raw_data/android_transactions/sample_wallet","filename_prefix":"sample_wallet","reference_size":[1080,2400],"swipe":[540,1700,540,600,600]}]
```

字段含义：

- `key`：稳定、唯一的英文标识。
- `name`：GUI 下拉框显示名称。
- `output_dir`：本机截图输出目录。
- `filename_prefix`：截图文件名前缀。
- `reference_size`：配置滑动坐标时使用的参考 `[宽, 高]`。
- `swipe`：参考分辨率上的 `[起点X, 起点Y, 终点X, 终点Y, 持续毫秒]`。

增加 App 时只需向 JSON 数组追加对象，不需要新增 Python 入口。

## GUI 使用

启动：

```bash
python main.py
```

进入“安卓 App 采集”页签，从下拉框选择 App。建议先选择 `check` 模式检查 ADB、设备授权、屏幕尺寸和坐标换算。随后在手机上手动打开交易流水页面，再选择：

- `capture`：截取当前屏幕一次。
- `capture-scroll`：按固定截图数采集并滑动。
- `capture-until-end`：持续采集，直到相邻页面稳定或达到最大截图数。

默认会清理输出目录中同一 App 文件名前缀的旧 PNG。需要保留时勾选“保留已有截图”。

## 通用 CLI 调试

GUI 是正式入口；排查问题时可以直接调用底层统一入口：

```bash
python flows/android_transaction_capture.py check --app sample_wallet
python flows/android_transaction_capture.py capture --app sample_wallet --keep-existing
python flows/android_transaction_capture.py capture-scroll --app sample_wallet --pages 5 --wait 1.5
python flows/android_transaction_capture.py capture-until-end --app sample_wallet --max-pages 50 --stop-on-stable
```

连接多台手机时使用 `--device <device_serial>`。GUI 命令预览和文件日志会显示脱敏序列号，不显示完整值。

## 日志与隐私

日志统一写入项目根目录：

```text
logs/android_capture_macos.log
logs/android_capture_windows.log
```

日志包含操作系统、ADB 路径、脱敏设备序列号、屏幕尺寸、App key、输出目录、截图结果、滑动参数和错误。日志不写入截图内容、完整设备序列号或交易流水内容。

## 光大银行三页人工测试

手机停在需要截取的光大银行流水页面后运行：

```bash
python tests/manual_cebbank_capture.py
```

该入口每次启动都会先清空 `tests/manual_android_capture/cebbank/` 中已有的 PNG，再截取并保存 3 页，方便人工校核。目录已被 Git 忽略，真实流水截图不会提交到仓库。
