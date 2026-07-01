# scraper.py
# らぶカル（DMM TL/乙女向け）ランキングをスクレイプし、JSONと静的HTMLを生成する

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import json
import re
import time
import csv as csv_module
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))

def now_jst():
    return datetime.now(JST)

RANKING_URL = "https://lovecul.dmm.co.jp/tl/-/ranking-all/=/submedia=voice/sort=popular/term=h24/"
NEW_WORKS_URL = "https://lovecul.dmm.co.jp/tl/-/list/=/media=voice/sort=date/"
AGE_CHECK_URL = "https://lovecul.dmm.co.jp/tl/-/ranking-all/=/submedia=voice/sort=popular/term=h24/"

DATA_DIR = Path("data")
DOCS_DATA_DIR = Path("docs") / "data"

# ----------------------------------------
# 年齢認証
# ----------------------------------------

def pass_age_check(page, url):
    page.goto(url, wait_until="domcontentloaded", timeout=90000)
    time.sleep(5)
    try:
        page.click("text=はい", timeout=8000)
        print(" 年齢認証: クリック成功")
        time.sleep(5)
    except:
        print(" 年齢認証: スキップ（不要または失敗）")
    # 年齢認証後にコンテンツが読み込まれるまで待機
    try:
        page.wait_for_selector("li.rank-rankListItem", timeout=20000)
        print(" 年齢認証後コンテンツ確認OK")
    except:
        print(" 年齢認証後コンテンツ待機タイムアウト（続行）")

# ----------------------------------------
# スクレイピング
# ----------------------------------------

def fetch_ranking(page):
    print(f" ランキング取得中: {RANKING_URL}")
    for attempt in range(3):
        try:
            page.goto(RANKING_URL, wait_until="domcontentloaded", timeout=90000)
            break
        except Exception as e:
            print(f" 失敗({attempt+1}/3): {e}")
            if attempt < 2:
                time.sleep(10)
            else:
                raise
    # 年齢認証が再表示された場合に再クリック
    try:
        page.click("text=はい", timeout=5000)
        print(" ランキングページ: 年齢認証再クリック")
        time.sleep(5)
    except:
        pass
    # コンテンツが読み込まれるまで待機
    try:
        page.wait_for_selector("li.rank-rankListItem", timeout=20000)
    except:
        print(" セレクタ待機タイムアウト")
    time.sleep(3)

    soup = BeautifulSoup(page.content(), "html.parser")
    works = []

    items = soup.select("li.rank-rankListItem")
    for item in items:
        if len(works) >= 30:
            break

        # cid
        link = item.find("a", href=re.compile(r"cid="))
        if not link:
            continue
        m = re.search(r"cid=(d_\w+)", link["href"])
        if not m:
            continue
        cid = m.group(1)
        work_url = f"https://lovecul.dmm.co.jp/tl/-/detail/=/cid={cid}/"

        # 順位
        rank_el = item.select_one(".rank-num, .rank-rankNum, [class*='rankNum'], [class*='rank-num']")
        rank = len(works) + 1

        # タイトル
        title_el = item.select_one("b.rank-name")
        title = title_el.get_text(strip=True) if title_el else ""

        # サークル・声優
        txt_el = item.select_one("div.rank-txtContent")
        circle = ""
        cv = ""
        if txt_el:
            texts = [t.strip() for t in txt_el.stripped_strings if t.strip()]
            # 構造: [商品種別?, タイトル?, サークル, '/', 声優, ...]
            for i, t in enumerate(texts):
                if t == "/" and i > 0 and i < len(texts) - 1:
                    circle = texts[i-1]
                    cv = texts[i+1]
                    break
            if not circle and len(texts) >= 1:
                circle = texts[0]

        # サムネイル
        img_el = item.select_one("div.rank-imgContent img")
        thumb_url = ""
        if img_el:
            thumb_url = img_el.get("src", "") or img_el.get("data-src", "")
            if thumb_url and not thumb_url.startswith("http"):
                thumb_url = "https:" + thumb_url

        # ジャンル（タグ）
        genre_els = item.select("a[href*='keyword']") or item.select(".rank-genre a") or []
        genres = [g.get_text(strip=True) for g in genre_els if g.get_text(strip=True)]

        # セール
        is_sale = bool(item.select_one("[class*='sale'], [class*='discount']"))

        # 発売日
        release_date = ""
        text_all = item.get_text()
        m_date = re.search(r'(\d{4})[/年](\d{1,2})[/月](\d{1,2})', text_all)
        if m_date:
            release_date = f"{m_date.group(1)}-{int(m_date.group(2)):02d}-{int(m_date.group(3)):02d}"

        if not title:
            continue

        works.append({
            "rank": rank,
            "cid": cid,
            "title": title,
            "circle": circle,
            "cv": cv,
            "release_date": release_date,
            "thumb_url": thumb_url,
            "genres": genres[:5],
            "is_sale": is_sale,
            "work_url": work_url,
        })
        print(f" {rank}位: {title[:40]}")

    print(f" {len(works)}件取得")
    return works


