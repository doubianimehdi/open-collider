#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one Open Collider API-mode iteration.")
    parser.add_argument("project", help="Project directory, for example projects/my_project")
    parser.add_argument("--brainstorm-id", help="Existing brainstorm id, for example brainstorm_001")
    args = parser.parse_args()

    repo_root = Path.cwd()
    sys.path.insert(0, str(repo_root / "src"))

    from open_collider.brainstorm import BrainstormOrchestrator

    result = BrainstormOrchestrator(
        Path(args.project),
        brainstorm_id=args.brainstorm_id,
    ).run_iteration()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
