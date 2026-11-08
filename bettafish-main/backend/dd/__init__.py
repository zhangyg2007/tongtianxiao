"""背调线 P0：投资尽调模板 + 评分卡 + 证据后校验。

模块划分（均为环境无关纯代码，服务器上经 RQ worker 执行）：
- template.py  12 章结构 + 评分卡配置（数据驱动，改模板不改代码）
- scorecard.py 三态判定 + 覆盖率计算（纯函数）
- verify.py    证据后校验：引用校验 + 数字回查（纯函数）
- pipeline.py  investment_dd 任务处理器（组装报告 → 后校验 → 落 PG）
"""
