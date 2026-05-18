from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from localai.modules.financial_transaction_schema import normalized_text


@dataclass(frozen=True)
class LedgerClassification:
    transaction_type: str
    category_lv1: str
    category_lv2: str
    category_lv3: str = ""
    target_person: str = "其他"
    project: str = ""
    tags: tuple[str, ...] = ()
    reimbursable_status: str = "否"
    budget_status: str = "未知"
    confidence: float = 0.5
    reason: str = ""
    review_required: bool = False


@dataclass(frozen=True)
class KeywordRule:
    keywords: tuple[str, ...]
    classification: LedgerClassification
    direction: str | None = None
    priority: int = 100


RULES: tuple[KeywordRule, ...] = (
    KeywordRule(
        keywords=("信用卡还款", "还信用卡", "卡还款", "借记卡还款"),
        direction="outflow",
        priority=10,
        classification=LedgerClassification(
            transaction_type="转账",
            category_lv1="信用卡",
            category_lv2="信用卡还款",
            category_lv3="储蓄卡还信用卡",
            target_person="本人",
            project="账户流转",
            tags=("非消费", "账户流转"),
            budget_status="不纳入预算",
            confidence=0.98,
            reason="命中信用卡还款关键词，按账户流转处理",
        ),
    ),
    KeywordRule(
        keywords=("账户互转", "转账", "转存", "转入", "转出", "提现", "充值到余额"),
        priority=20,
        classification=LedgerClassification(
            transaction_type="转账",
            category_lv1="账户互转",
            category_lv2="银行与支付账户",
            category_lv3="账户流转",
            target_person="本人",
            project="账户流转",
            tags=("非消费", "账户流转"),
            budget_status="不纳入预算",
            confidence=0.88,
            reason="命中转账或账户互转关键词",
        ),
    ),
    KeywordRule(
        keywords=("基金申购", "基金买入", "股票买入", "理财申购", "理财购买", "证券", "基金定投"),
        direction="outflow",
        priority=25,
        classification=LedgerClassification(
            transaction_type="资产变动",
            category_lv1="投资交易",
            category_lv2="投资买入",
            category_lv3="理财申购",
            target_person="本人",
            project="资产配置",
            tags=("非消费", "投资"),
            budget_status="不纳入预算",
            confidence=0.9,
            reason="命中投资买入关键词，按资产变动处理",
        ),
    ),
    KeywordRule(
        keywords=("基金赎回", "股票卖出", "理财赎回", "理财到期"),
        direction="inflow",
        priority=26,
        classification=LedgerClassification(
            transaction_type="资产变动",
            category_lv1="投资交易",
            category_lv2="投资卖出",
            category_lv3="理财赎回",
            target_person="本人",
            project="资产配置",
            tags=("非消费", "投资"),
            budget_status="不纳入预算",
            confidence=0.9,
            reason="命中投资卖出关键词，按资产变动处理",
        ),
    ),
    KeywordRule(
        keywords=("退款", "退货", "返现", "冲正", "refund"),
        direction="inflow",
        priority=30,
        classification=LedgerClassification(
            transaction_type="退款",
            category_lv1="其他收入",
            category_lv2="退款返现",
            category_lv3="购物退款",
            target_person="家庭",
            project="退款返还",
            tags=("退款",),
            budget_status="不纳入预算",
            confidence=0.9,
            reason="命中退款或返现关键词",
        ),
    ),
    KeywordRule(
        keywords=("报销", "差旅报销", "费用报销"),
        direction="inflow",
        priority=35,
        classification=LedgerClassification(
            transaction_type="收入",
            category_lv1="工资薪酬",
            category_lv2="报销到账",
            category_lv3="差旅报销",
            target_person="工作",
            project="工作报销",
            tags=("已报销", "工作"),
            reimbursable_status="已报销",
            budget_status="不纳入家庭预算",
            confidence=0.9,
            reason="命中报销到账关键词",
        ),
    ),
    KeywordRule(
        keywords=("工资", "薪资", "薪酬", "奖金", "绩效", "津贴", "补贴"),
        direction="inflow",
        priority=40,
        classification=LedgerClassification(
            transaction_type="收入",
            category_lv1="工资薪酬",
            category_lv2="固定工资",
            category_lv3="基本工资",
            target_person="本人",
            project="个人收入",
            tags=("收入",),
            budget_status="不纳入预算",
            confidence=0.88,
            reason="命中工资薪酬关键词",
        ),
    ),
    KeywordRule(
        keywords=("利息", "结息"),
        direction="inflow",
        priority=45,
        classification=LedgerClassification(
            transaction_type="收入",
            category_lv1="投资理财收入",
            category_lv2="利息收入",
            category_lv3="银行存款利息",
            target_person="本人",
            project="资产收益",
            tags=("收入", "投资"),
            budget_status="不纳入预算",
            confidence=0.85,
            reason="命中利息收入关键词",
        ),
    ),
    KeywordRule(
        keywords=("医院", "门诊", "挂号", "医保", "诊所"),
        direction="outflow",
        priority=60,
        classification=LedgerClassification(
            transaction_type="支出",
            category_lv1="医疗健康",
            category_lv2="医疗诊疗",
            category_lv3="门诊",
            target_person="家庭",
            project="医疗健康",
            tags=("刚性支出", "医疗"),
            budget_status="预算内",
            confidence=0.88,
            reason="命中医疗诊疗关键词",
        ),
    ),
    KeywordRule(
        keywords=("药房", "药店", "叮当智慧药房", "京东健康"),
        direction="outflow",
        priority=61,
        classification=LedgerClassification(
            transaction_type="支出",
            category_lv1="医疗健康",
            category_lv2="药品器械",
            category_lv3="非处方药",
            target_person="家庭",
            project="医疗健康",
            tags=("刚性支出", "医疗"),
            budget_status="预算内",
            confidence=0.86,
            reason="命中药房或药店关键词",
        ),
    ),
    KeywordRule(
        keywords=("体检", "疫苗", "牙科", "眼科"),
        direction="outflow",
        priority=62,
        classification=LedgerClassification(
            transaction_type="支出",
            category_lv1="医疗健康",
            category_lv2="体检保健",
            category_lv3="体检",
            target_person="家庭",
            project="医疗健康",
            tags=("医疗",),
            budget_status="预算内",
            confidence=0.86,
            reason="命中体检保健关键词",
        ),
    ),
    KeywordRule(
        keywords=("美团外卖", "饿了么", "外卖"),
        direction="outflow",
        priority=70,
        classification=LedgerClassification(
            transaction_type="支出",
            category_lv1="餐饮食品",
            category_lv2="外卖便利",
            category_lv3="外卖",
            target_person="本人",
            project="个人日常",
            tags=("弹性支出", "日常"),
            budget_status="预算内",
            confidence=0.88,
            reason="命中外卖平台关键词",
        ),
    ),
    KeywordRule(
        keywords=("美团平台商户", "meituan"),
        direction="outflow",
        priority=70,
        classification=LedgerClassification(
            transaction_type="支出",
            category_lv1="餐饮食品",
            category_lv2="外卖便利",
            category_lv3="外卖",
            target_person="本人",
            project="个人日常",
            tags=("弹性支出", "日常"),
            budget_status="预算内",
            confidence=0.76,
            reason="命中美团平台关键词，第一版按餐饮外卖处理并建议复核",
            review_required=True,
        ),
    ),
    KeywordRule(
        keywords=("咖啡", "奶茶", "星巴克", "瑞幸", "蜜雪冰城"),
        direction="outflow",
        priority=71,
        classification=LedgerClassification(
            transaction_type="支出",
            category_lv1="餐饮食品",
            category_lv2="饮品零食",
            category_lv3="咖啡奶茶",
            target_person="本人",
            project="个人日常",
            tags=("弹性支出", "日常"),
            budget_status="预算内",
            confidence=0.85,
            reason="命中咖啡奶茶关键词",
        ),
    ),
    KeywordRule(
        keywords=("餐饮", "饭店", "餐厅", "麦当劳", "肯德基", "必胜客", "赛百味", "午餐", "晚餐", "早餐"),
        direction="outflow",
        priority=72,
        classification=LedgerClassification(
            transaction_type="支出",
            category_lv1="餐饮食品",
            category_lv2="日常餐饮",
            category_lv3="日常餐食",
            target_person="本人",
            project="个人日常",
            tags=("弹性支出", "日常"),
            budget_status="预算内",
            confidence=0.82,
            reason="命中日常餐饮关键词",
        ),
    ),
    KeywordRule(
        keywords=("停车", "停车场", "etcp"),
        direction="outflow",
        priority=80,
        classification=LedgerClassification(
            transaction_type="支出",
            category_lv1="交通出行",
            category_lv2="自驾用车",
            category_lv3="停车费",
            target_person="家庭",
            project="家庭日常",
            tags=("交通",),
            budget_status="预算内",
            confidence=0.9,
            reason="命中停车费关键词",
        ),
    ),
    KeywordRule(
        keywords=("高速", "过路费"),
        direction="outflow",
        priority=81,
        classification=LedgerClassification(
            transaction_type="支出",
            category_lv1="交通出行",
            category_lv2="自驾用车",
            category_lv3="高速费",
            target_person="家庭",
            project="家庭日常",
            tags=("交通",),
            budget_status="预算内",
            confidence=0.86,
            reason="命中高速通行关键词",
        ),
    ),
    KeywordRule(
        keywords=("地铁", "公交"),
        direction="outflow",
        priority=82,
        classification=LedgerClassification(
            transaction_type="支出",
            category_lv1="交通出行",
            category_lv2="公共交通",
            category_lv3="公共交通",
            target_person="本人",
            project="个人日常",
            tags=("交通",),
            budget_status="预算内",
            confidence=0.84,
            reason="命中公共交通关键词",
        ),
    ),
    KeywordRule(
        keywords=("打车", "滴滴", "出租车", "网约车"),
        direction="outflow",
        priority=83,
        classification=LedgerClassification(
            transaction_type="支出",
            category_lv1="交通出行",
            category_lv2="打车租车",
            category_lv3="网约车",
            target_person="本人",
            project="个人日常",
            tags=("交通",),
            budget_status="预算内",
            confidence=0.84,
            reason="命中打车出行关键词",
        ),
    ),
    KeywordRule(
        keywords=("淘宝", "天猫", "拼多多", "京东", "抖音商城"),
        direction="outflow",
        priority=90,
        classification=LedgerClassification(
            transaction_type="支出",
            category_lv1="购物消费",
            category_lv2="日用百货",
            category_lv3="其他日用品",
            target_person="家庭",
            project="家庭日常",
            tags=("购物",),
            budget_status="预算内",
            confidence=0.78,
            reason="命中电商平台关键词，具体品类等待订单补充或人工复核",
            review_required=True,
        ),
    ),
    KeywordRule(
        keywords=("支付宝-商户", "财付通-平台商户", "微信支付", "支付宝"),
        direction="outflow",
        priority=95,
        classification=LedgerClassification(
            transaction_type="支出",
            category_lv1="购物消费",
            category_lv2="日用百货",
            category_lv3="其他日用品",
            target_person="家庭",
            project="家庭日常",
            tags=("购物",),
            budget_status="预算内",
            confidence=0.62,
            reason="命中泛支付商户关键词，需结合商户或订单复核",
            review_required=True,
        ),
    ),
    KeywordRule(
        keywords=("物业", "物业费", "房租", "租金", "供暖", "采暖"),
        direction="outflow",
        priority=100,
        classification=LedgerClassification(
            transaction_type="支出",
            category_lv1="居住生活",
            category_lv2="住房成本",
            category_lv3="物业费",
            target_person="家庭",
            project="家庭日常",
            tags=("刚性支出", "固定支出"),
            budget_status="预算内",
            confidence=0.86,
            reason="命中住房成本关键词",
        ),
    ),
    KeywordRule(
        keywords=("水费", "电费", "燃气", "国家电网", "自来水"),
        direction="outflow",
        priority=101,
        classification=LedgerClassification(
            transaction_type="支出",
            category_lv1="居住生活",
            category_lv2="水电能源",
            category_lv3="水电燃气",
            target_person="家庭",
            project="家庭日常",
            tags=("刚性支出", "固定支出"),
            budget_status="预算内",
            confidence=0.9,
            reason="命中水电燃气关键词",
        ),
    ),
    KeywordRule(
        keywords=("话费", "宽带", "流量包", "手机充值"),
        direction="outflow",
        priority=102,
        classification=LedgerClassification(
            transaction_type="支出",
            category_lv1="居住生活",
            category_lv2="通讯网络",
            category_lv3="手机话费",
            target_person="家庭",
            project="家庭日常",
            tags=("刚性支出", "固定支出"),
            budget_status="预算内",
            confidence=0.86,
            reason="命中通讯充值关键词",
        ),
    ),
    KeywordRule(
        keywords=("学费", "少儿", "培训", "英语", "托管", "兴趣班"),
        direction="outflow",
        priority=110,
        classification=LedgerClassification(
            transaction_type="支出",
            category_lv1="教育学习",
            category_lv2="子女教育",
            category_lv3="兴趣班",
            target_person="子女",
            project="子女教育",
            tags=("刚性支出", "周期支出"),
            budget_status="预算内",
            confidence=0.86,
            reason="命中子女教育或培训关键词",
        ),
    ),
)


