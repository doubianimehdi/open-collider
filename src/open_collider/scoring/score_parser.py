"""ScoreParser — Extraction of per-axis scores from Judge responses.

Parses the scoring table (Step 1) to extract the 5 hardcoded per-axis
scores + the aggregate score of each idea.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class AxisScores:
    """Per-axis scores for an idea extracted from the scoring table."""

    idea_num: int
    originality: float
    resistance: float
    thesis_density: float
    concrete_grounding: float
    cognitive_load: float
    score_aggregate: float


# Pattern to parse a row of the scoring table (Step 1)
# Supported formats:
#   | 1 | 4 | 5 | 3 | 4 | 5 | **4.25** |
#   | 1 | 4/5 | 5/5 | 3/5 | 4/5 | 5/5 | 4.25 |
#   | 1 | **4**/5 | 5 | 3 | 4 | 5 | 4.25 |
#   | 1 | 4/5 | 5/5 | 3/5 | 4/5 | 5/5 | **4.25 / 5** |
SCORING_ROW_PATTERN = re.compile(
    r"\|\s*(\d+)\s*\|"  # idea number
    r"\s*\*{0,2}([\d.]+)\*{0,2}(?:\s*/\s*5)?\*{0,2}\s*\|"  # originality
    r"\s*\*{0,2}([\d.]+)\*{0,2}(?:\s*/\s*5)?\*{0,2}\s*\|"  # resistance
    r"\s*\*{0,2}([\d.]+)\*{0,2}(?:\s*/\s*5)?\*{0,2}\s*\|"  # thesis_density
    r"\s*\*{0,2}([\d.]+)\*{0,2}(?:\s*/\s*5)?\*{0,2}\s*\|"  # concrete_grounding
    r"\s*\*{0,2}([\d.]+)\*{0,2}(?:\s*/\s*5)?\*{0,2}\s*\|"  # cognitive_load
    r"\s*\*{0,2}([\d.]+)\*{0,2}(?:\s*/\s*5)?\*{0,2}\s*\|"  # score_aggregate
)

# Pattern to extract judge_note (main strength) from the ✓ line
# Supports both French ("Idée") and English ("Idea")
# ✓ Idea #12 — Score 4.60 — [main strength in 1 sentence]
JUDGE_NOTE_PATTERN = re.compile(
    r'[✓✔☑]\s*(?:Id[eé]e|Idea)\s*#?(\d+)\s*[—\-–]+\s*Score\s*([\d.]+)\s*[—\-–]+\s*(.*)',
    re.IGNORECASE,
)


def parse_scoring_table(judge_content: str) -> list[AxisScores]:
    """Parse the scoring table (Step 1) of a judge response.

    Returns:
        List of AxisScores for each idea found in the table.
        Empty list if the table is missing or malformed.
    """
    results: list[AxisScores] = []
    try:
        for match in SCORING_ROW_PATTERN.finditer(judge_content):
            results.append(
                AxisScores(
                    idea_num=int(match.group(1)),
                    originality=float(match.group(2)),
                    resistance=float(match.group(3)),
                    thesis_density=float(match.group(4)),
                    concrete_grounding=float(match.group(5)),
                    cognitive_load=float(match.group(6)),
                    score_aggregate=float(match.group(7)),
                )
            )
    except (ValueError, IndexError):
        pass
    return results


def extract_judge_notes(judge_content: str) -> dict[int, str]:
    """Extract per-idea judge notes from the final list section.

    Returns: {idea_num: "main strength text"}
    """
    notes: dict[int, str] = {}
    for match in JUDGE_NOTE_PATTERN.finditer(judge_content):
        try:
            num = int(match.group(1))
            notes[num] = match.group(3).strip()
        except (ValueError, IndexError):
            continue
    return notes
