from __future__ import annotations

import json

import pytest

from fengge.verify import evaluate, load_queries, no_answer, top_k

DOCS = [[1.0, 0.0], [0.0, 1.0], [0.7, 0.7]]


def test_top_k_sorted_desc():
    got = top_k([1.0, 0.0], DOCS, k=2)
    assert [i for i, _ in got] == [0, 2]
    assert got[0][1] == pytest.approx(1.0)


def test_no_answer_uses_threshold():
    assert no_answer(0.55, 0.62) is True
    assert no_answer(0.70, 0.62) is False


def test_evaluate_counts_hits_and_edge_signals():
    queries = [
        {"query": "要不要读研", "has_answer": True},
        {"query": "怎么造火箭", "has_answer": False},
    ]
    records = [
        {"id": "a", "abstract_question": "要不要考研", "quality": 4},
        {"id": "b", "abstract_question": "怎么找对象", "quality": 3},
    ]
    vecs = {
        "要不要读研": [1.0, 0.0],
        "怎么造火箭": [0.0, 1.0],
        "要不要考研": [1.0, 0.0],
        "怎么找对象": [-0.9, 0.1],
    }
    res = evaluate(
        queries, records, embed=lambda ts: [vecs[t] for t in ts], threshold=0.9
    )
    assert res["answerable_hits"] == 1
    assert res["edge_no_answer"] == 1
    assert res["passed"] is True


def test_load_queries_reads_json_fence(tmp_path):
    body = [{"query": "要不要读研", "has_answer": True}]
    md = tmp_path / "q.md"
    md.write_text(
        "# 题库\n\n```json\n" + json.dumps(body, ensure_ascii=False) + "\n```\n",
        encoding="utf-8",
    )
    assert load_queries(md) == body


def test_load_queries_rejects_file_without_fence(tmp_path):
    md = tmp_path / "q.md"
    md.write_text("没有代码块", encoding="utf-8")
    with pytest.raises(ValueError):
        load_queries(md)
