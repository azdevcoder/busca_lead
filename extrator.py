import sys
import asyncio
import re
import aiohttp
import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from playwright.async_api import async_playwright

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

app = FastAPI()

# Configuração de CORS para permitir acesso do GitHub Pages
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
        # Adicionamos argumentos para economizar MUITA memória
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--no-first-run",
                "--no-zygote",
                "--single-process", # Crucial para o plano free do Render
            ]
        )

        await page.goto(f"https://www.google.com.br/maps/search/{keyword.replace(' ', '+')}", wait_until="networkidle")
        
        try:
            await page.wait_for_selector('a.hfpxzc', timeout=15000)
            scroll_container = 'div[role="feed"]'
            
            prev_count = 0
            while len(leads_extraidos) < limit:
                elementos = await page.locator('a.hfpxzc').all()
                atual_count = len(elementos)
                
                if atual_count >= limit or atual_count == prev_count:
                    break
                
                prev_count = atual_count
                await elementos[-1].scroll_into_view_if_needed()
                await page.locator(scroll_container).evaluate("e => e.scrollBy(0, 10000)")
                await asyncio.sleep(2)

            elementos = await page.locator('a.hfpxzc').all()
            total_final = min(limit, len(elementos))
            
            for i in range(total_final):
                try:
                    await elementos[i].click()
                    await asyncio.sleep(1)

                    nome = await elementos[i].get_attribute('aria-label')
                    tel_btn = page.locator('button[data-tooltip="Copiar número de telefone"]')
                    telefone = await tel_btn.first.get_attribute('aria-label') if await tel_btn.count() > 0 else "N/A"
                    
                    site_link = page.locator('a[data-tooltip="Abrir website"]')
                    url_site = await site_link.first.get_attribute('href') if await site_link.count() > 0 else None
                    
                    leads_extraidos.append({
                        "nome": nome, 
                        "telefone": telefone.replace("Telefone: ", "").strip(), 
                        "site": url_site
                    })
                except: continue
        except Exception as e:
            print(f"Erro no Scraper: {e}")
            
        await browser.close()

    leads_finais = []
    async with aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0"}) as session:
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
            lead['score'] = score
            leads_finais.append(lead)
            
    return sorted(leads_finais, key=lambda x: x['score'], reverse=True)

@app.post("/buscar")
async def api_buscar(request: BuscaRequest):
    try:
        dados = await scraper_maps_ultra(request.query, request.limit)
        return JSONResponse(content=dados)
    except Exception as e:
        return JSONResponse(content={"erro": str(e)}, status_code=500)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
