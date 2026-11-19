from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

from .filter import cosine
from .models import ClipMeta


def top_k(
    query: list[float], docs: list[list[float]], k: int = 3
) -> list[tuple[int, float]]:
    scored = [(i, cosine(query, doc)) for i, doc in enumerate(docs)]
    scored.sort(key=lambda pair: (-pair[1], pair[0]))
    return scored[:k]


def no_answer(top1: float, threshold: float) -> bool:
    return top1 < threshold


def load_queries(path: Path) -> list[dict[str, Any]]:
    text = Path(path).read_text(encoding="utf-8")
    match = re.search(r"```json\s*\n(.*?)\n```", text, re.DOTALL)
    if not match:
        raise ValueError(f"no ```json block in {path}")
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid json block in {path}: {exc}") from exc
    if not isinstance(data, list):
        raise ValueError("query file must contain a JSON list")
    return data


def _doc_text(record: dict[str, Any]) -> str:
    parts = [
        record.get("abstract_question") or "",
        " ".join(record.get("tags") or []),
        record.get("answer_summary") or "",
    ]
    return " ".join(p for p in parts if p)


def evaluate(
    queries: list[dict[str, Any]],
    records: list[dict[str, Any]],
    embed: Callable[[list[str]], list[list[float]]],
    threshold: float,
    k: int = 3,
) -> dict[str, Any]:
    doc_vectors = embed([_doc_text(r) for r in records])
    query_vectors = embed([q["query"] for q in queries])

    answerable = [q for q, _ in zip(queries, query_vectors) if q.get("has_answer")]
    edge = [q for q, _ in zip(queries, query_vectors) if not q.get("has_answer")]

    answerable_hits = 0
    rows: list[dict[str, Any]] = []
    for query, vector in zip(queries, query_vectors):
        hits = top_k(vector, doc_vectors, k=k) if doc_vectors else []
        best = hits[0][1] if hits else 0.0
        missing = not hits or no_answer(best, threshold)
        hit = bool(query.get("has_answer")) and not missing
        if hit:
            answerable_hits += 1
        rows.append(
            {
                "query": query["query"],
                "has_answer": bool(query.get("has_answer")),
                "top_score": round(best, 4),
                "no_answer": missing,
                "hits": [
                    {"id": records[i].get("id"), "score": round(score, 4)}
                    for i, score in hits
                ],
            }
        )

    edge_no_answer = sum(1 for r in rows if not r["has_answer"] and r["no_answer"])
    n_answerable = len(answerable) or 1
    n_edge = len(edge) or 1
    passed = (
        answerable_hits / n_answerable >= 0.8 and edge_no_answer / n_edge >= 0.6
    )
    return {
        "answerable_hits": answerable_hits,
        "answerable_total": len(answerable),
        "edge_no_answer": edge_no_answer,
        "edge_total": len(edge),
        "passed": passed,
        "threshold": threshold,
        "rows": rows,
    }


def _openai_embedder(settings) -> Callable[[list[str]], list[list[float]]]:
    from openai import OpenAI

    kwargs: dict[str, Any] = {"api_key": settings.openai_api_key}
    if settings.openai_base_url:
        kwargs["base_url"] = settings.openai_base_url
    client = OpenAI(**kwargs)

    def embed(texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        resp = client.embeddings.create(model=settings.embedding_model, input=texts)
        return [d.embedding for d in resp.data]

    return embed


def run_verification(settings, db) -> dict[str, Any]:
    from .export import records_from_rows

    queries_path = (
        Path(settings.root)
        / "docs"
        / "superpowers"
        / "specs"
        / "2026-11-17-verify-queries.md"
    )
    queries = load_queries(queries_path)

    rows = db.next_batch("accepted", 1_000_000)
    records, _ = records_from_rows(rows)

    from .embed import get_embedder

    return evaluate(
        queries,
        records,
        embed=get_embedder(settings),
        threshold=settings.verify_threshold,
    )
