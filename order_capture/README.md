# 订单截图采集 MVP

## 当前目标

手动打开手机 App 的订单页，然后用 ADB 截取当前屏幕，保存为后续 OCR 和 AI 解析的输入。

## 真机截图

先确认手机已连接：

```powershell
cd "C:\Program Files\Netease\MuMu\nx_device\12.0\shell"
.\adb.exe devices
```

看到类似下面的输出即可：

```text
10CF8C17KP004G0 device
```

在项目根目录执行：

```powershell
python -m order_capture.capture_screen pinduoduo --device 10CF8C17KP004G0
```

截图会保存到：

```text
raw_data/order_capture/screenshots/
```

脚本会在终端输出本次截图文件路径。

## 安卓订单入口脚本

项目根目录提供了通用安卓订单截图入口，支持拼多多和美团：

```powershell
python pdd_order_bot.py capture --device 10CF8C17KP004G0
python meituan_order_bot.py capture --device 10CF8C17KP004G0
```

默认输出目录：

```text
raw_data/pdd/
raw_data/meituan/
```

默认文件名前缀：

```text
pinduoduo_YYYYMMDD_HHMMSS.png
meituan_YYYYMMDD_HHMMSS.png
```

每次启动截图命令时，脚本会先清理当前平台输出目录里已有的同平台截图：

```text
raw_data/pdd/pinduoduo_*.png
raw_data/meituan/meituan_*.png
```

如果需要保留已有截图，可以加：

```powershell
--keep-existing
```

也可以使用平台专用兼容入口：

```powershell
python pdd_order_bot.py capture --device 10CF8C17KP004G0
python meituan_order_bot.py capture --device 10CF8C17KP004G0
```

连续截图并自动上滑：

```powershell
python pdd_order_bot.py capture-scroll --device 10CF8C17KP004G0 --pages 5 --wait 1.5
python meituan_order_bot.py capture-scroll --device 10CF8C17KP004G0 --pages 5 --wait 1.5
```

`capture-scroll` 会先截取当前页面，然后上滑，再等待 `--wait` 秒，直到保存 `--pages` 张截图。默认滑动参数适合常见 1080 宽安卓屏幕；如果滑动距离不合适，可以调整：

```powershell
python meituan_order_bot.py capture-scroll --device 10CF8C17KP004G0 --pages 5 --start-x 540 --start-y 1700 --end-x 540 --end-y 500 --duration-ms 600
```

不知道总页数时，使用自动到底模式：

```powershell
python pdd_order_bot.py capture-until-end --device 10CF8C17KP004G0 --max-pages 50 --wait 1.5
python meituan_order_bot.py capture-until-end --device 10CF8C17KP004G0 --max-pages 50 --wait 1.5
```

脚本会先截图当前页面，再上滑；如果上滑后的截图和上一张主体区域几乎没有变化，就判断已经到底并停止。`--max-pages` 是保险上限，避免页面异常时无限运行。

如果遇到美团这类页面提示“显示更多历史订单”，脚本检测到画面不变时会暂停。你可以先在手机上手工点击该按钮，然后在终端输入 `c` 继续截图；直接回车则停止。

如果停止太早，可以提高阈值或增大滑动距离：

```powershell
python meituan_order_bot.py capture-until-end --device 10CF8C17KP004G0 --max-pages 50 --stable-threshold 0.998 --start-y 1800 --end-y 450
```

如果希望恢复旧行为，检测到画面不变时直接停止：

```powershell
python meituan_order_bot.py capture-until-end --device 10CF8C17KP004G0 --max-pages 50 --stop-on-stable
```
