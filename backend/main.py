from contextlib import asynccontextmanager
import csv
from io import StringIO
import json
import logging
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from .catalog import DEPARTMENT_ALIASES, metric_catalog
from .config import ROOT, Settings
from .db import Database
from .importer import ImportProblem, commit_import, import_history, preview_import
from .schemas import ChatRequest, ImportCommit
from .service import ChatService, ConversationMissing

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None):
    settings = settings or Settings.from_env()
    db = Database(settings.database_path)
    service = ChatService(db, settings)

    @asynccontextmanager
    async def lifespan(app):
        if not db.catalog_state()["row_count"] and settings.seed_excel and settings.seed_excel.exists():
            preview = preview_import(db, settings.seed_excel.read_bytes(), settings.seed_excel.name)
            if preview["can_commit"]:
                commit_import(db, preview["id"], False)
            else:
                logger.warning("初始工作簿校验未通过，请在数据管理中查看错误")
        yield
        db.close()

    app = FastAPI(title="院数 · 科室经营数据助手", version="1.0.0", lifespan=lifespan)
    app.state.db, app.state.settings, app.state.service = db, settings, service
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_methods=["GET", "POST"], allow_headers=["Content-Type"])

    @app.middleware("http")
    async def local_request_boundary(request: Request, call_next):
        # Protect the local, unauthenticated demo from cross-site write requests.
        if request.method == "POST":
            origin = request.headers.get("origin")
            allowed = {"http://localhost:5173", "http://127.0.0.1:5173", str(request.base_url).rstrip("/")}
            if origin and origin not in allowed:
                return JSONResponse({"detail": "不接受跨站写请求"}, status_code=403)
        return await call_next(request)

    @app.exception_handler(ImportProblem)
    async def import_error(_, exc):
        return JSONResponse({"detail": str(exc)}, status_code=exc.status)

    @app.exception_handler(ConversationMissing)
    async def conversation_error(_, exc):
        return JSONResponse({"detail": "会话不存在"}, status_code=404)

    @app.get("/api/health")
    def health():
        return {"status": "ok", "mode": settings.llm_mode, "model": settings.llm_model if settings.llm_mode == "cloud" else "规则演示解析器",
                "model_configured": settings.llm_mode == "demo" or bool(settings.llm_base_url and settings.llm_model and settings.llm_api_key)}

    @app.get("/api/catalog")
    def catalog():
        return {**db.catalog_state(), "metrics": metric_catalog(), "aliases": DEPARTMENT_ALIASES, "mode": settings.llm_mode}

    @app.post("/api/imports/preview")
    async def preview(file: UploadFile = File(...)):
        content = await file.read(10 * 1024 * 1024 + 1)
        await file.close()
        return preview_import(db, content, file.filename or "upload.xlsx")

    @app.post("/api/imports/{identifier}/commit")
    def commit(identifier: str, payload: ImportCommit):
        return commit_import(db, identifier, payload.overwrite_conflicts)

    @app.get("/api/imports")
    def imports():
        return import_history(db)

    @app.post("/api/chat")
    async def chat(payload: ChatRequest):
        return await service.chat(payload.question, payload.conversation_id)

    @app.get("/api/conversations")
    def conversations():
        return service.conversations()

    @app.get("/api/conversations/{identifier}")
    def conversation(identifier: str):
        return service.conversation(identifier)

    @app.get("/api/queries/{identifier}/export")
    def export(identifier: str):
        with db.read_engine.connect() as con:
            message = con.execute(select(db.messages.c.response_json).where(db.messages.c.id == identifier)).scalar_one_or_none()
        if not message:
            raise HTTPException(404, "查询不存在")
        result = json.loads(message)
        if result["status"] != "success":
            raise HTTPException(409, "该查询没有可导出的结果")
        buffer = StringIO(newline="")
        writer = csv.writer(buffer)
        cols = result["columns"]
        writer.writerow([c["label"] + (f"({c['unit']})" if c["unit"] else "") for c in cols])
        for row in result["rows"]:
            values = []
            for col in cols:
                value = row.get(col["key"])
                if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
                    value = "'" + value
                values.append("不可计算" if value is None else value)
            writer.writerow(values)
        return Response(content="\ufeff" + buffer.getvalue(), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="hospital-query-{identifier}.csv"'})

    dist = ROOT / "frontend" / "dist"
    if dist.exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/")
        def index():
            return FileResponse(dist / "index.html")
    else:
        @app.get("/")
        def development_index():
            return {"message": "前端尚未构建。运行 .\\start.ps1，或在 frontend 中执行 npm run dev。", "api_docs": "/docs"}
    return app


app = create_app()
