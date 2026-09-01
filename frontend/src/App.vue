<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { approveCoupon, approveCouponFromWorkbench, createKnowledgeDocument, createTicket, getTicket, ingestKnowledgeDocument, listAgentRuns, listApprovals, listKnowledgeDocuments, listTickets, rejectApproval, reindexKnowledge, updateKnowledgeDocument } from './api'
import type { AgentRun, AgentRunQueueItem, ApprovalQueueItem, KnowledgeCitation, KnowledgeDocument, KnowledgeDocumentPayload, KnowledgeIngestionResult, Ticket } from './types'

const tickets = ref<Ticket[]>([])
const approvals = ref<ApprovalQueueItem[]>([])
const agentRunFeed = ref<AgentRunQueueItem[]>([])
const knowledgeDocuments = ref<KnowledgeDocument[]>([])
const selected = ref<Ticket | null>(null)
const loading = ref(false)
const processing = ref(false)
const syncingKnowledge = ref(false)
const savingKnowledgeDocument = ref(false)
const uploadingKnowledgeCorpus = ref(false)
const knowledgeDialogVisible = ref(false)
const editingKnowledgeDocumentId = ref<number | null>(null)
const knowledgeNeedsSync = ref(false)
const knowledgeFileInput = ref<HTMLInputElement | null>(null)
const selectedKnowledgeFile = ref<File | null>(null)
const uploadKnowledgeCategory = ref('after_sales')
const ingestionPreview = ref<KnowledgeIngestionResult | null>(null)
const activeView = ref<'workspace' | 'intake' | 'approvals' | 'knowledge' | 'agents'>('workspace')
const orderNo = ref('RF202608290001')
const content = ref('我的快递三天了还没到，现在到哪里了？')
const knowledgeForm = reactive<KnowledgeDocumentPayload>({
  title: '',
  content: '',
  category: 'logistics',
  version: 'v1.0',
  is_active: true,
})

const resolvedCount = computed(
  () => tickets.value.filter((ticket) => ticket.status === 'resolved').length,
)
const escalatedCount = computed(
  () => tickets.value.filter((ticket) => ticket.status === 'escalated').length,
)
const pendingApprovalCount = computed(
  () => tickets.value.filter((ticket) => ticket.status === 'pending_approval').length,
)
const completedAgentRunCount = computed(
  () => agentRunFeed.value.filter((run) => run.status === 'completed').length,
)

const statusLabel: Record<string, string> = {
  new: '待处理',
  processing: '处理中',
  pending_approval: '待审批',
  resolved: '已解决',
  escalated: '已升级',
}

const intentLabel: Record<string, string> = {
  logistics_query: '物流查询',
  delivery_delay_compensation: '延迟补偿',
  refund_risk_review: '退款风险复核',
  other: '其他咨询',
}

const statusType = (status: string) => {
  if (status === 'resolved') return 'success'
  if (status === 'escalated') return 'danger'
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
    await Promise.all([refreshTickets(), refreshAgentRuns()])
    activeView.value = 'workspace'
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
  if (classification.source === 'rules') return '规则降级'
  if (classification.source === 'llm') return '大模型识别'
  return '智能体编排'
}

function displayIntent(intent: string | null | undefined): string {
  return intent ? (intentLabel[intent] ?? intent) : '待识别'
}

const agentName: Record<string, string> = {
  dispatcher: '调度智能体',
  order_logistics: '订单物流智能体',
  knowledge: '知识库智能体',
  risk_control: '风控智能体',
  reply: '回复智能体',
}

const routeName: Record<string, string> = {
  logistics_fast_path: '物流快速处置',
  compensation_with_approval: '补偿审批流程',
  high_risk_refund_review: '高风险退款复核',
  human_handoff: '人工兜底流程',
}

interface OrchestrationPlan {
  route?: string
  reason?: string
  next_agents?: string[]
  skipped_agents?: Array<{ agent_name?: string; reason?: string }>
}

