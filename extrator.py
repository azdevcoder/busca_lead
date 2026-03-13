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

app = FastAPI()

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

async def scraper_maps_ultra(keyword: str, limit: int):
    leads_extraidos = []
    async with async_playwright() as p:
        # Args agressivos para rodar em servidor de 512MB
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage", "--single-process"]
        )
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
        page = await context.new_page()
        # Bloqueia imagens/estilos para economizar banda e RAM
        await page.route("**/*.{png,jpg,jpeg,svg,css}", lambda route: route.abort())

        try:
            await page.goto(f"https://www.google.com.br/maps/search/{keyword.replace(' ', '+')}", wait_until="domcontentloaded")
            await page.wait_for_selector('a.hfpxzc', timeout=10000)
            
            elementos = await page.locator('a.hfpxzc').all()
            for i in range(min(limit, len(elementos))):
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
                    "site": url_site,
                    "email": "Buscando...",
                    "estado": "...",
                    "score": 1
                })
        except Exception as e:
            print(f"Erro: {e}")
        
        await browser.close()
    return leads_extraidos

@app.post("/buscar")
async def api_buscar(request: BuscaRequest):
    try:
        dados = await scraper_maps_ultra(request.query, request.limit)
        return JSONResponse(content=dados)
    except Exception as e:
        return JSONResponse(content={"erro": str(e)}, status_code=500)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
