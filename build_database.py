import json
import os
import re
import time
import cloudscraper
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
    scraper = cloudscraper.create_scraper()
    
    headers = {
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
            res = scraper.post(url, json={"query": query, "variables": variables}, headers=headers, timeout=15)
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


def scrape_mfc(keyword: str, db: dict):
    # Cria o scraper inteligente que passa pela Cloudflare
    scraper = cloudscraper.create_scraper()
    search_url = f"https://myfigurecollection.net/browse.dialog.php?mode=search&page=1&keyword={keyword}"

    print(f"🔎 Buscando no MFC para: '{keyword}'...")
    try:
        res = scraper.get(search_url, timeout=15)
        if res.status_code != 200:
            print(f"    [!] Erro HTTP {res.status_code} na busca do MFC")
            return
    except Exception as e:
        print(f"    [!] Falha de conexão: {e}")
        return

    soup = BeautifulSoup(res.text, "html.parser")
    items = soup.select(".item-icon a")

    print(f"  📌 {len(items)} resultados encontrados no MFC.")

    added_count = 0
    for item in items[:6]:
        item_href = item.get("href", "")
        if not item_href.startswith("/item/"):
            continue

        item_url = f"https://myfigurecollection.net{item_href}"
        item_id = item_href.split("/")[2]

        try:
            time.sleep(1.0)
            detail_res = scraper.get(item_url, timeout=15)
            if detail_res.status_code != 200:
                continue

            detail_soup = BeautifulSoup(detail_res.text, "html.parser")
            
            title_el = detail_soup.select_one("h1[itemprop='name']")
            title_jp = title_el.text.strip() if title_el else ""

            if not title_jp:
                continue

            jan_code = None
            msrp_yen = None

            for data_row in detail_soup.select(".form-field"):
                label = data_row.select_one("label")
                value = data_row.select_one(".form-value")
                if label and value:
                    lbl_text = label.text.strip().lower()
                    val_text = value.text.strip()

                    if "jan" in lbl_text or "barcode" in lbl_text:
                        jan_match = re.search(r"\d{13}", val_text)
                        if jan_match:
                            jan_code = jan_match.group(0)

                    elif "price" in lbl_text:
                        price_match = re.search(r"¥\s*([\d,]+)", val_text)
                        if price_match:
                            msrp_yen = int(price_match.group(1).replace(",", ""))

            key = jan_code if jan_code else f"MFC_{item_id}"

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

    all_keywords = [char_data["name_en"] for char_data in catalog.values() if char_data.get("name_en")]
    pending_keywords = [kw for kw in all_keywords if kw not in scraped_progress]

    print(f"📊 Progresso do Banco: {len(scraped_progress)}/{len(all_keywords)} personagens já processados.")

    if not pending_keywords:
        print("🎉 Todos os 300 personagens do catálogo já foram raspados!")
    else:
        batch = pending_keywords[:25]
        print(f"🔄 Executando raspagem para o lote de {len(batch)} personagens (via MFC com Cloudscraper)...\n")

        for kw in batch:
            scrape_mfc(kw, db)
            scraped_progress.append(kw)

        save_json(DB_FILE, db)
        save_json(PROGRESS_FILE, scraped_progress)
        print(f"\n✅ Lote concluído com sucesso!")
