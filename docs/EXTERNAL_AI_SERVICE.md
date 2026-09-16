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

GUI 启动后会以短超时在后台分别访问健康和模型接口，默认每 30 秒自动刷新，也可手动刷新，并显示以下信息：

- 服务是否已经启动，以及健康接口返回的简要状态；
- 配置的模型名称，以及模型接口可读取时的实际加载模型；
- 本机调用地址。

模型接口返回 `HTTP 401` 时，GUI 仍会依据健康接口判断服务已经启动，同时提示模型列表需要鉴权。

GUI 首次检查和用户点击“测试 AI 连接”时还会向 `/v1/chat/completions` 发送“你好”，并把发送内容、
模型回复或鉴权错误写入共享日志区。周期性健康刷新不会重复发起对话。

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
