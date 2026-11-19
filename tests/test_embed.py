from __future__ import annotations

from types import SimpleNamespace

from fengge import embed


def _settings(**kw):
    base = dict(
        embedding_backend="local",
        local_embedding_model="BAAI/bge-small-zh-v1.5",
        embedding_model="text-embedding-3-small",
        openai_api_key="",
        openai_base_url="",
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_get_embedder_defaults_to_local(monkeypatch):
    called = {}

    def fake_local(model_name, device=None):
        called["model"] = model_name
        return lambda texts: [[1.0] for _ in texts]

    monkeypatch.setattr(embed, "local_embedder", fake_local)
    fn = embed.get_embedder(_settings())
    assert fn(["a"]) == [[1.0]]
    assert called["model"] == "BAAI/bge-small-zh-v1.5"


def test_get_embedder_can_use_openai(monkeypatch):
    called = {}

    def fake_openai(api_key, model, base_url=""):
        called.update(api_key=api_key, model=model, base_url=base_url)
        return lambda texts: [[2.0] for _ in texts]

    monkeypatch.setattr(embed, "openai_embedder", fake_openai)
    fn = embed.get_embedder(
        _settings(
            embedding_backend="openai",
            openai_api_key="k",
            openai_base_url="https://x",
        )
    )
    assert fn(["a"]) == [[2.0]]
    assert called == {"api_key": "k", "model": "text-embedding-3-small", "base_url": "https://x"}


def test_local_embedder_returns_empty_for_empty_input():
    fn = embed.local_embedder("whatever")
    assert fn([]) == []
