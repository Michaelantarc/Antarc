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

# Termos de ruído: Condição, Marcas, Linhas e Títulos de Animes/Franquias (para isolar os Personagens)
NOISE_TERMS = [
    # Condição / Avisos do anúncio
    r"新品", r"未開封", r"即購入OK", r"まとめ売り", r"箱あり", r"箱なし", r"美品", r"送料込み", 
    r"限定", r"セット", r"ジャンク", r"値下げ", r"中古", r"国内正規品", r"当時物", r"現状品", r"景品", r"賞", r"ラストワン", r"非売品", r"特典",
    # Marcas, Fabricantes e Vendedores
    r"FUNKO", r"amiibo", r"ALPHA", r"GIGO", r"ROMANCE", r"DAWN", r"POP", r"バンダイ", r"セガ", r"タイトー", r"フリュー", 
    r"グッドスマイルカンパニー", r"コトブキヤ", r"バンプレスト", r"メガハウス", r"KADOKAWA", r"アルター", r"アニプレックス", r"マックスファクトリー",
    # Linhas de Figures
    r"フィギュア", r"ねんどろいど", r"一番くじ", r"プライズ", r"スケール", r"ぬーどるストッパー", 
    r"フィギュアーツ", r"POP UP PARADE", r"AMP", r"Luminasta", r"VIBRATION STARS", 
    r"KING OF ARTIST", r"Relax time", r"BiCute Bunnies", r"SPM", r"Qposket", r"FIGURIZM", r"TENITOL",
    # Títulos de Franquias/Animes (Removidos para sobrar apenas os nomes dos personagens)
    r"ワンピース", r"ONE PIECE", r"ドラゴンボールZ?", r"DRAGON BALL", r"ドラゴンクエスト", r"DRAGON QUEST", 
    r"ポケモン", r"POKEMON", r"ポケットモンスター", r"NARUTO", r"ナルト", r"HUNTER×HUNTER", r"ハンターハンター", 
    r"鬼滅の刃", r"僕のヒーローアカデミア", r"ヒロアカ", r"呪術廻戦", r"チェンソーマン", r"BLEACH", r"ブリーチ", 
    r"銀魂", r"ハイキュー", r"エヴァンゲリオン", r"進撃の巨人", r"名探偵コナン", r"ガンダム", r"GUNDAM"
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
    """Limpa franquias e ruídos para isolar apenas o nome do personagem."""
    cleaned = title

    # Remove termos de ruído e marcas
    for term in NOISE_TERMS:
        cleaned = re.sub(term, "", cleaned, flags=re.IGNORECASE)

    # Limpa pontuações e símbolos
    cleaned = re.sub(r"[【】\[\]\(\)\/\\_\-\+！!！]", " ", cleaned).strip()

    words = cleaned.split()
    if words:
        return words[0].strip()
    return ""

def clean_figure_title(title: str) -> str:
    """Limpa avisos de venda mantendo a identificação do anúncio da figure."""
    cleaned = title
    # Remove apenas marcas institucionais e condições comerciais
    commercial_noise = [r"新品", r"未開封", r"即購入OK", r"まとめ売り", r"箱あり", r"箱なし", r"美品", r"送料込み", r"ジャンク", r"値下げ", r"中古"]
    for term in commercial_noise:
        cleaned = re.sub(term, "", cleaned, flags=re.IGNORECASE)
    return re.sub(r"[【】\[\]]", " ", cleaned).strip()

def process_rankings(items_list):
    character_counts = {}
    figure_counts = {}

    for item in items_list:
        raw_title = item.get("name", "")

        # 1. Ranking de Personagem
        char_name = extract_character_name(raw_title)
        if char_name and len(char_name) >= 2:
            if not character_counts:
                character_counts[char_name] = 1
            else:
                res = process.extractOne(char_name, character_counts.keys(), scorer=fuzz.token_sort_ratio)
                if res and res[1] >= 80:
                    character_counts[res[0]] += 1
                else:
                    character_counts[char_name] = 1

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

    md += "## 🏆 Top 15 Personagens Mais Vendidos\n\n"
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
    history = load_history()
    now = datetime.now(timezone.utc)
    today_iso = now.isoformat()
    cutoff_date = now - timedelta(days=60)

    # Define o limite de páginas: 100 páginas se o banco estiver vazio, senão 10 páginas diárias
    is_first_run = len(history) == 0
    max_pages = 100 if is_first_run else 10

    # Limpa registros antigos (+60 dias)
    history = {
        item_id: data for item_id, data in history.items()
        if datetime.fromisoformat(data["first_seen"]) > cutoff_date
    }

    mercapi = Mercapi()
    if is_first_run:
        print("🚀 Primeira execução detectada! Realizando busca estendida (até 100 páginas)...")
    else:
        print("🔄 Execução diária de rotina (buscando até 10 páginas)...")
    
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

    save_history(history)

    # Processa os rankings e atualiza o README
    all_items = list(history.values())
    dates = [datetime.fromisoformat(data["first_seen"]) for data in history.values()]
    days_tracked = (max(dates) - min(dates)).days + 1 if dates else 1

    top_chars, top_figs = process_rankings(all_items)
    readme_content = generate_readme_markdown(len(history), top_chars, top_figs, days_tracked)

    with open(README_FILE, "w", encoding="utf-8") as f:
        f.write(readme_content)

if __name__ == "__main__":
    asyncio.run(main())
