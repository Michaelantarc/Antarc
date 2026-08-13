import json
import os
from rapidfuzz import process, fuzz

HISTORY_FILE = "history.json"
DB_FILE = "database/figures.json"
OUTPUT_REPORT = "database/matched_report.json"

def load_json(filepath):
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def run_matching():
    history = load_json(HISTORY_FILE)
    db = load_json(DB_FILE)

    if not history or not db:
        print("❌ Certifique-se de que 'history.json' e 'database/figures.json' possuem dados.")
        return

    db_titles = {key: data.get("title_jp", "") for key, data in db.items() if data.get("title_jp")}
    
    matched_results = []

    print(f"🔄 Cruzando {len(history)} vendas com {len(db_titles)} figuras do banco de referência...")

    for item_id, item_data in history.items():
        mercari_title = item_data.get("name", "")
        price_sold = item_data.get("price", 0)

        # Busca o título mais parecido no banco oficial
        match = process.extractOne(
            mercari_title, 
            db_titles.values(), 
            scorer=fuzz.token_set_ratio
        )

        # Considera um match válido se a similaridade for >= 80%
        if match and match[1] >= 80:
            matched_title = match[0]
            # Encontra a chave no banco
            matched_key = [k for k, v in db_titles.items() if v == matched_title][0]
            ref_data = db[matched_key]

            msrp = ref_data.get("msrp_yen")
            discount_pct = round(((msrp - price_sold) / msrp) * 100, 1) if msrp else None

            matched_results.append({
                "mercari_item_id": item_id,
                "mercari_title": mercari_title,
                "price_sold_yen": price_sold,
                "official_title": matched_title,
                "official_msrp_yen": msrp,
                "jan_code": ref_data.get("jan_code"),
                "discount_vs_msrp_pct": discount_pct,
                "match_confidence": round(match[1], 1)
            })

    # Salva o relatório de correspondências
    with open(OUTPUT_REPORT, "w", encoding="utf-8") as f:
        json.dump(matched_results, f, ensure_ascii=False, indent=2)

    print(f"\n🎉 Processo finalizado!")
    print(f"Encontrados {len(matched_results)} cruzamentos exatos/próximos.")
    print(f"Relatório salvo em: '{OUTPUT_REPORT}'")

if __name__ == "__main__":
    run_matching()
