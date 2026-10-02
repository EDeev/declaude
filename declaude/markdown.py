"""Minimal Markdown → HTML renderer with code highlighting, tables and safe links."""
from __future__ import annotations

import html
import re
from typing import List


# ---------------------------------------------------------------------------
# MarkdownRenderer
# ---------------------------------------------------------------------------

_SCHEME = re.compile(r"^([a-z][a-z0-9+.\-]*):")
_LINK_SCHEMES = ("http", "https", "mailto")


def _safe_url(url: str, image: bool = False) -> str:
    """Allow only http(s)/mailto links and relative URLs; javascript:, data: and the like become "#".

    The text is already HTML-escaped at this point, so the scheme is checked on the unescaped form
    with control characters and spaces removed (browsers ignore them inside the scheme).
    """
    probe = re.sub(r"[\x00-\x20]", "", html.unescape(url)).lower()
    m = _SCHEME.match(probe)
    if m is None:
        return url
    if m.group(1) in _LINK_SCHEMES and not (image and m.group(1) == "mailto"):
        return url
    if image and probe.startswith("data:image/") and not probe.startswith("data:image/svg"):
        return url
    return "#"


class MarkdownRenderer:
    """
    Converts markdown text to HTML.
    Handles: code blocks, inline code, headers, bold, italic,
             links, images, horizontal rules, blockquotes, unordered/ordered lists.
    No external dependencies.
    """

    # Syntax highlight token patterns per language family
    _KEYWORDS = {
        "python": r'\b(def|class|return|import|from|if|elif|else|for|while|with|as|in|not|and|or|is|None|True|False|try|except|finally|raise|yield|lambda|pass|break|continue|del|global|nonlocal|assert|async|await)\b',
        "js":     r'\b(function|const|let|var|return|if|else|for|while|do|class|new|this|import|export|default|from|async|await|try|catch|finally|throw|typeof|instanceof|in|of|true|false|null|undefined|switch|case|break|continue)\b',
        "ts":     r'\b(function|const|let|var|return|if|else|for|while|do|class|new|this|import|export|default|from|async|await|try|catch|finally|throw|typeof|instanceof|in|of|true|false|null|undefined|switch|case|break|continue|type|interface|enum|extends|implements|readonly|abstract)\b',
        "html":   None,
        "css":    None,
        "sql":    r'\b(SELECT|FROM|WHERE|JOIN|LEFT|RIGHT|INNER|OUTER|ON|GROUP|BY|ORDER|HAVING|INSERT|INTO|VALUES|UPDATE|SET|DELETE|CREATE|TABLE|INDEX|DROP|ALTER|ADD|COLUMN|PRIMARY|KEY|FOREIGN|REFERENCES|NOT|NULL|UNIQUE|DEFAULT|AND|OR|AS|DISTINCT|LIMIT|OFFSET|COUNT|SUM|AVG|MAX|MIN|UNION|ALL|EXISTS|IN|LIKE|BETWEEN|CASE|WHEN|THEN|ELSE|END)\b',
        "bash":   r'\b(echo|if|then|else|fi|for|do|done|while|case|esac|function|return|exit|cd|ls|mkdir|rm|cp|mv|cat|grep|sed|awk|find|chmod|chown|export|source|alias|unset|set|read|printf|test|true|false)\b',
        "go":     r'\b(func|package|import|var|const|type|struct|interface|map|chan|go|defer|select|switch|case|default|return|if|else|for|range|break|continue|fallthrough|nil|true|false|make|new|len|cap|append|copy|delete|close|panic|recover)\b',
        "rust":   r'\b(fn|let|mut|pub|use|mod|struct|enum|impl|trait|for|while|loop|if|else|match|return|break|continue|true|false|None|Some|Ok|Err|self|Self|super|crate|move|ref|in|as|where|async|await|dyn|unsafe|extern)\b',
    }

    _LANG_ALIASES = {
        "javascript": "js", "typescript": "ts", "jsx": "js", "tsx": "ts",
        "shell": "bash", "sh": "bash", "zsh": "bash",
        "py": "python", "golang": "go",
    }

    def render(self, text: str) -> str:
        if not text:
            return ""

        # 1. Extract and protect code blocks
        code_blocks: List[str] = []
        text = re.sub(
            r'```(\w*)\n?([\s\S]*?)```',
            lambda m: self._store_code(m, code_blocks),
            text
        )

        # 2. Escape HTML in the remaining text
        text = self._escape_html(text)

        # 3. Inline code (protect from further processing)
        inline_codes: List[str] = []
        text = re.sub(
            r'`([^`\n]+)`',
            lambda m: self._store_inline(m, inline_codes),
            text
        )

        # 4a. Tables (before line-by-line block processing)
        text = self._process_tables(text)

        # 4. Block-level elements (process line by line)
        text = self._process_block(text)

        # 5. Inline formatting
        text = self._process_inline(text)

        # 6. Restore inline code
        for i, code in enumerate(inline_codes):
            text = text.replace(f'\x02INLINE{i}\x03', code)

        # 7. Restore code blocks
        for i, block in enumerate(code_blocks):
            text = text.replace(f'\x02CODE{i}\x03', block)

        return text

    def _store_code(self, m: re.Match, store: List[str]) -> str:
        lang_raw = m.group(1).strip().lower()
        lang = self._LANG_ALIASES.get(lang_raw, lang_raw)
        code = m.group(2)
        highlighted = self._highlight(self._escape_html(code), lang)
        lang_label = lang_raw or "code"
        html = (
            f'<div class="code-block">'
            f'<div class="code-header">'
            f'<span class="code-lang">{lang_label}</span>'
            f'<button class="copy-btn" onclick="copyCode(this)">Copy</button>'
            f'</div>'
            f'<pre><code class="lang-{lang}">{highlighted}</code></pre>'
            f'</div>'
        )
        idx = len(store)
        store.append(html)
        return f'\x02CODE{idx}\x03'

    def _store_inline(self, m: re.Match, store: List[str]) -> str:
        code = m.group(1)
        html = f'<code class="inline-code">{code}</code>'
        idx = len(store)
        store.append(html)
        return f'\x02INLINE{idx}\x03'

    def _highlight(self, code: str, lang: str) -> str:
        if lang not in self._KEYWORDS:
            return code
        pattern = self._KEYWORDS[lang]
        if not pattern:
            return code
        # Strings
        code = re.sub(r'(&#34;(?:[^\\&#]|\\.)*?&#34;|&#39;(?:[^\\&#]|\\.)*?&#39;)',
                      r'<span class="hl-string">\1</span>', code)
        # Keywords
        code = re.sub(pattern, r'<span class="hl-keyword">\1</span>', code,
                      flags=re.IGNORECASE if lang == "sql" else 0)
        # Numbers
        code = re.sub(r'\b(\d+\.?\d*)\b', r'<span class="hl-number">\1</span>', code)
        # Comments
        if lang in ("python", "bash"):
            code = re.sub(r'(#[^\n]*)', r'<span class="hl-comment">\1</span>', code)
        elif lang in ("js", "ts", "go", "rust", "css"):
            code = re.sub(r'(//[^\n]*)', r'<span class="hl-comment">\1</span>', code)
            code = re.sub(r'(/\*[\s\S]*?\*/)', r'<span class="hl-comment">\1</span>', code)
        elif lang == "sql":
            code = re.sub(r'(--[^\n]*)', r'<span class="hl-comment">\1</span>', code)
        return code

    def _escape_html(self, text: str) -> str:
        text = text.replace("&", "&amp;")
        text = text.replace("<", "&lt;")
        text = text.replace(">", "&gt;")
        return text

    def _process_tables(self, text: str) -> str:
        """Convert GFM pipe tables to HTML tables."""
        lines = text.split('\n')
        result: List[str] = []
        i = 0
        while i < len(lines):
            # A table starts with a pipe line followed by a separator line (---|---)
            if (i + 1 < len(lines)
                    and '|' in lines[i]
                    and re.match(r'^\s*\|?[\s\-:|]+\|[\s\-:|]*\|?\s*$', lines[i + 1])):
                # Collect header row
                header_line = lines[i].strip().strip('|')
                sep_line = lines[i + 1]
                i += 2

                # Parse alignments from separator
                sep_cells = [c.strip() for c in sep_line.strip().strip('|').split('|')]
                aligns: List[str] = []
                for cell in sep_cells:
                    if cell.startswith(':') and cell.endswith(':'):
                        aligns.append(' style="text-align:center"')
                    elif cell.endswith(':'):
                        aligns.append(' style="text-align:right"')
                    else:
                        aligns.append('')

                # Render header
                header_cells = [c.strip() for c in header_line.split('|')]
                thead = '<thead><tr>' + ''.join(
                    f'<th{aligns[j] if j < len(aligns) else ""}>{header_cells[j]}</th>'
                    for j in range(len(header_cells))
                ) + '</tr></thead>'

                # Collect body rows
                tbody_rows = ''
                while i < len(lines) and '|' in lines[i]:
                    row_line = lines[i].strip().strip('|')
                    row_cells = [c.strip() for c in row_line.split('|')]
                    tbody_rows += '<tr>' + ''.join(
                        f'<td{aligns[j] if j < len(aligns) else ""}>{row_cells[j]}</td>'
                        for j in range(len(row_cells))
                    ) + '</tr>'
                    i += 1

                result.append(f'<div class="table-wrap"><table>{thead}<tbody>{tbody_rows}</tbody></table></div>')
            else:
                result.append(lines[i])
                i += 1
        return '\n'.join(result)

    def _process_block(self, text: str) -> str:
        lines = text.split('\n')
        output: List[str] = []
        in_ul = False
        in_ol = False
        in_blockquote = False
        i = 0

        def close_lists():
            nonlocal in_ul, in_ol, in_blockquote
            if in_ul:
                output.append('</ul>')
                in_ul = False
            if in_ol:
                output.append('</ol>')
                in_ol = False
            if in_blockquote:
                output.append('</blockquote>')
                in_blockquote = False

        while i < len(lines):
            line = lines[i]

            # Horizontal rule
            if re.match(r'^(\*{3,}|-{3,}|_{3,})\s*$', line):
                close_lists()
                output.append('<hr>')
                i += 1
                continue

            # ATX Headers
            hm = re.match(r'^(#{1,6})\s+(.*)', line)
            if hm:
                close_lists()
                level = len(hm.group(1))
                content = hm.group(2).strip()
                output.append(f'<h{level}>{content}</h{level}>')
                i += 1
                continue

            # Blockquote
            if line.startswith('&gt; ') or line.startswith('&gt;'):
                if not in_blockquote:
                    close_lists()
                    output.append('<blockquote>')
                    in_blockquote = True
                content = re.sub(r'^&gt;\s?', '', line)
                output.append(f'<p>{content}</p>')
                i += 1
                continue
            elif in_blockquote:
                output.append('</blockquote>')
                in_blockquote = False

            # Unordered list
            ulm = re.match(r'^[\*\-\+]\s+(.*)', line)
            if ulm:
                if not in_ul:
                    close_lists()
                    output.append('<ul>')
                    in_ul = True
                output.append(f'<li>{ulm.group(1)}</li>')
                i += 1
                continue

            # Ordered list
            olm = re.match(r'^\d+\.\s+(.*)', line)
            if olm:
                if not in_ol:
                    close_lists()
                    output.append('<ol>')
                    in_ol = True
                output.append(f'<li>{olm.group(1)}</li>')
                i += 1
                continue

            # Empty line — close lists, paragraph break
            if not line.strip():
                close_lists()
                output.append('')
                i += 1
                continue

            # Regular paragraph line
            if in_ul or in_ol:
                close_lists()

            output.append(line)
            i += 1

        close_lists()

        # Wrap consecutive non-tag lines in <p>
        result = []
        para: List[str] = []

        def flush_para():
            if para:
                result.append('<p>' + '<br>'.join(para) + '</p>')
                para.clear()

        for line in output:
            if not line:
                flush_para()
            elif line.startswith('<') and not line.startswith('<br'):
                flush_para()
                result.append(line)
            else:
                para.append(line)
        flush_para()

        return '\n'.join(result)

    def _process_inline(self, text: str) -> str:
        # Images before links
        text = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)',
                      lambda m: f'<img alt="{m.group(1)}" src="{_safe_url(m.group(2), image=True)}" loading="lazy">', text)
        # Links
        text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)',
                      lambda m: f'<a href="{_safe_url(m.group(2))}" target="_blank" rel="noopener">{m.group(1)}</a>', text)
        # Bold+italic
        text = re.sub(r'\*\*\*(.+?)\*\*\*', r'<strong><em>\1</em></strong>', text)
        text = re.sub(r'___(.+?)___', r'<strong><em>\1</em></strong>', text)
        # Bold
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
        text = re.sub(r'__(.+?)__', r'<strong>\1</strong>', text)
        # Italic
        text = re.sub(r'\*([^\*\n]+?)\*', r'<em>\1</em>', text)
        text = re.sub(r'_([^_\n]+?)_', r'<em>\1</em>', text)
        # Strikethrough
        text = re.sub(r'~~(.+?)~~', r'<del>\1</del>', text)
        return text
