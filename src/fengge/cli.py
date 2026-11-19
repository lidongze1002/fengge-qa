from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Callable

from .config import Settings, load_settings
from .db import Database
from .export import (
    build_report,
    records_from_rows,
    to_record,
    write_jsonl,
    write_review_sample,
)
from .filter import dedupe, filter_item
from .models import ClipMeta

log = logging.getLogger("fengge")


def produce_dataset(
    settings: Settings,
    db: Database,
    embed: Callable[[list[str]], list[list[float]]] | None = None,
) -> dict[str, int]:
    rows = db.next_batch(["accepted", "rejected"], 1_000_000)
    records, rejected = records_from_rows(rows)

    if records:
        if embed is None:
            from .embed import get_embedder

            embed = get_embedder(settings)
        records, duplicates = dedupe(
            records, embed, threshold=settings.dedupe_threshold
        )
        rejected.extend(duplicates)

    stats = {"records": len(records), "rejected": len(rejected)}
    write_jsonl(settings.dataset_dir / "clips.jsonl", records)
    write_jsonl(settings.dataset_dir / "rejected.jsonl", rejected)
    (settings.dataset_dir / "report.md").write_text(
        build_report(records, rejected, db.counts(), disk_root=settings.root),
        encoding="utf-8",
    )
    write_review_sample(records, settings.dataset_dir / "review_sample.csv")
    return stats


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fengge", description="峰哥问答数据集流水线")
    parser.add_argument("--root", default=None, help="项目根目录")
    parser.add_argument("--limit", type=int, default=None, help="本批处理条数")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in (
        "discover",
        "enrich",
        "download",
        "asr",
        "archive",
        "structure",
        "export",
        "verify",
        "run",
        "check",
    ):
        child = sub.add_parser(name)
        # SUPPRESS 让子命令不覆盖根解析器已有的值，`--limit` 放在子命令前后都能用
        child.add_argument("--root", default=argparse.SUPPRESS)
        child.add_argument("--limit", type=int, default=argparse.SUPPRESS)
        if name == "discover":
            child.add_argument("--force", action="store_true")
    return parser


def _cmd_discover(
    settings: Settings, db: Database, limit: int | None, force: bool = False
) -> dict[str, int]:
    from .discover import read_manifest

    if settings.manifest_path.exists() and not force:
        metas = read_manifest(settings.manifest_path)
        print(f"using existing manifest: {settings.manifest_path} ({len(metas)} items)")
    else:
        from .discover import discover

        metas = discover(settings)
        print(f"discovered {len(metas)} videos -> {settings.manifest_path}")
    added = sum(1 for meta in metas if db.upsert_clip(meta))
    print(f"new rows: {added}, total: {sum(db.counts().values())}")
    return {"added": added}


def _setup_logging(settings: Settings) -> None:
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = settings.logs_dir / "pipeline.log"
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for handler in list(root.handlers):
        root.removeHandler(handler)
    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(formatter)
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    root.addHandler(stream)
    root.addHandler(file_handler)


def main(argv: list[str] | None = None) -> int:
    try:
        from dotenv import load_dotenv

        load_dotenv(override=True)
    except ImportError:
        pass

    args = _build_parser().parse_args(argv)
    root = Path(args.root) if args.root else None
    settings = load_settings(root=root)
    _setup_logging(settings)
    log.info("start %s (limit=%s)", args.command, getattr(args, "limit", None))
    for directory in (
        settings.data_dir,
        settings.clips_dir,
        settings.raw_dir,
        settings.audio_dir,
        settings.asr_dir,
        settings.structured_dir,
        settings.dataset_dir,
        settings.logs_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    db = Database(settings.db_path)
    db.init_schema()

    if args.command == "check":
        from .envcheck import print_report

        return 0 if print_report() else 1

    if args.command == "discover":
        _cmd_discover(settings, db, args.limit, force=getattr(args, "force", False))
        return 0

    if args.command == "enrich":
        from .discover import enrich_manifest

        updated = enrich_manifest(settings, limit=args.limit)
        print(f"enriched {updated} rows")
        from .discover import read_manifest

        for meta in read_manifest(settings.manifest_path):
            db.upsert_clip(meta)
        return 0

    if args.command == "export":
        stats = produce_dataset(settings, db)
        print(f"dataset: {stats['records']} records, {stats['rejected']} rejected")
        return 0

    if args.command == "verify":
        from .verify import run_verification

        result = run_verification(settings, db)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("passed") else 1

    from .pipeline import Pipeline

    pipeline = Pipeline(settings, db=db)
    if args.command == "run":
        from .pipeline import NetworkDown, RateLimited

        try:
            summary = pipeline.run_all(args.limit)
        except (RateLimited, NetworkDown) as exc:
            log.error("%s", exc)
            return 2
        print(json.dumps(summary, ensure_ascii=False))
        return 0

    from .pipeline import NetworkDown, RateLimited

    try:
        summary = pipeline.run(args.command, args.limit)
    except (RateLimited, NetworkDown) as exc:
        log.error("%s", exc)
        return 2
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
