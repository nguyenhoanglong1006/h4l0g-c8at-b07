"""Split an article into self-contained pieces, each small enough to be exactly one File Search chunk.

Every piece starts with the article title and its `Article URL:` line, so whichever chunk
File Search retrieves, the model can cite the correct URL.
"""

import re
from dataclasses import dataclass

import tiktoken

# Gemini File Search caps chunks at 512 tokens. Pieces are measured with o200k, not Gemini's tokenizer,
# so the budget keeps ~20% headroom and each uploaded piece is still embedded as a single chunk.
CHUNK_SIZE_TOKENS = 512
PIECE_BUDGET_TOKENS = 400

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_FENCE = "```"
_encoding = tiktoken.get_encoding("o200k_base")


@dataclass(frozen=True)
class Section:
    path: str
    text: str


def count_tokens(text: str) -> int:
    return len(_encoding.encode(text))


def _split_sections(body: str) -> list[Section]:
    """Split Markdown at headings (ignoring `#` lines inside code fences), tracking the heading path."""
    sections: list[Section] = []
    stack: list[tuple[int, str]] = []
    lines: list[str] = []
    in_code = False

    def flush() -> None:
        text = "\n".join(lines).strip()
        lines.clear()
        if text:
            sections.append(Section(path=" > ".join(title for _, title in stack), text=text))

    for line in body.splitlines():
        if line.startswith(_FENCE):
            in_code = not in_code
        heading = None if in_code else _HEADING.match(line)
        if not heading:
            lines.append(line)
            continue
        flush()
        level = len(heading.group(1))
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, heading.group(2).strip()))
        lines.append(line)
    flush()
    return sections


def _split_oversized(text: str, budget: int) -> list[str]:
    """Split by paragraph, then by line, then by raw tokens as a last resort."""
    for separator in ("\n\n", "\n"):
        parts = text.split(separator)
        if len(parts) > 1:
            return _pack(parts, budget, separator)
    tokens = _encoding.encode(text)
    return [_encoding.decode(tokens[i : i + budget]) for i in range(0, len(tokens), budget)]


def _pack(parts: list[str], budget: int, separator: str) -> list[str]:
    """Greedily join consecutive parts while they fit the budget."""
    pieces: list[str] = []
    current = ""
    for part in parts:
        if count_tokens(part) > budget:
            pieces.extend([current] if current else [])
            pieces.extend(_split_oversized(part, budget))
            current = ""
            continue
        candidate = f"{current}{separator}{part}" if current else part
        if count_tokens(candidate) <= budget:
            current = candidate
            continue
        pieces.append(current)
        current = part
    pieces.extend([current] if current else [])
    return [p.strip() for p in pieces if p.strip()]


def _section_blocks(section: Section, budget: int) -> list[str]:
    """A section that fits stays whole; a long one is split and later parts name the section they continue."""
    marker = f"({section.path}, continued)\n\n"
    first, *rest = _pack([section.text], budget - count_tokens(marker), "\n\n")
    return [first, *(marker + part for part in rest)]


def split_into_pieces(markdown: str, header: str) -> list[str]:
    """Pack consecutive sections into pieces of at most PIECE_BUDGET_TOKENS, each starting with `header`."""
    body = markdown.removeprefix(header)
    budget = PIECE_BUDGET_TOKENS - count_tokens(header)
    blocks = [block for section in _split_sections(body) for block in _section_blocks(section, budget)]
    return [header + piece for piece in _pack(blocks, budget, "\n\n")]
