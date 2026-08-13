"""
Monitor de preço de figures no Mercari Japão (jp.mercari.com)
---------------------------------------------------------------
Busca por um termo (ex: nome da figure), filtra os resultados por
palavras que devem/não devem aparecer no título, e envia uma
notificação no Telegram quando encontra um anúncio dentro do preço
desejado.

Cada execução faz UMA busca e termina (não fica rodando em loop).
Para checar várias vezes por dia, agende a execução com cron,
Task Scheduler do Windows, ou GitHub Actions (veja o README.md).

Uso:
    python monitor_mercari.py
"""

import asyncio
import json
import logging
import os
import unicodedata
from pathlib import Path

import requests
from mercapi import Mercapi
from mercapi.requests.search import SearchRequestData

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
STATE_PATH = BASE_DIR / "state.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("mercari-monitor")


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"Não encontrei {CONFIG_PATH}. Copie config.example.json para "
            f"config.json e preencha com seus dados."
        )
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    # Permite sobrescrever os dados sensíveis do Telegram via variáveis de
    # ambiente (usado no GitHub Actions, onde ficam em Secrets em vez de
    # dentro do config.json commitado no repositório).
    cfg["telegram_bot_token"] = os.environ.get(
        "TELEGRAM_BOT_TOKEN", cfg.get("telegram_bot_token", "")
    )
    cfg["telegram_chat_id"] = os.environ.get(
        "TELEGRAM_CHAT_ID", cfg.get("telegram_chat_id", "")
    )

    if not cfg["telegram_bot_token"] or not cfg["telegram_chat_id"]:
        raise ValueError(
            "telegram_bot_token / telegram_chat_id não configurados "
            "(nem no config.json, nem nas variáveis de ambiente)."
        )

    return cfg


def load_state() -> dict:
    if STATE_PATH.exists():
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(state: dict) -> None:
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def normalize(text: str) -> str:
    """Normaliza texto para comparação (minúsculas, acentos/largura unicode)."""
    return unicodedata.normalize("NFKC", text).lower()


def item_matches(name: str, must_include_groups, must_exclude) -> bool:
    """Confere se o título do anúncio bate com os critérios.

    must_include_groups: lista de grupos, onde cada grupo é uma lista de
    variações equivalentes (ex: ["ワールドイズマイン", "world is mine"]).
    O item só passa se, PARA CADA GRUPO, pelo menos uma das variações
    aparecer no título. Isso lida bem com vendedores que escrevem o nome
    do produto de formas diferentes.

    must_exclude: lista simples — se qualquer uma dessas palavras aparecer
    no título, o item é descartado.
    """
    norm_name = normalize(name)

    for group in must_include_groups:
        variants = [normalize(w) for w in group if w.strip()]
        if variants and not any(v in norm_name for v in variants):
            return False

    for word in must_exclude:
        if normalize(word) in norm_name:
            return False

    return True


def send_telegram(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = requests.post(
        url,
        data={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        },
        timeout=15,
    )
    if resp.status_code != 200:
        log.error("Falha ao enviar mensagem no Telegram: %s", resp.text)
    else:
        log.info("Notificação enviada no Telegram.")


async def check_search(mercapi: Mercapi, cfg: dict, state: dict) -> int:
    query = cfg["search_query"]
    price_min = cfg.get("price_min") or None
    price_max = cfg["price_max"]
    must_include_groups = cfg.get("must_include_groups", [])
    must_exclude = [w for w in cfg.get("must_exclude_words", []) if w.strip()]
    token = cfg["telegram_bot_token"]
    chat_id = cfg["telegram_chat_id"]

    log.info(
        "Buscando '%s' com preço entre ¥%s e ¥%s",
        query, price_min or 0, price_max,
    )

    results = await mercapi.search(
        query,
        price_min=price_min,
        price_max=price_max,
        status=[SearchRequestData.Status.STATUS_ON_SALE],
    )

    matches = 0
    new_alerts = 0
    already_notified = 0
    for item in results.items:
        if item.is_no_price:
            continue
        if not item_matches(item.name, must_include_groups, must_exclude):
            continue

        matches += 1
        last_notified_price = state.get(item.id_)

        # Notifica se for item novo ou se o preço mudou (pra cima ou pra
        # baixo) desde a última notificação. Só não reenvia se o preço
        # continua exatamente igual ao já notificado (evita spam idêntico).
        if last_notified_price is None or item.price != last_notified_price:
            item_url = f"https://jp.mercari.com/item/{item.id_}"
            msg = (
                f"🔔 <b>Figure encontrada no Mercari!</b>\n"
                f"{item.name}\n"
                f"💴 ¥{item.price:,}\n"
                f"{item_url}"
            )
            send_telegram(token, chat_id, msg)
            state[item.id_] = item.price
            new_alerts += 1
            log.info("Novo alerta: %s (¥%s)", item.name, item.price)
        else:
            already_notified += 1

    log.info(
        "Busca finalizada. %s anúncio(s) dentro dos critérios "
        "(%s novo(s)/preço alterado -> notificado(s), %s já notificado(s) antes com o mesmo preço).",
        matches, new_alerts, already_notified,
    )
    return matches


async def main() -> None:
    cfg = load_config()
    state = load_state()
    mercapi = Mercapi()
    try:
        await check_search(mercapi, cfg, state)
    finally:
        save_state(state)


if __name__ == "__main__":
    asyncio.run(main())
