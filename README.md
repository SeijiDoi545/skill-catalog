# skill-catalog

各部署の全社公開用スキルリポジトリ（`*-skills-public`）から、全社のスキル一覧HTMLを自動で作るリポジトリです（デモ用）。

## しくみ

```
部署リポジトリ（sales-skills-public など）
  └ skills/ か catalog.yml が main に入る
      └ notify-catalog.yml が skill-catalog に通知（repository_dispatch）
          └ build-catalog.yml
              1. scripts/collect.py  全部署の skills/*/README.md と catalog.yml を集めて data/skills.json に保存
              2. scripts/render.py   template/ のひな形に埋め込んで docs/index.html を出力
              3. 変更があればコミット → GitHub Pages で公開
```

- 新しいスキルは、部署リポジトリに `skills/<スキルID>/README.md` を足すだけで一覧に載ります。
- タイトルと概要は部署リポジトリの `catalog.yml` が優先です。書かれていなければ README の見出しと最初の段落を使い、一覧の「概要の出所」に「READMEから抽出」と表示します。
- 一覧に載せる部署は `config/departments.yml` で決めます。部署内公開用リポジトリはここに書かないので、一覧にも検索にも出ません。
- 取りこぼし対策として、毎朝6時（日本時間）にも作り直します。内容が変わっていなければコミットしません。

## フォルダ

| パス | 中身 |
|---|---|
| `template/skills-catalog.template.html` | HTMLのひな形。`/*__CATALOG_DATA__*/null` の位置にデータが入る |
| `scripts/collect.py` | スキル情報の収集 |
| `scripts/render.py` | ひな形への埋め込み |
| `config/departments.yml` | 一覧に載せる部署とリポジトリ |
| `data/skills.json` | 収集結果（自動生成） |
| `docs/index.html` | 公開用HTML（自動生成） |
| `.github/workflows/build-catalog.yml` | 生成ワークフロー |

## 初期設定

1. **GitHub Pages**：Settings > Pages で「Deploy from a branch」、`main` の `/docs` を選ぶ。
2. **部署リポジトリの通知用トークン**：skill-catalog に対して Contents: Read and write を持つ fine-grained token を作り、各部署リポジトリの Secret `CATALOG_DISPATCH_TOKEN` に登録する。
3. **部署リポジトリが非公開の場合**：部署リポジトリを読める token を、skill-catalog の Secret `CATALOG_READ_TOKEN` に登録する。公開リポジトリなら不要。

## 手元で試す

```bash
pip install pyyaml
# <root>/<リポジトリ名>/ に部署リポジトリを clone しておく
python scripts/collect.py --source local --local-root ../repos --owner <持ち主> --out data/skills.json
python scripts/render.py
open docs/index.html
```
