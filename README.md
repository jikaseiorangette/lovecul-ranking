# らぶカル ランキング分析

らぶカル（DMM TL/乙女向けボイス）の24時間ランキングを毎日23:30頃に自動取得・分析するサイトです。

## サイト

https://jikaseiorangette.github.io/lovecul-ranking/

## データソース

- ランキング: https://lovecul.dmm.co.jp/tl/-/ranking-all/=/submedia=voice/sort=popular/term=h24/
- 新着: https://lovecul.dmm.co.jp/tl/-/list/=/media=voice/sort=date/

## 構成

```
lovecul-ranking/
├── scraper.py              # スクレイパー本体
├── requirements.txt
├── .github/workflows/
│   └── scrape.yml          # 毎日23:30自動実行
├── data/                   # スクレイパーが生成するデータ
│   ├── latest.json         # 最新ランキング
│   ├── history.json        # ランキング履歴
│   ├── work_meta.json      # 作品メタデータ
│   ├── graph.json          # グラフデータ
│   └── meta.json           # 統計データ
└── docs/                   # GitHub Pages配信用
    ├── index.html
    └── data/
```
