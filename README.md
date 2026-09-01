# ResolveFlow

面向应届生面试演示的电商客服工单智能处置平台。系统通过可观测的多智能体协作完成处置，并在高风险场景保留人工审批闸门。

前端采用客服工作台的信息架构：左侧导航将高频处理的工单工作台、人工审批中心、低频配置的知识库管理和跨工单的智能体监控分开，避免把所有操作堆在一页。

## 核心链路

1. 客户提交工单后，系统自动触发处置流程。
2. 调度智能体识别意图，并在大模型不可用时降级到规则。
3. 订单物流智能体查询订单和物流轨迹。
4. 知识库智能体从 Milvus 检索客服规则。
5. 风控智能体决定是否允许自动处置或必须人工审批。
6. 回复智能体结合规则依据生成客服回复。
7. 保存审计日志和每个智能体的输入、输出、状态、耗时。

对于补偿和退款等高风险结果，平台会在独立的“人工审批工作台”集中展示待办：补偿可批准或驳回；退款会由风控智能体自动进入主管复核队列，系统不会执行自动退款。所有人工决定都会追加客户消息和审计记录。

另有中风险补偿场景：当客户提出物流延迟赔偿时，系统只会建议发放5元优惠券并创建审批任务；必须由客服确认后才会模拟发券、关闭工单并记录操作。

对于质量争议和退款诉求，系统会识别为高风险并转交主管复核，明确禁止AI直接执行退款。

## 多智能体与模型适配

调度、订单物流、知识库、风控、回复五个智能体由后端编排器顺序协作。前端会展示“多智能体执行轨迹”，包括模型/工具来源和执行耗时。

模型访问通过统一的 OpenAI 兼容适配层实现，可为不同智能体分别配置 DeepSeek、Qwen 或 OpenAI；未配置密钥时，会使用规则或模板降级，业务风控决策始终由后端规则负责。

## 接入 DeepSeek

DeepSeek 分类器使用 Chat Completions 接口与 JSON 输出模式，并在 API 异常、超时或输出格式不符合约束时自动回退到本地规则分类器。相关配置不应提交到 Git。

在项目根目录创建`.env`，并填写你的密钥：

```ini
AI_PROVIDER=deepseek
DEEPSEEK_API_KEY=你的DeepSeek密钥
DEEPSEEK_MODEL=deepseek-v4-flash
```

也可以为单个智能体覆盖模型提供方，例如：

```ini
# QWEN_API_KEY=你的通义密钥
# DISPATCHER_LLM_PROVIDER=qwen
# DISPATCHER_LLM_MODEL=qwen-turbo
# REPLY_LLM_PROVIDER=deepseek
```

之后重新构建服务：

```powershell
docker compose up --build
```

工单的审计日志会保存`classification`对象，其中包含`source: deepseek`；若降级，则记录`source: rules`和失败原因。DeepSeek的JSON输出能力见其[官方文档](https://api-docs.deepseek.com/guides/json_mode/)。

## 技术栈

- FastAPI
- SQLAlchemy 2
- MySQL 8
- Alembic
- Pydantic
- pytest
- Docker Compose
- Vue 3 + TypeScript + Element Plus
- Milvus Standalone + 本地中文 n-gram 向量化

## 使用 Docker 启动

项目根目录执行：

```powershell
docker compose up --build
```

启动完成后打开：

- Swagger：<http://localhost:8000/docs>
- 健康检查：<http://localhost:8000/api/health>
- 演示界面：<http://localhost:5173>
- Milvus Web UI：<http://localhost:19091/webui/>

演示订单号：`RF202608290001`

## 本地启动后端

先启动一个MySQL实例，并复制环境变量：

```powershell
Copy-Item .env.example .env
Set-Location backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

另开一个终端启动前端：

```powershell
Set-Location frontend
npm install
npm run dev
```

## 演示完整工单流程

创建工单：

```powershell
$ticket = Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8000/api/tickets `
  -ContentType 'application/json' `
  -Body '{"order_no":"RF202608290001","content":"我的快递三天了还没到，现在到哪里了？"}'
```

自动处理：

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8000/api/tickets/$($ticket.id)/process"
```

最终响应会包含：

- `intent: logistics_query`
- `risk_level: low`
- `status: resolved`
- 客服自动回复
- `query_logistics`审计记录

## 运行测试

测试使用内存SQLite，不要求本机已经运行MySQL：

```powershell
Set-Location backend
pytest -q
```

## RAG 知识库

启动后，系统会补齐 10 份演示客服规则，覆盖物流、延迟补偿、退款复核、售后取证与投诉升级。前端点击“同步知识库”后，系统会将规则切分、使用内置中文 n-gram 向量化并写入 Milvus，不依赖 Hugging Face、BGE 或 PyTorch 下载。之后工单处理会按工单意图过滤物流/售后规则，并以相似度阈值过滤弱匹配内容；命中的规则会作为回复上下文，并在详情页展示“RAG规则依据”。

前端“知识库管理”支持新增、编辑、启用/停用和版本维护。文档变化会标记为“待同步”，只有点击“同步知识库”后才会重建 Milvus 索引并在新工单中生效。

Milvus 由 Compose 中的 `etcd`、`minio` 和 `milvus` 服务构成；API 通过内部地址 `milvus:19530` 访问，不暴露向量检索端口。

## 当前边界

当前项目的交易、赔付和退款决策均为演示规则，未对接真实订单、支付或优惠券系统。生产环境还需补充身份认证、权限控制、异步任务队列、真实工具调用与脱敏策略。
