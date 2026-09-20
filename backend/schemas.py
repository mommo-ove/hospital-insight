from decimal import Decimal
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .catalog import BY_ID


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MetricFilter(StrictModel):
    metric: str
    op: Literal["gt", "gte", "lt", "lte", "eq"]
    value: Decimal = Field(ge=-1_000_000_000_000, le=1_000_000_000_000)

    @field_validator("metric")
    @classmethod
    def known_metric(cls, v):
        if v not in BY_ID:
            raise ValueError("未知指标")
        return v


class QueryPlan(StrictModel):
    metrics: list[str] = Field(default_factory=lambda: ["total_revenue"], min_length=1, max_length=5)
    departments: list[str] = Field(default_factory=list, max_length=30)
    department_types: list[str] = Field(default_factory=list, max_length=20)
    start_month: str
    end_month: str
    group_by: list[Literal["month", "department", "department_type"]] = Field(default_factory=list, max_length=3)
    filters: list[MetricFilter] = Field(default_factory=list, max_length=5)
    order_by: str | None = None
    order: Literal["asc", "desc"] = "desc"
    limit: int = Field(default=100, ge=1, le=100)
    comparison: Literal["none", "yoy", "mom"] = "none"
    unit: Literal["yuan", "wan"] = "yuan"
    time_explicit: bool = False

    @field_validator("metrics")
    @classmethod
    def known_metrics(cls, v):
        if any(m not in BY_ID for m in v) or len(v) != len(set(v)):
            raise ValueError("指标未知或重复")
        return v

    @field_validator("start_month", "end_month")
    @classmethod
    def valid_month(cls, v):
        if len(v) != 7 or datetime.strptime(v, "%Y-%m").strftime("%Y-%m") != v:
            raise ValueError("月份须为 YYYY-MM")
        return v

    @model_validator(mode="after")
    def coherent(self):
        if self.start_month > self.end_month:
            raise ValueError("起始月份不能晚于结束月份")
        if (int(self.end_month[:4]) - int(self.start_month[:4])) > 20:
            raise ValueError("查询时间跨度不能超过20年")
        if self.order_by and self.order_by not in self.metrics + self.group_by:
            raise ValueError("排序字段必须在结果字段内")
        if len(set(self.group_by)) != len(self.group_by):
            raise ValueError("分组字段不能重复")
        if any(f.metric not in self.metrics for f in self.filters):
            raise ValueError("筛选指标必须在查询指标内")
        return self


class Decision(StrictModel):
    status: Literal["query", "clarification", "unsupported"]
    plan: QueryPlan | None = None
    message: str = Field(default="", max_length=1000)
    choices: list[str] = Field(default_factory=list, max_length=6)

    @model_validator(mode="after")
    def query_has_plan(self):
        if self.status == "query" and self.plan is None:
            raise ValueError("查询必须包含 plan")
        if self.status != "query" and not self.message:
            raise ValueError("澄清或不支持必须有解释")
        return self


class ChatRequest(StrictModel):
    question: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = Field(default=None, max_length=64)

    @field_validator("question")
    @classmethod
    def nonblank(cls, v):
        if not v.strip():
            raise ValueError("请输入问题")
        return v.strip()


class ImportCommit(StrictModel):
    overwrite_conflicts: bool = False

