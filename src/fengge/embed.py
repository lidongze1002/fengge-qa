from __future__ import annotations

from typing import Any, Callable

_CACHE: dict[str, Any] = {}


def local_embedder(
    model_name: str = "BAAI/bge-small-zh-v1.5", device: str | None = None
) -> Callable[[list[str]], list[list[float]]]:
    """用 fastembed（ONNX）跑本地中文 embedding。

    不用 sentence-transformers：这台机器的 Keras 3 与 transformers 的 TF 后端冲突，
    而 fastembed 不依赖 torch/TF，CPU 上 1252 条也够快。
    """

    def embed(texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        from fastembed import TextEmbedding

        model = _CACHE.get(model_name)
        if model is None:
            model = TextEmbedding(model_name=model_name)
            _CACHE[model_name] = model
        vectors = []
        for vector in model.embed(texts, batch_size=32):
            values = [float(x) for x in vector]
            norm = sum(v * v for v in values) ** 0.5 or 1.0
            vectors.append([v / norm for v in values])
        return vectors

    return embed


def openai_embedder(
    api_key: str, model: str, base_url: str = ""
) -> Callable[[list[str]], list[list[float]]]:
    from openai import OpenAI

    kwargs: dict[str, Any] = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    client = OpenAI(**kwargs)

    def embed(texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        resp = client.embeddings.create(model=model, input=texts)
        return [d.embedding for d in resp.data]

    return embed


def get_embedder(settings) -> Callable[[list[str]], list[list[float]]]:
    if settings.embedding_backend == "openai":
        return openai_embedder(
            settings.openai_api_key, settings.embedding_model, settings.openai_base_url
        )
    return local_embedder(settings.local_embedding_model)
