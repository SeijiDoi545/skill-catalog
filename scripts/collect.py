#!/usr/bin/env python3
"""各部署の全社公開用リポジトリからスキル情報を集めて data/skills.json を作る。

スキルの見つけ方:
  skills/<スキルID>/README.md があるフォルダを1つのスキルとして扱う。
  タイトルと概要はリポジトリ直下の catalog.yml（人手で記載）を優先し、
  書かれていなければ README の見出しと最初の段落から作る。
  更新日は skills/<スキルID>/ を最後に変更したコミットの日付。

使い方:
  # GitHub から集める（Actions ではこちら）
  python scripts/collect.py --config config/departments.yml --owner <持ち主> --out data/skills.json
  # 手元のフォルダから集める（動作確認用。<root>/<repo名>/ に各リポジトリを置く）
  python scripts/collect.py --config config/departments.yml --source local --local-root ../repos --out data/skills.json

環境変数 GH_TOKEN（または GITHUB_TOKEN）があれば GitHub API の認証に使う。
"""
import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

API = os.environ.get("GITHUB_API_URL", "https://api.github.com")


# ---------------------------------------------------------------- sources
class GitHubSource:
    def __init__(self, owner, repo, branch):
        self.owner, self.repo, self.branch = owner, repo, branch
        self.token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")

    def _get(self, path, raw=False):
        req = urllib.request.Request(f"{API}{path}")
        req.add_header("Accept", "application/vnd.github.raw+json" if raw else "application/vnd.github+json")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise RuntimeError(f"GitHub API {path} -> HTTP {e.code}: {e.read()[:300]!r}") from e
        return body.decode("utf-8") if raw else json.loads(body)

    def _repo_path(self, rest):
        return f"/repos/{self.owner}/{self.repo}{rest}"

    def exists(self):
        return self._get(self._repo_path("")) is not None

    def list_files(self):
        tree = self._get(self._repo_path(f"/git/trees/{urllib.parse.quote(self.branch)}?recursive=1"))
        if tree is None:
            return []
        if tree.get("truncated"):
            print(f"warning: {self.repo} のファイル一覧が途中で切れています", file=sys.stderr)
        return [t["path"] for t in tree.get("tree", []) if t.get("type") == "blob"]

    def read(self, path):
        q = urllib.parse.quote(path)
        return self._get(self._repo_path(f"/contents/{q}?ref={urllib.parse.quote(self.branch)}"), raw=True)

    def last_updated(self, path):
        q = urllib.parse.urlencode({"path": path, "sha": self.branch, "per_page": 1})
        commits = self._get(self._repo_path(f"/commits?{q}")) or []
        if not commits:
            return ""
        # GitHub は UTC で返すので、日本時間の日付にそろえる
        when = dt.datetime.fromisoformat(commits[0]["commit"]["committer"]["date"].replace("Z", "+00:00"))
        return when.astimezone(dt.timezone(dt.timedelta(hours=9))).date().isoformat()


class LocalSource:
    def __init__(self, root, repo):
        self.dir = Path(root) / repo

    def exists(self):
        return self.dir.is_dir()

    def list_files(self):
        return [str(p.relative_to(self.dir)).replace(os.sep, "/") for p in self.dir.rglob("*")
                if p.is_file() and ".git" not in p.relative_to(self.dir).parts]

    def read(self, path):
        p = self.dir / path
        return p.read_text(encoding="utf-8") if p.is_file() else None

    def last_updated(self, path):
        try:
            out = subprocess.run(["git", "-C", str(self.dir), "log", "-1", "--format=%cs", "--", path],
                                 capture_output=True, text=True, check=True).stdout.strip()
            return out
        except (subprocess.CalledProcessError, FileNotFoundError):
            return ""


# ---------------------------------------------------------------- parsing
SKILL_README = re.compile(r"^skills/([A-Za-z0-9._-]+)/README\.md$")


def title_from_readme(readme, skill_id):
    for line in readme.splitlines():
        m = re.match(r"^#\s+(.+?)\s*$", line)
        if m:
            return re.sub(r"\s*\(" + re.escape(skill_id) + r"\)\s*$", "", m.group(1)).strip()
    return skill_id