def fetch_new_works(page, work_meta, today):
    """新着一覧から新作を取得し、発売日をwork_metaに登録する"""
    print(f" 新着一覧取得中: {NEW_WORKS_URL}")
    try:
        page.goto(NEW_WORKS_URL, wait_until="domcontentloaded", timeout=60000)
        # 年齢認証が再表示された場合に再クリック
        try:
            page.click("text=はい", timeout=5000)
            print(" 新着ページ: 年齢認証再クリック")
            time.sleep(5)
        except:
            pass
        page.wait_for_selector("ul.productList li", timeout=20000)
        time.sleep(3)
    except Exception as e:
        print(f" 新着ページアクセス失敗: {e}")
        return work_meta

    soup = BeautifulSoup(page.content(), "html.parser")
    updated = 0

    for item in soup.select("ul.productList li"):
        link = item.find("a", href=re.compile(r"cid="))
        if not link:
            continue
        m = re.search(r"cid=(d_\w+)", link["href"])
        if not m:
            continue
        cid = m.group(1)

        texts = [t.strip() for t in item.stripped_strings if t.strip()]
        title = texts[1] if len(texts) > 1 else texts[0] if texts else ""

        if cid not in work_meta:
            work_meta[cid] = {}

        if "registered_date" not in work_meta[cid]:
            work_meta[cid]["registered_date"] = today
            updated += 1

        if "release_date" not in work_meta[cid]:
            # 発売日をテキストから探す
            text_all = item.get_text()
            m_date = re.search(r'(\d{4})[/年](\d{1,2})[/月](\d{1,2})', text_all)
            if m_date:
                work_meta[cid]["release_date"] = f"{m_date.group(1)}-{int(m_date.group(2)):02d}-{int(m_date.group(3)):02d}"
            else:
                work_meta[cid]["release_date"] = today

        if title:
            work_meta[cid]["title"] = title

    print(f" 新着登録: {updated}件（累計: {len(work_meta)}件）")
    return work_meta


# ----------------------------------------
# データ管理
# ----------------------------------------

def load_work_meta():
    path = DATA_DIR / "work_meta.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}

def save_work_meta(work_meta):
    DATA_DIR.mkdir(exist_ok=True)
    path = DATA_DIR / "work_meta.json"
    path.write_text(json.dumps(work_meta, ensure_ascii=False, indent=2), encoding="utf-8")

def load_history():
    path = DATA_DIR / "history.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}

def save_history(history):
    DATA_DIR.mkdir(exist_ok=True)
    path = DATA_DIR / "history.json"
    path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")

def update_history(history, today, works):
    if "ranking" not in history:
        history["ranking"] = {}

    today_ranked = {w["cid"]: w["rank"] for w in works}

    all_tracked = set()
    for day_data in history["ranking"].values():
        all_tracked.update(day_data.keys())

    today_data = {}
    for cid in all_tracked:
        today_data[cid] = today_ranked.get(cid, 31)
    for cid, rank in today_ranked.items():
        today_data[cid] = rank

    history["ranking"][today] = today_data
    return history

def save_latest(works):
    DATA_DIR.mkdir(exist_ok=True)
    DOCS_DATA_DIR.mkdir(parents=True, exist_ok=True)
    json_str = json.dumps(works, ensure_ascii=False, indent=2)
    (DATA_DIR / "latest.json").write_text(json_str, encoding="utf-8")
    (DOCS_DATA_DIR / "latest.json").write_text(json_str, encoding="utf-8")

def get_all_works_count():
    path = DATA_DIR / "all_works.csv"
    if not path.exists():
        return 0
    with path.open(encoding="utf-8-sig") as f:
        return sum(1 for _ in csv_module.DictReader(f))

