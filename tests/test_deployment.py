from fastapi.testclient import TestClient
from backend.config import Settings
from backend.main import create_app


def test_fresh_clone_without_seed_can_start_and_accept_upload(tmp_path):
    import openpyxl
    from io import BytesIO
    from backend.catalog import HEADERS

    app = create_app(Settings(database_path=tmp_path / 'new.db', seed_excel=None))
    with TestClient(app) as client:
        assert client.get('/api/health').json()['status'] == 'ok'
        assert client.get('/api/catalog').json()['row_count'] == 0
        assert client.post('/api/chat', json={'question': '收入'}).json()['status'] == 'no_data'
        book = openpyxl.Workbook()
        book.active.append(list(HEADERS))
        book.active.append([1, '2026-04', '演示科室', '内科', 100, 200, 0, 0, 0, 0, 0, 300, 200, 100, 66.7, 10, 80, 5, 30, 20, 10, 0])
        stream = BytesIO()
        book.save(stream)
        preview = client.post('/api/imports/preview', files={'file': ('demo.xlsx', stream.getvalue())}).json()
        assert preview['can_commit']
        assert client.post('/api/imports/' + preview['id'] + '/commit', json={}).status_code == 200
        assert client.get('/api/catalog').json()['row_count'] == 1