function agentRuns(ticket: Ticket): AgentRun[] {
  return ticket.agent_runs ?? []
}

function orchestrationPlan(ticket: Ticket): OrchestrationPlan | null {
  const dispatcher = agentRuns(ticket).find((run) => run.agent_name === 'dispatcher')
  return dispatcher?.output_data as OrchestrationPlan | null
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
    knowledgeNeedsSync.value = false
    ElMessage.success(`已同步 ${result.document_count} 份规则文档、${result.chunk_count} 个知识分段`)
  } catch {
    ElMessage.error('知识库同步失败，请确认Milvus服务已启动并等待嵌入模型下载完成')
  } finally {
    syncingKnowledge.value = false
  }
}

async function refreshKnowledgeDocuments() {
  try {
    knowledgeDocuments.value = await listKnowledgeDocuments()
  } catch {
    ElMessage.error('无法读取知识库文档')
  }
}

function sourceTypeLabel(sourceType: string): string {
  return { manual: '手工录入', text: 'TXT 文本', markdown: 'Markdown', csv: 'CSV 表格' }[sourceType] ?? sourceType
}

function openKnowledgeFilePicker() {
  knowledgeFileInput.value?.click()
}

function selectKnowledgeFile(event: Event) {
  const input = event.target as HTMLInputElement
  selectedKnowledgeFile.value = input.files?.[0] ?? null
}

async function uploadKnowledgeCorpus() {
  if (!selectedKnowledgeFile.value) {
    ElMessage.warning('请选择 .txt、.md 或 .csv 语料文件')
    return
  }
  uploadingKnowledgeCorpus.value = true
  try {
    ingestionPreview.value = await ingestKnowledgeDocument(selectedKnowledgeFile.value, uploadKnowledgeCategory.value)
    knowledgeNeedsSync.value = true
    await refreshKnowledgeDocuments()
    ElMessage.success('语料已清洗并生成草稿，请预览后确认发布')
  } catch (error: unknown) {
    const detail = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    ElMessage.error(detail ?? '语料导入失败，请检查文件格式与内容')
  } finally {
    uploadingKnowledgeCorpus.value = false
  }
}

async function publishIngestedDocument() {
  if (!ingestionPreview.value) return
  try {
    await updateKnowledgeDocument(ingestionPreview.value.document.id, { is_active: true })
    knowledgeNeedsSync.value = true
    await refreshKnowledgeDocuments()
    ElMessage.success('语料已发布，请同步 Milvus 后用于 RAG 检索')
  } catch {
    ElMessage.error('发布语料失败')
  }
}

async function refreshAgentRuns() {
  try {
    agentRunFeed.value = await listAgentRuns()
  } catch {
    ElMessage.error('无法读取智能体执行记录')
  }
}

async function openAgentRunTicket(run: AgentRunQueueItem) {
  activeView.value = 'workspace'
  selected.value = await getTicket(run.ticket_id)
}

function resetKnowledgeForm() {
  editingKnowledgeDocumentId.value = null
  Object.assign(knowledgeForm, {
    title: '', content: '', category: 'logistics', version: 'v1.0', is_active: true,
  })
}

function openKnowledgeCreate() {
  resetKnowledgeForm()
  knowledgeDialogVisible.value = true
}

function openKnowledgeEdit(document: KnowledgeDocument) {
  editingKnowledgeDocumentId.value = document.id
  Object.assign(knowledgeForm, {
    title: document.title,
    content: document.content,
    category: document.category,
    version: document.version,
    is_active: document.is_active,
  })
  knowledgeDialogVisible.value = true
}

