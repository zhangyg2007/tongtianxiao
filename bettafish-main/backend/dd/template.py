"""投资尽调 v1 模板：12 章结构 + 评分卡配置。

依据：
- 定制化设计方案 §8.1.2（12 章报告结构）、§8.1.4（后校验硬机制）
- 前端与产品形态升级设计 §5.1.2（评分卡 7 维度权重）、§5.1.3（三态判定与覆盖率）

纯数据模块：调整章节/权重只改这里，不动计算与渲染代码。
"""

TEMPLATE_CODE = "investment_dd_v1"

# ------------------------------------------------------------------
# 12 章结构
# ------------------------------------------------------------------
# source:
#   "summary"  = 第 1 章，由评分卡结果生成
#   "verdict"  = 第 11 章，由覆盖率规则生成
#   "appendix" = 第 12 章，由证据列表生成
#   其余章节按 fact_types 从 core.evidence 取事实填充；
#   fact_types 为空 = 该章数据源 P0 未接入，固定输出【数据不足】。
CHAPTERS = [
    {"no": 1, "title": "摘要与结论", "source": "summary"},
    {"no": 2, "title": "主体基本信息", "fact_types": ["registration"]},
    {"no": 3, "title": "股权结构与实际控制人", "fact_types": []},
    {"no": 4, "title": "高管团队", "fact_types": ["exec_change"]},
    {"no": 5, "title": "司法涉诉", "fact_types": ["litigation"]},
    {"no": 6, "title": "行政处罚与监管措施", "fact_types": ["penalty"]},
    {"no": 7, "title": "财务表现", "fact_types": ["finance"]},
    {"no": 8, "title": "经营活跃度", "fact_types": ["bid"]},
    {"no": 9, "title": "知识产权", "fact_types": ["ip"]},
    {"no": 10, "title": "舆情态势", "fact_types": ["sentiment"]},
    {"no": 11, "title": "风险评级与建议", "source": "verdict"},
    {"no": 12, "title": "证据附录", "source": "appendix"},
]

# ------------------------------------------------------------------
# 评分卡（投资尽调 100 分，前端设计 §5.1.2）
# ------------------------------------------------------------------
# fact_types  = 判定该维度「有数据」的证据类型（空 = P0 无数据源，恒为数据缺失）
# risk_types  = 出现即触发「确有风险」的证据类型（如司法风险维度见到诉讼即风险）
SCORECARD_DIMENSIONS = [
    {"key": "stability", "name": "主体稳定性", "weight": 10,
     "fact_types": ["registration"], "risk_types": []},
    {"key": "ownership", "name": "股权结构", "weight": 15,
     "fact_types": [], "risk_types": []},
    {"key": "finance", "name": "财务健康", "weight": 25,
     "fact_types": ["finance"], "risk_types": []},
    {"key": "litigation", "name": "司法风险", "weight": 20,
     "fact_types": ["litigation"], "risk_types": ["litigation"]},
    {"key": "compliance", "name": "合规风险", "weight": 15,
     "fact_types": ["penalty"], "risk_types": ["penalty"]},
    {"key": "activity", "name": "经营活跃度", "weight": 10,
     "fact_types": ["bid"], "risk_types": []},
    {"key": "sentiment", "name": "舆情风险", "weight": 5,
     "fact_types": ["sentiment"], "risk_types": ["sentiment"]},
]

# 一票否决关键词：扫描事实文本，命中即整体降级（前端设计 §5.1.3）
VETO_KEYWORDS = ["失信被执行人", "吊销", "注销", "采取强制措施"]

# 覆盖率阈值（前端设计 §5.1.3）
#   >= 80%        结论可用
#   60% ~ 80%     结论仅供参考
#   < 60%         强制拒绝出结论，只输出证据不足清单
COVERAGE_USABLE = 0.80
COVERAGE_MINIMUM = 0.60

# 触发风险规则的维度得分（P0 规则占位：统一按 40/100 计，
# P1 接入真实数据源后按「金额/次数/时间衰减」细化扣分规则）
RISK_DIMENSION_SCORE = 40

# 合规表述固定文案（前端设计 §5.1.4）
COMPLIANCE_NOTE = (
    "本报告仅基于公开渠道可获取的信息编制，不构成任何投资建议。"
    "报告中标注【事实陈述】的内容均有证据支撑、可直接引用；"
    "标注【分析意见】的内容为基于事实的推断，不构成事实认定。"
)
