import json
import os
import re
import requests
from bs4 import BeautifulSoup

DB_FILE = "database/figures.json"


def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_db(data):
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def scrape_hobbysearch(keyword: str):
    """Busca figures no 1999.co.jp e extrai JAN, preço de tabela (MSRP) e fabricante."""
    db = load_db()
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    url = f"https://www.1999.co.jp/search?typ1_c=102&cat=gundam&target=Item&searchkey={keyword}"

    print(f"🔎 Pesquisando no Hobby Search por: '{keyword}'...")
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code != 200:
            print(f"❌ Erro na requisição: {res.status_code}")
            return
    except Exception as e:
        print(f"❌ Erro de conexão: {e}")
        return

    soup = BeautifulSoup(res.text, "html.parser")
    items = soup.select(".MasterGrid_itemInfo__3L6sX, .Table_MasterGrid__29A_d tr")

    added_count = 0

    for item in items:
        link = item.select_one("a")
        if not link or "1999.co.jp/" not in link.get("href", ""):
            continue

        item_url = link["href"]
        if not item_url.startswith("http"):
            item_url = f"https://www.1999.co.jp{item_url}"

        try:
            detail_res = requests.get(item_url, headers=headers, timeout=5)
            if detail_res.status_code != 200:
                continue

            detail_soup = BeautifulSoup(detail_res.text, "html.parser")

            title_el = detail_soup.select_one("h1, .ItemTitle")
            title_jp = title_el.text.strip() if title_el else ""

            jan_code = None
            page_text = detail_soup.get_text()
            jan_match = re.search(r"\b(45\d{11}|49\d{11})\b", page_text)
            if jan_match:
                jan_code = jan_match.group(1)

            msrp_yen = None
            price_match = re.search(r"¥\s*([\d,]+)", page_text)
            if price_match:
                msrp_yen = int(price_match.group(1).replace(",", ""))

            key = jan_code if jan_code else item_url.split("/")[-1]

            db[key] = {
                "jan_code": jan_code,
                "title_jp": title_jp,
                "msrp_yen": msrp_yen,
                "url": item_url,
            }
            added_count += 1
            print(f"  + Salvo: {title_jp[:30]}... | MSRP: ¥{msrp_yen}")

        except Exception:
            continue

    save_db(db)
    print(f"✅ Concluído! {added_count} figuras salvas no banco de dados.")


if __name__ == "__main__":
    keywords = [
        "初音ミク",  # Hatsune Miku
        "アンタークチサイト",  # Antarcticite
        "ルフィ",  # Luffy
        "ガッツ",  # Guts (Berserk)
        "チェンソーマン",  # Chainsaw Man
        "アルティメットまどか",  # Ultimate Madoka
    ]

    for kw in keywords:
        scrape_hobbysearch(kw)
