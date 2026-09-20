"""Independent reference calculations directly from the source workbook; no query-engine imports."""
from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

import openpyxl

FIELDS = ["sequence", "month", "department", "department_type", "outpatient_revenue", "inpatient_revenue", "surgery_revenue", "examination_revenue", "drug_revenue", "consumable_revenue", "other_revenue", "total_revenue", "insurance_amount", "self_pay_amount", "insurance_ratio", "beds", "bed_occupancy", "average_stay", "average_cost", "outpatient_visits", "discharges", "surgeries"]
MONEY = set(FIELDS[4:14]) | {"average_cost"}
RAW = {"bed_occupancy", "average_stay", "average_cost"}


def reference_rows(path):
    book = openpyxl.load_workbook(path, data_only=True)
    rows = []
    for values in list(book.active.values)[1:]:
        row = dict(zip(FIELDS, values, strict=True))
        row["month"] = row["month"].strftime("%Y-%m")
        rows.append(row)
    book.close()
    return rows


def calculate(rows, plan):
    selected = [r for r in rows if plan['start_month'] <= r['month'] <= plan['end_month']
                and (not plan['departments'] or r['department'] in plan['departments'])
                and (not plan['department_types'] or r['department_type'] in plan['department_types'])]
    groups = defaultdict(list)
    dims = plan['group_by']
    for row in selected:
        groups[tuple(row[d] for d in dims)].append(row)
    results = []
    for key, records in groups.items():
        result = dict(zip(dims, key, strict=True))
        for metric in plan['metrics']:
            if metric == 'insurance_ratio':
                value = Decimal(str(records[0][metric])) if len(records) == 1 else Decimal(sum(r['insurance_amount'] for r in records)) / Decimal(sum(r['total_revenue'] for r in records)) * 100
            elif metric in RAW:
                assert len(records) == 1
                value = Decimal(str(records[0][metric]))
            else:
                value = sum(Decimal(str(r[metric])) for r in records)
            result[metric] = value
        if any(not {"gt": result[f['metric']] > Decimal(f['value']), "gte": result[f['metric']] >= Decimal(f['value']),
                    "lt": result[f['metric']] < Decimal(f['value']), "lte": result[f['metric']] <= Decimal(f['value']),
                    "eq": result[f['metric']] == Decimal(f['value'])}[f['op']] for f in plan.get('filters', [])):
            continue
        results.append(result)
    if plan.get('comparison', 'none') != 'none':
        offset = -12 if plan['comparison'] == 'yoy' else -1
        def shift(month):
            y, m = map(int, month.split('-'))
            ordinal = y * 12 + m - 1 + offset
            return f'{ordinal//12:04d}-{ordinal%12+1:02d}'
        before = calculate(rows, {**plan, 'start_month': shift(plan['start_month']), 'end_month': shift(plan['end_month']), 'comparison': 'none', 'unit': 'yuan', 'filters': []})
        mapped = {tuple(r[d] for d in dims): r for r in before}
        for result in results:
            previous = mapped[tuple(result[d] for d in dims)]
            for metric in plan['metrics']:
                pv = Decimal(str(previous[metric]))
                result[metric + '_previous'] = pv
                result[metric + '_change'] = result[metric] - pv
                result[metric + '_growth'] = (result[metric] - pv) / pv * 100 if pv else None
    for result in results:
        for key, value in result.items():
            if key in dims or value is None:
                continue
            divisor = Decimal(10000) if plan.get('unit') == 'wan' and (key in MONEY or key.removesuffix('_previous').removesuffix('_change') in MONEY) else Decimal(1)
            precision = Decimal('0.000001') if divisor == 10000 else Decimal('0.01')
            result[key] = float((value / divisor).quantize(precision, rounding=ROUND_HALF_UP))
    sort_key = plan.get('order_by') or ('month' if 'month' in dims else dims[0] if dims else plan['metrics'][0])
    reverse = plan.get('order', 'desc') == 'desc' if plan.get('order_by') else False
    return sorted(results, key=lambda r: (r[sort_key], tuple(str(r[d]) for d in dims)), reverse=reverse)[:plan.get('limit', 100)]


def check_case(case, result, source):
    errors = []
    if result['status'] != case['status']:
        return [f"status: expected {case['status']}, got {result['status']}"]
    if case['status'] != 'success':
        if result['rows'] or result['sql']:
            errors.append('Non-answerable question executed a query')
        return errors
    expected = case['expected_plan']
    actual = result['plan']
    for key, value in expected.items():
        if key in {'departments', 'department_types', 'group_by', 'metrics'}:
            equal = set(actual[key]) == set(value)
        elif key == 'filters':
            equal = len(actual[key]) == len(value) and all(a['metric'] == b['metric'] and a['op'] == b['op'] and Decimal(a['value']) == Decimal(b['value']) for a, b in zip(actual[key], value))
        else:
            equal = actual.get(key) == value
        if not equal:
            errors.append(f"plan.{key}: expected {value}, got {actual.get(key)}")
    expected_rows = calculate(source, expected)
    # JSON/dict key order is not a correctness criterion.
    if result['rows'] != expected_rows:
        errors.append(f"Results differ: expected {expected_rows[:2]}, got {result['rows'][:2]}")
    if not result['sources']:
        errors.append('Missing provenance')
    return errors
