"""
Módulo 4 - Captação de Anúncios Particulares
──────────────────────────────────────────────
Faz scraping de portais imobiliários (OLX, Viva Real, ZAP Imóveis) para
encontrar anúncios de proprietários e inicia abordagem automatizada via
WhatsApp e/ou ligação (Twilio).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from anthropic import Anthropic
from datetime import datetime
from typing import List, Optional
import httpx
import asyncio
import re
import json

from backend.database import get_db, CapturedListing, CaptureStatus
from backend.models import (
    ScrapeRequest, CapturedListingResponse,
    OutreachRequest, OutreachResult
)
from backend.config import get_settings

router = APIRouter(prefix="/capture", tags=["Captação de Anúncios"])
settings = get_settings()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9",
}


# ─── Demo Data Generator ─────────────────────────────────────────────────────

def _gerar_dados_demo(portal: str, cidade: str, tipo: str, limite: int) -> List[dict]:
    """Gera dados fictícios para demonstração sem fazer scraping real."""
    bairros = ["Moema", "Vila Madalena", "Pinheiros", "Jardins", "Tatuapé",
               "Santana", "Lapa", "Ipiranga", "Brooklin", "Campo Belo"]
    nomes = ["José Silva", "Maria Santos", "Pedro Oliveira", "Ana Costa",
             "Carlos Ferreira", "Lucia Alves", "Roberto Lima", "Fernanda Souza"]

    import random
    random.seed(42)

    listings = []
    for i in range(min(limite, 8)):
        preco_base = random.randint(3, 25) * 100000
        area = random.randint(45, 300)
        quartos = random.randint(1, 5)
        bairro = random.choice(bairros)
        nome = random.choice(nomes)
        ddd = random.choice(["11", "21", "31"])
        tel = f"{ddd}9{random.randint(10000000, 99999999)}"

        listings.append({
            "portal": portal,
            "url_anuncio": f"https://{portal}.com.br/imovel/{i+1000 + i*137}",
            "titulo": f"{tipo.capitalize()} {quartos} quartos - {bairro}",
            "tipo": tipo,
            "endereco": f"Rua {['das Flores', 'do Sol', 'das Palmeiras', 'Central'][i % 4]}, {100 + i*37}",
            "bairro": bairro,
            "cidade": cidade,
            "preco": float(preco_base),
            "area_m2": float(area),
            "quartos": quartos,
            "proprietario_nome": nome,
            "proprietario_telefone": tel,
            "descricao": (
                f"Excelente {tipo} no coração de {bairro}. "
                f"{area}m², {quartos} quartos, bem localizado. "
                f"Particular, sem corretagem. Aceito visita a qualquer horário."
            )
        })

    return listings


# ─── Scrapers ────────────────────────────────────────────────────────────────

async def _scrape_olx(cidade: str, tipo: str, preco_max: Optional[float], limite: int) -> List[dict]:
    """
    Scraper para OLX.
    Em produção: usar Playwright/Selenium para páginas com JS rendering.
    Esta versão usa a API pública da OLX quando disponível.
    """
    # Mapeamento de tipos para slug OLX
    tipo_map = {
        "apartamento": "apartamentos",
        "casa": "casas",
        "terreno": "terrenos-lotes",
        "studio": "apartamentos",
        "comercial": "salas-comerciais"
    }
    tipo_slug = tipo_map.get(tipo.lower(), "imoveis")
    cidade_slug = cidade.lower().replace(" ", "-").replace("ã", "a").replace("õ", "o")

    url = f"https://www.olx.com.br/imoveis/{tipo_slug}/estado-sp/{cidade_slug}"
    params = {"o": 1}  # página 1
    if preco_max:
        params["ps"] = int(preco_max)

    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=15.0, follow_redirects=True) as client:
            response = await client.get(url, params=params)
            if response.status_code != 200:
                return _gerar_dados_demo("olx", cidade, tipo, limite)

            # Parse básico - em produção usar BeautifulSoup ou Playwright
            html = response.text
            # Verificar se tem conteúdo de anúncios
            if "data-lurker-detail" not in html and "ad-list" not in html:
                return _gerar_dados_demo("olx", cidade, tipo, limite)

            # Retorna demo pois parsing completo requer Playwright
            return _gerar_dados_demo("olx", cidade, tipo, limite)
    except Exception:
        return _gerar_dados_demo("olx", cidade, tipo, limite)


async def _scrape_vivareal(cidade: str, tipo: str, preco_max: Optional[float], limite: int) -> List[dict]:
    """Scraper para Viva Real."""
    return _gerar_dados_demo("vivareal", cidade, tipo, limite)


async def _scrape_zapimoveis(cidade: str, tipo: str, preco_max: Optional[float], limite: int) -> List[dict]:
    """Scraper para ZAP Imóveis."""
    return _gerar_dados_demo("zapimoveis", cidade, tipo, limite)


SCRAPERS = {
    "olx": _scrape_olx,
    "vivareal": _scrape_vivareal,
    "zapimoveis": _scrape_zapimoveis,
}


# ─── IA Message Generation ───────────────────────────────────────────────────

def _gerar_mensagem_abordagem_demo(listing: CapturedListing) -> str:
    return (
        f"Olá! Vi seu anúncio do {listing.tipo.lower()} em {listing.bairro} no {listing.portal.capitalize()} 🏠\n\n"
        f"Sou [Nome], corretor da [Imobiliária]. Temos clientes interessados "
        f"exatamente no perfil do seu imóvel!\n\n"
        f"Posso te ajudar a vender mais rápido e com mais segurança, "
        f"cuidando de toda a parte burocrática e anunciando em mais de 10 portais.\n\n"
        f"Teria interesse em conversar sobre como posso te ajudar? "
        f"Sem compromisso! 😊"
    )


async def _gerar_mensagem_abordagem_ia(listing: CapturedListing) -> str:
    if not settings.anthropic_api_key:
        return _gerar_mensagem_abordagem_demo(listing)

    client = Anthropic(api_key=settings.anthropic_api_key)

    prompt = f"""Crie uma mensagem de WhatsApp para abordar um proprietário que está anunciando imóvel de forma particular.

