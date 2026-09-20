from decimal import Decimal
import json

import openpyxl
import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from backend.query import QueryEngine
from backend.schemas import QueryPlan
from backend.importer import preview_import, commit_import
from .test_data import workbook_bytes
from .conftest import ROOT


def plan(**kwargs):
    return QueryPlan(start_month="2025-01", end_month="2025-12", time_explicit=True, **kwargs)


def test_totals_and_provenance(db):
    result = QueryEngine(db).execute(plan(departments=["心血管内科"]))
    assert result["rows"] == [{"total_revenue": 25979271.0}]
    assert len(result["sources"]) == 12
    assert all(s["version"] == 1 and s["file"] == "院管数据.xlsx" for s in result["sources"])
    assert result["sources"][0]["cells"]["total_revenue"] == "L98"
    assert "?" in result["sql"][0]["statement"]
    assert "2025-01" in result["sql"][0]["parameters"].values()


def test_ratio_is_weighted_not_mean_of_percentages(db):
    workbook = openpyxl.load_workbook(ROOT / "院管数据.xlsx", data_only=True)
    selected = [r for r in list(workbook.active.values)[1:] if r[1].year == 2025 and r[3] == "内科"]
    expected = round(Decimal(sum(r[12] for r in selected)) / Decimal(sum(r[11] for r in selected)) * 100, 2)
    result = QueryEngine(db).execute(plan(metrics=["insurance_ratio"], department_types=["内科"]))
    assert Decimal(str(result["rows"][0]["insurance_ratio"])) == expected
    workbook.close()


@pytest.mark.parametrize("metric", ["bed_occupancy", "average_stay", "average_cost", "beds"])
def test_nonadditive_across_months_requires_clarification(db, metric):
    result = QueryEngine(db).execute(plan(metrics=[metric], departments=["心血管内科"]))
    assert result["status"] == "clarification"


def test_raw_monthly_trend_and_same_month_beds(db):
    result = QueryEngine(db).execute(plan(metrics=["average_cost"], departments=["心血管内科"], group_by=["month"]))
    assert len(result["rows"]) == 12
    assert result["chart"]["type"] == "line"
    result = QueryEngine(db).execute(QueryPlan(start_month="2026-04", end_month="2026-04", metrics=["beds"]))
    assert result["rows"][0]["beds"] == 345


def test_ranking_filters_units_and_source_scope(db):
    result = QueryEngine(db).execute(QueryPlan(start_month="2026-04", end_month="2026-04", group_by=["department"], order_by="total_revenue", limit=3, unit="wan"))
    assert len(result["rows"]) == len(result["sources"]) == 3
    assert result["rows"][0]["department"] == "神经内科"
    assert result["rows"][0]["total_revenue"] == 214.1617
    assert result["columns"][1]["unit"] == "万元"
    result = QueryEngine(db).execute(QueryPlan(start_month="2026-04", end_month="2026-04", group_by=["department"], filters=[{"metric": "total_revenue", "op": "gt", "value": 2000000}]))
    assert len(result["rows"]) >= 1
    assert all(r["total_revenue"] > 2000000 for r in result["rows"])


def test_yoy_and_missing_period(db):
    result = QueryEngine(db).execute(plan(departments=["心血管内科"], comparison="yoy"))
    assert result["status"] == "success"
    row = result["rows"][0]
    assert row["total_revenue_change"] == round(row["total_revenue"] - row["total_revenue_previous"], 2)
    assert row["total_revenue_growth"] == round(row["total_revenue_change"] / row["total_revenue_previous"] * 100, 2)
    incomplete = QueryEngine(db).execute(QueryPlan(start_month="2026-01", end_month="2026-12", comparison="yoy"))
    assert incomplete["status"] == "no_data"
    assert "不完整" in incomplete["answer"]


def test_partial_year_is_labelled(db):
    result = QueryEngine(db).execute(QueryPlan(start_month="2026-01", end_month="2026-12"))
    assert result["status"] == "success"
    assert result["actual_months"] == ["2026-01", "2026-02", "2026-03", "2026-04"]
    assert any("数据不完整" in w for w in result["warnings"])


def test_zero_denominator_no_fabricated_growth_or_ratio(db):
    with db.write() as con:
        updates = {m: 0 for m in ["outpatient_revenue", "inpatient_revenue", "surgery_revenue", "examination_revenue", "drug_revenue", "consumable_revenue", "other_revenue", "total_revenue", "insurance_amount", "self_pay_amount"]}
        con.execute(db.facts.update().where(db.facts.c.month == "2024-01").values(**updates))
    result = QueryEngine(db).execute(QueryPlan(start_month="2025-01", end_month="2025-01", comparison="yoy"))
    assert result["rows"][0]["total_revenue_growth"] is None
    ratio = QueryEngine(db).execute(QueryPlan(start_month="2024-01", end_month="2024-01", metrics=["insurance_ratio"]))
    assert ratio["rows"][0]["insurance_ratio"] is None


def test_unknown_and_injection_cannot_query_arbitrary_data(db):
    result = QueryEngine(db).execute(plan(departments=["x' OR 1=1 --"]))
    assert result["status"] == "no_data"
    with pytest.raises(ValidationError):
        plan(metrics=["sqlite_master"])
    with pytest.raises(ValidationError):
        plan(sql="DROP TABLE department_monthly")
    with db.read_engine.connect() as con:
        with pytest.raises(OperationalError):
            con.exec_driver_sql("DELETE FROM department_monthly")


def test_historical_answers_keep_original_sources_after_import(client, db):
    result = client.post('/api/chat', json={'question': '2024年1月心内科总收入'}).json()
    before = result["rows"][0]["total_revenue"]
    def change(sheet):
        for col in [5, 12, 14]:
            sheet.cell(2, col).value += 100
    preview = preview_import(db, workbook_bytes(change), "update.xlsx")
    commit_import(db, preview["id"], True)
    old = client.get('/api/conversations/' + result['conversation_id']).json()['messages'][0]
    assert old['rows'][0]['total_revenue'] == before
    assert old['sources'][0]['version'] == 1
    fresh = client.post('/api/chat', json={'question': '2024年1月心内科总收入'}).json()
    assert fresh['rows'][0]['total_revenue'] == before + 100
    assert fresh['sources'][0]['version'] == 2

