from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Customer, KnowledgeDocument, LogisticsEvent, Order


DEMO_ORDER_NO = "RF202608290001"


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

    has_rules = db.scalar(select(KnowledgeDocument.id).limit(1))
    if not has_rules:
        db.add_all(
            [
                KnowledgeDocument(
                    title="物流延迟补偿规范",
                    category="logistics",
                    version="v1.0",
                    content=(
                        "当订单发货后超过承诺时效仍未送达，客服应先核实物流轨迹。"
                        "确认存在物流延迟且用户主动提出补偿时，可建议发放5元优惠券。"
                        "优惠券补偿必须由人工客服确认后发放，系统不得自动发券。"
                    ),
                ),
                KnowledgeDocument(
                    title="商品质量问题与退款复核规范",
                    category="after_sales",
                    version="v1.0",
                    content=(
                        "涉及商品质量、损坏、货不对板、假货或全额退款的诉求属于高风险售后。"
                        "客服应收集订单信息、商品问题照片或视频、签收及使用情况。"
                        "此类工单必须升级主管复核，AI和普通客服不得直接执行退款。"
                    ),
                ),
                KnowledgeDocument(
                    title="物流状态说明",
                    category="logistics",
                    version="v1.0",
                    content=(
                        "物流查询应以订单绑定的最新物流节点为准。"
                        "客服回复应说明当前节点和后续跟进方式，不得承诺无法确认的具体送达时间。"
                    ),
                ),
            ]
        )
    db.commit()
