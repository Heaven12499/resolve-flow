from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Customer, KnowledgeDocument, LogisticsEvent, Order


DEMO_ORDER_NO = "RF202608290001"


DEMO_KNOWLEDGE_DOCUMENTS = (
    {
        "title": "物流延迟补偿规范",
        "category": "logistics",
        "version": "v1.0",
        "content": (
            "当订单发货后超过承诺时效仍未送达，客服应先核实物流轨迹。"
            "确认存在物流延迟且用户主动提出补偿时，可建议发放5元优惠券。"
            "优惠券补偿必须由人工客服确认后发放，系统不得自动发券。"
        ),
    },
    {
        "title": "商品质量问题与退款复核规范",
        "category": "after_sales",
        "version": "v1.0",
        "content": (
            "涉及商品质量、损坏、货不对板、假货或全额退款的诉求属于高风险售后。"
            "客服应收集订单信息、商品问题照片或视频、签收及使用情况。"
            "此类工单必须升级主管复核，AI和普通客服不得直接执行退款。"
        ),
    },
    {
        "title": "物流状态说明",
        "category": "logistics",
        "version": "v1.0",
        "content": (
            "物流查询应以订单绑定的最新物流节点为准。"
            "客服回复应说明当前节点和后续跟进方式，不得承诺无法确认的具体送达时间。"
        ),
    },
    {
        "title": "发货与揽收异常处理规范",
        "category": "logistics",
        "version": "v1.0",
        "content": (
            "订单显示已发货但48小时内没有揽收记录时，客服应说明正在核实发货状态。"
            "不得虚构物流节点或承诺具体揽收时间；超过处理时限后应转人工跟进。"
        ),
    },
    {
        "title": "物流停滞与异常天气说明",
        "category": "logistics",
        "version": "v1.0",
        "content": (
            "物流节点超过72小时未更新时，应先核验最新轨迹并登记异常。"
            "受极端天气、交通管制等影响时，可以说明配送可能延迟，但不得承诺准确送达日期。"
        ),
    },
    {
        "title": "优惠券补偿审批边界",
        "category": "logistics",
        "version": "v1.0",
        "content": (
            "物流延迟补偿仅适用于已核实存在延迟且客户明确提出补偿的工单。"
            "标准建议为5元优惠券；所有优惠券均须进入人工审批，审批前AI不得发放或承诺券码。"
        ),
    },
    {
        "title": "售后证据收集清单",
        "category": "after_sales",
        "version": "v1.0",
        "content": (
            "质量、损坏、漏发和货不对板问题应收集订单号、商品照片或视频、外包装情况、签收时间及使用情况。"
            "证据不完整时只能请求补充材料，不得直接判断退款、赔偿或责任归属。"
        ),
    },
    {
        "title": "货不对板与错发漏发处理规范",
        "category": "after_sales",
        "version": "v1.0",
        "content": (
            "商品颜色、型号、规格与页面不符，或存在错发漏发时，应先核实订单商品与客户提供的证据。"
            "该类工单需要售后专员或主管复核后再决定补发、退货或退款方案。"
        ),
    },
    {
        "title": "退款时效与主管复核规范",
        "category": "after_sales",
        "version": "v1.0",
        "content": (
            "退款、部分退款和仅退款均属于资金操作，必须由具有权限的人工人员完成。"
            "AI只能提示所需材料和处理进度，任何情况下不得代替主管执行退款。"
        ),
    },
    {
        "title": "投诉升级与沟通规范",
        "category": "after_sales",
        "version": "v1.0",
        "content": (
            "客户明确表示投诉、曝光、起诉或情绪强烈时，客服应保持克制并记录诉求。"
            "不得争辩或给出未经核验的补偿承诺，应将工单标记为需人工优先跟进。"
        ),
    },
)


def seed_demo_data(db: Session) -> None:
    existing = db.scalar(select(Order).where(Order.order_no == DEMO_ORDER_NO))
    if not existing:
        customer = Customer(name="演示用户", phone="138****0000")
        db.add(customer)
        db.flush()

        order = Order(
            order_no=DEMO_ORDER_NO,
            customer_id=customer.id,
            product_name="无线蓝牙耳机",
            amount=Decimal("299.00"),
            status="shipped",
        )
        db.add(order)
        db.flush()

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        db.add_all(
            [
                LogisticsEvent(
                    order_id=order.id,
                    status="collected",
                    description="商家已发货，包裹已由快递公司揽收",
                    occurred_at=now - timedelta(days=3),
                ),
                LogisticsEvent(
                    order_id=order.id,
                    status="in_transit",
                    description="包裹已到达上海转运中心，正在发往下一站",
                    occurred_at=now - timedelta(days=1),
                ),
            ]
        )

    existing_rule_titles = set(db.scalars(select(KnowledgeDocument.title)).all())
    db.add_all(
        KnowledgeDocument(**document)
        for document in DEMO_KNOWLEDGE_DOCUMENTS
        if document["title"] not in existing_rule_titles
    )
    db.commit()
