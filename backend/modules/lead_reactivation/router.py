"""
Módulo 2 - Reaquecimento de Leads
──────────────────────────────────
Analisa leads frios/inativos, gera score de reaquecimento e cria
mensagens personalizadas via IA. Integração com WhatsApp via Evolution API.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from anthropic import Anthropic
from datetime import datetime, timedelta
from typing import List, Optional
import httpx
import json

from backend.database import get_db, Lead, LeadStatus
from backend.models import LeadCreate, LeadResponse, ReactivationRequest, ReactivationResult
from backend.config import get_settings

router = APIRouter(prefix="/leads", tags=["Reaquecimento de Leads"])
settings = get_settings()


# ─── Scoring ─────────────────────────────────────────────────────────────────

def _calcular_score_reaquecimento(lead: Lead) -> float:
    """
    Calcula score de 0-100 para priorizar leads para reaquecimento.
    Considera: tempo sem contato, faixa de orçamento e perfil de interesse.
    """
    score = 50.0

    # Penalizar por tempo sem contato (quanto mais tempo, menos urgente)
    if lead.ultimo_contato:
        dias_sem_contato = (datetime.utcnow() - lead.ultimo_contato).days
        if 30 <= dias_sem_contato <= 90:
            score += 20  # Janela ideal para reaquecimento
        elif 90 < dias_sem_contato <= 180:
            score += 10
        elif dias_sem_contato > 180:
            score -= 10
        else:
            score -= 20  # Menos de 30 dias, não precisa reaquecimento
    else:
        score += 15  # Nunca foi contatado, prioridade alta

    # Bônus por orçamento declarado
    if lead.orcamento_max:
        if lead.orcamento_max >= 1_000_000:
            score += 25
        elif lead.orcamento_max >= 500_000:
            score += 15
        elif lead.orcamento_max >= 200_000:
            score += 10
        else:
            score += 5

    # Bônus por completude do perfil
    if lead.interesse:
        score += 5
    if lead.bairro_interesse:
        score += 5
    if lead.email:
        score += 5

    return max(0.0, min(100.0, score))


# ─── WhatsApp ────────────────────────────────────────────────────────────────

async def _enviar_whatsapp(telefone: str, mensagem: str) -> str:
    """Envia mensagem via Evolution API (WhatsApp)."""
    if not settings.whatsapp_api_url or not settings.whatsapp_api_token:
        return "demo_mode"  # Modo demonstração

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{settings.whatsapp_api_url}/message/sendText/{settings.whatsapp_instance}",
                headers={
                    "apikey": settings.whatsapp_api_token,
                    "Content-Type": "application/json"
                },
                json={
                    "number": telefone.replace("+", "").replace(" ", "").replace("-", ""),
                    "text": mensagem
                }
            )
            if response.status_code == 201:
                return "enviado"
            return f"erro_{response.status_code}"
    except Exception as e:
        return f"erro_{str(e)[:50]}"


# ─── IA Message Generation ───────────────────────────────────────────────────

def _gerar_mensagem_demo(lead: Lead) -> str:
    orcamento_str = ""
    if lead.orcamento_max:
        orcamento_str = f" com orçamento de até R$ {lead.orcamento_max:,.0f}"

    interesse_str = lead.interesse or "imóvel"
    bairro_str = f" no {lead.bairro_interesse}" if lead.bairro_interesse else ""

    return (
        f"Olá {lead.nome.split()[0]}! Tudo bem? 😊\n\n"
        f"Sou da [Nome da Imobiliária] e percebi que você estava procurando "
        f"{interesse_str}{bairro_str}{orcamento_str}.\n\n"
        f"Tenho algumas novidades que podem te interessar! "
        f"Acabamos de receber imóveis que batem exatamente com o que você procura.\n\n"
        f"Posso te enviar as opções? Qual o melhor horário para conversarmos? 🏠"
    )


async def _gerar_mensagem_ia(lead: Lead) -> str:
    """Gera mensagem personalizada de reaquecimento usando Claude."""
    if not settings.anthropic_api_key:
        return _gerar_mensagem_demo(lead)

    client = Anthropic(api_key=settings.anthropic_api_key)

    dias_sem_contato = 0
    if lead.ultimo_contato:
        dias_sem_contato = (datetime.utcnow() - lead.ultimo_contato).days

    prompt = f"""Crie uma mensagem de WhatsApp para reaquecimento de lead imobiliário.

DADOS DO LEAD:
- Nome: {lead.nome}
- Interesse: {lead.interesse or 'não especificado'}
- Bairro desejado: {lead.bairro_interesse or 'não especificado'}
- Orçamento máximo: R$ {lead.orcamento_max:,.0f if lead.orcamento_max else 'não informado'}
- Dias sem contato: {dias_sem_contato}
- Histórico: {lead.historico or 'sem histórico registrado'}

DIRETRIZES:
- Tom: amigável, não invasivo, consultivo
- Tamanho: máximo 4 parágrafos curtos
- Incluir: nome do lead, referência ao interesse específico, proposta de valor clara
- NÃO usar: linguagem de vendas agressiva, urgência artificial, clichês
- Usar: emojis com moderação (1-2 no máximo)
- Finalizar com: pergunta aberta ou convite para conversa
- Idioma: português brasileiro informal

