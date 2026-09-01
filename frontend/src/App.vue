<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { approveCoupon, approveCouponFromWorkbench, createTicket, getTicket, listApprovals, listTickets, rejectApproval, reindexKnowledge } from './api'
import type { AgentRun, ApprovalQueueItem, KnowledgeCitation, Ticket } from './types'

const tickets = ref<Ticket[]>([])
const approvals = ref<ApprovalQueueItem[]>([])
const selected = ref<Ticket | null>(null)
const loading = ref(false)
const processing = ref(false)
const syncingKnowledge = ref(false)
const orderNo = ref('RF202608290001')
const content = ref('我的快递三天了还没到，现在到哪里了？')

const resolvedCount = computed(
  () => tickets.value.filter((ticket) => ticket.status === 'resolved').length,
)
const escalatedCount = computed(
  () => tickets.value.filter((ticket) => ticket.status === 'escalated').length,
)
const pendingApprovalCount = computed(
  () => tickets.value.filter((ticket) => ticket.status === 'pending_approval').length,
)

const statusLabel: Record<string, string> = {
  new: '待处理',
  processing: '处理中',
  pending_approval: '待审批',
  resolved: '已解决',
  escalated: '已升级',
}

const statusType = (status: string) => {
  if (status === 'resolved') return 'success'
  if (status === 'escalated') return 'warning'
  if (status === 'pending_approval') return 'warning'
  if (status === 'processing') return 'primary'
  return 'info'
}

async function refreshTickets() {
  loading.value = true
  try {
    const [ticketRows, approvalRows] = await Promise.all([listTickets(), listApprovals()])
    tickets.value = ticketRows
    approvals.value = approvalRows
  } catch {
    ElMessage.error('无法连接后端，请确认API已在8000端口启动')
  } finally {
    loading.value = false
  }
}

async function submitTicket() {
  if (!orderNo.value.trim() || !content.value.trim()) {
    ElMessage.warning('请填写订单号和客户问题')
    return
  }
  loading.value = true
  try {
    selected.value = await createTicket(orderNo.value.trim(), content.value.trim())
    await refreshTickets()
    ElMessage.success(
      selected.value.status === 'resolved' ? '工单已自动处理完成' : '工单已自动路由至人工队列',
    )
  } catch {
    ElMessage.error('创建失败，请确认演示订单号是否正确')
  } finally {
    loading.value = false
  }
}

async function selectTicket(ticket: Ticket) {
  selected.value = await getTicket(ticket.id)
}

async function approveCompensation() {
  if (!selected.value) return
  processing.value = true
  try {
    selected.value = await approveCoupon(selected.value.id)
    await refreshTickets()
    ElMessage.success('5元补偿优惠券已发放')
  } catch {
    ElMessage.error('审批失败，请刷新后重试')
  } finally {
    processing.value = false
  }
}

async function refreshSelected(ticketId: number) {
  selected.value = await getTicket(ticketId)
  await refreshTickets()
}

async function approveFromWorkbench(task: ApprovalQueueItem) {
  processing.value = true
  try {
    await approveCouponFromWorkbench(task.id)
    await refreshSelected(task.ticket_id)
    ElMessage.success('补偿优惠券已审批并发放')
  } catch {
    ElMessage.error('审批失败，请刷新后重试')
  } finally {
    processing.value = false
  }
}

async function rejectFromWorkbench(task: ApprovalQueueItem) {
  try {
    const { value } = await ElMessageBox.prompt('请填写驳回原因', '驳回审批', {
      confirmButtonText: '确认驳回',
      cancelButtonText: '取消',
      inputValue: '不满足当前审批条件',
    })
    processing.value = true
    await rejectApproval(task.id, value)
    await refreshSelected(task.ticket_id)
    ElMessage.success('审批任务已驳回并记录原因')
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error('驳回操作失败')
  } finally {
    processing.value = false
  }
}

function taskLabel(taskType: string): string {
  return taskType === 'coupon_compensation' ? '优惠券补偿' : '退款风险复核'
}

async function openApprovalTicket(task: ApprovalQueueItem) {
  await selectTicket({ id: task.ticket_id } as Ticket)
}

function useExample(example: 'logistics' | 'compensation' | 'refund') {
  const examples = {
    logistics: '我的快递三天了还没到，现在到哪里了？',
    compensation: '快递晚了三天，能赔偿我吗？',
    refund: '耳机的颜色和图片不一样，我要求全额退款。',
  }
  content.value = examples[example]
}

function requiredEvidence(ticket: Ticket): string {
  const evidence = ticket.approval_tasks?.[0]?.proposed_data.required_evidence
  return Array.isArray(evidence) ? evidence.join('、') : ''
}

