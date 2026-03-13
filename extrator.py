import sys
import asyncio
import re
import aiohttp
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from playwright.async_api import async_playwright

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class BuscaRequest(BaseModel):
    query: str
    limit: int

async def encontrar_email_no_site(session, url):
    if not url or any(x in url for x in ["facebook.com", "instagram.com", "youtube.com", "twitter.com"]):
        return "N/A"
    try:
        async with session.get(url, timeout=10) as response:
            html = await response.text()
            emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', html)
            validos = [e for e in emails if not e.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp'))]
            return list(set(validos))[0] if validos else "Não encontrado"
    except:
        return "Inacessível"

async def scraper_maps_ultra(keyword: str, limit: int):
    leads_preliminares = []
    async with async_playwright() as p:
        # No extrator.py, mude para:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0")
        page = await context.new_page()
        await page.route("**/*.{png,jpg,jpeg,svg}", lambda route: route.abort())

        await page.goto(f"https://www.google.com.br/maps/search/{keyword.replace(' ', '+')}")
        try:
            await page.wait_for_selector('a.hfpxzc', timeout=10000)
            scroll_container = 'div[role="feed"]'
            for _ in range((limit // 5) + 1):
                elementos = await page.locator('a.hfpxzc').all()
                if len(elementos) >= limit: break
                await page.locator(scroll_container).evaluate("e => e.scrollBy(0, 4000)")
                await asyncio.sleep(1)

            elementos = await page.locator('a.hfpxzc').all()
            for i in range(min(limit, len(elementos))):
                try:
                    await elementos[i].click()
                    await asyncio.sleep(0.7)
                    nome = await elementos[i].get_attribute('aria-label')
                    tel_btn = page.locator('button[data-tooltip="Copiar número de telefone"]')
                    telefone = await tel_btn.first.get_attribute('aria-label') if await tel_btn.count() > 0 else "N/A"
                    telefone = telefone.replace("Telefone: ", "").strip()
                    
                    site_link = page.locator('a[data-tooltip="Abrir website"]')
                    url_site = None
                    if await site_link.count() > 0:
                        raw_url = await site_link.first.get_attribute('href')
                        url_site = raw_url.split("url?q=")[1].split("&")[0] if "url?q=" in raw_url else raw_url
                    
                    leads_preliminares.append({"nome": nome, "telefone": telefone, "site": url_site})
                except: continue
        except: pass
        await browser.close()

    leads_finais = []
    async with aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0"}) as session:
        tarefas = [encontrar_email_no_site(session, item['site']) for item in leads_preliminares]
        emails = await asyncio.gather(*tarefas)
        for i, email in enumerate(emails):
            lead = leads_preliminares[i]
            lead['email'] = email
            score = 0
            if lead['telefone'] != "N/A" and len(lead['telefone']) > 5: score += 1
            if lead['site'] and len(lead['site']) > 5: score += 1
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
    uvicorn.run(app, host="127.0.0.1", port=8000)
