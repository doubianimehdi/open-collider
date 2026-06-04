#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


FLAG_ALIASES = {
    "love": "loved",
    "loved": "loved",
    "like": "liked",
    "liked": "liked",
    "trash": "trashed",
    "trashed": "trashed",
}


def parse_number_list(text: str) -> set[int]:
    numbers: set[int] = set()
    for part in re.split(r"[, ]+", text.strip()):
        if not part:
            continue
        if "-" in part and re.fullmatch(r"\d+\s*-\s*\d+", part):
            start, end = [int(x) for x in re.split(r"\s*-\s*", part)]
            numbers.update(range(min(start, end), max(start, end) + 1))
        elif part.isdigit():
            numbers.add(int(part))
    return numbers


def parse_flags(spec: str, all_numbers: set[int]) -> dict[int, str]:
    normalized = spec.replace("—", "-").replace(";", " - ")
    matches = list(re.finditer(r"\b(love|loved|like|liked|trash|trashed)\b", normalized, re.I))
    number_to_flag: dict[int, str] = {}

    for index, match in enumerate(matches):
        label = FLAG_ALIASES[match.group(1).lower()]
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(normalized)
        chunk = normalized[start:end].strip(" :-")
        if re.search(r"\b(the\s+)?rest\b", chunk, re.I):
            selected = all_numbers - set(number_to_flag)
        else:
            selected = parse_number_list(chunk)
        for number in selected:
            number_to_flag[number] = label

    unknown = set(number_to_flag) - all_numbers
    if unknown:
        raise SystemExit(f"Unknown display number(s): {sorted(unknown)}")
    return number_to_flag


def load_mapping(iter_dir: Path) -> list[dict]:
    mapping_path = iter_dir / "numbering_map.json"
    if mapping_path.is_file():
        return json.loads(mapping_path.read_text(encoding="utf-8"))

    curated = json.loads((iter_dir / "curated_ideas.json").read_text(encoding="utf-8"))
    insights_path = iter_dir / "insights_without_collision.json"
    insights = json.loads(insights_path.read_text(encoding="utf-8")) if insights_path.is_file() else []
    mapping: list[dict] = []
    for item in sorted(curated, key=lambda i: i.get("rank", 999999)):
        mapping.append({"number": len(mapping) + 1, "idea_id": item["idea_id"], "kind": "curated"})
    for item in sorted(insights, key=lambda i: i.get("rank", 999999)):
        mapping.append({"number": len(mapping) + 1, "idea_id": item["idea_id"], "kind": "insight"})
    mapping_path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    return mapping


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply love/like/trash flags from display numbers.")
    parser.add_argument("project", help="Project directory, for example projects/my_project")
    parser.add_argument("iteration", type=int, help="Iteration number, for example 1")
    parser.add_argument("flags", help='Flag spec, for example "love 1,3 - like 2 - trash the rest"')
    args = parser.parse_args()

    repo_root = Path.cwd()
    sys.path.insert(0, str(repo_root / "src"))

    from open_collider.skill_interface import _load_state, apply_flags

    project_dir = Path(args.project)
    state = _load_state(project_dir)
    brainstorm_dir = project_dir / "brainstorms" / state["brainstorm_id"]
    iter_dir = brainstorm_dir / f"iter_{args.iteration:03d}"

    mapping = load_mapping(iter_dir)
    number_to_id = {int(item["number"]): item["idea_id"] for item in mapping}
    number_to_flag = parse_flags(args.flags, set(number_to_id))

    flags = {number_to_id[number]: flag for number, flag in number_to_flag.items()}
    apply_flags(str(project_dir), args.iteration, flags)
    print(json.dumps({"applied": len(flags), "flags": flags}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
