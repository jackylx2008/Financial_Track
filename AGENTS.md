# Financial Track AI 编程协作规范

本文件适用于整个仓库。更完整的通用说明见 `docs/CROSS_PLATFORM_PROGRAMMING.md` 和
`docs/COMMON_PROJECT_SKILLS.md`；发生冲突时，以用户当前请求、本文件和更具体目录中的 `AGENTS.md` 为准。

## 项目结构

- 根目录只保留 `main.py` GUI 入口和 `logging_config.py` 日志配置。
- `flows/*.py` 是可独立执行的工作流入口，只负责参数解析、配置、日志、上下文、编排调用和退出状态。
- `flows/workflows/` 负责场景编排，`flows/modules/` 负责单一职责的可复用能力。
- 配置统一从根目录 `config.yaml` 加载，本机差异和凭据仅放在被忽略的 `common.env` 或专用 env 文件。
- 日志统一通过根目录 `logging_config.py` 初始化并写入 `logs/`。
- 测试统一放在 `tests/`，不得读取或修改真实个人财务数据。
- 除 `README.md` 和本文件外，项目说明文档统一放在 `docs/`。

## 安全与隐私

- 不提交 `common.env`、附件密码、令牌、邮箱授权码、浏览器 profile、原始账单、订单截图、日志或处理结果。
- 示例必须使用 `demo`、`sample`、`example` 等脱敏值，不写个人用户名、设备序列号或本机私有路径。
- 不对 `raw_data/`、`processed_data/` 或外部同步目录执行测试写入；使用临时目录和最小样本。
- 不用破坏性 Git 命令清理云盘同步产生的异常状态；先比较工作树、HEAD 和远端内容。

## 跨平台要求

- 使用 `pathlib.Path`，不在业务代码中拼接路径或硬编码盘符、用户名、路径分隔符。
- CloudStation 根目录使用 `${CLOUDSTATION_ROOT}`；平台变量为
  `CLOUDSTATION_ROOT_WINDOWS`、`CLOUDSTATION_ROOT_MACOS`、`CLOUDSTATION_ROOT_LINUX`。
- 文本默认 UTF-8；不要因为 CRLF/LF 提示批量改写无关文件。
- 平台专用外部命令集中封装，对不支持的平台给出明确错误。

## 修改与验证

修改前检查工作区和调用链。行为变化时同步更新 README、示例配置和测试。完成前至少运行：

```powershell
$env:PYTHONPATH='.'
python -m unittest discover -s tests -v
python -m compileall -q -f -x 'vendor|raw_data|processed_data|logs?|__pycache__' .
python -m flake8 .
git diff --check
```

若某项因环境或外部服务无法运行，必须报告具体限制，不得隐藏失败。
