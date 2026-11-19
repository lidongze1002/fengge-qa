from __future__ import annotations

import pytest

from fengge.server import Index, create_app, index_text


def rec(id_, question, answer="看专业", tags=None, verbatim=None):
    return {
        "id": id_,
        "abstract_question": question,
        "question_verbatim": verbatim or question,
        "answer_summary": answer,
        "quote": "先看专业",
        "key_claims": [],
        "question_type": "学历与教育",
        "tags": tags or [],
        "title": "t",
        "source_bvid": "BV1",
        "source_url": "https://www.bilibili.com/video/BV1",
        "trim": {"start": 1.0, "end": 9.0},
        "transcript": "正文",
    }


def fake_embed(texts):
    out = []
    for t in texts:
        if "读研" in t or "考研" in t:
            out.append([1.0, 0.0])
        elif "对象" in t:
            out.append([0.0, 1.0])
        else:
            out.append([0.5, 0.5])
    return out


def make_index(threshold=0.62):
    records = [rec("a", "要不要继续读研"), rec("b", "怎么找对象")]
    return Index.build(records, fake_embed, threshold)


def test_index_text_includes_question_and_tags():
    text = index_text(rec("a", "要不要继续读研", tags=["考研", "选择"]))
    assert "要不要继续读研" in text and "考研" in text


def test_search_ranks_related_first():
    idx = make_index()
    hits = idx.search("考研还是工作", k=2)
    assert hits[0].record["id"] == "a"
    assert hits[0].score > hits[1].score


def test_answer_marks_found_above_threshold():
    data = make_index().answer("考研还是工作")
    assert data["found"] is True
    assert data["best"]["id"] == "a"
    assert data["best"]["clip_url"].endswith("BV1.mp4")
    assert data["best"]["trim"] == {"start": 1.0, "end": 9.0}


def test_answer_rejects_below_threshold():
    data = make_index(threshold=0.99).answer("完全无关的问题")
    assert data["found"] is False
    assert data["results"]


def test_answer_rejects_empty_question():
    with pytest.raises(ValueError):
        make_index().answer("   ")


def test_answer_uses_abstracted_query():
    idx = make_index()
    idx.abstractor = lambda q: "要不要继续读研"
    idx.embed = fake_embed
    data = idx.answer("我在深圳送外卖还有救吗")
    assert data["abstracted"] == "要不要继续读研"
    assert data["best"]["id"] == "a"


def test_rerank_can_accept_below_threshold():
    idx = make_index(threshold=0.99)
    idx.reranker = lambda q, hits: {"id": "b", "verdict": "answers", "reason": "答了"}
    data = idx.answer("考研还是工作")
    assert data["found"] is True
    assert data["best"]["id"] == "b"


def test_rerank_no_blocks_even_high_score():
    idx = make_index()
    idx.reranker = lambda q, hits: {"id": "", "verdict": "no", "reason": "答非所问"}
    data = idx.answer("考研还是工作")
    assert data["found"] is False


def test_rerank_failure_falls_back_to_vector_score():
    idx = make_index()
    idx.reranker = lambda q, hits: None
    assert idx.answer("考研还是工作")["found"] is True


