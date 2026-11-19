"""把 pip 装进来的 NVIDIA 运行库目录挂进 DLL 搜索路径。

ctranslate2 在 Windows 上要求 cublas64_12.dll / cudnn_ops64_9.dll 能被找到，
而 pip 的 nvidia-* wheel 落在 site-packages 里，不会自动进 PATH。
"""

from __future__ import annotations

import os
import site
from pathlib import Path


def candidate_dirs() -> list[Path]:
    dirs: list[Path] = []
    seen: set[Path] = set()
    roots: list[Path] = []
    try:
        import nvidia

        roots.extend(Path(p) for p in nvidia.__path__)
    except ImportError:
        pass
    for base in site.getsitepackages() + [site.getusersitepackages()]:
        roots.append(Path(base) / "nvidia")
    for root in roots:
        if not root.is_dir():
            continue
        for sub in root.iterdir():
            for name in ("bin", "lib"):
                d = sub / name
                if d.is_dir() and any(d.glob("*.dll")) and d not in seen:
                    seen.add(d)
                    dirs.append(d)
    return dirs


def register() -> list[Path]:
    dirs = candidate_dirs()
    for d in dirs:
        if hasattr(os, "add_dll_directory"):
            try:
                os.add_dll_directory(str(d))
            except OSError:
                pass
        os.environ["PATH"] = str(d) + os.pathsep + os.environ.get("PATH", "")
    return dirs
