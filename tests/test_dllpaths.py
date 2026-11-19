from __future__ import annotations

from fengge import dllpaths


def test_candidate_dirs_are_unique():
    dirs = dllpaths.candidate_dirs()
    assert len(dirs) == len(set(dirs))


def test_register_returns_the_same_dirs():
    assert dllpaths.register() == dllpaths.candidate_dirs()
