# ResolveFlow

面向应届生面试演示的电商智能工单处置平台。当前版本已经跑通第一条完整链路：

1. 使用模拟订单创建客服工单。
2. 规则分类器识别物流咨询。
3. 查询模拟物流轨迹。
4. 自动生成客服回复。
5. 更新工单状态并保存审计日志。

另有中风险补偿场景：当客户提出物流延迟赔偿时，系统只会建议发放5元优惠券并创建审批任务；必须由客服确认后才会模拟发券、关闭工单并记录操作。

对于质量争议和退款诉求，系统会识别为高风险并转交主管复核，明确禁止AI直接执行退款。

## 接入 DeepSeek

DeepSeek分类器使用官方兼容的Chat Completions接口与JSON输出模式，并在API异常、超时或输出格式不符合约束时自动回退到本地规则分类器。相关配置不应提交到Git。

在项目根目录创建`.env`，并填写你的密钥：

```ini
AI_PROVIDER=deepseek
DEEPSEEK_API_KEY=你的DeepSeek密钥
DEEPSEEK_MODEL=deepseek-v4-flash
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
- Milvus Standalone + BGE中文嵌入模型

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

## RAG知识库

启动后，先在前端页面点击“同步知识库”。系统会将3份演示售后规则切分后，使用`BAAI/bge-small-zh-v1.5`生成中文向量并写入Milvus。首次同步会下载嵌入模型，耗时取决于网络状况；之后工单处理会检索相关规则、将其作为DeepSeek回复上下文，并在详情页展示“RAG规则依据”。

后端镜像固定从阿里云镜像安装CPU版PyTorch；项目不需要CUDA，也不会下载cuDNN、NCCL等GPU依赖。

Milvus由Compose中的`etcd`、`minio`和`milvus`服务构成；API通过内部地址`milvus:19530`访问，不暴露向量检索端口。Milvus官方的Standalone Compose部署说明见[官方文档](https://milvus.io/docs/install_standalone-docker-compose.md)。

## 当前边界

当前分类器是可离线运行的规则基线，入口位于
`backend/app/services/ticket_processor.py`。后续可以在保持结构化输出不变的情况下，替换为大模型分类器，并继续加入知识库、人工审批和风险控制。
