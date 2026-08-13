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

NOISE_TERMS = [
    r"新品", r"未開封", r"即購入OK", r"まとめ売り", r"箱あり", r"箱なし", r"美品", r"送料込み", 
    r"限定", r"セット", r"ジャンク", r"値下げ", r"中古", r"国内正規品", r"当時物", r"現状品",
    r"フィギュア", r"ねんどろいど", r"一番くじ", r"プライズ", r"スケール", r"ぬーどるストッパー", 
    r"フィギュアーツ", r"POP UP PARADE", r"AMP", r"Luminasta", r"VIBRATION STARS", 
    r"KING OF ARTIST", r"Relax time", r"BiCute Bunnies", r"SPM", r"Qposket", r"景品", r"賞"
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

def extract_character(title: str) -> str:
    brackets = re.findall(r"【(.*?)】|\[(.*?)\]", title)
    for b in brackets:
        candidate = b[0] or b[1]
        if candidate and not any(re.search(term, candidate) for term in ["新品", "未開封", "まとめ", "セット", "ジャンク", "即購入"]):
            return candidate.strip()
    
    cleaned = title
    for term in NOISE_TERMS:
        cleaned = re.sub(term, "", cleaned, flags=re.IGNORECASE)
    words = cleaned.strip().split()
    return words[0] if words else title[:15]

def clean_figure_title(title: str) -> str:
    cleaned = title
    for term in NOISE_TERMS:
        cleaned = re.sub(term, "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"【\s*】|\[\s*\]", "", cleaned)
    return cleaned.strip()

def process_rankings(items_list):
    character_counts = {}
    figure_counts = {}

    for item in items_list:
        title = item.get("name", "")

        # Personagem
        char_name = extract_character(title)
        if char_name:
            if not character_counts:
                character_counts[char_name] = 1
            else:
                match, score, _ = process_extract(char_name, character_counts.keys(), 75)
                if match:
                    character_counts[match] += 1
                else:
                    character_counts[char_name] = 1

        # Figure Específica
        fig_name = clean_figure_title(title) or title
        if not figure_counts:
            figure_counts[fig_name] = 1
        else:
            match, score, _ = process_extract(fig_name, figure_counts.keys(), 78)
            if match:
                figure_counts[match] += 1
            else:
                figure_counts[fig_name] = 1

    top_chars = sorted(character_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    top_figs = sorted(figure_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    return top_chars, top_figs

def process_extract(query, choices, threshold):
    if not choices:
        return None, 0, None
    res = process.extractOne(query, choices, scorer=fuzz.token_sort_ratio)
    if res and res[1] >= threshold:
        return res[0], res[1], None
    return None, 0, None

def generate_readme_markdown(total_sales, top_chars, top_figs, days_tracked):
    now_str = datetime.now(timezone.utc).strftime("%d/%m/%Y às %H:%M UTC")
    
    md = f"# 📊 SG Figures — Mercado Mercari JP\n\n"
    md += f"> **Última atualização:** {now_str}  \n"
    md += f"> **Total de vendas catalogadas:** {total_sales} figuras em {days_tracked} dias de histórico acumulado (Faixa: ¥1.000 a ¥10.000).\n\n"

    md += "## 🏆 Top 10 Personagens / Franquias Mais Vendidos\n\n"
    md += "| Rank | Personagem / Franquia | Unidades Vendidas |\n"
    md += "| :---: | :--- | :---: |\n"
    for i, (char, count) in enumerate(top_chars, 1):
        md += f"| {i} | **{char}** | {count} |\n"

    md += "\n## 📦 Top 10 Figures Específicas Mais Vendidas\n\n"
    md += "| Rank | Figura / Anúncio | Unidades Vendidas |\n"
    md += "| :---: | :--- | :---: |\n"
    for i, (fig, count) in enumerate(top_figs, 1):
        md += f"| {i} | {fig} | {count} |\n"

    return md

async def main():
    history = load_history()
    now = datetime.now(timezone.utc)
    today_iso = now.isoformat()
    cutoff_date = now - timedelta(days=60)

    # Limpa registros com mais de 60 dias
    history = {
        item_id: data for item_id, data in history.items()
        if datetime.fromisoformat(data["first_seen"]) > cutoff_date
    }

    mercapi = Mercapi()
    print("Buscando vendas do dia no Mercari JP...")
    
    res = await mercapi.search(
        query="フィギュア",
        price_min=1000,
        price_max=10000,
        status=[STATUS_SOLD_OUT]
    )

    new_items_count = 0
    pages_scanned = 0

    while res and res.items and pages_scanned < 10:
        pages_scanned += 1
        for item in res.items:
            item_id = str(item.id)
            if item_id not in history:
                history[item_id] = {
                    "name": item.name,
                    "price": item.price,
                    "first_seen": today_iso
                }
                new_items_count += 1

        if hasattr(res, 'has_next') and res.has_next:
            try:
                res = await res.next_page()
            except Exception:
                break
        else:
            break

    print(f"Novas vendas adicionadas hoje: {new_items_count}")
    print(f"Total acumulado no banco (últimos 60 dias): {len(history)}")

    save_history(history)

    # Calcula e atualiza o README
    all_items = list(history.values())
    
    # Calcula quantos dias de histórico já existem
    dates = [datetime.fromisoformat(data["first_seen"]) for data in history.values()]
    days_tracked = (max(dates) - min(dates)).days + 1 if dates else 1

    top_chars, top_figs = process_rankings(all_items)
    readme_content = generate_readme_markdown(len(history), top_chars, top_figs, days_tracked)

    with open(README_FILE, "w", encoding="utf-8") as f:
        f.write(readme_content)

if __name__ == "__main__":
    asyncio.run(main())
