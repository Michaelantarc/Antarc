import asyncio
import json
import os
import requests
from mercapi import Mercapi

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
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Erro ao enviar mensagem simples: {e}")


def process_telegram_commands(config):
    """Lê mensagens enviadas no chat do Telegram e processa comandos (/add, /remover, /lista)."""
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
            text = msg.get("text", "").strip()
            chat_id = str(msg.get("chat", {}).get("id", ""))

            if chat_id != str(TELEGRAM_CHAT_ID):
                continue

            if text.startswith("/add "):
                new_kw = text[5:].strip()
                if new_kw and new_kw not in config["keywords"]:
                    config["keywords"].append(new_kw)
                    config_modified = True
                    send_simple_message(f"✅ Termo <b>'{new_kw}'</b> adicionado com sucesso!")
                elif new_kw in config["keywords"]:
                    send_simple_message(f"⚠️ O termo <b>'{new_kw}'</b> já está na sua lista.")

            elif text.startswith("/remover ") or text.startswith("/del "):
                parts = text.split(" ", 1)
                if len(parts) > 1:
                    rem_kw = parts[1].strip()
                    if rem_kw in config["keywords"]:
                        config["keywords"].remove(rem_kw)
                        config_modified = True
                        send_simple_message(f"🗑️ Termo <b>'{rem_kw}'</b> removido com sucesso!")
                    else:
                        send_simple_message(f"❌ O termo <b>'{rem_kw}'</b> não foi encontrado na lista.")

            elif text == "/lista":
                kws = config.get("keywords", [])
                if kws:
                    msg_list = "<b>📋 Termos em Monitoramento:</b>\n\n"
                    for idx, kw in enumerate(kws, 1):
                        msg_list += f"{idx}. <code>{kw}</code>\n"
                    send_simple_message(msg_list)
                else:
                    send_simple_message("📋 Sua lista de monitoramento está vazia.")

        if last_update_id > 0:
            requests.get(f"{url}?offset={last_update_id + 1}")

        return config_modified

    except Exception as e:
        print(f"Erro ao processar comandos do Telegram: {e}")
        return False


def send_telegram_notification(item, is_new=True, price_changed=False):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"[AVISO] Telegram não configurado. Item: {item.name}")
        return

    if IS_MANUAL:
        header = "🔴 <b>[VERIFICAÇÃO MANUAL]</b>"
    elif is_new:
        header = "✨ <b>[NOVO ANÚNCIO]</b>"
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
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Erro ao enviar notificação no Telegram: {e}")


async def main():
    mercapi = Mercapi()

    config = load_json(CONFIG_FILE, {"keywords": ["フィギュア"], "price_min": 1000, "price_max": 10000})
    state = load_json(STATE_FILE, {})

    if process_telegram_commands(config):
        save_json(CONFIG_FILE, config)

    keywords = config.get("keywords", ["フィギュア"])
    price_min = config.get("price_min", None)
    price_max = config.get("price_max", None)

    for kw in keywords:
        results = await mercapi.search(
            query=kw,
            price_min=price_min,
            price_max=price_max
        )

        if results and results.items:
            for item in results.items:
                item_id = str(getattr(item, "id_", getattr(item, "id", "")))
                if not item_id:
                    continue

                current_price = item.price
                is_new = item_id not in state
                old_price = state[item_id].get("price") if not is_new else None
                price_changed = not is_new and old_price != current_price

                if IS_MANUAL or is_new or price_changed:
                    send_telegram_notification(item, is_new=is_new, price_changed=price_changed)

                state[item_id] = {"price": current_price}

    save_json(STATE_FILE, state)


if __name__ == "__main__":
    asyncio.run(main())
