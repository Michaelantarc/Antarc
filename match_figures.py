import json
import os
from collections import Counter
from rapidfuzz import process

HISTORY_FILE = "history.json"
OUTPUT_REPORT = "database/sales_analytics.json"


def load_json(filepath):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"❌ Erro ao ler {filepath}: {e}")
    return {}


def analyze_sales():
    history = load_json(HISTORY_FILE)

    if not history:
        print("❌ O arquivo 'history.json' está vazio ou não foi encontrado.")
        return

    print(f"📊 Analisando {len(history):,} registros de vendas no histórico...")

    total_revenue = 0
    prices = []
    items_list = []

    for item_id, item_data in history.items():
        # Trata o formato dos dados do histórico
        if isinstance(item_data, dict):
            name = item_data.get("name", "Desconhecido")
            price = item_data.get("price", 0)
        elif isinstance(item_data, (int, float)):
            name = "Item Antigo"
            price = item_data
        else:
            continue

        total_revenue += price
        prices.append(price)
        items_list.append({"id": item_id, "name": name, "price": price})

    if not prices:
        print("❌ Nenhum preço válido encontrado no histórico.")
        return

    avg_price = total_revenue / len(prices)
    max_price = max(prices)
    min_price = min(prices)

    report = {
        "total_items_sold": len(prices),
        "total_revenue_yen": total_revenue,
        "average_price_yen": round(avg_price, 2),
        "highest_price_yen": max_price,
        "lowest_price_yen": min_price,
        "sample_top_items": sorted(items_list, key=lambda x: x["price"], reverse=True)[:20]
    }

    os.makedirs(os.path.dirname(OUTPUT_REPORT), exist_ok=True)
    with open(OUTPUT_REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("\n🎉 Análise do Histórico Concluída!")
    print(f"  • Total de Vendas: {len(prices):,}")
    print(f"  • Faturamento Acumulado: ¥{total_revenue:,}")
    print(f"  • Preço Médio por Figure: ¥{int(avg_price):,}")
    print(f"  • Relatório salvo em: '{OUTPUT_REPORT}'")


if __name__ == "__main__":
    analyze_sales()
