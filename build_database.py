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
    """Busca figures no 1999.co.jp e extrai JAN, preço de tabela (MSRP) e título."""
    db = load_db()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    # URL oficial da categoria Figures no Hobby Search
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

    # Localiza os links de produtos de figures (padrão /10xxxxxx)
    product_links = set()
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        match = re.search(r"/(?:eng/)?(10\d{6})", href)
        if match:
            item_id = match.group(1)
            product_links.add((item_id, f"https://www.1999.co.jp/{item_id}"))

    print(f"  📌 {len(product_links)} produtos encontrados para '{keyword}'.")

    added_count = 0

    for item_id, item_url in product_links:
        try:
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

            # Extrai Preço Original de Tabela (MSRP em Ienes)
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
            print(f"  + Salvo: {title_jp[:40]}... | MSRP: ¥{msrp_yen}")

        except Exception as e:
            print(f"  ⚠️ Erro ao processar item {item_id}: {e}")
            continue

    save_db(db)
    print(f"✅ Concluído para '{keyword}'! Total no banco: {len(db)} figuras.")


if __name__ == "__main__":
    CHARACTER_INDEX_FILE = "database/character_index.json"

    keywords = []

    # Se o catálogo existir, lê os nomes em japonês de lá
    if os.path.exists(CHARACTER_INDEX_FILE):
        with open(CHARACTER_INDEX_FILE, "r", encoding="utf-8") as f:
            catalog = json.load(f)
            keywords = [char_data["name_jp"] for char_data in catalog.values() if char_data.get("name_jp")]

    # Lista de fallback caso o catálogo ainda não tenha sido gerado
    if not keywords:
        keywords = ["初音ミク", "アンタークチサイト", "ルフィ", "ガッツ", "チェンソーマン"]

    print(f"📊 Processando {len(keywords)} termos do catálogo de personagens...")

    # Limite de execução por rodada para não exceder o tempo do GitHub Actions
    for kw in keywords[:30]:  # Altere para processar mais por rodada se necessário
        scrape_hobbysearch(kw)
