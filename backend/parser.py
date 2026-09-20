"""Deterministic, explicitly labelled offline demo parser; cloud mode never falls back silently."""
from datetime import date
from decimal import Decimal
import re

from .catalog import BY_ID, DEPARTMENT_ALIASES, METRICS
from .query import shift_month
from .schemas import Decision, MetricFilter, QueryPlan


def guard_question(question: str):
    if re.search(r"删除|删库|删掉|清空|执行.*(?:SQL|代码|命令)|读取.*(?:文件|密钥)|系统提示|api.?key|drop\s|delete\s|insert\s|update\s|select\s|union\s|pragma\b|attach\b|read_csv|readfile|忽略.*(?:规则|指令)", question, re.I):
        return Decision(status="unsupported", message="这里只支持查询医院科室经营指标，不能执行任意 SQL、修改数据或读取本地文件。")
    if re.search(r"(?<![A-Za-z])CT(?![A-Za-z])|核磁|磁共振|挂号费|诊疗.*(?:价格|收费)|单价|成本|利润|盈利|患者.*(?:账单|费用)|病人.*(?:账单|费用)|治疗方案|诊断|推荐.*(?:药|治疗)|预测|为什么|原因", question, re.I):
        return Decision(status="unsupported", message="当前表格没有诊疗项目单价、患者账单、成本、利润或临床资料，也不足以解释原因或预测。可以查询科室月度收入、医保金额和运营指标。")
    if re.search(r"费用|花费|收费|多少钱", question) and not any(alias in question for m in METRICS for alias in m.aliases) and "收入" not in question:
        return Decision(status="clarification", message="请明确科室与费用口径：您要查询合计收入、次均费用，还是自费金额？", choices=["合计收入", "次均费用", "自费金额"])
    return None


def _number(text):
    return {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10, "十二": 12}.get(text, int(text) if text.isdigit() else 1)


def parse_time(question, latest, today):
    current = today.strftime("%Y-%m")
    # Explicit ranges take priority over single months and years.
    matches = list(re.finditer(r"(20\d{2})\s*[年/\-]\s*(\d{1,2})(?:月)?", question))
    if len(matches) >= 2:
        start, end = matches[0], matches[1]
        return f"{start[1]}-{int(start[2]):02d}", f"{end[1]}-{int(end[2]):02d}", True
    compact = re.search(r"(20\d{2})年\s*(\d{1,2})月?\s*(?:至|到|—|~|-)\s*(\d{1,2})月", question)
    if compact:
        return f"{compact[1]}-{int(compact[2]):02d}", f"{compact[1]}-{int(compact[3]):02d}", True
    quarter = re.search(r"(?:(20\d{2})年)?第?([一二三四1234])季度", question)
    if quarter:
        year = int(quarter[1] or today.year)
        q = _number(quarter[2])
        return f"{year}-{(q-1)*3+1:02d}", f"{year}-{q*3:02d}", True
    if matches:
        m = matches[0]
        return f"{m[1]}-{int(m[2]):02d}", f"{m[1]}-{int(m[2]):02d}", True
    latest_n = re.search(r"(?:最新|最近)([一二两三四五六七八九十\d]+)个?有数据月份", question)
    if latest_n:
        return shift_month(latest, -_number(latest_n[1]) + 1), latest, True
    if re.search(r"最新(?:的)?(?:一个)?月|最新数据", question):
        return latest, latest, True
    if "上个月" in question or "上月" in question:
        return shift_month(current, -1), shift_month(current, -1), True
    if "这个月" in question or "本月" in question:
        return current, current, True
    if re.search(r"过去一年|最近一年|近一年", question):
        return shift_month(current, -12), shift_month(current, -1), True
    last_n = re.search(r"(?:过去|最近|近)([一二两三四五六七八九十\d]+)个?月", question)
    if last_n:
        return shift_month(current, -_number(last_n[1])), shift_month(current, -1), True
    explicit_year = re.search(r"(20\d{2})年?", question)
    year = int(explicit_year[1]) if explicit_year else None
    if "今年" in question:
        year = today.year
    elif "去年" in question:
        year = today.year - 1
    elif "前年" in question:
        year = today.year - 2
    if year:
        bare_month = re.search(r"(?<!\d)(\d{1,2})月", question)
        if bare_month:
            return f"{year}-{int(bare_month[1]):02d}", f"{year}-{int(bare_month[1]):02d}", True
        return f"{year}-01", f"{year}-12", True
    return latest, latest, False


