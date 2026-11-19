from __future__ import annotations

from fengge.retrieval import BM25, rrf_fuse, tokenize


def test_tokenize_mixes_bigrams_and_ascii():
    tokens = tokenize("考研还是考公 python3")
    assert "考研" in tokens
    assert "考" in tokens
    assert "python3" in tokens


def test_bm25_prefers_exact_keyword_match():
    docs = [
        "要不要继续读研，考研还是直接工作",
        "怎么找对象，相亲市场普通人还有机会吗",
        "大城市还是小城市，回老家躺平好不好",
    ]
    bm25 = BM25(docs)
    hits = bm25.search("考研", k=3)
    assert hits[0][0] == 0
    assert hits[0][1] > 0


def test_bm25_returns_nothing_for_unseen_terms():
    bm25 = BM25(["考研", "找工作"])
    assert bm25.search("量子计算") == []


def test_bm25_handles_empty_corpus():
    assert BM25([]).search("考研") == []


def test_rrf_fuse_merges_rankings():
    vector = [(5, 0.81), (2, 0.79)]
    lexical = [(2, 12.0), (9, 8.0)]
    fused = rrf_fuse([vector, lexical], size=3)
    ids = [i for i, _ in fused]
    assert ids[0] == 2
    assert set(ids) == {2, 5, 9}


def test_rrf_fuse_empty():
    assert rrf_fuse([[], []]) == []
