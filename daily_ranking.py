import asyncio
import json
import os
import re
import requests
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from mercapi import Mercapi
from rapidfuzz import process, fuzz

HISTORY_FILE = "history.json"
CACHE_FILE = "character_cache.json"
README_FILE = "README.md"
STATUS_SOLD_OUT = SimpleNamespace(name="STATUS_SOLD_OUT")

COMMERCIAL_NOISE = [
    r"新品", r"未開封", r"即購入OK", r"まとめ売り", r"箱あり", r"箱なし", r"美品", r"送料込み", 
    r"限定", r"セット", r"ジャンク", r"値下げ", r"中古", r"国内正規品", r"当時物", r"現状品", 
    r"景品", r"賞", r"ラストワン", r"非売品", r"特典", r"フィギュア"
]

def load_json(filepath, default):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default
    return default

def save_json(filepath, data):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def is_valid_character_anilist(term: str, cache: dict) -> bool:
    """Verifica no cache local ou consulta a AniList API se a palavra é um personagem real."""
    if not term or len(term) < 2:
        return False

    # Se já está no cache, retorna a resposta salva (True para Personagem, False para Marca/Ruído)
    if term in cache:
        return cache[term]

    # Consulta a API pública da AniList
    query = '''
    query ($search: String) {
      Character(search: $search) {
        name {
          native
        }
      }
    }
    '''
    url = 'https://graphql.anilist.co'
    payload = {'query': query, 'variables': {'search': term}}

    try:
        response = requests.post(url, json=payload, timeout=2)
        if response.status_code == 200:
            data = response.json()
            char_data = data.get('data', {}).get('Character')
            if char_data and char_data.get('name', {}).get('native'):
                cache[term] = True
                return True
    except Exception:
        pass

    # Se a API não encontrou um personagem com este nome exato
    cache[term] = False
    return False

def extract_character_candidates(title: str) -> list:
    """Remove avisos comerciais e retorna palavras candidatas a nome de personagem."""
    cleaned = title
    for term in COMMERCIAL_NOISE:
        cleaned = re.sub(term, " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[【】\[\]\(\)\/\\_\-\+！!！]", " ", cleaned).strip()
    return [w.strip() for w in cleaned.split() if len(w.strip()) >= 2]

def clean_figure_title(title: str) -> str:
    """Limpa condições comerciais para agrupar o anúncio da figure específica."""
    cleaned = title
    for term in COMMERCIAL_NOISE:
        cleaned = re.sub(term, "", cleaned, flags=re.IGNORECASE)
    return re.sub(r"[【】\[\]]", " ", cleaned).strip()

def process_rankings(items_list, cache):
    character_counts = {}
    figure_counts = {}

    for item in items_list:
        raw_title = item.get("name", "")

        # 1. Ranking de Personagem (Validação via AniList / Cache)
        candidates = extract_character_candidates(raw_title)
        found_char = None

        for cand in candidates:
            if is_valid_character_anilist(cand, cache):
                found_char = cand
                break

        if found_char:
            if not character_counts:
                character_counts[found_char] = 1
            else:
                res = process.extractOne(found_char, character_counts.keys(), scorer=fuzz.token_sort_ratio)
                if res and res[1] >= 80:
                    character_counts[res[0]] += 1
                else:
                    character_counts[found_char] = 1

        # 2. Ranking de Figure Específica
        fig_title = clean_figure_title(raw_title)
        if fig_title:
            if not figure_counts:
                figure_counts[fig_title] = 1
            else:
                res = process.extractOne(fig_title, figure_counts.keys(), scorer=fuzz.token_sort_ratio)
                if res and res[1] >= 78:
                    figure_counts[res[0]] += 1
                else:
                    figure_counts[fig_title] = 1

    top_chars = sorted(character_counts.items(), key=lambda x: x[1], reverse=True)[:15]
    top_figs = sorted(figure_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    return top_chars, top_figs

def generate_readme_markdown(total_sales, top_chars, top_figs, days_tracked):
    now_str = datetime.now(timezone.utc).strftime("%d/%m/%Y às %H:%M UTC")
    
    md = f"# 📊 SG Figures — Mercado Mercari JP\n\n"
    md += f"> **Última atualização:** {now_str}  \n"
    md += f"> **Total de vendas catalogadas:** {total_sales} figuras em {days_tracked} dia(s) de histórico acumulado (Faixa: ¥1.000 a ¥10.000).\n\n"

    md += "## 🏆 Top 15 Personagens Mais Vendidos (Validados AniList)\n\n"
    md += "| Rank | Personagem | Unidades Vendidas |\n"
    md += "| :---: | :--- | :---: |\n"
    for i, (char, count) in enumerate(top_chars, 1):
        md += f"| **#{i}** | **{char}** | {count} vendas |\n"

    md += "\n## 📦 Top 10 Figures Específicas / Anúncios Mais Vendidos\n\n"
    md += "| Rank | Anúncio da Figura | Unidades Vendidas |\n"
    md += "| :---: | :--- | :---: |\n"
    for i, (fig, count) in enumerate(top_figs, 1):
        md += f"| **#{i}** | {fig} | {count} vendas |\n"

    return md

async def main():
    history = load_json(HISTORY_FILE, {})
    cache = load_json(CACHE_FILE, {})
    now = datetime.now(timezone.utc)
    today_iso = now.isoformat()
    cutoff_date = now - timedelta(days=60)

    is_first_run = len(history) == 0
    max_pages = 100 if is_first_run else 10

    history = {
        item_id: data for item_id, data in history.items()
        if datetime.fromisoformat(data["first_seen"]) > cutoff_date
    }

    mercapi = Mercapi()
    if is_first_run:
        print("🚀 Primeira execução detectada! Realizando busca estendida (100 páginas)...")
    else:
        print("🔄 Execução diária de rotina (até 10 páginas)...")
    
    res = await mercapi.search(
        query="フィギュア",
        price_min=1000,
        price_max=10000,
        status=[STATUS_SOLD_OUT]
    )

    new_items_count = 0
    pages_scanned = 0

    while res and res.items and pages_scanned < max_pages:
        pages_scanned += 1
        print(f"Lendo página {pages_scanned} de {max_pages}...")

        for item in res.items:
            item_id = str(getattr(item, "id_", getattr(item, "id", "")))
            if item_id and item_id not in history:
                history[item_id] = {
                    "name": item.name,
                    "price": item.price,
                    "first_seen": today_iso
                }
                new_items_count += 1

        try:
            res = await res.next_page()
            if not res or not res.items:
                break
        except Exception as e:
            print(f"Fim dos resultados disponíveis na página {pages_scanned}: {e}")
            break

    print(f"\nBusca concluída! {new_items_count} novas vendas catalogadas nesta rodada.")
    print(f"Total no banco de dados: {len(history)} figuras.")

    save_history(HISTORY_FILE, history)

    # Processa os rankings e atualiza o README e o Cache
    all_items = list(history.values())
    dates = [datetime.fromisoformat(data["first_seen"]) for data in history.values()]
    days_tracked = (max(dates) - min(dates)).days + 1 if dates else 1

    top_chars, top_figs = process_rankings(all_items, cache)
    save_json(CACHE_FILE, cache)  # Salva o aprendizado da AniList no cache local

    readme_content = generate_readme_markdown(len(history), top_chars, top_figs, days_tracked)

    with open(README_FILE, "w", encoding="utf-8") as f:
        f.write(readme_content)

if __name__ == "__main__":
    asyncio.run(main())
