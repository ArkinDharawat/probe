from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Section:
    header: str
    body: str


def split_markdown(text: str) -> tuple[Optional[str], list[Section]]:
    if not text:
        return None, []

    title: Optional[str] = None
    sections: list[Section] = []
    current_header: Optional[str] = None
    current_body_lines: list[str] = []

    for line in text.splitlines():
        if line.startswith("# ") and not line.startswith("## "):
            title = line[2:].strip()
        elif line.startswith("## "):
            if current_header is not None:
                sections.append(Section(current_header, "\n".join(current_body_lines).strip()))
            current_header = line[3:].strip()
            current_body_lines = []
        else:
            if current_header is not None:
                current_body_lines.append(line)

    if current_header is not None:
        sections.append(Section(current_header, "\n".join(current_body_lines).strip()))

    return title, sections
