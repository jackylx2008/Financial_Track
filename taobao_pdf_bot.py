# -*- coding: utf-8 -*-
"""淘宝订单分页自动打印 PDF 工具

用途：
  通过 PyAutoGUI 操作当前浏览器页面，按“点击下一页、触发 Ctrl+P、确认另存为 PDF、输入文件名”的顺序循环导出
  淘宝订单分页 PDF，直到用户按 Ctrl+C 中断。

配置文件：
  本入口不读取 `config.yaml` 或 `.env`。运行参数固定写在文件顶部配置区，包括页面加载等待、打印对话框等待、
  保存对话框等待、页间随机等待、启动倒计时和起始页码。运行前需要手动打开淘宝订单页面，并将浏览器默认打印目标
  设置为“另存为 PDF”。

必填参数：
  无。本工具通过文件顶部配置区和当前浏览器状态运行。

可选参数：
  无。需要调整等待时间、起始页码或倒计时，请修改文件顶部配置区。

示例：
  python taobao_pdf_bot.py

输出：
  PDF 由系统打印保存对话框写入用户选择的目录，文件名格式为 `<运行日期>_淘宝订单_<页码>.pdf`；
  控制台和日志输出每页处理进度、保存文件名和中断统计。

依赖：
  pip install pyautogui
"""

import pyautogui
import random
import time
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_PATH = str(PROJECT_ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from localai.logging_config import get_logger, setup_logger

# ================= 配置区域 =================
# 请根据电脑性能和网络速度调整以下延迟时间（单位：秒）
DELAY_PAGE_LOAD = 5.0  # 点击“下一页”后等待页面加载的时间
DELAY_PRINT_DIALOG = 3.0  # Ctrl+P 后等待打印预览弹出的时间
DELAY_SAVE_DIALOG = 2.0  # 点击“保存”后等待文件命名窗口弹出的时间
DELAY_AFTER_SAVE_MIN = 2.0  # 每页保存完成后的最短等待时间
DELAY_AFTER_SAVE_MAX = 6.0  # 每页保存完成后的最长等待时间
DELAY_BETWEEN_ACTIONS = 1.0  # 每个自动操作之间的短暂停顿时间
COUNTDOWN_BEFORE_START = 5  # 脚本启动后正式执行前的准备倒计时
COUNTDOWN_BEFORE_CLICK = 0  # 每次点击前倒数秒数（用于手动调整鼠标位置）
START_PAGE = 1  # 起始页码

# ===========================================


logger = get_logger(__name__)


def log_countdown(seconds: int, message: str) -> None:
    logger.info("%s，倒计时 %s 秒。", message, seconds)
    for i in range(seconds, 0, -1):
        logger.info("倒计时: %s 秒", i)
        time.sleep(1)


def pause_between_actions() -> None:
    time.sleep(DELAY_BETWEEN_ACTIONS)


def main():
    setup_logger(log_level="INFO")

    # 安全设置：鼠标移到屏幕左上角可紧急停止脚本
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.1

    logger.info("=" * 50)
    logger.info("淘宝订单自动打印 PDF 脚本已启动")
    logger.info(
        "配置：页面加载延迟=%ss | 打印对话框延迟=%ss | 保存对话框延迟=%ss | 操作间隔=%ss | 页间随机等待=%s-%ss",
        DELAY_PAGE_LOAD,
        DELAY_PRINT_DIALOG,
        DELAY_SAVE_DIALOG,
        DELAY_BETWEEN_ACTIONS,
        DELAY_AFTER_SAVE_MIN,
        DELAY_AFTER_SAVE_MAX,
    )
    logger.info("请确保浏览器已设置为默认【另存为 PDF】")
    logger.info("随时按 Ctrl+C 安全退出 | 紧急停止：将鼠标迅速移至屏幕左上角")
    logger.info("=" * 50)
    log_countdown(
        COUNTDOWN_BEFORE_START,
        "请打开淘宝订单页面，并将鼠标移动到【下一页】按钮上",
    )

    page_num = START_PAGE
    run_date = datetime.now().strftime("%Y%m%d")

    try:
        while True:
            logger.info("--- 准备处理第 %s 页 ---", page_num)
            log_countdown(
                COUNTDOWN_BEFORE_CLICK,
                "请确认鼠标位于【下一页】按钮上",
            )
            logger.info("已点击，等待页面加载...")
            pyautogui.click()
            pause_between_actions()
            time.sleep(DELAY_PAGE_LOAD)

            logger.info("触发 Ctrl+P 打印...")
            pyautogui.hotkey("ctrl", "p")
            pause_between_actions()
            time.sleep(DELAY_PRINT_DIALOG)

            logger.info("按 Enter 确认保存为 PDF...")
            pyautogui.press("enter")
            pause_between_actions()
            time.sleep(DELAY_SAVE_DIALOG)

            # 自动重命名文件
            filename = f"{run_date}_淘宝订单_{page_num:02d}"
            logger.info("输入文件名: %s.pdf", filename)
            pyautogui.hotkey("ctrl", "a")  # 全选默认文件名
            pause_between_actions()
            pyautogui.write(filename, interval=0.05)
            pause_between_actions()
            pyautogui.press("enter")  # 确认保存
            pause_between_actions()

            logger.info("第 %s 页 PDF 已成功保存。", page_num)
            page_num += 1
            delay_after_save = random.uniform(
                DELAY_AFTER_SAVE_MIN, DELAY_AFTER_SAVE_MAX
            )
            logger.info("本轮完成，随机等待 %.2f 秒后继续。", delay_after_save)
            time.sleep(delay_after_save)

    except KeyboardInterrupt:
        logger.info("检测到 Ctrl+C，脚本已安全退出。")
        logger.info("共成功处理 %s 个文件。", page_num - 1)
        sys.exit(0)
    except Exception as e:
        logger.exception("发生未预期错误: %s", e)
        logger.error("提示：可能是浏览器弹窗被拦截或延迟时间不足，请调整配置后重试。")
        sys.exit(1)


if __name__ == "__main__":
    main()
