"""
utils/markdown.py — Lightweight markdown → HTML converter for Groq analysis output.
Handles: ## headings, **bold**, - lists, [text](url) links, paragraphs.
"""
import re


def md_to_html(text: str) -> str:
    if not text:
        return ""

    lines    = text.split("\n")
    result   = []
    in_list  = False

    for line in lines:
        stripped = line.strip()

        # H2 heading
        if stripped.startswith("## "):
            if in_list:
                result.append("</ul>")
                in_list = False
            heading = _inline(stripped[3:])
            result.append(f'<h2 class="md-h2">{heading}</h2>')

        # Unordered list item
        elif stripped.startswith("- ") or stripped.startswith("* "):
            if not in_list:
                result.append('<ul class="md-ul">')
                in_list = True
            result.append(f'<li class="md-li">{_inline(stripped[2:])}</li>')

        # Empty line
        elif stripped == "":
            if in_list:
                result.append("</ul>")
                in_list = False
            # Don't emit <br> — blank lines naturally separate blocks

        # Paragraph (skip raw markdown tables)
        elif not stripped.startswith("|"):
            if in_list:
                result.append("</ul>")
                in_list = False
            result.append(f'<p class="md-p">{_inline(stripped)}</p>')

    if in_list:
        result.append("</ul>")

    return "\n".join(result)


def _inline(text: str) -> str:
    """Apply inline markdown: **bold**, [link](url)."""
    # Bold
    text = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", text)
    # Links
    text = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        r'<a href="\2" target="_blank" rel="noopener">\1</a>',
        text,
    )
    return text
