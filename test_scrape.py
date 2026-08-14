import cloudscraper
from bs4 import BeautifulSoup
import re

def test_single_scrape(character_name):
    # Cria o scraper que simula um navegador real para evitar bloqueios
    scraper = cloudscraper.create_scraper()
    search_url = f"https://myfigurecollection.net/browse.dialog.php?mode=search&page=1&keyword={character_name}"
    
    print(f"🔎 Testando raspagem local para o personagem: '{character_name}'...")
    
    try:
        res = scraper.get(search_url, timeout=15)
        if res.status_code != 200:
            print(f"❌ Erro de Acesso: HTTP {res.status_code}")
            return

        soup = BeautifulSoup(res.text, "html.parser")
        items = soup.select(".item-icon a")
        
        print(f"✅ Conexão bem-sucedida! Encontrados {len(items)} resultados brutos.\n")

        # Exibe os 3 primeiros resultados válidos para validação
        count = 0
        for item in items:
            href = item.get("href", "")
            if not href.startswith("/item/"):
                continue
            
            item_url = f"https://myfigurecollection.net{href}"
            print(link := f"  - Link do Item: {item_url}")
            
            count += 1
            if count >= 3:
                break
                
    except Exception as e:
        print(f"❌ Falha na execução: {e}")

if __name__ == "__main__":
    # Testando com um personagem específico para validar o filtro
    test_single_scrape("Antarcticite")
