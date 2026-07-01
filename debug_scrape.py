from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(user_agent=(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ))
    page.goto("https://lovecul.dmm.co.jp/tl/-/ranking-all/=/submedia=voice/sort=popular/term=h24/",
              wait_until="domcontentloaded", timeout=90000)
    time.sleep(3)
    try:
        page.click("text=はい", timeout=5000)
        print("年齢認証クリック成功")
    except Exception as e:
        print(f"年齢認証クリック失敗: {e}")
    time.sleep(5)

    print(f"現在のURL: {page.url}")
    soup = BeautifulSoup(page.content(), "html.parser")
    print(f"タイトル: {soup.title.string if soup.title else 'なし'}")

    items = soup.select("li.rank-rankListItem")
    print(f"li.rank-rankListItem 件数: {len(items)}")

    # 代替セレクタも試す
    for sel in ["li[class*='rank']", "li[class*='Item']", ".rank-name", "[class*='rankList']"]:
        found = soup.select(sel)
        print(f"  {sel}: {len(found)}件")

    browser.close()
