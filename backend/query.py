from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
import json

from sqlalchemy import case, cast, Float, func, select

from .catalog import BY_ID, DEPARTMENT_ALIASES
from .db import Database
from .schemas import QueryPlan


def shift_month(month: str, delta: int):
    year, number = map(int, month.split("-"))
    ordinal = year * 12 + number - 1 + delta
    return f"{ordinal // 12:04d}-{ordinal % 12 + 1:02d}"


def months_between(start, end):
    out = []
    while start <= end:
        out.append(start)
        start = shift_month(start, 1)
    return out


def rounded(value, places=2):
    if value is None:
        return None
    return float(Decimal(str(value)).quantize(Decimal(10) ** -places, rounding=ROUND_HALF_UP))


def format_value(value, unit):
    precision = 6 if unit == "万元" else 2
    return "不可计算（分母为零）" if value is None else f"{value:,.{precision}f}".rstrip("0").rstrip(".") + unit


def scope_description(plan, departments):
    if plan.departments:
        return "、".join(plan.departments)
    if plan.department_types:
        return "、".join(plan.department_types) + "（" + "、".join(departments) + "）"
    return "全部科室"


def empty_result(status, message, plan=None, choices=None):
    return {"status": status, "answer": message, "plan": plan.model_dump(mode="json") if plan else None,
            "rows": [], "columns": [], "chart": None, "sources": [], "sql": [], "warnings": [], "choices": choices or []}


