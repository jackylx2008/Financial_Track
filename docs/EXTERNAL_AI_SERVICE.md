# 外部 AI 服务接入

Financial Track 不负责安装模型、启动推理服务、配置 CUDA 运行时或管理推理进程。相关能力由独立的
AI 运行时项目提供，本项目仅通过 OpenAI 兼容 HTTP API 调用已经运行的服务。

## 接口要求

外部服务需要提供以下接口：

- `GET /health`
- `GET /v1/models`
- `POST /v1/chat/completions`

订单截图识别还要求服务和模型支持 OpenAI 兼容的图片 data URL 输入。

## 连接配置

连接默认值保留在 `config.yaml` 的 `llamacpp` 段。地址、模型或令牌既可由启动本项目的进程环境注入，
也可写入被 Git 忽略的本机 `common.env`。令牌不得写入 `config.yaml` 或提交到版本库。
变量名前缀仅用于保持现有客户端兼容，服务可以由任意实现提供，只要接口兼容。

GUI 状态栏只显示以下静态配置信息，不会访问 AI 服务：

- 尚未检测，实际使用 AI 功能时才检查服务；
- 配置的模型名称；
- 本机调用地址。

订单图片识别等 AI 工作流真正开始时，会先访问健康和模型接口；检查失败则停止该工作流并记录错误。
GUI 启动、配置重载和空闲期间均不执行心跳或测试对话。

财务邮件归一化首先使用银行专用正文规则和 PDF、XLS/XLSX、CSV 解析器。只有附件版式无法稳定识别时，
才会启用 `financial_document_ai_fallback`，并在当次首次调用前检查一次服务和模型；AI 结果会降低置信度并
标记为需要人工复核。默认最多尝试 10 个文档，避免未知版式造成无界调用。

## 验证

先在专用运行时项目中启动 AI 服务，再从本项目根目录执行：

```powershell
python flows/ai_self_check.py --no-chat
python flows/ai_self_check.py --prompt "请直接回答两个字：可用" --max-tokens 32
```

服务不可用时，本项目只报告连接错误，不会尝试创建、重启或关闭外部进程。

## 日志

Financial Track 自身的调用日志由根目录 `logging_config.py` 管理，写入：

```text
logs/ai_self_check.log
logs/order_image_ai.log
```

AI 服务端日志由运行时项目自行管理，不写入本项目目录。