def build_graph_data(history, cids, today):
    today_dt = datetime.strptime(today, "%Y-%m-%d")
    dates = [(today_dt - timedelta(days=29 - i)).strftime("%Y-%m-%d") for i in range(30)]
    ranking_history = history.get("ranking", {})

    graph = {}
    for cid in cids:
        first_date = None
        for d in dates:
            if cid in ranking_history.get(d, {}):
                first_date = d
                break

        ranks = []
        for d in dates:
            day_data = ranking_history.get(d, {})
            if cid in day_data:
                ranks.append(day_data[cid])
            elif first_date and d > first_date:
                ranks.append(31)
            else:
                ranks.append(None)

        graph[cid] = {"labels": dates, "ranks": ranks}

    return graph


# ----------------------------------------
# HTML生成
# ----------------------------------------

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>らぶカル ランキング分析</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+JP:wght@400;500&family=Noto+Sans+JP:wght@400;500&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root{
--rose-50:#fff1f4;--rose-100:#fde0e7;--rose-600:#d4386f;
--rose-800:#8b1a42;--mauve-50:#fdf4f8;
--text-main:#3a1628;--text-sub:#8b4f6a;--text-muted:#b8829a;
--border:#f0c4d8;--border-light:#fae0ec;
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Noto Sans JP',sans-serif;background:var(--rose-50);color:var(--text-main);min-height:100vh}
.site-wrap{max-width:1200px;margin:0 auto;padding:20px 16px 60px}
.header{display:flex;align-items:center;gap:14px;padding:16px 24px;background:#fff;border:0.5px solid var(--border);border-radius:16px;margin-bottom:20px}
.header-icon{width:38px;height:38px;border-radius:50%;background:var(--rose-100);display:flex;align-items:center;justify-content:center;font-size:18px}
.header-title{font-family:'Noto Serif JP',serif;font-size:18px;font-weight:500;color:var(--rose-800);letter-spacing:.04em}
.header-sub{font-size:12px;font-weight:500;color:var(--rose-600);margin-top:3px;letter-spacing:.02em;border-left:2.5px solid var(--rose-600);padding-left:7px}
.header-update{margin-left:auto;font-size:11px;color:var(--rose-600);background:var(--rose-50);border:0.5px solid var(--border);border-radius:20px;padding:5px 12px;white-space:nowrap}
.stat-row{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:20px}
.stat-card{background:#fff;border:0.5px solid var(--border);border-radius:14px;padding:14px 16px}
.stat-label{font-size:11px;color:var(--text-muted);margin-bottom:6px}
.stat-value{font-family:'Noto Serif JP',serif;font-size:26px;font-weight:500;color:var(--rose-800)}
.stat-sub{font-size:10px;color:var(--text-muted);margin-top:3px}
.section{margin-bottom:28px}
.section-head{display:flex;align-items:center;gap:8px;margin-bottom:12px}
.section-title{font-family:'Noto Serif JP',serif;font-size:15px;font-weight:500;color:var(--rose-800)}
.section-badge{font-size:10px;background:var(--rose-100);color:var(--rose-600);border:0.5px solid var(--border);border-radius:20px;padding:2px 9px}
.table-card{background:#fff;border:0.5px solid var(--border);border-radius:16px;overflow:hidden}
table{width:100%;border-collapse:collapse;font-size:12px;table-layout:fixed}
thead th{background:var(--mauve-50);color:var(--rose-800);font-weight:500;padding:10px 8px;border-bottom:0.5px solid var(--border-light);text-align:left;font-size:11px}
tbody td{padding:6px 8px;border-bottom:0.5px solid var(--border-light);vertical-align:top}
tbody td.thumb-wrap{vertical-align:middle}
tbody tr:last-child td{border-bottom:none}
tbody tr:hover td{background:var(--rose-50)}
.rb{display:inline-flex;align-items:center;justify-content:center;width:24px;height:24px;border-radius:50%;font-size:11px;font-weight:500}
.r1{background:#fef3c7;color:#92400e;border:0.5px solid #fde68a}
.r2{background:#f1f5f9;color:#475569;border:0.5px solid #e2e8f0}
.r3{background:#fef0e6;color:#9a3412;border:0.5px solid #fed7aa}
.rn{background:var(--rose-50);color:var(--text-muted);border:0.5px solid var(--border-light)}
.thumb-wrap{width:150px;min-width:150px;padding:4px 6px 4px 8px;position:relative}
.thumb-wrap img{width:146px;height:110px;object-fit:cover;border-radius:8px;border:0.5px solid var(--border-light);display:block}
.thumb-wrap a{display:block}
.thumb-rank{position:absolute;top:7px;left:11px;z-index:1}
.title-cell{padding-left:8px !important}
.work-title{font-weight:500;color:var(--rose-800);font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.work-title a{color:var(--rose-800);text-decoration:none}
.work-title a:hover{color:var(--rose-600);text-decoration:underline}
.work-meta{font-size:10px;color:var(--text-muted);margin-top:2px}
.genres{display:flex;flex-wrap:wrap;gap:3px;margin-top:3px}
.gtag{display:inline-block;font-size:9px;background:var(--rose-50);color:var(--text-muted);border:0.5px solid var(--border-light);border-radius:20px;padding:1px 6px;white-space:nowrap}
.gtag-sale{background:#ecfdf5;color:#065f46;border-color:#6ee7b7}
.tnew{display:inline-flex;align-items:center;gap:2px;background:#ecfdf5;color:#065f46;border:0.5px solid #6ee7b7;border-radius:20px;padding:2px 7px;font-size:10px;font-weight:500}
.tup{font-size:11px;font-weight:500;color:#be123c}
.tdn{font-size:11px;font-weight:500;color:#0369a1}
.tsm{font-size:11px;color:var(--text-muted)}
.chart-cell{width:240px}
.chart-wrap{width:100%;height:80px}
.no-data{font-size:11px;color:var(--text-muted)}
.footer{text-align:center;margin-top:40px;font-size:11px;color:var(--text-muted);padding-top:20px;border-top:0.5px solid var(--border-light)}
@media(max-width:640px){
.site-wrap{padding:10px 8px 40px}
.header{padding:10px 12px;gap:8px;flex-wrap:wrap}
.header-title{font-size:13px}
.header-update{font-size:9px;padding:3px 8px;margin-left:0;width:100%}
.stat-row{gap:5px}
.stat-card{padding:8px 6px}
.stat-value{font-size:18px}
.stat-label{font-size:8px}
table{display:block}
thead{display:none}
tbody{display:flex;flex-direction:column;gap:6px;padding:6px}
tbody tr{display:grid;grid-template-columns:110px 1fr;background:#fff;border:0.5px solid var(--border);border-radius:10px;overflow:hidden;padding:0}
tbody td{border-bottom:none;padding:0;width:auto !important}
tbody tr:hover td{background:transparent}
.thumb-wrap{grid-column:1;grid-row:1/4;width:110px !important;min-width:110px;padding:6px 4px 6px 6px;position:relative}
.thumb-wrap img{width:100px;height:75px;border-radius:6px;object-fit:cover}
.thumb-rank{top:9px;left:9px}
.title-cell{grid-column:2;grid-row:1;padding:6px 8px 2px 4px !important}
.work-title{font-size:11px;white-space:normal;line-height:1.3}
.chart-cell{grid-column:1/3;grid-row:4;width:100% !important}
.chart-wrap{height:72px;padding:0 4px 6px}
}
</style>
</head>
<body>
<div class="site-wrap">
<div class="header">
<div class="header-icon">💕</div>
<div>
<div class="header-title">らぶカル ランキング分析</div>
<div class="header-sub">TL/乙女向けボイス作品データ（24時間）</div>
</div>
<div class="header-update">🔄 毎日23:30頃更新 ／ $today_str</div>
</div>
<div class="stat-row">
<div class="stat-card">
<div class="stat-label">📦 収録作品数</div>
<div class="stat-value">$total_works</div>
<div class="stat-sub">追跡作品数</div>
</div>
<div class="stat-card">
<div class="stat-label">✨ 新着</div>
<div class="stat-value">$new_today</div>
<div class="stat-sub">$today_str</div>
</div>
<div class="stat-card">
<div class="stat-label">🔥 セール中</div>
<div class="stat-value">$sale_count</div>
<div class="stat-sub">本日ランキング内</div>
</div>
</div>
<div class="section">
<div class="section-head">
<span style="font-size:16px">🏆</span>
<span class="section-title">本日のランキング</span>
<span class="section-badge">TOP 10</span>
</div>
<div class="table-card">
<table>
<colgroup>
<col style="width:150px">
<col style="width:auto">
<col style="width:10%">
<col style="width:7%">
<col style="width:28%">
</colgroup>
<thead>
<tr><th></th><th>タイトル / 発売日 / サークル / ジャンル</th><th>声優</th><th>推移</th><th class="chart-cell">推移グラフ（30日）</th></tr>
</thead>
<tbody>
$ranking_rows
</tbody>
</table>
</div>
</div>
<div class="footer">
らぶカル ランキング分析 ／ データは毎日23:30頃に自動更新されます<br>
※ 本サイトはらぶカル（DMM TL/乙女向け）のデータを使用しています
</div>
</div>
<script>
const graphData = $graph_data_json;
const PINK = '#e8528a';
function drawChart(canvasId, cid) {
const ctx = document.getElementById(canvasId);
if (!ctx) return;
const d = graphData[cid];
if (!d) { ctx.parentElement.innerHTML = '<span class="no-data">データ蓄積中</span>'; return; }
const disp = d.ranks.map(v => (v === null || v === undefined) ? null : (v > 14 ? 15 : v));
const nonNull = d.ranks.filter(v => v !== null);
const isSingle = nonNull.length === 1;
new Chart(ctx, {
type: 'line',
data: {
labels: d.labels,
datasets: [{
data: disp,
borderColor: PINK,
backgroundColor: 'transparent',
borderWidth: 1.5,
pointRadius: isSingle ? 5 : 2,
pointHoverRadius: 6,
pointBackgroundColor: PINK,
fill: false,
tension: 0.4,
spanGaps: false,
}]
},
options: {
responsive: true,
maintainAspectRatio: false,
layout: { padding: { top: 6, left: 2 } },
interaction: { mode: 'index', intersect: false },
scales: {
y: {
reverse: true, min: -1, max: 17,
ticks: {
font: { size: 11 }, color: '#b8829a',
callback: v => v===1?'1位':v===5?'5位':v===10?'10位':v===15?'圏外':null
},
beforeFit: axis => {
axis.ticks = [{value:1,label:'1位'},{value:5,label:'5位'},{value:10,label:'10位'},{value:15,label:'圏外'}];
},
grid: { color: 'rgba(232,82,138,0.07)' },
border: { display: false }
},
x: {
ticks: { font: { size: 9 }, color: '#b8829a', maxTicksLimit: 4 },
grid: { display: false }, border: { display: false }
}
},
plugins: {
legend: { display: false },
tooltip: {
callbacks: {
label: c => {
const raw = d.ranks[c.dataIndex];
if (raw === null || raw === undefined) return '';
return raw > 30 ? '圏外' : raw + '位';
}
},
titleFont: { size: 11 }, bodyFont: { size: 12 }, padding: 8,
backgroundColor: 'rgba(139,26,66,0.85)',
titleColor: '#fde0e7', bodyColor: '#fff',
}
}
}
});
}
document.querySelectorAll('canvas[data-cid]').forEach(c => drawChart(c.id, c.dataset.cid));
</script>
</body>
</html>
"""

def rank_badge(rank):
    cls = {1: "r1", 2: "r2", 3: "r3"}.get(rank, "rn")
    return f'<span class="rb {cls}">{rank}</span>'

def change_html(rank_change, is_new):
    if is_new:
        return '<span class="tnew">🆕 新着</span>'
    if rank_change and rank_change > 0:
        return f'<span class="tup">▲{rank_change}</span>'
    if rank_change and rank_change < 0:
        return f'<span class="tdn">▼{abs(rank_change)}</span>'
    return '<span class="tsm">－</span>'

def make_row(w, rank_change, is_new, canvas_id):
    rb = rank_badge(w["rank"])
    thumb = w.get("thumb_url", "")
    img_html = f'<img src="{thumb}" alt="" loading="lazy">' if thumb else '<div style="width:146px;height:110px;background:var(--rose-50);border-radius:8px;"></div>'
    ch = change_html(rank_change, is_new)

    tags = []
    if w.get("is_sale"):
        tags.append('<span class="gtag gtag-sale">セール中</span>')
    for g in w.get("genres", [])[:4]:
        tags.append(f'<span class="gtag">{g}</span>')
    tags_html = f'<div class="genres">{"".join(tags)}</div>' if tags else ""

    release = w.get("release_date", "")
    release_span = f'<span>発売日: {release}　</span>' if release else ""

    return f"""<tr>
  <td class="thumb-wrap">
    <span class="thumb-rank">{rb}</span>
    <a href="{w['work_url']}" target="_blank" rel="noopener">{img_html}</a>
  </td>
  <td class="title-cell">
    <div class="work-title"><a href="{w['work_url']}" target="_blank" rel="noopener">{w['title']}</a></div>
    <div class="work-meta">{release_span}{w.get('circle','')}</div>
    {tags_html}
  </td>
  <td style="font-size:11px;color:var(--text-sub)">{w.get('cv','')}</td>
  <td>{ch}</td>
  <td class="chart-cell"><canvas id="{canvas_id}" class="chart-wrap" data-cid="{w['cid']}"></canvas></td>
</tr>"""

def generate_html(works, graph_data, today_str, total_works, new_today, work_meta, today):
    top10 = works[:10]

    prev_map = {}
    today_dt = datetime.strptime(today, "%Y-%m-%d")
    prev_date = (today_dt - timedelta(days=1)).strftime("%Y-%m-%d")
    for cid, gd in graph_data.items():
        if prev_date in gd["labels"]:
            idx = gd["labels"].index(prev_date)
            v = gd["ranks"][idx]
            if v and v <= 30:
                prev_map[cid] = v

    ranking_rows = []
    for i, w in enumerate(top10):
        cid = w["cid"]
        prev = prev_map.get(cid, 0)
        rank_change = (prev - w["rank"]) if prev else 0
        is_new = work_meta.get(cid, {}).get("release_date") == today
        ranking_rows.append(make_row(w, rank_change, is_new, f"wc_{i+1}"))

    sale_count = sum(1 for w in top10 if w.get("is_sale"))

    from string import Template
    html = Template(HTML_TEMPLATE).safe_substitute(
        today_str=today_str,
        total_works=total_works,
        new_today=new_today,
        sale_count=sale_count,
        ranking_rows="\n".join(ranking_rows),
        graph_data_json=json.dumps(graph_data, ensure_ascii=False),
    )
    return html


# ----------------------------------------
# メイン
# ----------------------------------------

def run():
    today = now_jst().strftime("%Y-%m-%d")
    today_str = now_jst().strftime("%Y/%m/%d")
    print(f"\n=== らぶカル スクレイピング開始: {today} ===")

    history = load_history()
    work_meta = load_work_meta()

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ))

        # 年齢認証クッキーを事前にセット（ボタンクリック不要にする）
        for cookie_name in ["age_check_done", "ckcy"]:
            for domain in [".dmm.co.jp", "lovecul.dmm.co.jp"]:
                context.add_cookies([{
                    "name": cookie_name,
                    "value": "1",
                    "domain": domain,
                    "path": "/",
                }])
        print(" 年齢認証クッキーセット完了")

        # 年齢認証（クッキーで突破できなかった場合の保険）
        page = context.new_page()
        pass_age_check(page, AGE_CHECK_URL)

        # 新着取得（同じページオブジェクトを使い回してCookieを維持）
        pids_before = set(work_meta.keys())
        work_meta = fetch_new_works(page, work_meta, today)
        save_work_meta(work_meta)
        new_pids_today = set(work_meta.keys()) - pids_before

        # ランキング取得
        works = fetch_ranking(page)
        browser.close()

    if not works:
        print("取得データなし・終了")
        return

    # work_metaから発売日を付与
    for w in works:
        cid = w["cid"]
        meta = work_meta.get(cid, {})
        if not w.get("release_date") and meta.get("release_date"):
            w["release_date"] = meta["release_date"]

    # 履歴更新
    history = update_history(history, today, works)
    save_history(history)
    save_latest(works)

    # グラフデータ（TOP10）
    top10_cids = [w["cid"] for w in works[:10]]
    graph_data = build_graph_data(history, top10_cids, today)
    graph_json = json.dumps(graph_data, ensure_ascii=False)
    DATA_DIR.mkdir(exist_ok=True)
    DOCS_DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "graph.json").write_text(graph_json, encoding="utf-8")
    (DOCS_DATA_DIR / "graph.json").write_text(graph_json, encoding="utf-8")

    # 統計
    total_works = get_all_works_count() or len(work_meta)
    new_today = sum(1 for w in works if work_meta.get(w["cid"], {}).get("release_date") == today)
    new_work_ids = [w["cid"] for w in works if work_meta.get(w["cid"], {}).get("release_date") == today]

    meta = {
        "updated": today_str,
        "total_works": total_works,
        "new_today": new_today,
        "new_work_ids": new_work_ids,
    }
    meta_json = json.dumps(meta, ensure_ascii=False)
    (DATA_DIR / "meta.json").write_text(meta_json, encoding="utf-8")
    (DOCS_DATA_DIR / "meta.json").write_text(meta_json, encoding="utf-8")

    # HTML生成
    html = generate_html(works, graph_data, today_str, total_works, new_today, work_meta, today)
    docs_dir = Path("docs")
    docs_dir.mkdir(exist_ok=True)
    (docs_dir / "index.html").write_text(html, encoding="utf-8")
    print(f"\n[OK] docs/index.html 生成完了")

if __name__ == "__main__":
    run()
