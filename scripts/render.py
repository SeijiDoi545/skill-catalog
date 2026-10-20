#!/usr/bin/env python3
"""data/skills.json をHTMLのひな形に埋め込んで、公開用のHTMLを出力する。

ひな形の中の /*__CATALOG_DATA__*/null を、スキル一覧のJSONに置き換える。

使い方:
  python scripts/render.py --template template/skills-catalog.template.html \
      --data data/skills.json --out docs/index.html
"""
import argparse
import json
from pathlib import Path

PLACEHOLDER = "/*__CATALOG_DATA__*/null"


def to_script_json(data):
    s = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    # <script> の中に安全に置けるようにする
    return s.replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", default="template/skills-catalog.template.html")
    ap.add_argument("--data", default="data/skills.json")
    ap.add_argument("--out", default="docs/index.html")
    a = ap.parse_args()

    tpl = Path(a.template).read_text(encoding="utf-8")
    if tpl.count(PLACEHOLDER) != 1:
        raise SystemExit(f"ひな形に {PLACEHOLDER} がちょうど1つ必要です")
    data = json.loads(Path(a.data).read_text(encoding="utf-8"))
    html = tpl.replace(PLACEHOLDER, to_script_json(data))
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"{out} を出力しました（スキル {len(data.get('skills', []))}件）")


if __name__ == "__main__":
    main()
