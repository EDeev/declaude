import pytest

from declaude import MarkdownRenderer

md = MarkdownRenderer()


@pytest.mark.parametrize("url", [
    "javascript:alert(1)",
    "JaVaScRiPt:alert(1)",
    " javascript:alert(1)",
    "java\tscript:alert(1)",
    "data:text/html;base64,PHNjcmlwdD4=",
    "vbscript:msgbox",
])
def test_dangerous_link_schemes_are_neutralized(url):
    html = md.render(f"[клик]({url})")
    assert 'href="#"' in html
    assert "script:" not in html.lower().replace("#", "")


@pytest.mark.parametrize("url", ["https://example.com/a?b=1", "http://example.com", "mailto:me@example.com", "#anchor", "/local/page"])
def test_normal_links_are_kept(url):
    assert f'href="{url}"'.replace("&", "&amp;") in md.render(f"[ссылка]({url})")


def test_image_rejects_javascript_and_svg_data():
    assert 'src="#"' in md.render("![x](javascript:alert(2))")
    assert 'src="#"' in md.render("![x](data:image/svg+xml;base64,PHN2Zz4=)")
    assert 'src="https://example.com/a.png"' in md.render("![x](https://example.com/a.png)")


def test_raw_html_is_escaped():
    html = md.render("<script>alert(3)</script>")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_code_block_is_escaped_and_highlighted():
    html = md.render("```python\nif a < b:\n    return '<x>'\n```")
    assert "<pre" in html and "&lt;x&gt;" in html
    assert "<x>" not in html


def test_table_and_emphasis():
    html = md.render("| A | B |\n|---|---|\n| **1** | *2* |")
    assert "<table" in html
    assert "<strong>1</strong>" in html and "<em>2</em>" in html


def test_headings_and_lists():
    html = md.render("## Заголовок\n\n1. один\n2. два")
    assert "<h2" in html and "Заголовок" in html
    assert "<ol" in html and html.count("<li") == 2
