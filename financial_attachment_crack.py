"""财务附件密码破解工具

用途：
  对邮件工作流发现的加密 ZIP/PDF 附件尝试候选密码、hashcat 字典或数字掩码破解。

配置文件：
  默认读取项目根目录 ``config.yaml`` 和本地密码文件；外部工具路径由
  ``financial_attachment_cracker`` 配置及 ``common.env`` 提供。

参数：
  使用 ``--help`` 查看附件范围、破解模式、工具路径、密码显示和输出选项。

示例：
  python financial_attachment_crack.py --check-tools
  python financial_attachment_crack.py --target encrypted

输出：
  破解结果仅写入被 Git 忽略的本地密码文件和 ``raw_data/``；默认不在控制台显示真实密码。
"""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
SRC_PATH = str(PROJECT_ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from localai.modules.financial_attachment_cracker import main


if __name__ == "__main__":
    raise SystemExit(main(__doc__))
