"""Dedicated demo server with an isolated temporary database for browser tests."""
from datetime import date
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import uvicorn
from backend.config import Settings
from backend.main import create_app

if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='hospital-browser-') as temp:
        config = Settings(database_path=Path(temp) / 'browser.db', seed_excel=ROOT / '院管数据.xlsx', today=date(2026, 9, 20))
        uvicorn.run(create_app(config), host='127.0.0.1', port=8765)

