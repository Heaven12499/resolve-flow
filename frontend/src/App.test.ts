import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App.vue'


const pendingTicket = {
  id: 7,
  ticket_no: 'RF-TICKET-7',
  customer_id: 1,
  order_id: 1,
  title: '物流延迟补偿',
  content: '我的快递晚了三天，能赔偿吗？',
  intent: 'delivery_delay_compensation',
  priority: 'medium',
  risk_level: 'medium',
  decision_source: 'rules',
  status: 'pending_approval',
  created_at: '2026-09-05T10:00:00Z',
  updated_at: '2026-09-05T10:00:00Z',
  messages: [],
  audit_logs: [],
  agent_runs: [],
  approval_tasks: [{
    id: 17,
    task_type: 'coupon_compensation',
    status: 'pending',
    proposed_data: {
      coupon_amount: 5,
      approval_level: 'agent',
      reason: '满足延迟补偿规则',
    },
    decision_data: null,
    created_at: '2026-09-05T10:00:00Z',
    decided_at: null,
  }],
} as const

const resolvedTicket = {
  ...pendingTicket,
  status: 'resolved',
  approval_tasks: [{
    ...pendingTicket.approval_tasks[0],
    status: 'approved',
    decision_data: { approved_by: 'local_demo' },
    decided_at: '2026-09-05T10:01:00Z',
  }],
} as const

const waitingRefundTicket = {
  ...pendingTicket,
  title: '退款争议',
  content: '耳机有质量问题，我要退款',
  intent: 'refund_risk_review',
  priority: 'high',
  risk_level: 'high',
  status: 'waiting_customer',
  approval_tasks: [],
  case_agent_state: {
    status: 'waiting_customer',
    goal: '准备退款复核事实包',
    state_data: {},
    pending_question: '请补充商品问题照片或视频',
    created_at: '2026-09-05T10:00:00Z',
    updated_at: '2026-09-05T10:00:00Z',
  },
} as const

const apiMocks = vi.hoisted(() => ({
  addCustomerMessage: vi.fn(),
  approveCoupon: vi.fn(),
  approveCouponFromWorkbench: vi.fn(),
  clearAccessToken: vi.fn(),
  createKnowledgeDocument: vi.fn(),
  createTicket: vi.fn(),
  currentActorRole: vi.fn(),
  getHealth: vi.fn(),
  getTicket: vi.fn(),
  hasAccessToken: vi.fn(),
  ingestKnowledgeDocument: vi.fn(),
  listAgentRuns: vi.fn(),
  listApprovals: vi.fn(),
  listKnowledgeDocuments: vi.fn(),
  listTickets: vi.fn(),
  login: vi.fn(),
  processTicket: vi.fn(),
  rejectApproval: vi.fn(),
  reindexKnowledge: vi.fn(),
  reviewRefund: vi.fn(),
  updateKnowledgeDocument: vi.fn(),
}))

vi.mock('./api', () => apiMocks)
vi.mock('element-plus/es/components/message/index', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn() },
}))
vi.mock('element-plus/es/components/message-box/index', () => ({
  ElMessageBox: { prompt: vi.fn() },
}))

function buttonByText(wrapper: VueWrapper, label: string) {
  const button = wrapper.findAllComponents({ name: 'ElButton' }).find((item) => item.text().includes(label))
    ?? wrapper.findAll('el-button-stub').find((item) => item.text().includes(label))
  if (!button) throw new Error(`button not found: ${label}`)
  return button
}

describe('ticket compensation workflow', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMocks.getHealth.mockResolvedValue({ status: 'ok', auth_enabled: false })
    apiMocks.currentActorRole.mockReturnValue(null)
    apiMocks.hasAccessToken.mockReturnValue(false)
    apiMocks.listTickets.mockResolvedValue([])
    apiMocks.listApprovals.mockResolvedValue([])
    apiMocks.listKnowledgeDocuments.mockResolvedValue([])
    apiMocks.listAgentRuns.mockResolvedValue([])
    apiMocks.createTicket.mockResolvedValue(pendingTicket)
    apiMocks.approveCoupon.mockResolvedValue(resolvedTicket)
    apiMocks.addCustomerMessage.mockResolvedValue({ ...waitingRefundTicket, status: 'queued' })
  })

  it('creates a delayed-delivery ticket and approves its governed coupon', async () => {
    const wrapper = mount(App, { global: { plugins: [ElementPlus] } })
    await flushPromises()

    await wrapper.findAll('button').find((item) => item.text().includes('模拟工单接入'))!.trigger('click')
    await buttonByText(wrapper, '提交并进入工作台').trigger('click')
    await flushPromises()

    expect(apiMocks.createTicket).toHaveBeenCalledWith(
      'RF202608290001',
      '我的快递三天了还没到，现在到哪里了？',
    )
    expect(wrapper.text()).toContain('发放 5 元优惠券补偿')

    await buttonByText(wrapper, '确认发放').trigger('click')
    await flushPromises()

    expect(apiMocks.approveCoupon).toHaveBeenCalledWith(7)
    expect(wrapper.text()).toContain('已解决')
  })

  it('starts a new investigation version after customer evidence arrives', async () => {
    apiMocks.createTicket.mockResolvedValueOnce(waitingRefundTicket)
    const wrapper = mount(App, { global: { plugins: [ElementPlus] } })
    await flushPromises()

    await wrapper.findAll('button').find((item) => item.text().includes('模拟工单接入'))!.trigger('click')
    await buttonByText(wrapper, '提交并进入工作台').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('Specialist Agent 正在等待客户材料')
    await buttonByText(wrapper, '提交材料并重新分析').trigger('click')
    await flushPromises()

    expect(apiMocks.addCustomerMessage).toHaveBeenCalledWith(
      7,
      '我已上传商品故障视频和照片，请继续复核。',
      [{
        file_name: 'earphone-defect.mp4',
        media_type: 'video/mp4',
        storage_uri: 'demo://tickets/7/earphone-defect.mp4',
        sha256: `${'0'.repeat(63)}7`,
      }],
    )
  })
})
