import pytest

from eval.cases import CASES
from eval.reference import check_case, reference_rows
from .conftest import ROOT


@pytest.fixture(scope='module')
def golden_source():
    return reference_rows(ROOT / '院管数据.xlsx')


@pytest.mark.parametrize('case', CASES, ids=[c['id'] for c in CASES])
def test_fixed_question_against_independent_excel_calculation(client, golden_source, case):
    result = client.post('/api/chat', json={'question': case['question']}).json()
    assert not (issues := check_case(case, result, golden_source)), issues
