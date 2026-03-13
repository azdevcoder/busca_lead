import sys
import asyncio
import re
import aiohttp
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from playwright.async_api import async_playwright
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Configuração de CORS Ultra-Permissiva para evitar bloqueios
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permite qualquer origem (inclusive seu github.io)
    allow_credentials=True,
    allow_methods=["*"],  # Permite POST, GET, etc.
    allow_headers=["*"],  # Permite todos os cabeçalhos
)

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class BuscaRequest(BaseModel):
    query: str
    limit: int

async def validar_ddd_brasilapi(session, telefone):
    ddd = re.sub(r'\D', '', telefone)[:2]
    if len(ddd) != 2: return "N/A"
    try:
        async with session.get(f"https://brasilapi.com.br/api/ddd/v1/{ddd}", timeout=5) as resp:
            if resp.status == 200:
                dados = await resp.json()
                return dados.get('state', "N/A")
    except: return "N/A"

async def encontrar_email_no_site(session, url):
    if not url or any(x in url for x in ["facebook", "instagram", "youtube", "twitter"]):
        return "N/A"
    try:
        async with session.get(url, timeout=10) as response:
            html = await response.text()
            emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', html)
            validos = [e for e in emails if not e.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp'))]
            return list(set(validos))[0] if validos else "Não encontrado"
    except: return "Inacessível"

async def scraper_maps_ultra(keyword: str, limit: int):
    leads_extraidos = []
    
    async with async_playwright() as p:
        # Launch com slow_mo ajuda a evitar detecção em buscas longas
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        page = await context.new_page()
        await page.route("**/*.{png,jpg,jpeg,svg,css}", lambda route: route.abort())

        await page.goto(f"https://www.google.com.br/maps/search/{keyword.replace(' ', '+')}")
        
        try:
            await page.wait_for_selector('a.hfpxzc', timeout=15000)
            scroll_container = 'div[role="feed"]'
            
            # --- SCROLL AGRESSIVO PARA 1000 LEADS ---
            print(f"Iniciando scroll para {limit} leads...")
            prev_count = 0
            while True:
                # Localiza todos os links de empresas
                elementos = await page.locator('a.hfpxzc').all()
                atual_count = len(elementos)
                
                if atual_count >= limit:
                    print(f"Alvo atingido: {atual_count} encontrados.")
                    break
                
                if atual_count == prev_count:
                    # Se não carregou mais, tenta scrollar um pouco mais devagar
                    await asyncio.sleep(2)
                    # Verifica se apareceu a mensagem "Você chegou ao fim da lista"
                    if await page.get_by_text("Você chegou ao fim da lista").is_visible():
                        break
                
                prev_count = atual_count
                # Scroll para o último elemento encontrado para forçar o carregamento do próximo lote
                await elementos[-1].scroll_into_view_if_needed()
                await page.locator(scroll_container).evaluate("e => e.scrollBy(0, 10000)")
                await asyncio.sleep(1.5) # Pausa crucial para o Maps processar

            # --- EXTRAÇÃO DOS DADOS ---
            elementos = await page.locator('a.hfpxzc').all()
            total_final = min(limit, len(elementos))
            
            for i in range(total_final):
                try:
                    # Clica para abrir o painel lateral
                    await elementos[i].click()
                    await asyncio.sleep(0.7) # Delay para carregar o painel

                    nome = await elementos[i].get_attribute('aria-label')
                    
                    # Seletores robustos para Telefone e Site
                    tel_btn = page.locator('button[data-tooltip="Copiar número de telefone"]')
                    telefone = await tel_btn.first.get_attribute('aria-label') if await tel_btn.count() > 0 else "N/A"
                    
                    site_link = page.locator('a[data-tooltip="Abrir website"]')
                    url_site = await site_link.first.get_attribute('href') if await site_link.count() > 0 else None
                    if url_site and "url?q=" in url_site:
                        url_site = url_site.split("url?q=")[1].split("&")[0]

                    leads_extraidos.append({
                        "nome": nome, 
                        "telefone": telefone.replace("Telefone: ", "").strip(), 
                        "site": url_site
                    })
                    
                    if (i+1) % 10 == 0: print(f"Processado: {i+1}/{total_final}")
                except: continue
        except Exception as e:
            print(f"Erro: {e}")
            
        await browser.close()

    # --- ENRIQUECIMENTO ---
    leads_finais = []
    async with aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0"}) as session:
        # Processa em lotes de 50 para não estourar a memória ou conexões
        tarefas_email = [encontrar_email_no_site(session, item['site']) for item in leads_extraidos]
        tarefas_ddd = [validar_ddd_brasilapi(session, item['telefone']) for item in leads_extraidos]
        
        emails = await asyncio.gather(*tarefas_email)
        estados = await asyncio.gather(*tarefas_ddd)
        
        for i, lead in enumerate(leads_extraidos):
            lead['email'] = emails[i]
            lead['estado'] = estados[i]
            score = 0
            if lead['telefone'] != "N/A": score += 1
            if lead['site']: score += 1
            if "@" in lead['email']: score += 1
            
            if score > 0:
                lead['score'] = score
                leads_finais.append(lead)
            
    return sorted(leads_finais, key=lambda x: x['score'], reverse=True)

@app.post("/buscar")
async def api_buscar(request: BuscaRequest):
    return await scraper_maps_ultra(request.query, request.limit)

if __name__ == "__main__":
    import uvicorn
    import os
    # O Render passa a porta na variável de ambiente PORT
    port = int(os.environ.get("PORT", 8000))
    # O host DEVE ser 0.0.0.0 para ser acessível externamente
    uvicorn.run(app, host="0.0.0.0", port=port)
