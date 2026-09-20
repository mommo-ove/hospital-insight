from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

from sqlalchemy import (Column, Integer, Float, MetaData, String, Table, Text, UniqueConstraint, create_engine, event, select)

from .catalog import METRICS


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def encode(value):
    return json.dumps(value, ensure_ascii=False, default=str)


class Database:
    def __init__(self, path: Path):
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine("sqlite:///" + self.path.as_posix(), connect_args={"check_same_thread": False, "timeout": 15})
        self.meta = MetaData()
        self.facts = Table("department_monthly", self.meta,
            Column("id", Integer, primary_key=True),
            Column("sequence", Integer, nullable=False),
            Column("month", String, nullable=False),
            Column("department", String, nullable=False),
            Column("department_type", String, nullable=False),
            *[Column(m.id, Integer if m.unit in {"元", "张", "人次", "台次"} else Float, nullable=False) for m in METRICS],
            Column("source_json", Text, nullable=False),
            UniqueConstraint("month", "department"),
        )
        self.imports = Table("imports", self.meta,
            Column("id", String, primary_key=True), Column("filename", String), Column("created_at", String),
            Column("status", String), Column("base_revision", Integer), Column("payload_json", Text),
            Column("summary_json", Text), Column("revision", Integer),
        )
        self.state = Table("state", self.meta, Column("id", Integer, primary_key=True), Column("revision", Integer, nullable=False))
        self.conversations = Table("conversations", self.meta,
            Column("id", String, primary_key=True), Column("title", String), Column("created_at", String),
            Column("updated_at", String), Column("last_plan_json", Text), Column("pending_json", Text),
        )
        self.messages = Table("messages", self.meta,
            Column("id", String, primary_key=True), Column("conversation_id", String, index=True),
            Column("created_at", String), Column("question", Text), Column("response_json", Text),
        )
        @event.listens_for(self.engine, "connect")
        def pragma(connection, _):
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA busy_timeout=15000")
        self.meta.create_all(self.engine)
        with self.engine.begin() as con:
            if con.execute(select(self.state.c.id)).first() is None:
                con.execute(self.state.insert().values(id=1, revision=0))
        self.read_engine = create_engine("sqlite://", creator=self._readonly_connection)

    def _readonly_connection(self):
        con = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, check_same_thread=False)
        con.execute("PRAGMA query_only=ON")
        return con

    def revision(self, con):
        return con.execute(select(self.state.c.revision).where(self.state.c.id == 1)).scalar_one()

    def catalog_state(self):
        with self.read_engine.connect() as con:
            rows = con.execute(select(self.facts.c.month, self.facts.c.department, self.facts.c.department_type)).all()
            revision = self.revision(con)
        months = sorted({r.month for r in rows})
        departments = sorted({r.department for r in rows})
        types = sorted({r.department_type for r in rows})
        return {"row_count": len(rows), "months": months, "start_month": months[0] if months else None,
                "end_month": months[-1] if months else None, "departments": departments,
                "department_types": types, "revision": revision,
                "department_map": {r.department: r.department_type for r in rows}}

    @contextmanager
    def write(self):
        with self.engine.connect() as con:
            con.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                yield con
                con.commit()
            except Exception:
                con.rollback()
                raise

    def close(self):
        self.read_engine.dispose()
        self.engine.dispose()
