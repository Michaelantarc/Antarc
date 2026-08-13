import asyncio
import json
import os
import re
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from mercapi import Mercapi
from rapidfuzz import process, fuzz

HISTORY_FILE = "history.json"
README_FILE = "README.md"
STATUS_SOLD_OUT = SimpleNamespace(name="STATUS_SOLD_OUT")

# Lista expandida para remover marcas, linhas, avisos e termos genéricos
NOISE_TERMS = [
    # Condição / Avisos do anúncio
    r"新品", r"未開封", r"即購入OK", r"まとめ売り", r"箱あり", r"箱なし", r"美品", r"送料込み", 
    r"限定", r"セット", r"ジャンク", r"値下げ", r"中古", r"国内正規品", r"当時物", r"現状品", r"景品", r"賞", r"ラストワン",
    # Termos genéricos de Figures e Linhas
    r"フィギュア", r"ねんどろいど", r"一番くじ", r"プライズ", r"スケール", r"ぬーどるストッパー", 
    r"フィギュアーツ", r"POP UP PARADE", r"AMP", r"Luminasta", r"VIBRATION STARS", 
    r"KING OF ARTIST", r"Relax time", r"BiCute Bunnies", r"SPM", r"Qposket", r"FIGURIZM", r"TENITOL",
    # Marcas e Fabricantes Japoneses
    r"バンダイ", r"セガ", r"タイトー", r"フリュー", r"グッドスマイルカンパニー", r"コトブキヤ", 
    r"バンプレスト", r"メガハウス", r"KADOKAWA", r"アルター", r"アニプレックス", r"マックスファクトリー"
]

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_history(data):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def extract_character_name(title: str) -> str:
    """Limpa ruídos e isola exclusivamente o nome do personagem."""
    cleaned = title

    # Extrai o conteúdo dentro de colchetes se disponível (muitas vezes é o personagem ou obra)
    brackets = re.findall(r"【(.*?)】|\[(.*?)\]", cleaned)
    for b in brackets:
        candidate = b[0] or b[1]
        if candidate and not any(re.search(term, candidate, flags=re.IGNORECASE) for term in NOISE_TERMS):
            cleaned = candidate
            break

    # Remove todos os termos de ruído
    for term in NOISE_TERMS:
        cleaned = re.sub(term, "", cleaned, flags=re.IGNORECASE)

    # Remove pontuações e símbolos residuais
    cleaned = re.sub(r"[【】\[\]\(\)\/\\_\-\+！!！]", " ", cleaned).strip()

    # Retorna o primeiro termo relevante encontrado
    words = cleaned.split()
    if words:
        return words[0].strip()
    return title[:15]

def process_character_ranking(items_list):
    """Agrupa e conta as vendas unicamente por personagem."""
    character_counts = {}

    for item in items_list:
        raw_title = item.get("name", "")
        char_name = extract_character_name(raw_title)

        if not char_name or len(char_name) < 2:
            continue

        if not character_counts:
            character_counts[char_name] = 1
        else:
            # Match por similaridade para unificar variações do mesmo nome
            res = process.extractOne(char_name, character_counts.keys(), scorer=fuzz.token_sort_ratio)
            if res and res[1] >= 75:
                character_counts[res[0]] += 1
            else:
                character_counts[char_name] = 1

    # Retorna o Top 15 Personagens
    return sorted(character_counts.items(), key=lambda x: x[1], reverse=True)[:15]

def generate_readme_markdown(total_sales, top_chars, days_tracked):
    now_str = datetime.now(timezone.utc).strftime("%d/%m/%Y às %H:%M UTC")
    
    md = f"# 📊 SG Figures — Ranking de Popularidade de Personagens\n\n"
    md += f"> **Última atualização:** {now_str}  \n"
    md += f"> **Total de figuras catalogadas:** {total_sales} vendas acumuladas em {days_tracked} dia(s) de monitoramento (Faixa: ¥1.000 a ¥10.000).\n\n"

    md += "## 🏆 Top Personagens Mais Vendidos no Mercari JP\n\n"
    md += "| Rank | Personagem | Unidades Vendidas |\n"
    md += "| :---: | :--- | :---: |\n"
    for i, (char, count) in enumerate(top_chars, 1):
        md += f"| **#{i}** | **{char}** | {count} vendas |\n"

    return md

async def main():
    history = load_history()
    now = datetime.now(timezone.utc)
    today_iso = now.isoformat()
    cutoff_date = now - timedelta(days=60)

    # Mantém registros dos últimos 60 dias
    history = {
        item_id: data for item_id, data in history.items()
        if datetime.fromisoformat(data["first_seen"]) > cutoff_date
    }

    mercapi = Mercapi()
    print("Iniciando varredura profunda no Mercari JP (~1.200 itens)...")
    
    res = await mercapi.search(
        query="フィギュア",
        price_min=1000,
        price_max=10000,
        status=[STATUS_SOLD_OUT]
    )

    new_items_count = 0
    pages_scanned = 0
    max_pages = 10  # Garante a raspagem de ~1.200 itens

    while res and res.items and pages_scanned < max_pages:
        pages_scanned += 1
        print(f"Processando página {pages_scanned}...")

        for item in res.items:
            item_id = str(getattr(item, "id_", getattr(item, "id", "")))
            if item_id and item_id not in history:
                history[item_id] = {
                    "name": item.name,
                    "price": item.price,
                    "first_seen": today_iso
                }
                new_items_count += 1

        # Avança para a próxima página até atingir o limite
        try:
            res = await res.next_page()
            if not res or not res.items:
                break
        except Exception as e:
            print(f"Fim dos resultados disponíveis: {e}")
            break

    print(f"Varredura concluída! {new_items_count} novas vendas catalogadas hoje.")
    print(f"Total acumulado no banco: {len(history)} figuras.")

    save_history(history)

    # Processa e gera a página inicial do repositório
    all_items = list(history.values())
    dates = [datetime.fromisoformat(data["first_seen"]) for data in history.values()]
    days_tracked = (max(dates) - min(dates)).days + 1 if dates else 1

    top_chars = process_character_ranking(all_items)
    readme_content = generate_readme_markdown(len(history), top_chars, days_tracked)

    with open(README_FILE, "w", encoding="utf-8") as f:
        f.write(readme_content)

if __name__ == "__main__":
    asyncio.run(main())