def test_api_ask_returns_payload(monkeypatch):
    from fastapi.testclient import TestClient

    app = create_app(index=make_index())
    client = TestClient(app)
    resp = client.post("/api/ask", json={"question": "考研还是工作"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["found"] is True
    assert body["best"]["answer"] == "看专业"


def test_api_ask_rejects_blank(monkeypatch):
    from fastapi.testclient import TestClient

    app = create_app(index=make_index())
    resp = TestClient(app).post("/api/ask", json={"question": ""})
    assert resp.status_code == 400


def test_api_health_reports_records(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from fengge.config import load_settings

    settings = load_settings(root=tmp_path, env={})
    app = create_app(index=make_index(), settings=settings)
    body = TestClient(app).get("/api/health").json()
    assert body["records"] == 2
    assert body["threshold"] == pytest.approx(0.62)


def test_topics_groups_and_orders_by_count():
    records = [
        rec("a", "q1"),
        {**rec("b", "q2"), "question_type": "职业发展"},
        {**rec("c", "q3"), "question_type": "职业发展"},
    ]
    idx = Index.build(records, fake_embed)
    topics = idx.topics()
    assert topics[0]["type"] == "职业发展"
    assert topics[0]["count"] == 2
    assert topics[1]["type"] == "学历与教育"


def test_topic_items_filters_and_paginates():
    records = [
        {**rec("a", "q1"), "question_type": "职业发展", "quality": 3},
        {**rec("b", "q2"), "question_type": "职业发展", "quality": 5},
        {**rec("c", "q3"), "question_type": "情感两性", "quality": 4},
    ]
    idx = Index.build(records, fake_embed)
    page = idx.topic_items("职业发展", limit=1, offset=0)
    assert page["total"] == 2
    assert page["items"][0]["id"] == "b"
    assert page["items"][0]["clip_url"].endswith("BV1.mp4")


class _Reply:
    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


class _ReplySession:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def get(self, url, params=None, timeout=None):
        self.calls += 1
        return _Reply(self.payload)


def test_fetch_comments_maps_and_sorts():
    from fengge.server import fetch_comments

    payload = {
        "code": 0,
        "data": {
            "replies": [
                {"member": {"uname": "b友A"}, "content": {"message": " 说得好 "}, "like": 3},
                {"member": {"uname": "b友B"}, "content": {"message": "泪目"}, "like": 99},
                {"member": {"uname": "b友C"}, "content": {"message": "  "}, "like": 1},
            ]
        },
    }
    out = fetch_comments(_ReplySession(payload), 123)
    assert [c["user"] for c in out] == ["b友B", "b友A"]
    assert out[0]["like"] == 99


def test_fetch_comments_returns_empty_on_error_code():
    from fengge.server import fetch_comments

    assert fetch_comments(_ReplySession({"code": -400}), 1) == []
    assert fetch_comments(_ReplySession({"code": 0}), 0) == []


def test_comment_store_caches_first_fetch(tmp_path):
    from fengge.server import CommentStore

    session = _ReplySession(
        {"code": 0, "data": {"replies": [{"member": {"uname": "u"}, "content": {"message": "hi"}, "like": 1}]}}
    )
    store = CommentStore(tmp_path, session=session)
    first, cached1 = store.get("BV1", 42)
    assert first and cached1 is False
    second, cached2 = store.get("BV1", 42)
    assert second == first and cached2 is True
    assert session.calls == 1


def test_comment_store_survives_fetch_failure(tmp_path):
    from fengge.server import CommentStore

    def boom(session, aid):
        raise RuntimeError("network")

    store = CommentStore(tmp_path, session=object(), fetcher=boom)
    data, cached = store.get("BV1", 42)
    assert data == [] and cached is False


def test_live2d_models_route_lists_model_json(tmp_path):
    from fastapi.testclient import TestClient
    from fengge.config import load_settings

    settings = load_settings(root=tmp_path, env={})
    model_dir = tmp_path / "web" / "vendor" / "live2d" / "models" / "demo" / "assets"
    model_dir.mkdir(parents=True)
    (model_dir / "demo.model3.json").write_text("{}", encoding="utf-8")

    app = create_app(index=make_index(), settings=settings)
    body = TestClient(app).get("/api/live2d/models").json()
    assert body["models"] == [
        {"name": "demo", "json": "/vendor/live2d/models/demo/assets/demo.model3.json"}
    ]


def test_live2d_models_route_empty_when_no_models(tmp_path):
    from fastapi.testclient import TestClient
    from fengge.config import load_settings

    settings = load_settings(root=tmp_path, env={})
    app = create_app(index=make_index(), settings=settings)
    assert TestClient(app).get("/api/live2d/models").json() == {"models": []}


def test_api_topics_and_comments_routes(tmp_path):
    from fastapi.testclient import TestClient
    from fengge.config import load_settings

    settings = load_settings(root=tmp_path, env={})
    app = create_app(index=make_index(), settings=settings)
    client = TestClient(app)
    topics = client.get("/api/topics").json()["topics"]
    assert topics[0]["type"] == "学历与教育"
    page = client.get("/api/topics/学历与教育").json()
    assert page["total"] == 2
    comments = client.get("/api/comments/BV1").json()
    assert comments["comments"] == []
