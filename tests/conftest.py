from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from backend.config import Settings
from backend.main import create_app

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def client(tmp_path):
    settings = Settings(database_path=tmp_path / "hospital.db", seed_excel=ROOT / "院管数据.xlsx", today=date(2026, 9, 20))
    app = create_app(settings)
    with TestClient(app) as client:
        yield client


@pytest.fixture
def db(client):
    return client.app.state.db