class QueryEngine:
    def __init__(self, db: Database):
        self.db = db

    def execute(self, plan: QueryPlan):
        plan = plan.model_copy(deep=True)
        plan.departments = [DEPARTMENT_ALIASES.get(d, d) for d in plan.departments]
        state = self.db.catalog_state()
        unknown = set(plan.departments) - set(state["departments"])
        unknown_types = set(plan.department_types) - set(state["department_types"])
        if unknown or unknown_types:
            return empty_result("no_data", "未找到科室或类型：" + "、".join(sorted(unknown | unknown_types)) + "。请查看指标说明中的科室列表。", plan)
        if not state["row_count"]:
            return empty_result("no_data", "尚未导入数据，请先在数据管理中上传 Excel。", plan)
        if plan.comparison == "mom" and plan.start_month != plan.end_month:
            return empty_result("clarification", "环比请指定一个月份，以便与上一个月比较。", plan)
        if plan.comparison != "none" and "month" in plan.group_by:
            return empty_result("clarification", "第一版的同比、环比支持一个时间区间的汇总比较，请去掉按月趋势或指定一个月份。", plan)
        selected_departments = [d for d in state["departments"] if (not plan.departments or d in plan.departments)
            and (not plan.department_types or state["department_map"][d] in plan.department_types)]
        if not selected_departments:
            return empty_result("no_data", "所选科室与科室类型没有交集。", plan)
        # Open a read transaction so every result and source in this answer uses one consistent version.
        with self.db.read_engine.connect() as con:
            con.exec_driver_sql("BEGIN")
            revision = self.db.revision(con)
            facts, source_stmt = self._facts(con, plan)
            if not facts:
                return empty_result("no_data", f"{plan.start_month} 至 {plan.end_month} 没有匹配数据。当前数据覆盖 {state['start_month']} 至 {state['end_month']}。", plan)
            problem = self._aggregation_check(plan, facts)
            if problem:
                return empty_result("clarification", problem, plan)
            expected = {(m, d) for m in months_between(plan.start_month, plan.end_month) for d in selected_departments}
            actual = {(r["month"], r["department"]) for r in facts}
            previous_rows, previous_facts, previous_stmt = [], [], None
            if plan.comparison != "none":
                offset = -12 if plan.comparison == "yoy" else -1
                previous_plan = plan.model_copy(update={"start_month": shift_month(plan.start_month, offset), "end_month": shift_month(plan.end_month, offset)})
                previous_facts, _ = self._facts(con, previous_plan)
                expected_before = {(shift_month(m, offset), d) for m, d in expected}
                actual_before = {(r["month"], r["department"]) for r in previous_facts}
                if actual != expected or actual_before != expected_before:
                    return empty_result("no_data", "比较区间的数据不完整，不能计算同比或环比。请使用双方都有完整数据的相同长度区间。", plan)
                problem = self._aggregation_check(previous_plan, previous_facts)
                if problem:
                    return empty_result("clarification", problem, plan)
                previous_rows, previous_stmt = self._aggregate(con, previous_plan, apply_filters=False)
            result_rows, stmt = self._aggregate(con, plan)
            warnings = []
            available_months = sorted({r["month"] for r in facts})
            if actual != expected:
                warnings.append(f"数据不完整：请求 {plan.start_month} 至 {plan.end_month}；实际包含 {available_months[0]} 至 {available_months[-1]}，缺少 {len(expected-actual)} 条科室月度记录。以下为已有数据汇总。")
            if not plan.time_explicit:
                warnings.append(f"未指定时间，使用最新有数据月份 {plan.start_month}。")
            metric_columns = [{"key": m, "label": BY_ID[m].label, "unit": "万元" if BY_ID[m].unit == "元" and plan.unit == "wan" else BY_ID[m].unit} for m in plan.metrics]
            dimensions = {"month": "年月", "department": "科室", "department_type": "科室类型"}
            columns = [{"key": key, "label": dimensions[key], "unit": ""} for key in plan.group_by] + metric_columns
            original_values = {tuple(row[k] for k in plan.group_by): {m: row[m] for m in plan.metrics} for row in result_rows}
            for row in result_rows:
                for metric in plan.metrics:
                    row[metric] = self._display(row[metric], metric, plan.unit)
            if plan.comparison != "none":
                previous_map = {tuple(r[k] for k in plan.group_by): r for r in previous_rows}
                for row in result_rows:
                    previous = previous_map.get(tuple(row[k] for k in plan.group_by))
                    for metric in plan.metrics:
                        value = self._display(previous[metric], metric, plan.unit) if previous else None
                        current = row[metric]
                        row[metric + "_previous"] = value
                        raw_current = original_values[tuple(row[k] for k in plan.group_by)][metric]
                        raw_previous = previous[metric] if previous else None
                        row[metric + "_change"] = self._display(Decimal(str(raw_current)) - Decimal(str(raw_previous)), metric, plan.unit) if raw_current is not None and raw_previous is not None else None
                        row[metric + "_growth"] = rounded((Decimal(str(raw_current)) - Decimal(str(raw_previous))) / Decimal(str(raw_previous)) * 100) if raw_current is not None and raw_previous not in (None, 0) else None
                for col in metric_columns:
                    columns.extend([{"key": col["key"] + "_previous", "label": col["label"] + "·对比期", "unit": col["unit"]},
                        {"key": col["key"] + "_change", "label": col["label"] + "·变化", "unit": "百分点" if col["unit"] == "%" else col["unit"]},
                        {"key": col["key"] + "_growth", "label": col["label"] + "·增长率", "unit": "%"}])
                if any(row.get(m + "_previous") == 0 for row in result_rows for m in plan.metrics):
                    warnings.append("对比期为零的指标无法计算增长率；已显示绝对变化。")
            # Sorting/limit are deterministic, applied after aggregation and before presentation.
            order_key = plan.order_by or ("month" if "month" in plan.group_by else (plan.group_by[0] if plan.group_by else plan.metrics[0]))
            reverse = plan.order == "desc" if plan.order_by else False
            present = [r for r in result_rows if r[order_key] is not None]
            nulls = [r for r in result_rows if r[order_key] is None]
            result_rows = sorted(present, key=lambda r: (r[order_key], tuple(str(r[k]) for k in plan.group_by)), reverse=reverse) + nulls
            total_groups = len(result_rows)
            result_rows = result_rows[:plan.limit]
            if total_groups > plan.limit:
                warnings.append(f"共 {total_groups} 组结果，当前展示前 {plan.limit} 组；来源仅列出展示结果对应的原始记录。")
            if not result_rows:
                return empty_result("no_data", "该范围有数据，但没有满足筛选条件的结果。", plan)
            displayed_groups = {tuple(r[k] for k in plan.group_by) for r in result_rows}
            sources = []
            for fact in facts + previous_facts:
                if tuple(fact[k] for k in plan.group_by) not in displayed_groups:
                    continue
                source = json.loads(fact["source_json"])
                fields = set(plan.metrics) | {"month", "department", "department_type"}
                if "insurance_ratio" in fields:
                    fields.update(["insurance_amount", "total_revenue"])
                source["cells"] = {field: source["columns"][field] + str(source["row"]) for field in sorted(fields)}
                source["values"] = {field: source["values"][field] for field in sorted(fields)}
                sources.append(source)
            scope = scope_description(plan, sorted({r["department"] for r in facts}))
            period = plan.start_month if plan.start_month == plan.end_month else f"{plan.start_month} 至 {plan.end_month}"
            answer = f"{period}，{scope}"
            if not plan.group_by:
                answer += "：" + "；".join(c["label"] + "为 " + format_value(result_rows[0][c["key"]], c["unit"]) for c in metric_columns) + "。"
            else:
                answer += f"，查询到 {total_groups} 组结果。"
                if plan.order_by in plan.metrics and result_rows:
                    label = "、".join(str(result_rows[0][k]) for k in plan.group_by)
                    col = next(c for c in metric_columns if c["key"] == plan.order_by)
                    answer += f"当前排序首项为 {label}，{col['label']} {format_value(result_rows[0][col['key']], col['unit'])}。"
            if plan.comparison != "none":
                answer += f" 对比期间：{previous_plan.start_month} 至 {previous_plan.end_month}（{'同比' if plan.comparison == 'yoy' else '环比'}）。"
            chart = self._chart(plan, result_rows, metric_columns)
            sql = [self._sql(stmt, "本期聚合"), self._sql(source_stmt, "本期来源")]
            if previous_stmt is not None:
                sql.append(self._sql(previous_stmt, "对比期聚合"))
            return {"status": "success", "answer": answer, "plan": plan.model_dump(mode="json"), "rows": result_rows,
                "columns": columns, "chart": chart, "sources": sources, "sql": sql, "warnings": warnings,
                "choices": [], "revision": revision, "scope": scope, "actual_months": available_months,
                "metric_notes": [BY_ID[m].description for m in plan.metrics], "total_groups": total_groups}

    def _facts(self, con, plan):
        table = self.db.facts
        stmt = select(table).where(table.c.month >= plan.start_month, table.c.month <= plan.end_month)
        if plan.departments:
            stmt = stmt.where(table.c.department.in_(plan.departments))
        if plan.department_types:
            stmt = stmt.where(table.c.department_type.in_(plan.department_types))
        stmt = stmt.order_by(table.c.month, table.c.department)
        return [dict(r) for r in con.execute(stmt).mappings()], stmt

    def _aggregation_check(self, plan, facts):
        groups = defaultdict(list)
        for row in facts:
            groups[tuple(row[k] for k in plan.group_by)].append(row)
        for metric in plan.metrics:
            definition = BY_ID[metric]
            if definition.aggregation == "raw" and any(len(g) > 1 for g in groups.values()):
                return f"{definition.label}只支持科室月度原值，不能直接跨记录平均。请指定一个科室和月份，或按科室、月份分别展示。"
            if definition.aggregation == "snapshot" and any(len({r['month'] for r in g}) > 1 for g in groups.values()):
                return "床位数不能跨月累加，请指定一个月份或按月分别展示。"
        return None

    def _aggregate(self, con, plan, apply_filters=True):
        table = self.db.facts
        expressions = {}
        for metric in plan.metrics:
            definition = BY_ID[metric]
            col = table.c[metric]
            if definition.aggregation in {"sum", "snapshot"}:
                expr = func.sum(col)
            elif definition.aggregation == "ratio":
                expr = case((func.count() == 1, func.max(col)), else_=cast(func.sum(table.c.insurance_amount), Float) * 100 / func.nullif(func.sum(table.c.total_revenue), 0))
            else:
                expr = func.max(col)
            expressions[metric] = expr
        stmt = select(*[table.c[k] for k in plan.group_by], *[e.label(m) for m, e in expressions.items()],
            func.count().label("_count"), func.sum(table.c.insurance_amount).label("_insurance"), func.sum(table.c.total_revenue).label("_total"))
        stmt = stmt.where(table.c.month >= plan.start_month, table.c.month <= plan.end_month)
        if plan.departments:
            stmt = stmt.where(table.c.department.in_(plan.departments))
        if plan.department_types:
            stmt = stmt.where(table.c.department_type.in_(plan.department_types))
        if plan.group_by:
            stmt = stmt.group_by(*[table.c[k] for k in plan.group_by])
        if apply_filters:
            for condition in plan.filters:
                value = condition.value * (100 if BY_ID[condition.metric].unit == "元" else 1)
                operand = expressions[condition.metric]
                comparisons = {"gt": operand > value, "gte": operand >= value, "lt": operand < value, "lte": operand <= value, "eq": operand == value}
                stmt = stmt.having(comparisons[condition.op])
        rows = []
        for result in con.execute(stmt).mappings():
            row = dict(result)
            if row["_count"] == 0:
                continue
            if "insurance_ratio" in row and row["_count"] > 1:
                row["insurance_ratio"] = (Decimal(row["_insurance"]) / Decimal(row["_total"]) * 100) if row["_total"] else None
            rows.append({k: v for k, v in row.items() if not k.startswith("_")})
        return rows, stmt

    def _display(self, value, metric, unit):
        if value is None:
            return None
        if BY_ID[metric].unit == "元":
            return rounded(Decimal(str(value)) / (1_000_000 if unit == "wan" else 100), 6 if unit == "wan" else 2)
        return rounded(value)

    def _sql(self, stmt, label):
        compiled = stmt.compile(self.db.read_engine, compile_kwargs={"render_postcompile": True})
        return {"label": label, "statement": str(compiled), "parameters": {k: str(v) if isinstance(v, Decimal) else v for k, v in compiled.params.items()}}

    def _chart(self, plan, rows, columns):
        if not plan.group_by:
            return None
        # Separate charts by metric unit in the frontend; no incomparable values on one axis.
        return {"type": "line" if "month" in plan.group_by else "bar", "dimensions": plan.group_by,
            "metrics": columns, "rows": rows}
