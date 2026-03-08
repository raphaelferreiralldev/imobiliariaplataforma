"""
Módulo 3 - Atualização de Base de Imóveis
──────────────────────────────────────────
Valida disponibilidade e preços dos imóveis com proprietários via WhatsApp.
Evita gastos com anúncios de imóveis já vendidos ou com dados desatualizados.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from anthropic import Anthropic
from datetime import datetime, timedelta
from typing import List, Optional
import httpx

from backend.database import get_db, Property, PropertyStatus
from backend.models import (
    PropertyCreate, PropertyResponse,
    ValidationRequest, ValidationResult
)
from backend.config import get_settings

router = APIRouter(prefix="/properties", tags=["Atualização de Imóveis"])
settings = get_settings()


# ─── WhatsApp ────────────────────────────────────────────────────────────────

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


# ─── IA Message Generation ───────────────────────────────────────────────────

def _gerar_mensagem_validacao_demo(prop: Property) -> str:
    preco_str = f"R$ {prop.preco_venda:,.0f}" if prop.preco_venda else "o imóvel"
    return (
        f"Olá {prop.proprietario_nome.split()[0]}! Bom dia! 😊\n\n"
        f"Sou [Nome], da [Imobiliária]. Estou entrando em contato sobre "
        f"o imóvel cadastrado conosco ({prop.titulo}, {prop.bairro}).\n\n"
        f"Gostaríamos de confirmar:\n"
        f"✅ O imóvel ainda está disponível para venda?\n"
        f"✅ O valor de {preco_str} ainda está correto?\n\n"
        f"Temos clientes interessados no perfil do seu imóvel! "
        f"Poderia me confirmar? Qualquer atualização, pode me avisar aqui. 🏠"
    )


async def _gerar_mensagem_validacao_ia(prop: Property) -> str:
    if not settings.anthropic_api_key:
        return _gerar_mensagem_validacao_demo(prop)

    client = Anthropic(api_key=settings.anthropic_api_key)

    dias_sem_validar = 0
    if prop.ultima_validacao:
        dias_sem_validar = (datetime.utcnow() - prop.ultima_validacao).days
    else:
        dias_sem_validar = (datetime.utcnow() - prop.criado_em).days

    prompt = f"""Crie uma mensagem de WhatsApp para validar disponibilidade de imóvel com proprietário.

DADOS DO IMÓVEL:
- Tipo: {prop.tipo}
- Título: {prop.titulo}
- Bairro: {prop.bairro}, {prop.cidade}
- Preço anunciado: R$ {prop.preco_venda:,.0f if prop.preco_venda else 'não informado'}
- Proprietário: {prop.proprietario_nome}
- Dias desde última validação: {dias_sem_validar}

OBJETIVO DA MENSAGEM:
1. Confirmar se o imóvel ainda está disponível para venda/locação
2. Confirmar se o preço ainda está correto
3. Perguntar sobre interesse em continuar a parceria com nossa imobiliária
4. Informar que temos clientes interessados (desperta interesse sem pressão)

DIRETRIZES:
- Tom: profissional, amigável, respeitoso
- Tamanho: máximo 4 parágrafos curtos
- NÃO usar: linguagem de pressão ou urgência artificial
- Usar: emojis com moderação (1-2)
- Incluir checkboxes ✅ para facilitar resposta do proprietário
- Idioma: português brasileiro

Escreva APENAS a mensagem, sem explicações."""

    response = client.messages.create(
        model=settings.claude_model,
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text


# ─── Routers ─────────────────────────────────────────────────────────────────

@router.get("/", response_model=List[PropertyResponse])
async def listar_imoveis(
    status: Optional[str] = None,
    bairro: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Lista imóveis com filtros opcionais."""
    query = db.query(Property)
    if status:
        query = query.filter(Property.status == status)
    if bairro:
        query = query.filter(Property.bairro.ilike(f"%{bairro}%"))
    return query.offset(skip).limit(limit).all()


@router.post("/", response_model=PropertyResponse)
async def cadastrar_imovel(prop: PropertyCreate, db: Session = Depends(get_db)):
    """Cadastra novo imóvel na base."""
    db_prop = Property(**prop.model_dump())
    db.add(db_prop)
    db.commit()
    db.refresh(db_prop)
    return db_prop


