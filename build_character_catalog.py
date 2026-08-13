import json
import os
import requests

CATALOG_FILE = "database/character_index.json"


def load_catalog():
    if os.path.exists(CATALOG_FILE):
        try:
            with open(CATALOG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_catalog(data):
    os.makedirs(os.path.dirname(CATALOG_FILE), exist_ok=True)
    with open(CATALOG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def fetch_top_characters(pages=6, per_page=50):
    """Consulta a API do AniList e extrai o Top 300 personagens com nome em Japonês."""
    catalog = load_catalog()
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

    print(f"🚀 Baixando Top {pages * per_page} personagens do AniList...")

    added_count = 0

    for page in range(1, pages + 1):
        variables = {"page": page, "perPage": per_page}
        try:
            res = requests.post(url, json={"query": query, "variables": variables}, timeout=10)
            if res.status_code != 200:
                print(f"❌ Erro na página {page}: HTTP {res.status_code}")
                continue

            data = res.json()
            characters = data.get("data", {}).get("Page", {}).get("characters", [])

            for char in characters:
                char_id = str(char["id"])
                name_en = char.get("name", {}).get("full")
                name_jp = char.get("name", {}).get("native")

                media_nodes = char.get("media", {}).get("nodes", [])
                anime_en = media_nodes[0].get("title", {}).get("userPreferred") if media_nodes else "Desconhecido"
                anime_jp = media_nodes[0].get("title", {}).get("native") if media_nodes else ""

                if not name_jp:
                    continue

                catalog[char_id] = {
                    "anilist_id": char_id,
                    "name_en": name_en,
                    "name_jp": name_jp,
                    "anime_en": anime_en,
                    "anime_jp": anime_jp
                }
                added_count += 1

        except Exception as e:
            print(f"⚠️ Erro ao processar página {page}: {e}")

    save_catalog(catalog)
    print(f"✅ Catálogo de personagens atualizado! Total: {len(catalog)} personagens no índice.")


if __name__ == "__main__":
    # 6 páginas x 50 itens = Top 300
    fetch_top_characters(pages=6, per_page=50)
