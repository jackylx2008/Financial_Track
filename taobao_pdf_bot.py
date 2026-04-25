# -*- coding: utf-8 -*-
"""
淘宝订单分页自动打印 PDF 工具 (taobao_order_pdf_auto.py)
功能：自动点击下一页 → Ctrl+P 打印 → 重命名保存 → 循环至 Ctrl+C 中断
依赖：pip install pyautogui
注意：请确保浏览器默认打印目标为“另存为 PDF”，且打印对话框布局为标准样式。
"""

import pyautogui
import random
import time
import sys
from datetime import datetime

from logging_config import get_logger, setup_logger

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