Escreva APENAS a mensagem, sem explicações adicionais."""

    response = client.messages.create(
        model=settings.claude_model,
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )

    return response.content[0].text


# ─── Routers ─────────────────────────────────────────────────────────────────

@router.get("/", response_model=List[LeadResponse])
async def listar_leads(
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Lista leads com filtro opcional por status."""
    query = db.query(Lead)
    if status:
        query = query.filter(Lead.status == status)
    return query.offset(skip).limit(limit).all()


@router.post("/", response_model=LeadResponse)
async def criar_lead(lead: LeadCreate, db: Session = Depends(get_db)):
    """Cadastra novo lead."""
    db_lead = Lead(**lead.model_dump())
    db.add(db_lead)
    db.commit()
    db.refresh(db_lead)
    return db_lead


@router.post("/seed-demo")
async def popular_leads_demo(db: Session = Depends(get_db)):
    """Popula banco com leads de demonstração."""
    if db.query(Lead).count() > 0:
        return {"mensagem": "Leads de demo já existem"}

    leads_demo = [
        Lead(nome="Carlos Mendes", telefone="11999001001", email="carlos@email.com",
             interesse="Apartamento 3 quartos", bairro_interesse="Moema",
             orcamento_max=850000, status="perdido",
             ultimo_contato=datetime.utcnow() - timedelta(days=65),
             historico="Visitou 2 imóveis em novembro. Gostou do apto na Alameda Santos mas achou caro."),
        Lead(nome="Ana Paula Ferreira", telefone="11988002002", email="ana.ferreira@email.com",
             interesse="Casa com quintal", bairro_interesse="Granja Viana",
             orcamento_max=1200000, status="perdido",
             ultimo_contato=datetime.utcnow() - timedelta(days=120),
             historico="Procura casa para família com 2 filhos. Precisa de espaço para cachorro."),
        Lead(nome="Roberto Silva", telefone="11977003003",
             interesse="Apartamento 2 quartos", bairro_interesse="Vila Madalena",
             orcamento_max=600000, status="perdido",
             ultimo_contato=datetime.utcnow() - timedelta(days=45),
             historico="Primeiro imóvel. Jovem profissional. Quer área de lazer e home office."),
        Lead(nome="Juliana Costa", telefone="11966004004", email="ju.costa@email.com",
             interesse="Studio / Kitnet", bairro_interesse="Pinheiros",
             orcamento_max=400000, status="perdido",
             ultimo_contato=datetime.utcnow() - timedelta(days=90),
             historico="Investidora. Quer imóvel para renda com aluguel para executivos."),
        Lead(nome="Marcos Oliveira", telefone="11955005005",
             interesse="Cobertura", bairro_interesse="Jardins",
             orcamento_max=2500000, status="perdido",
             ultimo_contato=datetime.utcnow() - timedelta(days=30),
             historico="Empresário. Trocar o atual apartamento por cobertura na mesma região."),
    ]

    db.add_all(leads_demo)
    db.commit()
    return {"mensagem": f"{len(leads_demo)} leads de demonstração criados"}


@router.post("/reativar", response_model=List[ReactivationResult])
async def reativar_leads(request: ReactivationRequest, db: Session = Depends(get_db)):
    """
    Analisa leads frios, gera score e cria mensagens personalizadas de reaquecimento.
    Opcionalmente envia via WhatsApp.
    """
    # Selecionar leads
    if request.lead_ids:
        leads = db.query(Lead).filter(Lead.id.in_(request.lead_ids)).all()
    else:
        # Leads inativos: status perdido ou sem contato há mais de 30 dias
        cutoff = datetime.utcnow() - timedelta(days=30)
        leads = db.query(Lead).filter(
            (Lead.status == LeadStatus.perdido) |
            (Lead.ultimo_contato < cutoff) |
            (Lead.ultimo_contato == None)
        ).limit(20).all()

    if not leads:
        raise HTTPException(status_code=404, detail="Nenhum lead elegível para reaquecimento")

    resultados: List[ReactivationResult] = []

    for lead in leads:
        score = _calcular_score_reaquecimento(lead)
        mensagem = await _gerar_mensagem_ia(lead)

        # Atualizar score no banco
        lead.score_reaquecimento = score
        lead.mensagem_ia = mensagem

        # Enviar WhatsApp se solicitado
        status_envio = "pendente"
        if request.enviar_whatsapp:
            status_envio = await _enviar_whatsapp(lead.telefone, mensagem)
            if status_envio in ("enviado", "demo_mode"):
                lead.status = LeadStatus.em_contato
                lead.ultimo_contato = datetime.utcnow()

        resultados.append(ReactivationResult(
            lead_id=lead.id,
            nome=lead.nome,
            telefone=lead.telefone,
            score=score,
            mensagem=mensagem,
            status_envio=status_envio if status_envio != "demo_mode" else "demo_simulado"
        ))

    db.commit()

    # Ordenar por score decrescente
    resultados.sort(key=lambda x: x.score, reverse=True)
    return resultados
