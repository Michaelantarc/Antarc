import asyncio
import json
import os
import requests
from mercapi import Mercapi

# Detecta se a execução foi disparada manualmente no GitHub Actions
IS_MANUAL = os.getenv("GITHUB_EVENT_NAME") == "workflow_dispatch"
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
        "chat_id": str(TELEGRAM_CHAT_ID).strip(),
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"[ERRO TELEGRAM] Falha ao enviar mensagem: {e}")


def is_title_valid(title: str, config: dict) -> bool:
    title_lower = title.lower()

    exclusions = config.get("must_exclude_words", [])
    for word in exclusions:
        if word.lower() in title_lower:
            return False

    include_groups = config.get("must_include_groups", [])
    for group in include_groups:
        if not any(term.lower() in title_lower for term in group):
            return False

    return True


def process_telegram_commands(config):
    if not TELEGRAM_BOT_TOKEN:
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    try:
        res = requests.get(url, timeout=5).json()
        if not res.get("ok"):
            return False

        updates = res.get("result", [])
        if not updates:
            return False

        expected_chat_id = str(TELEGRAM_CHAT_ID).strip() if TELEGRAM_CHAT_ID else ""
        last_update_id = 0

        for update in updates:
            last_update_id = max(last_update_id, update["update_id"])
            msg = update.get("message") or update.get("edited_message")
            if not msg:
                continue

            raw_text = msg.get("text", "").strip()
            incoming_chat_id = str(msg.get("chat", {}).get("id", "")).strip()

            if expected_chat_id and incoming_chat_id != expected_chat_id:
                continue

            cmd = raw_text.split(" ", 1)[0].lower().split("@")[0]

            if cmd == "/lista":
                query = config.get("search_query", "Não configurada")
                p_min = config.get("price_min", "N/A")
                p_max = config.get("price_max", "N/A")
                exclusions = config.get("must_exclude_words", [])
                
                msg_info = (
                    f"<b>📋 Monitoramento Ativo:</b>\n\n"
                    f"<b>Busca:</b> <code>{query}</code>\n"
                    f"<b>Faixa de Preço:</b> ¥{p_min:,} - ¥{p_max:,}\n"
                    f"<b>Exclusões:</b> {', '.join(exclusions) if exclusions else 'Nenhuma'}"
                )
                send_simple_message(msg_info)

        if last_update_id > 0:
            requests.get(f"{url}?offset={last_update_id + 1}")

    except Exception as e:
        print(f"[ERRO TELEGRAM COMMANDS] {e}")


def send_telegram_notification(item, is_manual=False, is_new=True, price_changed=False):
    if is_manual:
        header = "🔴 <b>[BUSCA MANUAL / TESTE]</b>"
    elif is_new:
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

    send_simple_message(message)


async def main():
    mercapi = Mercapi()

    config = load_json(CONFIG_FILE, {})
    state = load_json(STATE_FILE, {})

    process_telegram_commands(config)

    search_query = config.get("search_query", "初音ミク フィギュア")
    price_min = config.get("price_min", 12000)
    price_max = config.get("price_max", 20000)

    print(f"🔎 Buscando no Mercari: '{search_query}' (¥{price_min:,} a ¥{price_max:,})...")

    results = await mercapi.search(
        query=search_query,
        price_min=price_min,
        price_max=price_max
    )

    if results and results.items:
        valid_items_found = 0
        notifications_sent = 0

        for item in results.items:
            item_id = str(getattr(item, "id_", getattr(item, "id", "")))
            if not item_id:
                continue

            if not is_title_valid(item.name, config):
                continue

            valid_items_found += 1
            current_price = item.price
            is_new = item_id not in state

            old_price = None
            if not is_new:
                old_data = state[item_id]
                if isinstance(old_data, dict):
                    old_price = old_data.get("price")
                elif isinstance(old_data, (int, float)):
                    old_price = old_data

            price_changed = not is_new and old_price is not None and old_price != current_price

            # Envia no Telegram se for disparo manual OU se for anúncio novo / mudança de preço no automático
            if IS_MANUAL or is_new or price_changed:
                send_telegram_notification(item, is_manual=IS_MANUAL, is_new=is_new, price_changed=price_changed)
                notifications_sent += 1

            state[item_id] = {"price": current_price}

        print(f"Busca finalizada. Itens válidos encontrados: {valid_items_found}. Notificações enviadas: {notifications_sent}.")

    save_json(STATE_FILE, state)


if __name__ == "__main__":
    asyncio.run(main())
