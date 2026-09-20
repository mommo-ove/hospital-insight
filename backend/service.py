from datetime import date
import json
import re
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from .catalog import BY_ID
from .config import Settings
from .db import Database, encode, utcnow
from .llm import ModelError, cloud_parse
from .parser import demo_parse, guard_question
from .query import QueryEngine, empty_result
from .schemas import QueryPlan


class ConversationMissing(Exception):
    pass


class ChatService:
    def __init__(self, db: Database, settings: Settings):
        self.db, self.settings = db, settings
        self.engine = QueryEngine(db)

    async def chat(self, question: str, conversation_id: str | None):
        now = utcnow()
        if conversation_id:
            with self.db.read_engine.connect() as con:
                conversation = con.execute(select(self.db.conversations).where(self.db.conversations.c.id == conversation_id)).mappings().first()
            if not conversation:
                raise ConversationMissing()
        else:
            conversation_id = uuid4().hex
            conversation = {"last_plan_json": None, "pending_json": None}
            with self.db.write() as con:
                con.execute(self.db.conversations.insert().values(id=conversation_id, title=question[:60], created_at=now, updated_at=now))
        previous = QueryPlan.model_validate_json(conversation["last_plan_json"]) if conversation["last_plan_json"] else None
        pending = json.loads(conversation["pending_json"]) if conversation["pending_json"] else None
        effective = question
        # A fully specified new question should not inherit an unfinished clarification.
        independent = bool(re.search(r"20\d{2}|今年|去年|上个月", question) and any(m.label in question or any(a in question for a in m.aliases) for m in BY_ID.values()))
        if pending and not independent:
            if pending.get("plan"):
                previous = QueryPlan.model_validate(pending["plan"])
                effective = "改成：" + question
            else:
                effective = pending["question"] + "；补充条件：" + question
        today = self.settings.today or date.today()
        catalog = self.db.catalog_state()
        decision = guard_question(effective)
        result = None
        try:
            if not catalog["row_count"]:
                result = empty_result("no_data", "尚未导入数据，请先在数据管理中上传 Excel。")
            elif decision is None:
                if self.settings.llm_mode == "cloud":
                    decision = await cloud_parse(self.settings, effective, catalog, today, previous)
                else:
                    decision = demo_parse(effective, catalog, today, previous)
            if result is None:
                if decision.status == "query":
                    result = self.engine.execute(decision.plan)
                else:
                    result = empty_result(decision.status, decision.message, decision.plan, decision.choices)
        except ModelError as exc:
            result = empty_result("error", str(exc))
        except (SQLAlchemyError, ArithmeticError):
            result = empty_result("error", "本地查询未能完成，可能存在超出计算范围的数据。问题已保留，请检查导入数据后重试。")
        query_id = uuid4().hex
        result.update(id=query_id, conversation_id=conversation_id, question=question, created_at=now,
                      mode=self.settings.llm_mode, model=self.settings.llm_model if self.settings.llm_mode == "cloud" else "规则演示解析器")
        values = {"updated_at": utcnow()}
        if result["status"] == "success":
            values["last_plan_json"] = encode(result["plan"])
            values["pending_json"] = None
        elif result["status"] == "clarification":
            values["pending_json"] = encode({"question": effective[-4000:], "plan": result.get("plan")})
        elif result["status"] != "error":
            values["pending_json"] = None
        with self.db.write() as con:
            con.execute(self.db.messages.insert().values(id=query_id, conversation_id=conversation_id, created_at=now, question=question, response_json=encode(result)))
            con.execute(self.db.conversations.update().where(self.db.conversations.c.id == conversation_id).values(**values))
        return result

    def conversations(self):
        with self.db.read_engine.connect() as con:
            return [dict(r) for r in con.execute(select(self.db.conversations.c.id, self.db.conversations.c.title,
                self.db.conversations.c.created_at, self.db.conversations.c.updated_at).order_by(self.db.conversations.c.updated_at.desc()).limit(100)).mappings()]

    def conversation(self, identifier):
        with self.db.read_engine.connect() as con:
            conv = con.execute(select(self.db.conversations).where(self.db.conversations.c.id == identifier)).mappings().first()
            if not conv:
                raise ConversationMissing()
            rows = con.execute(select(self.db.messages.c.response_json).where(self.db.messages.c.conversation_id == identifier).order_by(self.db.messages.c.created_at, self.db.messages.c.id)).all()
        return {"id": identifier, "title": conv["title"], "messages": [json.loads(row[0]) for row in rows]}
