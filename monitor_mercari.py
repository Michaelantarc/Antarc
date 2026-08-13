import asyncio
import json
import os
import requests
from types import SimpleNamespace
from mercapi import Mercapi

STATUS_ON_SALE = SimpleNamespace(name="STATUS_ON_SALE")

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


def is_title_valid(title: str, target: dict) -> bool:
    title_lower = title.lower()

    exclusions = target.get("must_exclude_words", [])
    for word in exclusions:
        if word.lower() in title_lower:
            return False

    include_groups = target.get("must_include_groups", [])
    for group in include_groups:
        if not any(term.lower() in title_lower for term in group):
            return False

    return True


def process_telegram_commands(config):
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
        expected_chat_id = str(TELEGRAM_CHAT_ID).strip()

        targets = config.get("targets", [])

        for update in updates:
            last_update_id = max(last_update_id, update["update_id"])
            msg = update.get("message") or update.get("edited_message")
            if not msg:
                continue

            raw_text = msg.get("text", "").strip()
            incoming_chat_id = str(msg.get("chat", {}).get("id", "")).strip()

            if incoming_chat_id != expected_chat_id or not raw_text:
                continue

            parts = raw_text.split(" ", 1)
            cmd = parts[0].lower().split("@")[0]
            args = parts[1].strip() if len(parts) > 1 else ""

            # Comando /lista
            if cmd == "/lista":
                if not targets:
                    send_simple_message("📋 Nenhuma figure em monitoramento no momento.")
                else:
                    msg_info = "<b>📋 Figures em Monitoramento:</b>\n\n"
                    for idx, t in enumerate(targets, 1):
                        msg_info += (
                            f"<b>#{idx}. {t.get('name', t.get('search_query'))}</b>\n"
                            f"├ Busca: <code>{t.get('search_query')}</code>\n"
                            f"└ Preço: ¥{t.get('price_min', 0):,} - ¥{t.get('price_max', 0):,}\n\n"
                        )
                    msg_info += "<i>Use /del <número> para remover um item.</i>"
                    send_simple_message(msg_info)

            # Comando /add termo | min | max
            elif cmd == "/add":
                if args:
                    subparts = [p.strip() for p in args.split("|")]
                    query = subparts[0]
                    p_min = int(subparts[1]) if len(subparts) > 1 and subparts[1].isdigit() else 1000
                    p_max = int(subparts[2]) if len(subparts) > 2 and subparts[2].isdigit() else 50000

                    new_target = {
                        "name": query,
                        "search_query": query,
                        "must_include_groups": [],
                        "must_exclude_words": ["レプリカ", "海賊版", "ジャンク", "破損"],
                        "price_min": p_min,
                        "price_max": p_max
                    }

                    targets.append(new_target)
                    config["targets"] = targets
                    config_modified = True
                    send_simple_message(f"✅ Nova figure adicionada:\n<b>{query}</b> (¥{p_min:,} - ¥{p_max:,})")
                else:
                    send_simple_message("⚠️ Formato incorreto. Use:\n<code>/add Nome da Figure | PreçoMin | PreçoMax</code>")

            # Comando /del número
            elif cmd in ["/del", "/remover"]:
                if args.isdigit():
                    idx = int(args) - 1
                    if 0 <= idx < len(targets):
                        removed = targets.pop(idx)
                        config["targets"] = targets
                        config_modified = True
                        send_simple_message(f"🗑️ Removido com sucesso: <b>{removed.get('name', 'Item')}</b>")
                    else:
                        send_simple_message("❌ Número inválido na lista.")
                else:
                    send_simple_message("⚠️ Envie o número do item. Exemplo: <code>/del 1</code>")

        if last_update_id > 0:
            requests.get(f"{url}?offset={last_update_id + 1}")

        return config_modified

    except Exception as e:
        print(f"[ERRO TELEGRAM COMMANDS] {e}")
        return False


def send_telegram_notification(item, target_name, is_manual=False, is_new=True, price_changed=False):
    if is_manual:
        header = f"🔴 <b>[BUSCA MANUAL | {target_name}]</b>"
    elif is_new:
        header = f"✨ <b>[NOVA FIGURE | {target_name}]</b>"
    elif price_changed:
        header = f"📉 <b>[MUDANÇA DE PREÇO | {target_name}]</b>"
    else:
        header = f"🔍 <b>[ANÚNCIO | {target_name}]</b>"

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

    config = load_json(CONFIG_FILE, {"targets": []})
    state = load_json(STATE_FILE, {})

    if process_telegram_commands(config):
        save_json(CONFIG_FILE, config)

    targets = config.get("targets", [])

    # Retrocompatibilidade se o config antigo for um objeto único
    if not targets and "search_query" in config:
        targets = [config]

    if not targets:
        print("Nenhuma figure cadastrada para monitoramento.")
        return

    is_initial_run = len(state) == 0

    for target in targets:
        target_name = target.get("name", target.get("search_query", "Figure"))
        search_query = target.get("search_query", "")
        price_min = target.get("price_min", 1000)
        price_max = target.get("price_max", 50000)

        print(f"🔎 Monitorando '{target_name}' no Mercari (¥{price_min:,} a ¥{price_max:,})...")

        results = await mercapi.search(
            query=search_query,
            price_min=price_min,
            price_max=price_max,
            status=[STATUS_ON_SALE]
        )

        if results and results.items:
            for item in results.items:
                item_id = str(getattr(item, "id_", getattr(item, "id", "")))
                if not item_id:
                    continue

                if not is_title_valid(item.name, target):
                    continue

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

                if (IS_MANUAL or is_new or price_changed) and not is_initial_run:
                    send_telegram_notification(item, target_name, is_manual=IS_MANUAL, is_new=is_new, price_changed=price_changed)

                state[item_id] = {"price": current_price}

    save_json(STATE_FILE, state)


if __name__ == "__main__":
    asyncio.run(main())
