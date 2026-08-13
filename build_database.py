import json
import os
import re
import time
import requests
from bs4 import BeautifulSoup

DB_FILE = "database/figures.json"
CATALOG_FILE = "database/character_index.json"
PROGRESS_FILE = "database/scraped_keywords.json"


def load_json(filepath, default):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default
    return default


def save_json(filepath, data):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def fetch_top_300_characters():
    catalog = {}
    url = "https://graphql.anilist.co"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    query = """
    query ($page: Int, $perPage: Int) {
      Page(page: $page, perPage: $perPage) {
        characters(sort: [FAVOURITES_DESC]) {
          id
          name {
            full
            native
          }
        }
      }
    }
    """

    print("🌐 Baixando ranking dos Top 300 Personagens via AniList API...")
    for page in range(1, 7):
        variables = {"page": page, "perPage": 50}
        try:
            res = requests.post(url, json={"query": query, "variables": variables}, headers=headers, timeout=10)
            if res.status_code == 200:
                data = res.json()
                characters = data.get("data", {}).get("Page", {}).get("characters", [])
                for char in characters:
                    char_id = str(char["id"])
                    name_en = char.get("name", {}).get("full", "")
                    name_jp = char.get("name", {}).get("native", "")
                    if name_jp:
                        catalog[char_id] = {"anilist_id": char_id, "name_en": name_en, "name_jp": name_jp}
            time.sleep(0.3)
        except Exception:
            pass

    save_json(CATALOG_FILE, catalog)
    return catalog


def scrape_hobbysearch(keyword: str, db: dict):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }

    # RESTAURADO: Parâmetros corretos da busca de figures
    base_url = "https://www.1999.co.jp/search"
    params = {
        "typ1_c": "101",
        "cat": "figure",
        "target": "Item",
        "searchkey": keyword
    }

    print(f"🔎 Buscando figures para: '{keyword}'...")
    try:
        res = requests.get(base_url, params=params, headers=headers, timeout=10)
        if res.status_code != 200:
            return
    except Exception:
        return

    soup = BeautifulSoup(res.text, "html.parser")

    # RESTAURADO: O Extrator de links correto
    product_links = set()
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        match = re.search(r"/(?:eng/)?(10\d{6,7})", href)
        if match:
            item_id = match.group(1)
            product_links.add((item_id, f"https://www.1999.co.jp/{item_id}"))

    print(f"  📌 {len(product_links)} resultados encontrados.")

    added_count = 0
    for item_id, item_url in list(product_links)[:8]:
        try:
            time.sleep(0.4)
            detail_res = requests.get(item_url, headers=headers, timeout=5)
            if detail_res.status_code != 200:
                continue

            detail_soup = BeautifulSoup(detail_res.text, "html.parser")
            title_el = detail_soup.select_one("h1, .ItemTitle, title")
            title_jp = title_el.text.strip() if title_el else ""
            title_jp = re.sub(r"\s*\|\s*HobbySearch.*$", "", title_jp, flags=re.IGNORECASE)

            if not title_jp:
                continue

            page_text = detail_soup.get_text()
            
            jan_code = None
            jan_match = re.search(r"\b(45\d{11}|49\d{11})\b", page_text)
            if jan_match:
                jan_code = jan_match.group(1)

            msrp_yen = None
            price_match = re.search(r"¥\s*([\d,]+)", page_text)
            if price_match:
                msrp_yen = int(price_match.group(1).replace(",", ""))

            key = jan_code if jan_code else f"HS_{item_id}"

            db[key] = {
                "jan_code": jan_code,
                "title_jp": title_jp,
                "msrp_yen": msrp_yen,
                "url": item_url,
            }
            added_count += 1
        except Exception:
            continue

    print(f"  └ Salvas {added_count} figuras. Banco agora tem: {len(db)} itens.")


if __name__ == "__main__":
    db = load_json(DB_FILE, {})
    catalog = load_json(CATALOG_FILE, {})
    scraped_progress = load_json(PROGRESS_FILE, [])

    if not catalog or len(catalog) <= 10:
        catalog = fetch_top_300_characters()
        scraped_progress = []  

    all_keywords = [char_data["name_jp"] for char_data in catalog.values() if char_data.get("name_jp")]
    pending_keywords = [kw for kw in all_keywords if kw not in scraped_progress]

    print(f"📊 Progresso do Banco: {len(scraped_progress)}/{len(all_keywords)} personagens já processados.")

    if not pending_keywords:
        print("🎉 Todos os 300 personagens do catálogo já foram raspados!")
    else:
        batch = pending_keywords[:25]
        print(f"🔄 Executando raspagem para o lote de {len(batch)} personagens...\n")

        for kw in batch:
            scrape_hobbysearch(kw, db)
            scraped_progress.append(kw)

        save_json(DB_FILE, db)
        save_json(PROGRESS_FILE, scraped_progress)
        print(f"\n✅ Lote concluído com sucesso!")
