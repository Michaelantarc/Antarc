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
    """Consulta a API do AniList e gera o índice com os 300 personagens mais populares."""
    catalog = {}
    url = "https://graphql.anilist.co"

    query = """
    query ($page: Int, $perPage: Int) {
      Page(page: $page, perPage: $perPage) {
        characters(sort: FAVORITES_DESC) {
          id
          name {
            full
            native
          }
          media(sort: POPULARITY_DESC, perPage: 1) {
            nodes {
              title {
                userPreferred
                native
              }
            }
          }
        }
      }
    }
    """

    print("🌐 Baixando ranking dos Top 300 Personagens via AniList API...")

    for page in range(1, 7):  # 6 páginas x 50 itens = 300
        variables = {"page": page, "perPage": 50}
        try:
            res = requests.post(url, json={"query": query, "variables": variables}, timeout=10)
            if res.status_code == 200:
                data = res.json()
                characters = data.get("data", {}).get("Page", {}).get("characters", [])

                for char in characters:
                    char_id = str(char["id"])
                    name_en = char.get("name", {}).get("full")
                    name_jp = char.get("name", {}).get("native")

                    media_nodes = char.get("media", {}).get("nodes", [])
                    anime_en = media_nodes[0].get("title", {}).get("userPreferred") if media_nodes else "Desconhecido"
                    anime_jp = media_nodes[0].get("title", {}).get("native") if media_nodes else ""

                    if name_jp:
                        catalog[char_id] = {
                            "anilist_id": char_id,
                            "name_en": name_en,
                            "name_jp": name_jp,
                            "anime_en": anime_en,
                            "anime_jp": anime_jp,
                        }
            time.sleep(0.3)
        except Exception as e:
            print(f"⚠️ Erro ao consultar AniList na página {page}: {e}")

    # Fallback básico caso a API falhe totalmente por algum motivo
    if not catalog:
        print("⚠️ AniList indisponível. Aplicando lista básica de emergência...")
        fallback_names = ["初音ミク", "アンタークチサイト", "ルフィ", "ガッツ", "チェンソーマン", "アルティメットまどか"]
        for idx, name in enumerate(fallback_names, 1):
            catalog[str(idx)] = {"name_jp": name, "name_en": f"Item {idx}"}

    save_json(CATALOG_FILE, catalog)
    print(f"✅ Índice de personagens pronto! Total: {len(catalog)} personagens cadastrados.\n")
    return catalog


def scrape_hobbysearch(keyword: str, db: dict):
    """Busca figures de um personagem específico no Hobby Search e atualiza o dict do DB."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    base_url = "https://www.1999.co.jp/search"
    params = {"typ1_c": "101", "cat": "figure", "target": "Item", "searchkey": keyword}

    print(f"🔎 Buscando figures no Hobby Search para: '{keyword}'...")
    try:
        res = requests.get(base_url, params=params, headers=headers, timeout=10)
        if res.status_code != 200:
            print(f"❌ Erro HTTP {res.status_code} para '{keyword}'")
            return
    except Exception as e:
        print(f"❌ Falha de conexão para '{keyword}': {e}")
        return

    soup = BeautifulSoup(res.text, "html.parser")

    # Coleta os links de produtos de figures (/10xxxxxx)
    product_links = set()
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        match = re.search(r"/(?:eng/)?(10\d{6})", href)
        if match:
            item_id = match.group(1)
            product_links.add((item_id, f"https://www.1999.co.jp/{item_id}"))

    added_count = 0

    # Processa até os 8 primeiros itens por personagem
    for item_id, item_url in list(product_links)[:8]:
        try:
            time.sleep(0.4)
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

            # Extrai Código JAN (13 dígitos)
            jan_code = None
            jan_match = re.search(r"\b(45\d{11}|49\d{11})\b", page_text)
            if jan_match:
                jan_code = jan_match.group(1)

            # Extrai MSRP (Preço em Ienes)
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

    print(f"  └ Salvas {added_count} figuras para '{keyword}'. Total acumulado no banco: {len(db)}.")


if __name__ == "__main__":
    db = load_json(DB_FILE, {})
    catalog = load_json(CATALOG_FILE, {})
    scraped_progress = load_json(PROGRESS_FILE, [])

    # 1. Se o índice de personagens não existir, baixa automaticamente do AniList
    if not catalog:
        catalog = fetch_top_300_characters()

    # 2. Pega todos os nomes em japonês do catálogo
    all_keywords = [char_data["name_jp"] for char_data in catalog.values() if char_data.get("name_jp")]

    # 3. Descobre quais ainda não foram raspados
    pending_keywords = [kw for kw in all_keywords if kw not in scraped_progress]

    print(f"📊 Progresso do Banco: {len(scraped_progress)}/{len(all_keywords)} personagens já processados.")

    if not pending_keywords:
        print("🎉 Todos os 300 personagens do catálogo já foram raspados!")
    else:
        # Pega o próximo lote de 25 personagens por rodada
        batch = pending_keywords[:25]
        print(f"🔄 Executando raspagem para o lote atual de {len(batch)} personagens...\n")

        for kw in batch:
            scrape_hobbysearch(kw, db)
            scraped_progress.append(kw)

        # Atualiza todos os arquivos
        save_json(DB_FILE, db)
        save_json(PROGRESS_FILE, scraped_progress)
        print(f"\n✅ Lote concluído com sucesso! Banco atualizado em '{DB_FILE}'.")
