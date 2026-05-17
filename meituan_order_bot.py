# -*- coding: utf-8 -*-
"""美团订单截图采集快捷入口

用途：
  作为 `android_order_bot.py` 的美团平台兼容入口，默认选择美团平台并复用 Android 订单截图采集流程。

配置文件：
  本入口不读取 `config.yaml` 或 `.env`。ADB 路径优先使用 `--adb` 指定值，其次使用系统 PATH，
  再尝试常见模拟器自带 ADB。默认输出目录为 `raw_data/meituan`。

必填参数：
  command  采集命令，可选 `capture`、`capture-scroll`、`capture-until-end`。

可选参数：
  --device            ADB 设备序列号，多设备连接时使用。
  --adb               adb.exe 路径。
  --output-dir        截图输出目录，默认 `raw_data/meituan`。
  --keep-existing     保留输出目录中已有的美团截图。
  --pages             `capture-scroll` 的截图页数，默认 5。
  --max-pages         `capture-until-end` 的最大截图页数，默认 50。
  --wait              滑动后等待秒数，默认 1.5。
  --stable-threshold  判定页面不再变化的相似度阈值，默认 0.995。

示例：
  python meituan_order_bot.py capture --device 10CF8C17KP004G0
  python meituan_order_bot.py capture-until-end --device 10CF8C17KP004G0

输出：
  将 PNG 截图写入输出目录，并在控制台打印生成的截图路径、相似度和停止原因等运行信息。
"""

from __future__ import annotations

from android_order_bot import main


if __name__ == "__main__":
    raise SystemExit(main(default_platform="meituan"))
