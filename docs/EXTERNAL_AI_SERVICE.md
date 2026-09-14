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

连接默认值保留在 `config.yaml` 的 `llamacpp` 段。本项目的 `common.env` 不再重复保存
`LLAMACPP_*` 项；如外部运行时需要覆盖地址、模型或令牌，应在启动本项目进程时注入对应环境变量。
变量名前缀仅用于保持现有客户端兼容，服务可以由任意实现提供，只要接口兼容。

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