function classificationSource(ticket: Ticket): string {
  const classification = ticket.audit_logs
    ?.find((log) => log.input_data?.classification)
    ?.input_data?.classification as Record<string, unknown> | undefined
  if (!classification) return '未处理'
  return classification.source === 'rules' ? '规则降级' : String(classification.source)
}

const agentName: Record<string, string> = {
  dispatcher: '调度智能体',
  order_logistics: '订单物流智能体',
  knowledge: '知识库智能体',
  risk_control: '风控智能体',
  reply: '回复智能体',
}

function agentRuns(ticket: Ticket): AgentRun[] {
  return ticket.agent_runs ?? []
}

function knowledgeCitations(ticket: Ticket): KnowledgeCitation[] {
  const sources = ticket.audit_logs
    ?.find((log) => Array.isArray(log.output_data?.knowledge_sources))
    ?.output_data?.knowledge_sources
  return Array.isArray(sources) ? sources as KnowledgeCitation[] : []
}

async function syncKnowledge() {
  syncingKnowledge.value = true
  try {
    const result = await reindexKnowledge()
    ElMessage.success(`已同步 ${result.document_count} 份规则文档、${result.chunk_count} 个知识分段`)
  } catch {
    ElMessage.error('知识库同步失败，请确认Milvus服务已启动并等待嵌入模型下载完成')
  } finally {
    syncingKnowledge.value = false
  }
}

onMounted(refreshTickets)
</script>