async function saveKnowledgeDocument() {
  if (knowledgeForm.title.trim().length < 2 || knowledgeForm.content.trim().length < 10) {
    ElMessage.warning('请填写规则标题和至少 10 个字的规则内容')
    return
  }
  savingKnowledgeDocument.value = true
  try {
    const payload = { ...knowledgeForm, title: knowledgeForm.title.trim(), content: knowledgeForm.content.trim() }
    if (editingKnowledgeDocumentId.value) {
      await updateKnowledgeDocument(editingKnowledgeDocumentId.value, payload)
      ElMessage.success('规则文档已更新，请同步到 Milvus 后生效')
    } else {
      await createKnowledgeDocument(payload)
      ElMessage.success('规则文档已创建，请同步到 Milvus 后生效')
    }
    knowledgeNeedsSync.value = true
    knowledgeDialogVisible.value = false
    await refreshKnowledgeDocuments()
  } catch {
    ElMessage.error('保存规则文档失败')
  } finally {
    savingKnowledgeDocument.value = false
  }
}

async function toggleKnowledgeDocument(document: KnowledgeDocument) {
  try {
    await updateKnowledgeDocument(document.id, { is_active: !document.is_active })
    knowledgeNeedsSync.value = true
    await refreshKnowledgeDocuments()
    ElMessage.success(document.is_active ? '规则已停用，请同步索引' : '规则已启用，请同步索引')
  } catch {
    ElMessage.error('更新规则状态失败')
  }
}

