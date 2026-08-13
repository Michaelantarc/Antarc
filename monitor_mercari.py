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
        print("[AVISO] Bot Token ou Chat ID ausente. Mensagem não enviada.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": str(TELEGRAM_CHAT_ID).strip(),
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        res = requests.post(url, json=payload, timeout=5)
        print(f"[TELEGRAM] Resposta do envio: {res.status_code}")
    except Exception as e:
        print(f"[ERRO TELEGRAM] Falha ao enviar mensagem: {e}")


def is_title_valid(title: str, config: dict) -> bool:
    """Valida se o título atende a todos os grupos de inclusão e não contém termos excluídos."""
    title_lower = title.lower()

    # 1. Checa palavras proibidas (Exclusões)
    exclusions = config.get("must_exclude_words", [])
    for word in exclusions:
        if word.lower() in title_lower:
            return False

    # 2. Checa grupos obrigatórios
    include_groups = config.get("must_include_groups", [])
    for group in include_groups:
        if not any(term.lower() in title_lower for term in group):
            return False

    return True


def process_telegram_commands(config):
    """Lê e processa comandos enviados pelo Telegram (/lista)."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[TELEGRAM] Token ou Chat ID não configurados nas variáveis de ambiente.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    try:
        res = requests.get(url, timeout=5).json()
        if not res.get("ok"):
            print(f"[TELEGRAM API ERRO] {res}")
            return False

        updates = res.get("result", [])
        if not updates:
            print("[TELEGRAM] Nenhuma mensagem nova recebida.")
            return False

        config_modified = False
        last_update_id = 0
        expected_chat_id = str(TELEGRAM_CHAT_ID).strip()

        for update in updates:
            last_update_id = update["update_id"]
            msg = update.get("message", {})
            raw_text = msg.get("text", "").strip()
            incoming_chat_id = str(msg.get("chat", {}).get("id", "")).strip()

            print(f"[TELEGRAM MSG] Recebida de {incoming_chat_id}: '{raw_text}' (Esperado: {expected_chat_id})")

            if incoming_chat_id != expected_chat_id or not raw_text:
                continue

            parts = raw_text.split(" ", 1)
            cmd = parts[0].lower().split("@")[0]

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

        return config_modified

    except Exception as e:
        print(f"[ERRO TELEGRAM COMMANDS] {e}")
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

    send_simple_message(message)


async def main():
    mercapi = Mercapi()

    config = load_json(CONFIG_FILE, {})
    state = load_json(STATE_FILE, {})

    # Processa comandos enviados pelo Telegram
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

    # Proteção contra flooding de notificações na 1ª execução / state limpo
    is_initial_run = len(state) == 0

    if results and results.items:
        valid_items_found = 0
        new_notifications_sent = 0

        for item in results.items:
            item_id = str(getattr(item, "id_", getattr(item, "id", "")))
            if not item_id:
                continue

            # Aplica filtros do config.json
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

            # Notifica apenas novos anúncios se NÃO for a primeira execução do estado
            if not is_initial_run and (is_new or price_changed):
                send_telegram_notification(item, is_new=is_new, price_changed=price_changed)
                new_notifications_sent += 1

            state[item_id] = {"price": current_price}

        if is_initial_run:
            print(f"⚡ Inicialização concluída! {valid_items_found} anúncios cadastrados no estado inicial sem spam.")
            send_simple_message(f"🚀 <b>Monitoramento Inicializado!</b>\n\nMapeados {valid_items_found} anúncios ativos. A partir de agora você só receberá alertas de <b>novos anúncios</b> ou <b>mudanças de preço</b>.")

        print(f"Busca finalizada. Encontrados {valid_items_found} itens válidos. Notificações enviadas: {new_notifications_sent}.")

    save_json(STATE_FILE, state)


if __name__ == "__main__":
    asyncio.run(main())
