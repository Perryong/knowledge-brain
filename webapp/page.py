"""Render docs/index.html from webapp/template.html + docs/data.json."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOCS = HERE.parent / "docs"
MARK = "/*__PAYLOAD__*/null"


def build_page():
    payload = (DOCS / "data.json").read_text()
    html = (HERE / "template.html").read_text()
    assert html.count(MARK) == 1, "template payload marker missing"
    out = DOCS / "index.html"
    out.write_text(html.replace(MARK, payload))
    return out
