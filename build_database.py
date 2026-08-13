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


def scrape_hobbysearch(keyword: str, db: dict):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    base_url = "https://www.1999.co.jp/search"
    params = {
        "typ1_c": "101",
        "cat": "figure",
        "target": "Item",
        "searchkey": keyword
    }

    print(f"\n🔎 Pesquisando no Hobby Search por: '{keyword}'...")
    try:
        res = requests.get(base_url, params=params, headers=headers, timeout=10)
        if res.status_code != 200:
            print(f"❌ Erro HTTP {res.status_code} ao buscar '{keyword}'")
            return
    except Exception as e:
        print(f"❌ Erro de conexão ao buscar '{keyword}': {e}")
        return

    soup = BeautifulSoup(res.text, "html.parser")

    product_links = set()
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        match = re.search(r"/(?:eng/)?(10\d{6})", href)
        if match:
            item_id = match.group(1)
            product_links.add((item_id, f"https://www.1999.co.jp/{item_id}"))

    print(f"  📌 {len(product_links)} produtos encontrados para '{keyword}'.")

    added_count = 0

    for item_id, item_url in list(product_links)[:10]:  # Limita aos 10 principais resultados por termo
        try:
            time.sleep(0.5)  # Intervalo de cortesia para não sobrecarregar o servidor
            detail_res = requests.get(item_url, headers=headers, timeout=5)
            if detail_res.status_code != 200:
                continue

            detail_soup = BeautifulSoup(detail_res.text, "html.parser")

            title_el = detail_soup.select_one("h1, .ItemTitle, title")
            title_jp = ""
            if title_el:
                title_jp = title_el.text.strip()
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

    print(f"  + {added_count} figuras salvas para '{keyword}'. Total no banco: {len(db)}.")


if __name__ == "__main__":
    db = load_json(DB_FILE, {})
    catalog = load_json(CATALOG_FILE, {})
    scraped_progress = load_json(PROGRESS_FILE, [])

    all_keywords = [char_data["name_jp"] for char_data in catalog.values() if char_data.get("name_jp")]

    # Filtra apenas os termos que ainda não foram buscados
    pending_keywords = [kw for kw in all_keywords if kw not in scraped_progress]

    print(f"📊 Total no Catálogo: {len(all_keywords)} | Já processados: {len(scraped_progress)} | Pendentes: {len(pending_keywords)}")

    if not pending_keywords:
        print("🎉 Todos os 300 personagens do catálogo já foram processados!")
    else:
        # Pega os próximos 30 personagens pendentes por rodada
        batch = pending_keywords[:30]
        print(f"🔄 Processando lote atual de {len(batch)} personagens...")

        for kw in batch:
            scrape_hobbysearch(kw, db)
            scraped_progress.append(kw)

        save_json(DB_FILE, db)
        save_json(PROGRESS_FILE, scraped_progress)
        print(f"\n✅ Lote concluído com sucesso! Salvo em '{DB_FILE}'.")
