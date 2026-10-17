from optibot.ingestion.chunker import PIECE_BUDGET_TOKENS, count_tokens, split_into_pieces

HEADER = "# Title\n\nArticle URL: https://support.optisigns.com/hc/en-us/articles/1-title\n\n"


def test_short_article_is_a_single_piece_with_header():
    markdown = HEADER + "Intro.\n\n## Step 1\n\nDo this.\n"

    pieces = split_into_pieces(markdown, HEADER)

    assert pieces == [HEADER + "Intro.\n\n## Step 1\n\nDo this."]


def test_long_article_splits_at_sections_and_every_piece_carries_the_url():
    # Each section fits alone, but any two together exceed the budget.
    section = "word " * (PIECE_BUDGET_TOKENS * 2 // 3)
    markdown = HEADER + f"## A\n\n{section}\n\n## B\n\n{section}\n\n## C\n\n{section}\n"

    pieces = split_into_pieces(markdown, HEADER)

    assert len(pieces) == 3
    assert all(p.startswith(HEADER) for p in pieces)
    assert all(count_tokens(p) <= PIECE_BUDGET_TOKENS for p in pieces)
    assert [p.split("\n")[4] for p in pieces] == ["## A", "## B", "## C"]


def test_oversized_section_is_split_and_marks_continuation():
    paragraphs = "\n\n".join(f"Paragraph {i} " + "text " * 100 for i in range(10))
    markdown = HEADER + f"## Setup\n\n### Wi-Fi\n\n{paragraphs}\n"

    pieces = split_into_pieces(markdown, HEADER)

    assert len(pieces) > 1
    assert all(count_tokens(p) <= PIECE_BUDGET_TOKENS for p in pieces)
    assert "(Setup > Wi-Fi, continued)" in pieces[1]


def test_hash_lines_inside_code_fences_are_not_headings():
    markdown = HEADER + "## Config\n\n```\n# not a heading\n```\n"

    pieces = split_into_pieces(markdown, HEADER)

    assert pieces == [HEADER + "## Config\n\n```\n# not a heading\n```"]