@router.post("/seed-demo")
async def popular_imoveis_demo(db: Session = Depends(get_db)):
    """Popula banco com imóveis de demonstração."""
    if db.query(Property).count() > 0:
        return {"mensagem": "Imóveis de demo já existem"}

    imoveis_demo = [
        Property(codigo="AP001", titulo="Apartamento 3 quartos - Moema", tipo="Apartamento",
                 endereco="Rua Itapeva, 123", bairro="Moema", cidade="São Paulo",
                 area_m2=95, quartos=3, banheiros=2, vagas=2,
                 preco_venda=920000, proprietario_nome="João Santos",
                 proprietario_telefone="11999101001", status="disponivel",
                 ultima_validacao=datetime.utcnow() - timedelta(days=95)),
        Property(codigo="CA001", titulo="Casa 4 quartos - Granja Viana", tipo="Casa",
                 endereco="Rua das Palmeiras, 456", bairro="Granja Viana", cidade="Cotia",
                 area_m2=280, quartos=4, banheiros=3, vagas=3,
                 preco_venda=1450000, proprietario_nome="Maria Oliveira",
                 proprietario_telefone="11988102002", status="disponivel",
                 ultima_validacao=datetime.utcnow() - timedelta(days=120)),
        Property(codigo="AP002", titulo="Studio moderno - Vila Madalena", tipo="Studio",
                 endereco="Rua Harmonia, 789", bairro="Vila Madalena", cidade="São Paulo",
                 area_m2=42, quartos=1, banheiros=1, vagas=1,
                 preco_venda=550000, preco_aluguel=2800,
                 proprietario_nome="Pedro Costa", proprietario_telefone="11977103003",
                 status="disponivel", ultima_validacao=datetime.utcnow() - timedelta(days=60)),
        Property(codigo="AP003", titulo="Cobertura duplex - Jardins", tipo="Cobertura",
                 endereco="Alameda Jardins, 321", bairro="Jardins", cidade="São Paulo",
                 area_m2=350, quartos=4, banheiros=5, vagas=4,
                 preco_venda=3800000, proprietario_nome="Luisa Ferreira",
                 proprietario_telefone="11966104004", status="disponivel",
                 ultima_validacao=datetime.utcnow() - timedelta(days=45)),
        Property(codigo="CA002", titulo="Casa geminada - Tatuapé", tipo="Casa",
                 endereco="Rua do Tatuapé, 654", bairro="Tatuapé", cidade="São Paulo",
                 area_m2=120, quartos=3, banheiros=2, vagas=2,
                 preco_venda=680000, proprietario_nome="Antônio Melo",
                 proprietario_telefone="11955105005", status="disponivel",
                 ultima_validacao=datetime.utcnow() - timedelta(days=200)),
    ]

    db.add_all(imoveis_demo)
    db.commit()
    return {"mensagem": f"{len(imoveis_demo)} imóveis de demonstração criados"}


@router.get("/desatualizados", response_model=List[PropertyResponse])
async def listar_desatualizados(
    dias: int = 60,
    db: Session = Depends(get_db)
):
    """Lista imóveis não validados há mais de N dias (padrão: 60 dias)."""
    cutoff = datetime.utcnow() - timedelta(days=dias)
    imoveis = db.query(Property).filter(
        (Property.ultima_validacao < cutoff) |
        (Property.ultima_validacao == None),
        Property.status == PropertyStatus.disponivel
    ).all()
    return imoveis


@router.post("/validar", response_model=List[ValidationResult])
async def validar_imoveis(request: ValidationRequest, db: Session = Depends(get_db)):
    """
    Gera e opcionalmente envia mensagens de validação para proprietários via WhatsApp.
    Prioriza imóveis mais desatualizados.
    """
    if request.property_ids:
        imoveis = db.query(Property).filter(Property.id.in_(request.property_ids)).all()
    else:
        # Selecionar os mais desatualizados
        cutoff = datetime.utcnow() - timedelta(days=60)
        imoveis = db.query(Property).filter(
            (Property.ultima_validacao < cutoff) |
            (Property.ultima_validacao == None),
            Property.status == PropertyStatus.disponivel
        ).order_by(Property.ultima_validacao.asc()).limit(15).all()

    if not imoveis:
        raise HTTPException(status_code=404, detail="Nenhum imóvel elegível para validação")

    resultados: List[ValidationResult] = []

    for prop in imoveis:
        mensagem = await _gerar_mensagem_validacao_ia(prop)
        prop.status = PropertyStatus.validando

        status_envio = "pendente"
        if request.enviar_whatsapp:
            status_envio = await _enviar_whatsapp(prop.proprietario_telefone, mensagem)
            if status_envio in ("enviado", "demo_mode"):
                status_envio = status_envio if status_envio != "demo_mode" else "demo_simulado"

        resultados.append(ValidationResult(
            property_id=prop.id,
            codigo=prop.codigo,
            titulo=prop.titulo,
            proprietario_telefone=prop.proprietario_telefone,
            mensagem=mensagem,
            status_envio=status_envio,
            status_atual=prop.status
        ))

    db.commit()
    return resultados


@router.patch("/{property_id}/resposta")
async def registrar_resposta_proprietario(
    property_id: int,
    disponivel: bool,
    novo_preco: Optional[float] = None,
    observacao: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Registra a resposta do proprietário sobre disponibilidade do imóvel."""
    prop = db.query(Property).filter(Property.id == property_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Imóvel não encontrado")

    prop.ultima_validacao = datetime.utcnow()
    prop.resposta_proprietario = observacao
    prop.anuncio_ativo = disponivel

    if disponivel:
        prop.status = PropertyStatus.disponivel
        if novo_preco:
            prop.preco_venda = novo_preco
    else:
        prop.status = PropertyStatus.vendido
        prop.anuncio_ativo = False

    db.commit()
    db.refresh(prop)

    economia = "R$ ~500/mês" if not disponivel else None
    return {
        "mensagem": "Resposta registrada com sucesso",
        "status_atualizado": prop.status,
        "anuncio_ativo": prop.anuncio_ativo,
        "economia_estimada": economia
    }