def demo_parse(question: str, catalog: dict, today: date, previous: QueryPlan | None = None):
    guard = guard_question(question)
    if guard:
        return guard
    q = question.strip()
    followup = previous is not None and bool(re.search(r"那|呢|改成|换成|再看|同样|也看|按月|按科室|万元|环比|同比|这个科室|该科室|它", q))
    base = previous.model_dump() if followup else {}
    departments, types = [], []
    remaining = q
    names = {d: d for d in catalog["departments"]}
    names.update({a: d for a, d in DEPARTMENT_ALIASES.items() if d in catalog["departments"]})
    # Match full type names before shorter embedded department names (妇产科 vs 产科).
    candidates = {name: (target, "department") for name, target in names.items()}
    candidates.update({t: (t, "type") for t in catalog["department_types"] if t not in names})
    unknown_mentions = re.findall(r"(?:^|年|月|查询|看看|比较|对比|那|和|与|、)\s*([\u4e00-\u9fff]{1,8}科)(?=的|收入|合计|总|门诊|住院|费用|次均|医保|床位|平均|手术|药品|检查|耗材|其他|自费|呢|[，。？? ]|$)", q)
    for mention in unknown_mentions:
        if mention not in candidates and not any(name in mention for name in names) and mention not in {"各科", "每科", "哪个科", "该科", "这个科"}:
            departments.append(mention)
            remaining = remaining.replace(mention, " ")
    for name in sorted(candidates, key=len, reverse=True):
        if name in remaining:
            target, kind = candidates[name]
            (departments if kind == "department" else types).append(target)
            remaining = remaining.replace(name, " ")
    departments = list(dict.fromkeys(departments))
    known_unknowns = re.findall(r"骨科|眼科|皮肤科|口腔科|肿瘤科|耳鼻喉科|不存在科|不存在的科室|测试科", remaining)
    if known_unknowns:
        departments.extend(known_unknowns)
    if departments or types:
        base["departments"] = departments
        base["department_types"] = types
    elif re.search(r"全院|全部科室|所有科室|各科室|哪个科室|哪些科室|各个科室|每个科室", q):
        base["departments"], base["department_types"] = [], []
    elif re.search(r"这个科室|该科室|这个科", q) and not base.get("departments"):
        return Decision(status="clarification", message="请指定要查询的科室，以及合计收入、次均费用或自费金额等具体指标。", choices=["心血管内科的合计收入", "儿科的次均费用", "产科的自费金额"])
    selected = []
    metric_remaining = q
    aliases = sorted([(a, m.id) for m in METRICS for a in m.aliases], key=lambda pair: len(pair[0]), reverse=True)
    for alias, metric in aliases:
        if alias in metric_remaining:
            if metric not in selected:
                selected.append(metric)
            metric_remaining = metric_remaining.replace(alias, " ")
    if not selected and re.search(r"收入|营收", q):
        selected = ["total_revenue"]
    if not selected and re.search(r"费用|花费|收费|多少钱|花了多少", q):
        return Decision(status="clarification", message="您说的费用是指合计收入、次均费用，还是自费金额？", choices=["合计收入", "次均费用", "自费金额"])
    if selected:
        base["metrics"] = selected
        # Do not carry incompatible metric filters/order from a different metric.
        base["filters"] = []
        base["order_by"] = None
    elif not base.get("metrics"):
        return Decision(status="clarification", message="请说明要查询的指标，例如收入、医保占比、门诊人次或床位使用率。", choices=["合计收入", "门诊人次", "医保占比"])
    latest = catalog["end_month"] or today.strftime("%Y-%m")
    start, end, explicit = parse_time(q, latest, today)
    if explicit or not base.get("start_month"):
        base.update(start_month=start, end_month=end, time_explicit=explicit)
    if re.search(r"全部时间|所有月份|整个期间", q) and catalog["start_month"]:
        base.update(start_month=catalog["start_month"], end_month=latest, time_explicit=True)
    groups = list(base.get("group_by", []))
    if re.search(r"走势|趋势|每月|按月|逐月|各月", q):
        groups = ["month"]
        # Multiple departments need separate series for raw metrics or explicitly compared departments.
        if len(base.get("departments", [])) > 1 or any(BY_ID[m].aggregation == "raw" for m in base["metrics"]) and not base.get("departments"):
            groups.append("department")
    if re.search(r"各科室|每个科室|哪个科室|哪些科室|按科室|各个科室|排名|排行|最高|最低|最多|最少|前\s*[一二三四五六七八九十\d]+", q):
        if "department" not in groups:
            groups.append("department")
    if re.search(r"按类型|各类型|按科室类型", q):
        groups = ["department_type"]
    if len(base.get("departments", [])) > 1 and re.search(r"比较|对比|分别|各自", q) and "department" not in groups:
        groups.append("department")
    base["group_by"] = groups
    base["unit"] = "wan" if "万元" in q or "按万" in q else base.get("unit", "yuan")
    if "同比" in q or "去年同期" in q:
        base["comparison"] = "yoy"
    elif "环比" in q or "上月相比" in q:
        base["comparison"] = "mom"
    elif not followup:
        base["comparison"] = "none"
    if re.search(r"排名|排行|最高|最低|最多|最少|前\s*[一二三四五六七八九十\d]+|从高到低|从低到高", q):
        base["order_by"] = base["metrics"][0]
        base["order"] = "asc" if re.search(r"最低|最少|从低到高", q) else "desc"
        top = re.search(r"前\s*([一二三四五六七八九十\d]+)", q)
        base["limit"] = min(_number(top[1]), 100) if top else 100
    threshold = re.search(r"(超过|大于|高于|不少于|至少|低于|小于|不超过|至多|等于)\s*([\d.]+)\s*(万|亿)?", q)
    if threshold:
        operators = {"超过": "gt", "大于": "gt", "高于": "gt", "不少于": "gte", "至少": "gte", "低于": "lt", "小于": "lt", "不超过": "lte", "至多": "lte", "等于": "eq"}
        factor = {None: 1, "万": 10000, "亿": 100000000}[threshold[3]]
        base["filters"] = [MetricFilter(metric=base["metrics"][0], op=operators[threshold[1]], value=Decimal(threshold[2]) * factor)]
        if not base.get("departments") and "department" not in base["group_by"]:
            base["group_by"].append("department")
    try:
        return Decision(status="query", plan=QueryPlan.model_validate(base))
    except ValueError:
        return Decision(status="clarification", message="日期或查询条件无法识别，请使用明确的科室、指标及 YYYY年M月 或年份重试。")
