"""Run with: python -m eval.run [--mode demo|cloud] [--output docs/evaluation-demo.json]."""
import argparse
from collections import Counter
from dataclasses import replace
from datetime import date, datetime, timezone
import json
from pathlib import Path
import tempfile

from fastapi.testclient import TestClient

from backend.config import ROOT, Settings
from backend.main import create_app
from .cases import CASES
from .reference import check_case, reference_rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['demo', 'cloud'], default='demo')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    source = reference_rows(ROOT / '院管数据.xlsx')
    config = Settings.from_env()
    if args.mode == 'cloud' and not all([config.llm_base_url, config.llm_model, config.llm_api_key]):
        parser.error('云端评测需要在 .env 配置模型地址、名称和密钥；未执行真实模型评测。')
    results = []
    with tempfile.TemporaryDirectory(prefix='hospital-eval-') as temp:
        settings = replace(config, database_path=Path(temp) / 'eval.db', seed_excel=ROOT / '院管数据.xlsx', llm_mode=args.mode, today=date(2026, 9, 20))
        app = create_app(settings)
        with TestClient(app) as client:
            for case in CASES:
                response = client.post('/api/chat', json={'question': case['question']})
                result = response.json()
                issues = check_case(case, result, source)
                results.append({'id': case['id'], 'category': case['category'], 'question': case['question'], 'passed': not issues, 'issues': issues})
                print(f"{case['id']} {'PASS' if not issues else 'FAIL'} {case['question']}")
                for issue in issues:
                    print('  ' + issue)
    summary = {group: {'passed': sum(r['passed'] for r in results if r['category'] == group), 'total': sum(r['category'] == group for r in results)} for group in ['answerable', 'clarification', 'boundary']}
    report = {'mode': args.mode, 'model': config.llm_model if args.mode == 'cloud' else 'deterministic-demo',
        'temperature': 0, 'calendar_reference': '2026-09-20', 'executed_at': datetime.now(timezone.utc).isoformat(),
        'real_model_evaluated': args.mode == 'cloud', 'summary': summary, 'results': results}
    print(json.dumps(summary, ensure_ascii=False))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    raise SystemExit(0 if all(r['passed'] for r in results) else 1)


if __name__ == '__main__':
    main()

