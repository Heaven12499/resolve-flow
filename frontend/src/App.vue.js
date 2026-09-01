import { computed, onMounted, ref } from 'vue';
import { ElMessage } from 'element-plus';
import { approveCoupon, createTicket, getTicket, listTickets, processTicket, reindexKnowledge } from './api';
const tickets = ref([]);
const selected = ref(null);
const loading = ref(false);
const processing = ref(false);
const syncingKnowledge = ref(false);
const orderNo = ref('RF202608290001');
const content = ref('我的快递三天了还没到，现在到哪里了？');
const resolvedCount = computed(() => tickets.value.filter((ticket) => ticket.status === 'resolved').length);
const escalatedCount = computed(() => tickets.value.filter((ticket) => ticket.status === 'escalated').length);
const pendingApprovalCount = computed(() => tickets.value.filter((ticket) => ticket.status === 'pending_approval').length);
const statusLabel = {
    new: '待处理',
    processing: '处理中',
    pending_approval: '待审批',
    resolved: '已解决',
    escalated: '已升级',
};
const statusType = (status) => {
    if (status === 'resolved')
        return 'success';
    if (status === 'escalated')
        return 'warning';
    if (status === 'pending_approval')
        return 'warning';
    if (status === 'processing')
        return 'primary';
    return 'info';
};
async function refreshTickets() {
    loading.value = true;
    try {
        tickets.value = await listTickets();
    }
    catch {
        ElMessage.error('无法连接后端，请确认API已在8000端口启动');
    }
    finally {
        loading.value = false;
    }
}
async function submitTicket() {
    if (!orderNo.value.trim() || !content.value.trim()) {
        ElMessage.warning('请填写订单号和客户问题');
        return;
    }
    loading.value = true;
    try {
        selected.value = await createTicket(orderNo.value.trim(), content.value.trim());
        await refreshTickets();
        ElMessage.success('工单创建成功');
    }
    catch {
        ElMessage.error('创建失败，请确认演示订单号是否正确');
    }
    finally {
        loading.value = false;
    }
}
async function selectTicket(ticket) {
    selected.value = await getTicket(ticket.id);
}
async function runProcessing() {
    if (!selected.value)
        return;
    processing.value = true;
    try {
        selected.value = await processTicket(selected.value.id);
        await refreshTickets();
        ElMessage.success(selected.value.status === 'resolved' ? '工单已自动处理' : '工单已升级人工');
    }
    catch {
        ElMessage.error('自动处理失败');
    }
    finally {
        processing.value = false;
    }
}
async function approveCompensation() {
    if (!selected.value)
        return;
    processing.value = true;
    try {
        selected.value = await approveCoupon(selected.value.id);
        await refreshTickets();
        ElMessage.success('5元补偿优惠券已发放');
    }
    catch {
        ElMessage.error('审批失败，请刷新后重试');
    }
    finally {
        processing.value = false;
    }
}
function useExample(example) {
    const examples = {
        logistics: '我的快递三天了还没到，现在到哪里了？',
        compensation: '快递晚了三天，能赔偿我吗？',
        refund: '耳机的颜色和图片不一样，我要求全额退款。',
    };
    content.value = examples[example];
}
function requiredEvidence(ticket) {
    const evidence = ticket.approval_tasks?.[0]?.proposed_data.required_evidence;
    return Array.isArray(evidence) ? evidence.join('、') : '';
}
function classificationSource(ticket) {
    const classification = ticket.audit_logs
        ?.find((log) => log.input_data?.classification)
        ?.input_data?.classification;
    if (!classification)
        return '未处理';
    return classification.source === 'deepseek' ? 'DeepSeek' : '规则降级';
}
function knowledgeCitations(ticket) {
    const sources = ticket.audit_logs
        ?.find((log) => Array.isArray(log.output_data?.knowledge_sources))
        ?.output_data?.knowledge_sources;
    return Array.isArray(sources) ? sources : [];
}
async function syncKnowledge() {
    syncingKnowledge.value = true;
    try {
        const result = await reindexKnowledge();
        ElMessage.success(`已同步 ${result.document_count} 份规则文档、${result.chunk_count} 个知识分段`);
    }
    catch {
        ElMessage.error('知识库同步失败，请确认Milvus服务已启动并等待嵌入模型下载完成');
    }
    finally {
        syncingKnowledge.value = false;
    }
}
onMounted(refreshTickets);
const __VLS_ctx = {
    ...{},
    ...{},
};
let __VLS_components;
let __VLS_intrinsics;
let __VLS_directives;
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
    ...{ class: "app-shell" },
});
/** @type {__VLS_StyleScopedClasses['app-shell']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.header, __VLS_intrinsics.header)({
    ...{ class: "hero" },
});
/** @type {__VLS_StyleScopedClasses['hero']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
    ...{ class: "eyebrow" },
});
/** @type {__VLS_StyleScopedClasses['eyebrow']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.h1, __VLS_intrinsics.h1)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.p, __VLS_intrinsics.p)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
    ...{ class: "hero-actions" },
});
/** @type {__VLS_StyleScopedClasses['hero-actions']} */ ;
let __VLS_0;
/** @ts-ignore @type { | typeof __VLS_components.elButton | typeof __VLS_components.ElButton | typeof __VLS_components['el-button'] | typeof __VLS_components.elButton | typeof __VLS_components.ElButton | typeof __VLS_components['el-button']} */
elButton;
// @ts-ignore
const __VLS_1 = __VLS_asFunctionalComponent1(__VLS_0, new __VLS_0({
    ...{ 'onClick': {} },
    loading: (__VLS_ctx.syncingKnowledge),
}));
const __VLS_2 = __VLS_1({
    ...{ 'onClick': {} },
    loading: (__VLS_ctx.syncingKnowledge),
}, ...__VLS_functionalComponentArgsRest(__VLS_1));
let __VLS_5;
const __VLS_6 = {
    /** @type {typeof __VLS_5.click} */
    onClick: (__VLS_ctx.syncKnowledge),
};
const { default: __VLS_7 } = __VLS_3.slots;
// @ts-ignore
[syncingKnowledge, syncKnowledge,];
var __VLS_3;
var __VLS_4;
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
    ...{ class: "system-state" },
});
/** @type {__VLS_StyleScopedClasses['system-state']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.section, __VLS_intrinsics.section)({
    ...{ class: "metrics" },
});
/** @type {__VLS_StyleScopedClasses['metrics']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.article, __VLS_intrinsics.article)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.strong, __VLS_intrinsics.strong)({});
(__VLS_ctx.tickets.length);
__VLS_asFunctionalElement1(__VLS_intrinsics.article, __VLS_intrinsics.article)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.strong, __VLS_intrinsics.strong)({});
(__VLS_ctx.resolvedCount);
__VLS_asFunctionalElement1(__VLS_intrinsics.article, __VLS_intrinsics.article)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.strong, __VLS_intrinsics.strong)({});
(__VLS_ctx.pendingApprovalCount);
__VLS_asFunctionalElement1(__VLS_intrinsics.article, __VLS_intrinsics.article)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.strong, __VLS_intrinsics.strong)({});
(__VLS_ctx.escalatedCount);
__VLS_asFunctionalElement1(__VLS_intrinsics.main, __VLS_intrinsics.main)({
    ...{ class: "workspace" },
});
/** @type {__VLS_StyleScopedClasses['workspace']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.section, __VLS_intrinsics.section)({
    ...{ class: "panel creation-panel" },
});
/** @type {__VLS_StyleScopedClasses['panel']} */ ;
/** @type {__VLS_StyleScopedClasses['creation-panel']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
    ...{ class: "panel-title" },
});
/** @type {__VLS_StyleScopedClasses['panel-title']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.h2, __VLS_intrinsics.h2)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.p, __VLS_intrinsics.p)({});
let __VLS_8;
/** @ts-ignore @type { | typeof __VLS_components.elForm | typeof __VLS_components.ElForm | typeof __VLS_components['el-form'] | typeof __VLS_components.elForm | typeof __VLS_components.ElForm | typeof __VLS_components['el-form']} */
elForm;
// @ts-ignore
const __VLS_9 = __VLS_asFunctionalComponent1(__VLS_8, new __VLS_8({
    labelPosition: "top",
}));
const __VLS_10 = __VLS_9({
    labelPosition: "top",
}, ...__VLS_functionalComponentArgsRest(__VLS_9));
const { default: __VLS_13 } = __VLS_11.slots;
let __VLS_14;
/** @ts-ignore @type { | typeof __VLS_components.elFormItem | typeof __VLS_components.ElFormItem | typeof __VLS_components['el-form-item'] | typeof __VLS_components.elFormItem | typeof __VLS_components.ElFormItem | typeof __VLS_components['el-form-item']} */
elFormItem;
// @ts-ignore
const __VLS_15 = __VLS_asFunctionalComponent1(__VLS_14, new __VLS_14({
    label: "订单号",
}));
const __VLS_16 = __VLS_15({
    label: "订单号",
}, ...__VLS_functionalComponentArgsRest(__VLS_15));
const { default: __VLS_19 } = __VLS_17.slots;
let __VLS_20;
/** @ts-ignore @type { | typeof __VLS_components.elInput | typeof __VLS_components.ElInput | typeof __VLS_components['el-input']} */
elInput;
// @ts-ignore
const __VLS_21 = __VLS_asFunctionalComponent1(__VLS_20, new __VLS_20({
    modelValue: (__VLS_ctx.orderNo),
}));
const __VLS_22 = __VLS_21({
    modelValue: (__VLS_ctx.orderNo),
}, ...__VLS_functionalComponentArgsRest(__VLS_21));
// @ts-ignore
[tickets, resolvedCount, pendingApprovalCount, escalatedCount, orderNo,];
var __VLS_17;
let __VLS_25;
/** @ts-ignore @type { | typeof __VLS_components.elFormItem | typeof __VLS_components.ElFormItem | typeof __VLS_components['el-form-item'] | typeof __VLS_components.elFormItem | typeof __VLS_components.ElFormItem | typeof __VLS_components['el-form-item']} */
elFormItem;
// @ts-ignore
const __VLS_26 = __VLS_asFunctionalComponent1(__VLS_25, new __VLS_25({
    label: "客户问题",
}));
const __VLS_27 = __VLS_26({
    label: "客户问题",
}, ...__VLS_functionalComponentArgsRest(__VLS_26));
const { default: __VLS_30 } = __VLS_28.slots;
let __VLS_31;
/** @ts-ignore @type { | typeof __VLS_components.elInput | typeof __VLS_components.ElInput | typeof __VLS_components['el-input']} */
elInput;
// @ts-ignore
const __VLS_32 = __VLS_asFunctionalComponent1(__VLS_31, new __VLS_31({
    modelValue: (__VLS_ctx.content),
    type: "textarea",
    rows: (4),
    resize: "none",
}));
const __VLS_33 = __VLS_32({
    modelValue: (__VLS_ctx.content),
    type: "textarea",
    rows: (4),
    resize: "none",
}, ...__VLS_functionalComponentArgsRest(__VLS_32));
// @ts-ignore
[content,];
var __VLS_28;
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
    ...{ class: "example-actions" },
});
/** @type {__VLS_StyleScopedClasses['example-actions']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
let __VLS_36;
/** @ts-ignore @type { | typeof __VLS_components.elButton | typeof __VLS_components.ElButton | typeof __VLS_components['el-button'] | typeof __VLS_components.elButton | typeof __VLS_components.ElButton | typeof __VLS_components['el-button']} */
elButton;
// @ts-ignore
const __VLS_37 = __VLS_asFunctionalComponent1(__VLS_36, new __VLS_36({
    ...{ 'onClick': {} },
    size: "small",
}));
const __VLS_38 = __VLS_37({
    ...{ 'onClick': {} },
    size: "small",
}, ...__VLS_functionalComponentArgsRest(__VLS_37));
let __VLS_41;
const __VLS_42 = {
    /** @type {typeof __VLS_41.click} */
    onClick: (...[$event]) => {
        return (__VLS_ctx.useExample('logistics'));
        // @ts-ignore
        [useExample,];
    },
};
const { default: __VLS_43 } = __VLS_39.slots;
// @ts-ignore
[];
var __VLS_39;
var __VLS_40;
let __VLS_44;
/** @ts-ignore @type { | typeof __VLS_components.elButton | typeof __VLS_components.ElButton | typeof __VLS_components['el-button'] | typeof __VLS_components.elButton | typeof __VLS_components.ElButton | typeof __VLS_components['el-button']} */
elButton;
// @ts-ignore
const __VLS_45 = __VLS_asFunctionalComponent1(__VLS_44, new __VLS_44({
    ...{ 'onClick': {} },
    size: "small",
}));
const __VLS_46 = __VLS_45({
    ...{ 'onClick': {} },
    size: "small",
}, ...__VLS_functionalComponentArgsRest(__VLS_45));
let __VLS_49;
const __VLS_50 = {
    /** @type {typeof __VLS_49.click} */
    onClick: (...[$event]) => {
        return (__VLS_ctx.useExample('compensation'));
        // @ts-ignore
        [useExample,];
    },
};
const { default: __VLS_51 } = __VLS_47.slots;
// @ts-ignore
[];
var __VLS_47;
var __VLS_48;
let __VLS_52;
/** @ts-ignore @type { | typeof __VLS_components.elButton | typeof __VLS_components.ElButton | typeof __VLS_components['el-button'] | typeof __VLS_components.elButton | typeof __VLS_components.ElButton | typeof __VLS_components['el-button']} */
elButton;
// @ts-ignore
const __VLS_53 = __VLS_asFunctionalComponent1(__VLS_52, new __VLS_52({
    ...{ 'onClick': {} },
    size: "small",
}));
const __VLS_54 = __VLS_53({
    ...{ 'onClick': {} },
    size: "small",
}, ...__VLS_functionalComponentArgsRest(__VLS_53));
let __VLS_57;
const __VLS_58 = {
    /** @type {typeof __VLS_57.click} */
    onClick: (...[$event]) => {
        return (__VLS_ctx.useExample('refund'));
        // @ts-ignore
        [useExample,];
    },
};
const { default: __VLS_59 } = __VLS_55.slots;
// @ts-ignore
[];
var __VLS_55;
var __VLS_56;
let __VLS_60;
/** @ts-ignore @type { | typeof __VLS_components.elButton | typeof __VLS_components.ElButton | typeof __VLS_components['el-button'] | typeof __VLS_components.elButton | typeof __VLS_components.ElButton | typeof __VLS_components['el-button']} */
elButton;
// @ts-ignore
const __VLS_61 = __VLS_asFunctionalComponent1(__VLS_60, new __VLS_60({
    ...{ 'onClick': {} },
    type: "primary",
    loading: (__VLS_ctx.loading),
}));
const __VLS_62 = __VLS_61({
    ...{ 'onClick': {} },
    type: "primary",
    loading: (__VLS_ctx.loading),
}, ...__VLS_functionalComponentArgsRest(__VLS_61));
let __VLS_65;
const __VLS_66 = {
    /** @type {typeof __VLS_65.click} */
    onClick: (__VLS_ctx.submitTicket),
};
const { default: __VLS_67 } = __VLS_63.slots;
// @ts-ignore
[loading, submitTicket,];
var __VLS_63;
var __VLS_64;
// @ts-ignore
[];
var __VLS_11;
__VLS_asFunctionalElement1(__VLS_intrinsics.section, __VLS_intrinsics.section)({
    ...{ class: "panel ticket-panel" },
});
/** @type {__VLS_StyleScopedClasses['panel']} */ ;
/** @type {__VLS_StyleScopedClasses['ticket-panel']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
    ...{ class: "panel-title" },
});
/** @type {__VLS_StyleScopedClasses['panel-title']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.h2, __VLS_intrinsics.h2)({});
let __VLS_68;
/** @ts-ignore @type { | typeof __VLS_components.elButton | typeof __VLS_components.ElButton | typeof __VLS_components['el-button'] | typeof __VLS_components.elButton | typeof __VLS_components.ElButton | typeof __VLS_components['el-button']} */
elButton;
// @ts-ignore
const __VLS_69 = __VLS_asFunctionalComponent1(__VLS_68, new __VLS_68({
    ...{ 'onClick': {} },
    text: true,
}));
const __VLS_70 = __VLS_69({
    ...{ 'onClick': {} },
    text: true,
}, ...__VLS_functionalComponentArgsRest(__VLS_69));
let __VLS_73;
const __VLS_74 = {
    /** @type {typeof __VLS_73.click} */
    onClick: (__VLS_ctx.refreshTickets),
};
const { default: __VLS_75 } = __VLS_71.slots;
// @ts-ignore
[refreshTickets,];
var __VLS_71;
var __VLS_72;
let __VLS_76;
/** @ts-ignore @type { | typeof __VLS_components.elTable | typeof __VLS_components.ElTable | typeof __VLS_components['el-table'] | typeof __VLS_components.elTable | typeof __VLS_components.ElTable | typeof __VLS_components['el-table']} */
elTable;
// @ts-ignore
const __VLS_77 = __VLS_asFunctionalComponent1(__VLS_76, new __VLS_76({
    ...{ 'onRowClick': {} },
    data: (__VLS_ctx.tickets),
    height: "310",
}));
const __VLS_78 = __VLS_77({
    ...{ 'onRowClick': {} },
    data: (__VLS_ctx.tickets),
    height: "310",
}, ...__VLS_functionalComponentArgsRest(__VLS_77));
let __VLS_81;
const __VLS_82 = {
    /** @type {typeof __VLS_81.rowClick} */
    onRowClick: (__VLS_ctx.selectTicket),
};
__VLS_asFunctionalDirective(__VLS_directives.vLoading, {})(null, { ...__VLS_directiveBindingRestFields, value: (__VLS_ctx.loading), }, null, null);
const { default: __VLS_83 } = __VLS_79.slots;
let __VLS_84;
/** @ts-ignore @type { | typeof __VLS_components.elTableColumn | typeof __VLS_components.ElTableColumn | typeof __VLS_components['el-table-column']} */
elTableColumn;
// @ts-ignore
const __VLS_85 = __VLS_asFunctionalComponent1(__VLS_84, new __VLS_84({
    prop: "ticket_no",
    label: "工单编号",
    minWidth: "190",
}));
const __VLS_86 = __VLS_85({
    prop: "ticket_no",
    label: "工单编号",
    minWidth: "190",
}, ...__VLS_functionalComponentArgsRest(__VLS_85));
let __VLS_89;
/** @ts-ignore @type { | typeof __VLS_components.elTableColumn | typeof __VLS_components.ElTableColumn | typeof __VLS_components['el-table-column']} */
elTableColumn;
// @ts-ignore
const __VLS_90 = __VLS_asFunctionalComponent1(__VLS_89, new __VLS_89({
    prop: "title",
    label: "问题",
    minWidth: "180",
    showOverflowTooltip: true,
}));
const __VLS_91 = __VLS_90({
    prop: "title",
    label: "问题",
    minWidth: "180",
    showOverflowTooltip: true,
}, ...__VLS_functionalComponentArgsRest(__VLS_90));
let __VLS_94;
/** @ts-ignore @type { | typeof __VLS_components.elTableColumn | typeof __VLS_components.ElTableColumn | typeof __VLS_components['el-table-column'] | typeof __VLS_components.elTableColumn | typeof __VLS_components.ElTableColumn | typeof __VLS_components['el-table-column']} */
elTableColumn;
// @ts-ignore
const __VLS_95 = __VLS_asFunctionalComponent1(__VLS_94, new __VLS_94({
    label: "状态",
    width: "95",
}));
const __VLS_96 = __VLS_95({
    label: "状态",
    width: "95",
}, ...__VLS_functionalComponentArgsRest(__VLS_95));
const { default: __VLS_99 } = __VLS_97.slots;
{
    const { default: __VLS_100 } = __VLS_97.slots;
    const [scope] = __VLS_vSlot(__VLS_100);
    let __VLS_101;
    /** @ts-ignore @type { | typeof __VLS_components.elTag | typeof __VLS_components.ElTag | typeof __VLS_components['el-tag'] | typeof __VLS_components.elTag | typeof __VLS_components.ElTag | typeof __VLS_components['el-tag']} */
    elTag;
    // @ts-ignore
    const __VLS_102 = __VLS_asFunctionalComponent1(__VLS_101, new __VLS_101({
        type: (__VLS_ctx.statusType(scope.row.status)),
    }));
    const __VLS_103 = __VLS_102({
        type: (__VLS_ctx.statusType(scope.row.status)),
    }, ...__VLS_functionalComponentArgsRest(__VLS_102));
    const { default: __VLS_106 } = __VLS_104.slots;
    (__VLS_ctx.statusLabel[scope.row.status]);
    // @ts-ignore
    [tickets, loading, selectTicket, vLoading, statusType, statusLabel,];
    var __VLS_104;
    // @ts-ignore
    [];
}
// @ts-ignore
[];
var __VLS_97;
// @ts-ignore
[];
var __VLS_79;
var __VLS_80;
__VLS_asFunctionalElement1(__VLS_intrinsics.section, __VLS_intrinsics.section)({
    ...{ class: "panel detail-panel" },
});
/** @type {__VLS_StyleScopedClasses['panel']} */ ;
/** @type {__VLS_StyleScopedClasses['detail-panel']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
    ...{ class: "panel-title" },
});
/** @type {__VLS_StyleScopedClasses['panel-title']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.h2, __VLS_intrinsics.h2)({});
if (__VLS_ctx.selected && __VLS_ctx.selected.status === 'new') {
    let __VLS_107;
    /** @ts-ignore @type { | typeof __VLS_components.elButton | typeof __VLS_components.ElButton | typeof __VLS_components['el-button'] | typeof __VLS_components.elButton | typeof __VLS_components.ElButton | typeof __VLS_components['el-button']} */
    elButton;
    // @ts-ignore
    const __VLS_108 = __VLS_asFunctionalComponent1(__VLS_107, new __VLS_107({
        ...{ 'onClick': {} },
        type: "primary",
        loading: (__VLS_ctx.processing),
    }));
    const __VLS_109 = __VLS_108({
        ...{ 'onClick': {} },
        type: "primary",
        loading: (__VLS_ctx.processing),
    }, ...__VLS_functionalComponentArgsRest(__VLS_108));
    let __VLS_112;
    const __VLS_113 = {
        /** @type {typeof __VLS_112.click} */
        onClick: (__VLS_ctx.runProcessing),
    };
    const { default: __VLS_114 } = __VLS_110.slots;
    // @ts-ignore
    [selected, selected, processing, runProcessing,];
    var __VLS_110;
    var __VLS_111;
}
if (!__VLS_ctx.selected) {
    let __VLS_115;
    /** @ts-ignore @type { | typeof __VLS_components.elEmpty | typeof __VLS_components.ElEmpty | typeof __VLS_components['el-empty']} */
    elEmpty;
    // @ts-ignore
    const __VLS_116 = __VLS_asFunctionalComponent1(__VLS_115, new __VLS_115({
        description: "选择或创建一张工单",
    }));
    const __VLS_117 = __VLS_116({
        description: "选择或创建一张工单",
    }, ...__VLS_functionalComponentArgsRest(__VLS_116));
}
else {
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
        ...{ class: "ticket-meta" },
    });
    /** @type {__VLS_StyleScopedClasses['ticket-meta']} */ ;
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({});
    __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
    __VLS_asFunctionalElement1(__VLS_intrinsics.strong, __VLS_intrinsics.strong)({});
    (__VLS_ctx.selected.intent ?? '待识别');
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({});
    __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
    __VLS_asFunctionalElement1(__VLS_intrinsics.strong, __VLS_intrinsics.strong)({});
    (__VLS_ctx.selected.priority);
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({});
    __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
    __VLS_asFunctionalElement1(__VLS_intrinsics.strong, __VLS_intrinsics.strong)({});
    (__VLS_ctx.selected.risk_level);
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({});
    __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
    __VLS_asFunctionalElement1(__VLS_intrinsics.strong, __VLS_intrinsics.strong)({});
    (__VLS_ctx.statusLabel[__VLS_ctx.selected.status]);
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({});
    __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
    __VLS_asFunctionalElement1(__VLS_intrinsics.strong, __VLS_intrinsics.strong)({});
    (__VLS_ctx.classificationSource(__VLS_ctx.selected));
    if (__VLS_ctx.selected.status === 'pending_approval' && __VLS_ctx.selected.approval_tasks?.[0]) {
        __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
            ...{ class: "approval-card" },
        });
        /** @type {__VLS_StyleScopedClasses['approval-card']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({});
        __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
        __VLS_asFunctionalElement1(__VLS_intrinsics.strong, __VLS_intrinsics.strong)({});
        (__VLS_ctx.selected.approval_tasks[0].proposed_data.coupon_amount);
        __VLS_asFunctionalElement1(__VLS_intrinsics.p, __VLS_intrinsics.p)({});
        (__VLS_ctx.selected.approval_tasks[0].proposed_data.reason);
        let __VLS_120;
        /** @ts-ignore @type { | typeof __VLS_components.elButton | typeof __VLS_components.ElButton | typeof __VLS_components['el-button'] | typeof __VLS_components.elButton | typeof __VLS_components.ElButton | typeof __VLS_components['el-button']} */
        elButton;
        // @ts-ignore
        const __VLS_121 = __VLS_asFunctionalComponent1(__VLS_120, new __VLS_120({
            ...{ 'onClick': {} },
            type: "primary",
            loading: (__VLS_ctx.processing),
        }));
        const __VLS_122 = __VLS_121({
            ...{ 'onClick': {} },
            type: "primary",
            loading: (__VLS_ctx.processing),
        }, ...__VLS_functionalComponentArgsRest(__VLS_121));
        let __VLS_125;
        const __VLS_126 = {
            /** @type {typeof __VLS_125.click} */
            onClick: (__VLS_ctx.approveCompensation),
        };
        const { default: __VLS_127 } = __VLS_123.slots;
        // @ts-ignore
        [statusLabel, selected, selected, selected, selected, selected, selected, selected, selected, selected, selected, processing, classificationSource, approveCompensation,];
        var __VLS_123;
        var __VLS_124;
    }
    if (__VLS_ctx.selected.status === 'escalated' && __VLS_ctx.selected.approval_tasks?.[0]?.task_type === 'refund_review') {
        __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
            ...{ class: "escalation-card" },
        });
        /** @type {__VLS_StyleScopedClasses['escalation-card']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({});
        __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
        __VLS_asFunctionalElement1(__VLS_intrinsics.strong, __VLS_intrinsics.strong)({});
        __VLS_asFunctionalElement1(__VLS_intrinsics.p, __VLS_intrinsics.p)({});
        (__VLS_ctx.requiredEvidence(__VLS_ctx.selected));
    }
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
        ...{ class: "conversation" },
    });
    /** @type {__VLS_StyleScopedClasses['conversation']} */ ;
    for (const [message] of __VLS_vFor((__VLS_ctx.selected.messages))) {
        __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
            key: (message.id),
            ...{ class: "message" },
            ...{ class: (message.sender_type) },
        });
        /** @type {__VLS_StyleScopedClasses['message']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.small, __VLS_intrinsics.small)({});
        (message.sender_type === 'customer' ? '客户' : '智能客服');
        __VLS_asFunctionalElement1(__VLS_intrinsics.p, __VLS_intrinsics.p)({});
        (message.content);
        // @ts-ignore
        [selected, selected, selected, selected, requiredEvidence,];
    }
    if (__VLS_ctx.knowledgeCitations(__VLS_ctx.selected).length) {
        __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
            ...{ class: "knowledge-card" },
        });
        /** @type {__VLS_StyleScopedClasses['knowledge-card']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.h3, __VLS_intrinsics.h3)({});
        for (const [source] of __VLS_vFor((__VLS_ctx.knowledgeCitations(__VLS_ctx.selected)))) {
            __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
                key: (source.document_id),
                ...{ class: "knowledge-row" },
            });
            /** @type {__VLS_StyleScopedClasses['knowledge-row']} */ ;
            __VLS_asFunctionalElement1(__VLS_intrinsics.strong, __VLS_intrinsics.strong)({});
            (source.title);
            __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
            (source.version);
            (source.score.toFixed(3));
            // @ts-ignore
            [selected, selected, knowledgeCitations, knowledgeCitations,];
        }
    }
    if (__VLS_ctx.selected.audit_logs?.length) {
        __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
            ...{ class: "audit-area" },
        });
        /** @type {__VLS_StyleScopedClasses['audit-area']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.h3, __VLS_intrinsics.h3)({});
        for (const [log] of __VLS_vFor((__VLS_ctx.selected.audit_logs))) {
            __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
                key: (log.id),
                ...{ class: "audit-row" },
            });
            /** @type {__VLS_StyleScopedClasses['audit-row']} */ ;
            __VLS_asFunctionalElement1(__VLS_intrinsics.code, __VLS_intrinsics.code)({});
            (log.action);
            __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
            (log.operator_type);
            __VLS_asFunctionalElement1(__VLS_intrinsics.time, __VLS_intrinsics.time)({});
            (new Date(log.created_at).toLocaleString());
            // @ts-ignore
            [selected, selected,];
        }
    }
}
// @ts-ignore
[];
const __VLS_export = (await import('vue')).defineComponent({});
export default {};
