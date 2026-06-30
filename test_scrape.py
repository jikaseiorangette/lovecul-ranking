from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import time, re

def test():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ))

        # 年齢認証（一度だけ）
        page.goto("https://lovecul.dmm.co.jp/tl/-/ranking-all/=/submedia=voice/sort=popular/term=h24/",
                  wait_until="domcontentloaded", timeout=60000)
        time.sleep(3)
        page.click("text=はい", timeout=5000)
        time.sleep(5)

        # ランキング全件取得テスト
        soup = BeautifulSoup(page.content(), "html.parser")
        items = soup.select("li.rank-rankListItem")
        print(f"ランキング取得件数: {len(items)}")
        for item in items[:5]:
            cid = ""
            link = item.find("a", href=re.compile(r"cid="))
            if link:
                m = re.search(r"cid=(d_\w+)", link["href"])
                cid = m.group(1) if m else ""
            title = item.select_one("b.rank-name")
            title = title.get_text(strip=True) if title else ""
            texts = [t.strip() for t in item.select_one("div.rank-txtContent").stripped_strings] if item.select_one("div.rank-txtContent") else []
            img = item.select_one("div.rank-imgContent img")
            thumb = img.get("src","") if img else ""
            print(f"cid={cid} title={title[:30]} texts={texts[:4]} thumb={thumb[:60]}")

        # 新着ページ構造確認
        print("\n=== 新着ページ ===")
        page.goto("https://lovecul.dmm.co.jp/tl/-/list/=/media=voice/sort=date/",
                  wait_until="domcontentloaded", timeout=60000)
        time.sleep(5)
        soup2 = BeautifulSoup(page.content(), "html.parser")

        # よくある商品リストセレクタを試す
        for sel in ["li.productListItem", "li.tileListItem", "ul.productList li", "div.productListArea li", ".productList li"]:
            items2 = soup2.select(sel)
            if items2:
                print(f"新着セレクタ '{sel}': {len(items2)}件")
                item2 = items2[0]
                texts2 = [t.strip() for t in item2.stripped_strings if t.strip()]
                print(f"  テキスト: {texts2[:6]}")
                links2 = item2.select("a[href*='cid=']")
                if links2:
                    print(f"  href: {links2[0]['href'][:80]}")
                break

        browser.close()

test()
