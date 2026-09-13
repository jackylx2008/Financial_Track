# 外部 AI 服务接入

Financial Track 不负责安装模型、启动推理服务、配置 CUDA 运行时或管理推理进程。相关能力由独立的
AI 运行时项目提供，本项目仅通过 OpenAI 兼容 HTTP API 调用已经运行的服务。

## 接口要求

外部服务需要提供以下接口：

- `GET /health`
- `GET /v1/models`
- `POST /v1/chat/completions`

订单截图识别还要求服务和模型支持 OpenAI 兼容的图片 data URL 输入。

## 本地配置

连接信息写入根目录 `common.env`，不得提交到 Git：

```dotenv
LLAMACPP_BASE_URL=http://127.0.0.1:8080/v1
LLAMACPP_MODEL=local-model
LLAMACPP_API_KEY=
LLAMACPP_TIMEOUT_SEC=120
LLAMACPP_MAX_TOKENS=4096
LLAMACPP_TEMPERATURE=0
```

这里沿用 `LLAMACPP_` 变量名前缀以保持现有配置兼容，但服务可以由任意实现提供，只要接口兼容。

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
