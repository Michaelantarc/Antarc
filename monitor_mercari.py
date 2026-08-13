import asyncio
import json
import os
import requests
from mercapi import Mercapi

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


def send_simple_message(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Erro ao enviar mensagem simples: {e}")


def is_title_valid(title: str, config: dict) -> bool:
    """Valida se o título atende a todos os grupos de inclusão e não contém termos excluídos."""
    title_lower = title.lower()

    # 1. Checa palavras proibidas (Exclusões)
    exclusions = config.get("must_exclude_words", [])
    for word in exclusions:
        if word.lower() in title_lower:
            return False

    # 2. Checa grupos obrigatórios (Pelo menos um termo de cada grupo deve existir)
    include_groups = config.get("must_include_groups", [])
    for group in include_groups:
        if not any(term.lower() in title_lower for term in group):
            return False

    return True


def process_telegram_commands(config):
    """Lê e processa comandos enviados pelo Telegram (/add, /remover, /lista)."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    try:
        res = requests.get(url, timeout=5).json()
        if not res.get("ok"):
            return False

        updates = res.get("result", [])
        if not updates:
            return False

        config_modified = False
        last_update_id = 0

        for update in updates:
            last_update_id = update["update_id"]
            msg = update.get("message", {})
            raw_text = msg.get("text", "").strip()
            chat_id = str(msg.get("chat", {}).get("id", ""))

            if chat_id != str(TELEGRAM_CHAT_ID) or not raw_text:
                continue

            parts = raw_text.split(" ", 1)
            cmd = parts[0].lower().split("@")[0]
            args = parts[1].strip() if len(parts) > 1 else ""

            if cmd == "/lista":
                query = config.get("search_query", "Não configurada")
                p_min = config.get("price_min", "N/A")
                p_max = config.get("price_max", "N/A")
                msg_info = (
                    f"<b>📋 Monitoramento Ativo:</b>\n\n"
                    f"<b>Busca:</b> <code>{query}</code>\n"
                    f"<b>Faixa de Preço:</b> ¥{p_min:,} - ¥{p_max:,}\n"
                    f"<b>Filtros de Exclusão:</b> {', '.join(config.get('must_exclude_words', []))}"
                )
                send_simple_message(msg_info)

        if last_update_id > 0:
            requests.get(f"{url}?offset={last_update_id + 1}")

        return config_modified

    except Exception as e:
        print(f"Erro ao processar comandos do Telegram: {e}")
        return False


def send_telegram_notification(item, is_new=True, price_changed=False):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    if is_new:
        header = "✨ <b>[NOVA FIGURE ENCONTRADA]</b>"
    elif price_changed:
        header = "📉 <b>[MUDANÇA DE PREÇO]</b>"
    else:
        header = "🔍 <b>[ANÚNCIO]</b>"

    item_id = str(getattr(item, "id_", getattr(item, "id", "")))

    message = (
        f"{header}\n\n"
        f"<b>{item.name}</b>\n"
        f"<b>Preço:</b> ¥{item.price:,}\n\n"
        f"🔗 <a href='https://jp.mercari.com/item/{item_id}'>Ver no Mercari</a>"
    )

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }

    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Erro ao enviar notificação: {e}")


async def main():
    mercapi = Mercapi()

    config = load_json(CONFIG_FILE, {})
    state = load_json(STATE_FILE, {})

    process_telegram_commands(config)

    search_query = config.get("search_query", "初音ミク フィギュア")
    price_min = config.get("price_min", 12000)
    price_max = config.get("price_max", 20000)

    results = await mercapi.search(
        query=search_query,
        price_min=price_min,
        price_max=price_max
    )

    if results and results.items:
        for item in results.items:
            item_id = str(getattr(item, "id_", getattr(item, "id", "")))
            if not item_id:
                continue

            # Aplica a filtragem avançada antes de notificar
            if not is_title_valid(item.name, config):
                continue

            current_price = item.price
            is_new = item_id not in state
            old_price = state[item_id].get("price") if not is_new else None
            price_changed = not is_new and old_price != current_price

            if is_new or price_changed:
                send_telegram_notification(item, is_new=is_new, price_changed=price_changed)

            state[item_id] = {"price": current_price}

    save_json(STATE_FILE, state)


if __name__ == "__main__":
    asyncio.run(main())
