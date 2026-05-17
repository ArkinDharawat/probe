from probe.markdown_split import split_markdown


def test_split_extracts_h1_title(sample_md_text):
    title, _sections = split_markdown(sample_md_text)
    assert title == "Palantir Bull Case"


def test_split_sections_on_h2(sample_md_text):
    _title, sections = split_markdown(sample_md_text)
    headers = [s.header for s in sections]
    assert headers == ["Core Claim", "Evidence", "Open Questions"]


def test_split_preserves_bullets_verbatim(sample_md_text):
    _title, sections = split_markdown(sample_md_text)
    evidence = next(s for s in sections if s.header == "Evidence")
    assert "US commercial revenue grew 55% YoY in Q4 2024" in evidence.body
    assert "AIP bootcamp conversion rate reportedly above 40%" in evidence.body
    assert "Rule of 40 score crossed 60 for the first time in Q3 2024" in evidence.body
    assert "Net dollar retention above 120% for three consecutive quarters" in evidence.body


def test_split_empty_input():
    title, sections = split_markdown("")
    assert title is None
    assert sections == []


def test_split_no_h1_returns_none_title():
    title, sections = split_markdown("## Only H2\n\nbody text\n")
    assert title is None
    assert len(sections) == 1
    assert sections[0].header == "Only H2"
    assert "body text" in sections[0].body
