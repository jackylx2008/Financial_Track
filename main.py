"""Financial Track 图形界面入口

用途：
  启动个人财务信息追溯桌面控制台，通过统一窗口运行邮件流水、附件破解、订单采集与识别、
  交易归一、账本构建、审核导出、订单归档和外部 AI 服务自检工作流。

配置文件：
  固定读取项目根目录 ``config.yaml``；本机路径、邮箱授权码和模型路径由被 Git 忽略的
  ``common.env`` 提供，附件密码保存在专用本地 env 文件中。

必填参数：
  无。各工作流参数在图形界面的对应选项卡中填写。

示例：
  python main.py

输出：
  界面显示实时日志、总体进度、状态与实际耗时；各工作流仍写入其原有 ``raw_data/``、
  ``processed_data/`` 和 ``logs/`` 目标位置。
"""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent

from flows.gui.app import run


if __name__ == "__main__":
    raise SystemExit(run(PROJECT_ROOT))