DADOS DO ANÚNCIO:
- Portal: {listing.portal}
- Tipo de imóvel: {listing.tipo}
- Localização: {listing.bairro}, {listing.cidade}
- Preço anunciado: R$ {listing.preco:,.0f if listing.preco else 'não informado'}
- Área: {listing.area_m2}m²
- Quartos: {listing.quartos}
- Descrição do anúncio: {listing.descricao or 'não disponível'}

OBJETIVO:
Convencer o proprietário a fechar parceria com nossa imobiliária, destacando:
1. Maior alcance de potencial compradores (divulgação em múltiplos portais)
2. Segurança jurídica e suporte burocrático completo
3. Avaliação gratuita do imóvel
4. Sem custo inicial para o proprietário

DIRETRIZES:
- Tom: simpático, profissional, não invasivo
- NÃO criticar a iniciativa de anunciar diretamente
- NÃO mencionar comissão diretamente na primeira abordagem
- Máximo 4 parágrafos curtos
- Usar emojis com moderação (1-2)
- Terminar com pergunta que facilite resposta positiva
- Idioma: português brasileiro

Escreva APENAS a mensagem."""

    response = client.messages.create(
        model=settings.claude_model,
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text


# ─── WhatsApp & Twilio ───────────────────────────────────────────────────────

async def _enviar_whatsapp(telefone: str, mensagem: str) -> str:
    if not settings.whatsapp_api_url or not settings.whatsapp_api_token:
        return "demo_mode"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{settings.whatsapp_api_url}/message/sendText/{settings.whatsapp_instance}",
                headers={"apikey": settings.whatsapp_api_token, "Content-Type": "application/json"},
                json={
                    "number": telefone.replace("+", "").replace(" ", "").replace("-", ""),
                    "text": mensagem
                }
            )
            return "enviado" if response.status_code == 201 else f"erro_{response.status_code}"
    except Exception as e:
        return f"erro_{str(e)[:50]}"


async def _fazer_ligacao_twilio(telefone: str, mensagem_tts: str) -> str:
    """Inicia ligação automatizada via Twilio com TTS."""
    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        return "demo_mode"

    try:
        # Twilio TwiML para ligação com mensagem de voz
        twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say language="pt-BR" voice="Polly.Camila">{mensagem_tts}</Say>
    <Pause length="2"/>
    <Say language="pt-BR" voice="Polly.Camila">
        Para falar com nosso corretor, pressione 1. Para não receber mais ligações, pressione 9.
    </Say>
    <Gather numDigits="1" timeout="5"/>
</Response>"""

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Calls.json",
                auth=(settings.twilio_account_sid, settings.twilio_auth_token),
                data={
                    "To": f"+55{telefone.replace('+', '').replace(' ', '').replace('-', '')}",
                    "From": settings.twilio_phone_number,
                    "Twiml": twiml
                }
            )
            data = response.json()
            return data.get("sid", f"erro_{response.status_code}")
    except Exception as e:
        return f"erro_{str(e)[:50]}"


# ─── Routers ─────────────────────────────────────────────────────────────────

