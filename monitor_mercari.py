import asyncio
import json
import os
import requests
from mercapi import Mercapi

# Detecta se a execução foi disparada manualmente no GitHub Actions
IS_MANUAL = os.getenv("GITHUB_EVENT_NAME") == "workflow_dispatch"

# Tokens do Telegram configurados nos Secrets do GitHub
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

STATE_FILE = "state.json"
CONFIG_FILE = "config.json"


def load_json(filepath, default_value):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default_value
    return default_value


def save_json(filepath, data):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def send_telegram_notification(item, is_new=True, price_changed=False):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"[AVISO] Telegram não configurado. Item encontrado: {item.name}")
        return

    # Define a tag do topo da mensagem
    if IS_MANUAL:
        header = "🔴 <b>[VERIFICAÇÃO MANUAL]</b>"
    elif is_new:
        header = "✨ <b>[NOVO ANÚNCIO]</b>"
    elif price_changed:
        header = "📉 <b>[MUDANÇA DE PREÇO]</b>"
    else:
        header = "🔍 <b>[ANÚNCIO]</b>"

    message = (
        f"{header}\n\n"
        f"<b>{item.name}</b>\n"
        f"<b>Preço:</b> ¥{item.price:,}\n\n"
        f"🔗 <a href='https://jp.mercari.com/item/{item.id}'>Ver no Mercari</a>"
    )

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }

    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Erro ao enviar notificação no Telegram: {e}")


async def main():
    mercapi = Mercapi()

    # Carrega as configurações de busca e o estado salvo
    config = load_json(CONFIG_FILE, {"keywords": ["フィギュア"], "price_min": 1000, "price_max": 10000})
    state = load_json(STATE_FILE, {})

    keywords = config.get("keywords", ["フィギュア"])
    price_min = config.get("price_min", None)
    price_max = config.get("price_max", None)

    for kw in keywords:
        results = await mercapi.search(
            kw=kw,
            price_min=price_min,
            price_max=price_max
        )

        for item in results.items:
            item_id = str(item.id)
            current_price = item.price

            is_new = item_id not in state
            old_price = state[item_id].get("price") if not is_new else None
            price_changed = not is_new and old_price != current_price

            # Regra de disparo:
            # - Se for MANUAL (workflow_dispatch): envia tudo.
            # - Se for AUTOMÁTICO (cron): envia apenas se for novo ou mudou de preço.
            if IS_MANUAL or is_new or price_changed:
                send_telegram_notification(item, is_new=is_new, price_changed=price_changed)

            # Atualiza o estado
            state[item_id] = {"price": current_price}

    save_json(STATE_FILE, state)


if __name__ == "__main__":
    asyncio.run(main())