def summary_from_readme(readme, limit=80):
    for line in readme.splitlines():
        t = line.strip()
        if not t or t.startswith(("#", "-", "*", ">", "|", "```")):
            continue
        return t if len(t) <= limit else t[: limit - 1] + "…"
    return ""


def collect_department(dept, source, owner, branch):
    if not source.exists():
        print(f"warning: {dept['repo']} が見つかりません。スキップします", file=sys.stderr)
        return []
    catalog_text = source.read("catalog.yml")
    catalog = (yaml.safe_load(catalog_text) or {}) if catalog_text else {}
    meta = catalog.get("skills") or {}
    skills = []
    for path in sorted(source.list_files()):
        m = SKILL_README.match(path)
        if not m:
            continue
        sid = m.group(1)
        info = meta.get(sid) or {}
        if info.get("hidden"):
            continue
        readme = source.read(path) or ""
        skills.append({
            "id": sid,
            "dept": dept["key"],
            "title": str(info.get("title") or title_from_readme(readme, sid)),
            "summary": str(info.get("summary") or summary_from_readme(readme)),
            "summarySource": "catalog" if info.get("summary") else "readme",
            "updated": source.last_updated(f"skills/{sid}"),
            "readme": readme.strip(),
            "repo": dept["repo"],
            "url": f"https://github.com/{owner}/{dept['repo']}/tree/{branch}/skills/{sid}",
        })
    return skills


# ---------------------------------------------------------------- main
def diff_summary(old, new):
    o = {f"{s['dept']}/{s['id']}": s for s in (old or {}).get("skills", [])}
    n = {f"{s['dept']}/{s['id']}": s for s in new["skills"]}
    keys = ("title", "summary", "readme", "updated")
    added = sorted(set(n) - set(o))
    removed = sorted(set(o) - set(n))
    changed = sorted(k for k in set(n) & set(o) if any(n[k].get(f) != o[k].get(f) for f in keys))
    return added, removed, changed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/departments.yml")
    ap.add_argument("--owner", default=os.environ.get("CATALOG_OWNER"))
    ap.add_argument("--source", choices=["github", "local"], default="github")
    ap.add_argument("--local-root")
    ap.add_argument("--out", default="data/skills.json")
    a = ap.parse_args()

    cfg = yaml.safe_load(Path(a.config).read_text(encoding="utf-8"))
    owner = cfg.get("owner") or a.owner
    branch = cfg.get("branch", "main")
    if not owner:
        sys.exit("リポジトリの持ち主がわかりません。config の owner か --owner を指定してください")
    if a.source == "local" and not a.local_root:
        sys.exit("--source local には --local-root が必要です")

    departments, skills = {}, []
    for d in cfg["departments"]:
        departments[d["key"]] = {"name": d["name"], "cls": d.get("color", "d-dx"), "repo": d["repo"],
                                 "url": f"https://github.com/{owner}/{d['repo']}"}
        src = GitHubSource(owner, d["repo"], branch) if a.source == "github" else LocalSource(a.local_root, d["repo"])
        skills += collect_department(d, src, owner, branch)

    data = {"generatedAt": "", "departments": departments, "skills": skills}
    out = Path(a.out)
    old = json.loads(out.read_text(encoding="utf-8")) if out.exists() else None
    added, removed, changed = diff_summary(old, data)
    same = old is not None and {k: v for k, v in old.items() if k != "generatedAt"} == {k: v for k, v in data.items() if k != "generatedAt"}
    # 内容が同じなら生成日時も据え置き、不要なコミットを作らない
    data["generatedAt"] = old["generatedAt"] if same else dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    lines = [f"## スキル一覧の収集結果", "", f"- 部署: {len(departments)} / スキル: {len(skills)}件"]
    lines += [f"- 追加: {', '.join(added) or 'なし'}", f"- 更新: {', '.join(changed) or 'なし'}", f"- 削除: {', '.join(removed) or 'なし'}"]
    report = "\n".join(lines) + "\n"
    print(report)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(report)


if __name__ == "__main__":
    main()
