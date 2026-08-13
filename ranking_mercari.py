import asyncio
import re
import os
import requests
from mercapi import Mercapi
from rapidfuzz import process, fuzz

# Tokens do Telegram vindos das variáveis do GitHub Actions
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Palavras para remover dos títulos em japonês para melhorar o agrupamento
NOISE_WORDS = [
    r"新品", r"未開封", r"即購入OK", r"まとめ売り", r"箱あり", 
    r"美品", r"送料込み", r"限定", r"フィギュア", r"【.*?】", r"\[.*?\]"
]

def clean_title(title: str) -> str:
    """Limpa o título removendo marcas genéricas de anúncios do Mercari."""
    cleaned = title
    for word in NOISE_WORDS:
        cleaned = re.sub(word, "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()

def group_and_rank(items):
    """Agrupa figuras com títulos parecidos usando Fuzzy Matching."""
    canonical_ranking = {} # { "Nome Limpo": quantidade }

    for item in items:
        raw_name = item.name
        cleaned = clean_title(raw_name)
        
        if not cleaned:
            cleaned = raw_name

        if not canonical_ranking:
            canonical_ranking[cleaned] = 1
            continue

        # Procura se já existe um título com 75%+ de similaridade
        match, score, _ = process.extractOne(
            cleaned, 
            canonical_ranking.keys(), 
            scorer=fuzz.token_sort_ratio
        )

        if score >= 75:
            canonical_ranking[match] += 1
        else:
            canonical_ranking[cleaned] = 1

    # Ordena do mais vendido para o menos vendido
    sorted_ranking = sorted(canonical_ranking.items(), key=lambda x: x[1], reverse=True)
    return sorted_ranking[:10]  # Retorna o Top 10

def send_telegram_ranking(ranking_data):
    """Envia o relatório formatado para o Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[AVISO] Telegram não configurado. Exibindo ranking no console:")
        for idx, (title, count) in enumerate(ranking_data, 1):
            print(f"{idx}. {title} — {count} vendas")
        return

    message = "<b>📊 Ranking de Figures Vendidas no Mercari JP</b>\n"
    message += "<i>Faixa: ¥1.000 a ¥10.000</i>\n\n"

    for idx, (title, count) in enumerate(ranking_data, 1):
        message += f"<b>{idx}.</b> {title} — <b>{count} vendas</b>\n"

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    requests.post(url, json=payload)

async def main():
    mercapi = Mercapi()
    
    # Usa 'query' para o termo de busca no mercapi
    results = await mercapi.search(
        query="フィギュア",
        price_min=1000,
        price_max=10000,
        status=["status_sold_out"]
    )

    if results.items:
        top_ranking = group_and_rank(results.items)
        send_telegram_ranking(top_ranking)

if __name__ == "__main__":
    asyncio.run(main())