def classify_ledger_fact(fact: dict[str, Any]) -> LedgerClassification:
    text = normalized_text(
        " ".join(
            [
                fact.get("merchant", ""),
                fact.get("counterparty", ""),
                fact.get("title", ""),
                fact.get("summary", ""),
                fact.get("platform", ""),
                fact.get("payment_channel", ""),
            ]
        )
    )
    direction = fact.get("direction", "unknown")
    for rule in sorted(RULES, key=lambda item: item.priority):
        if rule.direction and rule.direction != direction:
            continue
        if any(normalized_text(keyword) in text for keyword in rule.keywords):
            return rule.classification

    if direction == "inflow":
        return LedgerClassification(
            transaction_type="收入",
            category_lv1="其他收入",
            category_lv2="其他收入",
            category_lv3="",
            target_person="本人",
            project="个人收入",
            tags=("收入",),
            budget_status="不纳入预算",
            confidence=0.55,
            reason="金额流入但未命中明确收入规则",
            review_required=True,
        )
    if direction == "outflow":
        return LedgerClassification(
            transaction_type="支出",
            category_lv1="未分类",
            category_lv2="未分类",
            category_lv3="",
            target_person="其他",
            project="",
            tags=(),
            budget_status="未知",
            confidence=0.35,
            reason="金额流出但未命中支出分类规则",
            review_required=True,
        )
    return LedgerClassification(
        transaction_type="未知",
        category_lv1="未分类",
        category_lv2="未分类",
        confidence=0.1,
        reason="无法判断资金方向",
        review_required=True,
    )