onMounted(async () => {
  await Promise.all([refreshTickets(), refreshKnowledgeDocuments(), refreshAgentRuns()])
})
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
        <el-badge :is-dot="knowledgeNeedsSync" type="warning">
          <el-button :loading="syncingKnowledge" @click="syncKnowledge">同步知识库</el-button>
        </el-badge>
        <div class="system-state"><span></span> 规则引擎在线</div>
      </div>
    </header>

    <section class="metrics">
      <article><span>工单总数</span><strong>{{ tickets.length }}</strong></article>
      <article><span>自动解决</span><strong>{{ resolvedCount }}</strong></article>
      <article><span>待人工审批</span><strong>{{ pendingApprovalCount }}</strong></article>
      <article><span>人工升级</span><strong>{{ escalatedCount }}</strong></article>
    </section>

    <div class="application-layout">
      <aside class="sidebar">
        <div class="sidebar-label">运营工作区</div>
        <button class="nav-item" :class="{ active: activeView === 'workspace' }" @click="activeView = 'workspace'">工单工作台</button>
        <button class="nav-item" :class="{ active: activeView === 'intake' }" @click="activeView = 'intake'">模拟工单接入</button>
        <button class="nav-item" :class="{ active: activeView === 'approvals' }" @click="activeView = 'approvals'">
          审批中心 <em v-if="approvals.length">{{ approvals.length }}</em>
        </button>
        <div class="sidebar-label">AI 配置</div>
        <button class="nav-item" :class="{ active: activeView === 'knowledge' }" @click="activeView = 'knowledge'">知识库管理</button>
        <button class="nav-item" :class="{ active: activeView === 'agents' }" @click="activeView = 'agents'">智能体监控</button>
      </aside>

      <main class="workspace" :class="`view-${activeView}`">
      <section v-if="activeView === 'intake'" class="panel creation-panel">
        <div class="panel-title">
          <div><span>01</span><h2>模拟外部工单接入</h2></div>
          <p>模拟商城或 IM 客服系统通过 API 创建一张真实落库的工单</p>
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
          <el-button type="primary" :loading="loading" @click="submitTicket">提交并进入工作台</el-button>
        </el-form>
      </section>

      <section v-if="activeView === 'workspace'" class="panel ticket-panel">
        <div class="panel-title">
          <div><span>02</span><h2>工单队列</h2></div>
          <el-button text @click="refreshTickets">刷新</el-button>
        </div>
        <el-table :data="tickets" v-loading="loading" height="310" @row-click="selectTicket">
          <el-table-column prop="ticket_no" label="工单编号" width="230" show-overflow-tooltip />
          <el-table-column prop="title" label="问题" min-width="220" show-overflow-tooltip />
          <el-table-column label="状态" width="110">
            <template #default="scope">
              <el-tag :type="statusType(scope.row.status)">{{ statusLabel[scope.row.status] }}</el-tag>
            </template>
          </el-table-column>
        </el-table>
      </section>

      <section v-if="activeView === 'approvals'" class="panel approval-panel">
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

      <section v-if="activeView === 'knowledge'" class="panel knowledge-management-panel">
        <div class="panel-title">
          <div><span>04</span><h2>知识库管理</h2></div>
          <div class="knowledge-actions">
            <small v-if="knowledgeNeedsSync">规则有改动，需同步到 Milvus 后生效</small>
            <input ref="knowledgeFileInput" class="hidden-file-input" type="file" accept=".txt,.md,.csv,text/plain,text/markdown,text/csv" @change="selectKnowledgeFile" />
            <el-select v-model="uploadKnowledgeCategory" class="knowledge-category-select" size="small">
              <el-option label="售后规则" value="after_sales" />
              <el-option label="物流规则" value="logistics" />
            </el-select>
            <el-button @click="openKnowledgeFilePicker">导入语料</el-button>
            <el-button type="primary" @click="openKnowledgeCreate">新增规则</el-button>
          </div>
        </div>
        <div v-if="selectedKnowledgeFile" class="selected-corpus-file">
          <span>待导入：{{ selectedKnowledgeFile.name }} · {{ Math.ceil(selectedKnowledgeFile.size / 1024) }} KB</span>
          <el-button size="small" type="primary" :loading="uploadingKnowledgeCorpus" @click="uploadKnowledgeCorpus">清洗并生成草稿</el-button>
        </div>
        <div v-if="ingestionPreview" class="corpus-preview">
          <div class="corpus-preview-heading">
            <div>
              <span>语料处理预览</span>
              <strong>{{ ingestionPreview.document.source_name }}</strong>
            </div>
            <el-tag type="warning">待人工发布</el-tag>
          </div>
          <p>已完成 Unicode 规范化、控制字符与空行清洗，得到 {{ ingestionPreview.cleaned_characters }} 个字符、{{ ingestionPreview.chunk_count }} 个切片。</p>
          <div v-for="(chunk, index) in ingestionPreview.preview_chunks" :key="index" class="corpus-chunk-preview">
            <small>切片 {{ index + 1 }}</small>{{ chunk }}
          </div>
          <el-button type="primary" size="small" @click="publishIngestedDocument">确认发布该语料</el-button>
        </div>
        <el-table :data="knowledgeDocuments" height="360">
          <el-table-column prop="title" label="规则文档" min-width="220" />
          <el-table-column prop="category" label="分类" width="120" />
          <el-table-column label="来源" min-width="180">
            <template #default="scope"><span class="knowledge-source">{{ sourceTypeLabel(scope.row.source_type) }} · {{ scope.row.source_name ?? '默认演示规则' }}</span></template>
          </el-table-column>
          <el-table-column prop="version" label="版本" width="100" />
          <el-table-column label="状态" width="120">
            <template #default="scope"><el-tag :type="scope.row.is_active ? 'success' : 'info'">{{ scope.row.is_active ? '已发布' : '草稿' }}</el-tag></template>
          </el-table-column>
          <el-table-column label="操作" width="210" fixed="right">
            <template #default="scope">
              <el-button size="small" @click="openKnowledgeEdit(scope.row)">编辑</el-button>
              <el-button size="small" :type="scope.row.is_active ? 'warning' : 'success'" @click="toggleKnowledgeDocument(scope.row)">
                {{ scope.row.is_active ? '停用' : '启用' }}
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </section>

      <section v-if="activeView === 'agents'" class="panel agent-monitoring-panel">
        <div class="panel-title">
          <div><span>AI</span><h2>智能体执行监控</h2></div>
          <div class="monitor-summary"><span>已完成 {{ completedAgentRunCount }} / {{ agentRunFeed.length }}</span><el-button text @click="refreshAgentRuns">刷新</el-button></div>
        </div>
        <el-empty v-if="!agentRunFeed.length" description="还没有智能体执行记录" :image-size="90" />
        <el-table v-else :data="agentRunFeed" height="620" @row-click="openAgentRunTicket">
          <el-table-column prop="ticket_no" label="工单编号" min-width="180" />
          <el-table-column label="智能体" width="150"><template #default="scope">{{ agentName[scope.row.agent_name] ?? scope.row.agent_name }}</template></el-table-column>
          <el-table-column prop="provider" label="模型 / 工具" width="140" />
          <el-table-column prop="model" label="模型名称" min-width="150"><template #default="scope">{{ scope.row.model ?? '—' }}</template></el-table-column>
          <el-table-column label="状态" width="100"><template #default="scope"><el-tag :type="scope.row.status === 'completed' ? 'success' : 'danger'">{{ scope.row.status === 'completed' ? '完成' : '失败' }}</el-tag></template></el-table-column>
          <el-table-column prop="duration_ms" label="耗时" width="100"><template #default="scope">{{ scope.row.duration_ms }} ms</template></el-table-column>
          <el-table-column prop="started_at" label="执行时间" min-width="180"><template #default="scope">{{ new Date(scope.row.started_at).toLocaleString() }}</template></el-table-column>
        </el-table>
      </section>

      <section v-if="activeView === 'workspace'" class="panel detail-panel">
        <div class="panel-title">
          <div><span>05</span><h2>智能处置结果</h2></div>
        </div>

        <el-empty v-if="!selected" description="选择或创建一张工单" />
        <template v-else>
          <div class="ticket-meta">
            <div><span>意图</span><strong>{{ displayIntent(selected.intent) }}</strong></div>
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
            <div v-if="orchestrationPlan(selected)" class="route-decision">
              <div>
                <span>调度路线</span>
                <strong>{{ routeName[orchestrationPlan(selected)?.route ?? ''] ?? '动态编排' }}</strong>
              </div>
              <p>{{ orchestrationPlan(selected)?.reason }}</p>
              <div class="route-agents">
                <span v-for="agent in orchestrationPlan(selected)?.next_agents ?? []" :key="agent" class="route-agent active">
                  {{ agentName[agent] ?? agent }}
                </span>
                <span
                  v-for="agent in orchestrationPlan(selected)?.skipped_agents ?? []"
                  :key="agent.agent_name"
                  class="route-agent skipped"
                  :title="agent.reason"
                >
                  跳过 {{ agentName[agent.agent_name ?? ''] ?? agent.agent_name }}
                </span>
              </div>
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

    <el-dialog v-model="knowledgeDialogVisible" :title="editingKnowledgeDocumentId ? '编辑规则文档' : '新增规则文档'" width="620px">
      <el-form label-position="top">
        <el-form-item label="规则标题"><el-input v-model="knowledgeForm.title" /></el-form-item>
        <div class="knowledge-form-grid">
          <el-form-item label="分类"><el-select v-model="knowledgeForm.category"><el-option label="物流规则" value="logistics" /><el-option label="售后规则" value="after_sales" /><el-option label="通用规则" value="general" /></el-select></el-form-item>
          <el-form-item label="版本"><el-input v-model="knowledgeForm.version" /></el-form-item>
        </div>
        <el-form-item label="规则内容"><el-input v-model="knowledgeForm.content" type="textarea" :rows="7" resize="none" /></el-form-item>
        <el-form-item><el-switch v-model="knowledgeForm.is_active" active-text="启用此规则" inactive-text="暂不启用" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="knowledgeDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingKnowledgeDocument" @click="saveKnowledgeDocument">保存并等待同步</el-button>
      </template>
    </el-dialog>
  </div>
</template>
