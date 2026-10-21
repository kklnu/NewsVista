"""Run one collection job from the command line (local testing or manual ops).

    python -m scripts.collect [--max-ai N] [--trigger cli]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import get_db  # noqa: E402
from app.pipeline import CollectionJob, default_services  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-ai", type=int, default=None)
    parser.add_argument("--trigger", default="cli")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    db = get_db()
    db.create_all()
    summary = CollectionJob(db, default_services()).run(args.trigger, max_ai=args.max_ai)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