<template>
  <div class="app-shell">
    <header class="hero">
      <div>
        <span class="eyebrow">AI TICKET OPERATIONS</span>
        <h1>ResolveFlow</h1>
        <p>电商智能工单处置平台 · 面试演示版</p>
      </div>
      <div class="hero-actions">
        <el-button :loading="syncingKnowledge" @click="syncKnowledge">同步知识库</el-button>
        <div class="system-state"><span></span> 规则引擎在线</div>
      </div>
    </header>

    <section class="metrics">
      <article><span>工单总数</span><strong>{{ tickets.length }}</strong></article>
      <article><span>自动解决</span><strong>{{ resolvedCount }}</strong></article>
      <article><span>待人工审批</span><strong>{{ pendingApprovalCount }}</strong></article>
      <article><span>人工升级</span><strong>{{ escalatedCount }}</strong></article>
    </section>

    <main class="workspace">
      <section class="panel creation-panel">
        <div class="panel-title">
          <div><span>01</span><h2>模拟客户请求</h2></div>
          <p>使用演示订单创建一张真实落库的工单</p>
        </div>
        <el-form label-position="top">
          <el-form-item label="订单号">
            <el-input v-model="orderNo" />
          </el-form-item>
          <el-form-item label="客户问题">
            <el-input v-model="content" type="textarea" :rows="4" resize="none" />
          </el-form-item>
          <div class="example-actions">
            <span>快速填充：</span>
            <el-button size="small" @click="useExample('logistics')">物流查询</el-button>
            <el-button size="small" @click="useExample('compensation')">延迟补偿</el-button>
            <el-button size="small" @click="useExample('refund')">质量退款</el-button>
          </div>
          <el-button type="primary" :loading="loading" @click="submitTicket">创建工单</el-button>
        </el-form>
      </section>

      <section class="panel ticket-panel">
        <div class="panel-title">
          <div><span>02</span><h2>工单队列</h2></div>
          <el-button text @click="refreshTickets">刷新</el-button>
        </div>
        <el-table :data="tickets" v-loading="loading" height="310" @row-click="selectTicket">
          <el-table-column prop="ticket_no" label="工单编号" min-width="190" />
          <el-table-column prop="title" label="问题" min-width="180" show-overflow-tooltip />
          <el-table-column label="状态" width="95">
            <template #default="scope">
              <el-tag :type="statusType(scope.row.status)">{{ statusLabel[scope.row.status] }}</el-tag>
            </template>
          </el-table-column>
        </el-table>
      </section>

      <section class="panel approval-panel">
        <div class="panel-title">
          <div><span>03</span><h2>人工审批工作台</h2></div>
          <p>AI 只能提出建议，涉及权益和退款必须由人工决定</p>
        </div>
        <el-empty v-if="!approvals.length" description="当前没有待审批任务" :image-size="72" />
        <el-table v-else :data="approvals" v-loading="processing" height="280" @row-click="openApprovalTicket">
          <el-table-column prop="ticket_no" label="工单编号" min-width="175" />
          <el-table-column label="审批类型" width="130">
            <template #default="scope"><el-tag :type="scope.row.task_type === 'refund_review' ? 'danger' : 'warning'">{{ taskLabel(scope.row.task_type) }}</el-tag></template>
          </el-table-column>
          <el-table-column prop="ticket_title" label="客户诉求" min-width="210" show-overflow-tooltip />
          <el-table-column label="AI建议" min-width="180">
            <template #default="scope">
              {{ scope.row.task_type === 'coupon_compensation' ? `发放 ${scope.row.proposed_data.coupon_amount} 元优惠券` : '禁止自动退款，转主管复核' }}
            </template>
          </el-table-column>
          <el-table-column label="人工操作" width="230" fixed="right">
            <template #default="scope">
              <template v-if="scope.row.task_type === 'coupon_compensation'">
                <el-button size="small" type="primary" :loading="processing" @click.stop="approveFromWorkbench(scope.row)">批准</el-button>
                <el-button size="small" :loading="processing" @click.stop="rejectFromWorkbench(scope.row)">驳回</el-button>
              </template>
              <el-tag v-else type="danger">已自动转主管复核</el-tag>
            </template>
          </el-table-column>
        </el-table>
      </section>

      <section class="panel detail-panel">
        <div class="panel-title">
          <div><span>04</span><h2>智能处置结果</h2></div>
        </div>

        <el-empty v-if="!selected" description="选择或创建一张工单" />
        <template v-else>
          <div class="ticket-meta">
            <div><span>意图</span><strong>{{ selected.intent ?? '待识别' }}</strong></div>
            <div><span>优先级</span><strong>{{ selected.priority }}</strong></div>
            <div><span>风险</span><strong>{{ selected.risk_level }}</strong></div>
            <div><span>状态</span><strong>{{ statusLabel[selected.status] }}</strong></div>
            <div><span>决策来源</span><strong>{{ classificationSource(selected) }}</strong></div>
          </div>

          <div
            v-if="selected.status === 'pending_approval' && selected.approval_tasks?.[0]"
            class="approval-card"
          >
            <div>
              <span>待人工确认</span>
              <strong>发放 {{ selected.approval_tasks[0].proposed_data.coupon_amount }} 元优惠券补偿</strong>
              <p>{{ selected.approval_tasks[0].proposed_data.reason }}</p>
            </div>
            <el-button type="primary" :loading="processing" @click="approveCompensation">
              确认发放
            </el-button>
          </div>

          <div
            v-if="selected.status === 'escalated' && selected.approval_tasks?.[0]?.task_type === 'refund_review'"
            class="escalation-card"
          >
            <div>
              <span>高风险：已转交主管复核</span>
              <strong>系统禁止AI直接执行退款</strong>
              <p>需要补充：{{ requiredEvidence(selected) }}</p>
            </div>
          </div>

          <div class="conversation">
            <div
              v-for="message in selected.messages"
              :key="message.id"
              class="message"
              :class="message.sender_type"
            >
              <small>{{ message.sender_type === 'customer' ? '客户' : '智能客服' }}</small>
              <p>{{ message.content }}</p>
            </div>
          </div>

          <div v-if="knowledgeCitations(selected).length" class="knowledge-card">
            <h3>RAG规则依据</h3>
            <div v-for="source in knowledgeCitations(selected)" :key="source.document_id" class="knowledge-row">
              <strong>{{ source.title }}</strong>
              <span>{{ source.version }} · 相似度 {{ source.score.toFixed(3) }}</span>
            </div>
          </div>

          <div v-if="agentRuns(selected).length" class="agent-trace">
            <div class="trace-heading">
              <h3>多智能体执行轨迹</h3>
              <span>{{ agentRuns(selected).length }} 个智能体已协作完成</span>
            </div>
            <div v-for="run in agentRuns(selected)" :key="run.id" class="agent-run">
              <span class="sequence">{{ run.sequence }}</span>
              <div>
                <strong>{{ agentName[run.agent_name] ?? run.agent_name }}</strong>
                <p>{{ run.provider }}<template v-if="run.model"> · {{ run.model }}</template></p>
              </div>
              <el-tag :type="run.status === 'completed' ? 'success' : 'danger'">
                {{ run.status === 'completed' ? '完成' : '失败' }}
              </el-tag>
              <time>{{ run.duration_ms }} ms</time>
            </div>
          </div>

          <div v-if="selected.audit_logs?.length" class="audit-area">
            <h3>决策审计</h3>
            <div v-for="log in selected.audit_logs" :key="log.id" class="audit-row">
              <code>{{ log.action }}</code>
              <span>{{ log.operator_type }}</span>
              <time>{{ new Date(log.created_at).toLocaleString() }}</time>
            </div>
          </div>
        </template>
      </section>
    </main>
  </div>
</template>
