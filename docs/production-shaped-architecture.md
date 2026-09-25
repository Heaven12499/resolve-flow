# ResolveFlow 生产形态改造

## 服务所有权

| 服务 | 权威数据 | 允许的动作 |
| --- | --- | --- |
| `business-api` | 用户、订单、物流、工单、审批、业务审计、AI任务摘要 | 校验权限、推进状态机、创建审批、执行模拟业务动作 |
| `api`（逐步更名为 `ai-api`） | Agent运行、模型调用、知识元数据、向量索引 | 分析不可变案件快照并返回非约束性建议 |
| `frontend` | 无 | 只调用 `business-api`，由 Java 代理知识库和 Agent 轨迹 |

Java 和 Python 可以使用同一个 MySQL 容器，但必须使用不同数据库。禁止 Python 直接写入
`resolveflow_business`，禁止 Java 直接读取 AI 内部表。

## 当前业务时序

```mermaid
sequenceDiagram
    participant UI as Vue
    participant B as Spring Boot
    participant DB as Business MySQL
    participant AI as FastAPI AI

    UI->>B: 创建工单
    B->>DB: 工单 + 消息 + AI_TASK（同一事务）
    B-->>UI: AI_QUEUED
    B->>AI: POST /internal/v1/ai/analyze（案件快照）
    AI-->>B: 结构化建议 + businessVersion
    B->>DB: 校验任务、版本和建议枚举
    B->>DB: 推进状态 + 创建审批 + 审计
```

## 安全不变量

1. AI 返回值是建议，不是业务命令。
2. Python 不持有业务数据库凭据。
3. 所有资金权益动作必须经过 Java 确定性规则和人工审批。
4. AI 结果中的 `taskId`、`ticketId` 和 `businessVersion` 必须与任务记录一致。
5. 旧版本结果不能覆盖更新后的工单。

## 本地端口

| 组件 | 端口 |
| --- | --- |
| Vue | `5173` |
| Java Business API | `8080` |
| Python AI API / 旧兼容 API | `8000` |
| Chroma | 仅 Compose 内网 |
| MySQL | 仅 Compose 内网 |
| Redis | 仅 Compose 内网 |

Vue 开发服务器把 `/api` 代理到 `localhost:8080`；Docker 中由 Nginx 把 `/api` 代理到
`business-api:8080`。浏览器不再直接访问 Python。Python 原业务接口暂时保留用于回归，后续在
AI 状态迁入 `resolveflow_ai` 后删除。