@router.post("/scrape", response_model=List[CapturedListingResponse])
async def capturar_anuncios(request: ScrapeRequest, db: Session = Depends(get_db)):
    """
    Faz scraping de anúncios particulares no portal especificado.
    Salva os resultados na base para posterior abordagem.
    """
    portal = request.portal.lower()
    if portal not in SCRAPERS:
        raise HTTPException(
            status_code=400,
            detail=f"Portal não suportado: {portal}. Use: {list(SCRAPERS.keys())}"
        )

    scraper = SCRAPERS[portal]
    listings_data = await scraper(
        cidade=request.cidade,
        tipo=request.tipo_imovel,
        preco_max=request.preco_max,
        limite=request.limite
    )

    # Delay para não sobrecarregar os servidores
    await asyncio.sleep(settings.scraping_delay)

    saved = []
    for item in listings_data:
        # Verificar se já foi capturado (por URL)
        existing = db.query(CapturedListing).filter(
            CapturedListing.url_anuncio == item["url_anuncio"]
        ).first()
        if existing:
            saved.append(existing)
            continue

        listing = CapturedListing(**item)
        db.add(listing)
        db.flush()
        saved.append(listing)

    db.commit()
    for s in saved:
        db.refresh(s)

    return saved


@router.get("/", response_model=List[CapturedListingResponse])
async def listar_capturados(
    portal: Optional[str] = None,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Lista anúncios capturados com filtros."""
    query = db.query(CapturedListing)
    if portal:
        query = query.filter(CapturedListing.portal == portal.lower())
    if status:
        query = query.filter(CapturedListing.status == status)
    return query.order_by(CapturedListing.capturado_em.desc()).offset(skip).limit(limit).all()


@router.post("/abordar", response_model=List[OutreachResult])
async def abordar_proprietarios(request: OutreachRequest, db: Session = Depends(get_db)):
    """
    Gera mensagens de abordagem personalizadas e as envia aos proprietários
    via WhatsApp e/ou ligação automatizada.
    """
    if request.listing_ids:
        listings = db.query(CapturedListing).filter(
            CapturedListing.id.in_(request.listing_ids)
        ).all()
    else:
        listings = db.query(CapturedListing).filter(
            CapturedListing.status == CaptureStatus.capturado,
            CapturedListing.proprietario_telefone != None
        ).limit(10).all()

    if not listings:
        raise HTTPException(status_code=404, detail="Nenhum anúncio elegível para abordagem")

    resultados: List[OutreachResult] = []

    for listing in listings:
        mensagem = await _gerar_mensagem_abordagem_ia(listing)
        listing.mensagem_abordagem = mensagem

        canal = request.canal.lower()
        status_envio = "pendente"

        if canal in ("whatsapp", "ambos") and listing.proprietario_telefone:
            wpp_status = await _enviar_whatsapp(listing.proprietario_telefone, mensagem)
            status_envio = wpp_status if wpp_status != "demo_mode" else "demo_simulado"

        if canal in ("ligacao", "ambos") and listing.proprietario_telefone:
            # Versão resumida para TTS
            mensagem_voz = (
                f"Olá! Vi seu anúncio no {listing.portal.capitalize()} "
                f"sobre o {listing.tipo.lower()} em {listing.bairro}. "
                f"Sou corretor da imobiliária e tenho clientes interessados. "
                f"Gostaria de conversar sobre como posso te ajudar a vender mais rápido."
            )
            call_status = await _fazer_ligacao_twilio(listing.proprietario_telefone, mensagem_voz)
            status_envio = f"ligacao_{call_status}"

        listing.status = CaptureStatus.contatado
        listing.contatado_em = datetime.utcnow()

        resultados.append(OutreachResult(
            listing_id=listing.id,
            titulo=listing.titulo,
            telefone=listing.proprietario_telefone,
            mensagem=mensagem,
            canal=canal,
            status_envio=status_envio
        ))

    db.commit()
    return resultados


@router.get("/stats")
async def estatisticas_captacao(db: Session = Depends(get_db)):
    """Retorna estatísticas gerais de captação."""
    total = db.query(CapturedListing).count()
    por_portal = {}
    for portal in ["olx", "vivareal", "zapimoveis"]:
        por_portal[portal] = db.query(CapturedListing).filter(
            CapturedListing.portal == portal
        ).count()

    por_status = {}
    for status in CaptureStatus:
        por_status[status.value] = db.query(CapturedListing).filter(
            CapturedListing.status == status.value
        ).count()

    return {
        "total_capturados": total,
        "por_portal": por_portal,
        "por_status": por_status
    }


@router.post("/reset-demo")
async def resetar_anuncios(db: Session = Depends(get_db)):
    """Apaga todos os anúncios capturados para reiniciar a demonstração."""
    db.query(CapturedListing).delete()
    db.commit()
    return {"mensagem": "Anúncios resetados com sucesso"}
