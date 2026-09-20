from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Metric:
    id: str
    label: str
    unit: str
    aggregation: str
    description: str
    aliases: tuple[str, ...] = ()


METRICS = [
    Metric("outpatient_revenue", "门诊收入", "元", "sum", "表内门诊收入，可跨月与科室求和。", ("门诊收入",)),
    Metric("inpatient_revenue", "住院收入", "元", "sum", "表内住院收入，可跨月与科室求和。", ("住院收入",)),
    Metric("surgery_revenue", "手术收入", "元", "sum", "表内手术收入，不代表单次手术价格。", ("手术收入",)),
    Metric("examination_revenue", "检查检验收入", "元", "sum", "检查与检验收入合计，不包含项目单价。", ("检查检验收入", "检查收入", "检验收入")),
    Metric("drug_revenue", "药品收入", "元", "sum", "药品收入合计。", ("药品收入", "药费收入")),
    Metric("consumable_revenue", "耗材收入", "元", "sum", "耗材收入合计。", ("耗材收入",)),
    Metric("other_revenue", "其他收入", "元", "sum", "其他收入合计。", ("其他收入",)),
    Metric("total_revenue", "合计收入", "元", "sum", "使用表内合计收入，不能再叠加七项收入分项。", ("合计收入", "总收入", "总营收", "营收")),
    Metric("insurance_amount", "医保结算金额", "元", "sum", "医保结算金额合计。", ("医保结算金额", "医保金额", "医保结算", "医保收入")),
    Metric("self_pay_amount", "自费金额", "元", "sum", "表内自费金额合计，不代表某个患者的账单。", ("自费金额", "自费收入", "自费")),
    Metric("insurance_ratio", "医保占比", "%", "ratio", "单行保留原值；汇总按医保结算金额之和÷合计收入之和×100计算。", ("医保占比", "医保比例")),
    Metric("beds", "床位数", "张", "snapshot", "允许同月跨科室求和；不允许跨月累加。", ("床位数", "多少张床", "床位数量")),
    Metric("bed_occupancy", "床位使用率", "%", "raw", "仅展示科室月度原值、趋势和同月比较，不推导综合平均值。", ("床位使用率", "床位利用率")),
    Metric("average_stay", "平均住院天数", "天", "raw", "仅展示科室月度原值，不推导跨记录平均值。", ("平均住院天数", "平均住院日", "平均住院时间")),
    Metric("average_cost", "次均费用", "元", "raw", "仅展示表内科室月度原值。业务定义待确认，不等同于患者平均住院账单。", ("次均费用",)),
    Metric("outpatient_visits", "门诊人次", "人次", "sum", "统计就诊人次，不等同于去重患者人数。", ("门诊人次", "门诊量")),
    Metric("discharges", "出院人次", "人次", "sum", "出院人次合计。", ("出院人次", "出院人数", "出院量")),
    Metric("surgeries", "手术台次", "台次", "sum", "手术台次合计。", ("手术台次", "手术量", "手术数量")),
]
BY_ID = {m.id: m for m in METRICS}
HEADERS = {"序号": "sequence", "年月": "month", "科室名称": "department", "科室类型": "department_type"}
for metric in METRICS:
    suffix = f"({metric.unit})" if metric.unit in {"元", "%"} else ""
    HEADERS[metric.label + suffix] = metric.id

DEPARTMENT_ALIASES = {"心内科": "心血管内科", "心内": "心血管内科", "普外科": "普通外科", "普外": "普通外科", "泌尿科": "泌尿外科", "神内": "神经内科", "呼吸科": "呼吸内科", "消化科": "消化内科"}


def metric_catalog():
    return [asdict(m) for m in METRICS]

