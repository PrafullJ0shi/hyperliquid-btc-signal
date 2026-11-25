"""Light checks on the public docs: structure, banned words, no emoji."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

BANNED = re.compile(r"\b(BITS|Pilani|university|college|campus)\b", re.I)
# Common emoji ranges plus a few dingbats; the plate and the README forbid them.
EMOJI = re.compile(
    "["
    "\U0001F300-\U0001F6FF"
    "\U0001F900-\U0001FAFF"
    "\U00002600-\U000026FF"
    "\U00002700-\U000027BF"
    "]+"
)
DOCS = [
    ROOT / "README.md",
    ROOT / "CHANGELOG.md",
    ROOT / "CONTRIBUTING.md",
    ROOT / "docs" / "ROADMAP.md",
    ROOT / "DESIGN.md",
]


def test_docs_have_no_banned_or_emoji_copy():
    for path in DOCS:
        text = path.read_text()
        assert not BANNED.search(text), f"{path.name} has a banned word"
        assert not EMOJI.search(text), f"{path.name} contains emoji"


def test_readme_has_upcoming_and_contents():
    text = (ROOT / "README.md").read_text()
    assert "## Upcoming: v2.0" in text
    assert "## Contents" in text
    assert "## What it shows" in text
    assert "## Quick start" in text
    assert "## Disclaimer" in text
    assert "docs/ROADMAP.md" in text
    assert "docs/signal.png" in text
    assert "docs/flows.png" in text
    assert "docs/backtest.png" in text
    assert "CHANGELOG.md" in text
    assert "## Roadmap: v2.0" not in text


def test_changelog_covers_three_releases():
    text = (ROOT / "CHANGELOG.md").read_text()
    assert "## 1.0.0 — 24 November 2026" in text
    assert "## 1.1.0 — 25 November 2026" in text
    assert "## 1.2.0 — 25 November 2026" in text
    assert "market-intelligence layer" in text
    assert "Flows tab" in text
    assert "Backtest tab" in text
    assert "Publishing" in text


def test_roadmap_v20_has_priorities_and_done_when():
    text = (ROOT / "docs" / "ROADMAP.md").read_text()
    assert "X sentiment" in text
    assert "data/x_sentiment.json" in text
    for label in ("P1", "P2", "P3"):
        assert label in text
    assert text.lower().count("done when") >= 7
    assert "not a promise of profit" in text.lower()
    # The official API gap must stay honest.
    assert "no market-wide liquidation" in text.lower() or "no such feed" in text.lower()


def test_formula_fixed_in_6f54ee5_still_uses_fractions():
    """GitHub treats % inside maths as a comment; keep the thresholds as decimals."""
    text = (ROOT / "README.md").read_text()
    assert r"\le -0.015" in text
    assert r"|r_t| \ge 0.01" in text
    assert r"-1.5\%" not in text
