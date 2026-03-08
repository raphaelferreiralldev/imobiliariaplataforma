"""
Módulo 1 - Suporte Interno IA
─────────────────────────────
Chatbot baseado em RAG que responde perguntas sobre processos internos,
estatutos, regulamentos e políticas da imobiliária.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from anthropic import Anthropic
import json

from backend.database import get_db, KnowledgeBase
from backend.models import SupportQuery, SupportResponse
from backend.config import get_settings

router = APIRouter(prefix="/support", tags=["Suporte Interno"])
settings = get_settings()


def _buscar_contexto(pergunta: str, db: Session) -> tuple[str, list[str]]:
    """Busca documentos relevantes na base de conhecimento (RAG simples por keywords)."""
    palavras = pergunta.lower().split()
    docs = db.query(KnowledgeBase).all()

    scored: list[tuple[float, KnowledgeBase]] = []
    for doc in docs:
        score = 0.0
        texto_busca = (doc.titulo + " " + doc.conteudo + " " + (doc.tags or "")).lower()
        for palavra in palavras:
            if len(palavra) > 3 and palavra in texto_busca:
                score += 1.0
        if score > 0:
            scored.append((score, doc))

    scored.sort(key=lambda x: x[0], reverse=True)
    top_docs = scored[:3]

    if not top_docs:
        # Retorna tudo se não encontrou nada específico
        top_docs = [(0, doc) for doc in docs[:2]]

    contexto = "\n\n".join([
        f"### {doc.titulo} ({doc.categoria})\n{doc.conteudo}"
        for _, doc in top_docs
    ])
    fontes = [doc.titulo for _, doc in top_docs]

    return contexto, fontes


@router.post("/chat", response_model=SupportResponse)
async def chat_suporte(query: SupportQuery, db: Session = Depends(get_db)):
    """
    Responde perguntas da equipe sobre processos internos, regulamentos e políticas.
    """
    if not settings.anthropic_api_key:
        # Modo demo sem API key
        return SupportResponse(
            resposta=(
                "**[MODO DEMO]** Este é um exemplo de resposta do Suporte Interno IA.\n\n"
                "Com a API key configurada, eu buscaria na base de conhecimento e responderia:\n\n"
                f"Sobre sua pergunta: *\"{query.pergunta}\"*\n\n"
                "A comissão padrão de venda é **6%** sobre o valor da transação, "
                "conforme Resolução COFECI 326/92. Internamente, a divisão é: "
                "30% captador, 40% vendedor, 30% imobiliária."
            ),
            fontes=["CRECI - Regulamentação da Profissão", "Comissões e Honorários Internos"],
            confianca=0.95
        )

    client = Anthropic(api_key=settings.anthropic_api_key)
    contexto, fontes = _buscar_contexto(query.pergunta, db)

    system_prompt = f"""Você é o assistente interno de suporte da imobiliária.
Sua função é responder perguntas da equipe de corretores e gestores sobre:
- Processos internos de captação e venda
- Regulamentos do CRECI e legislação imobiliária
- Políticas de atendimento e SLAs
- Tabelas de comissões e honorários
- Documentação necessária para transações

Use APENAS as informações da base de conhecimento fornecida abaixo.
Se não souber a resposta com base no contexto, diga isso claramente e sugira consultar o gestor.
Responda em português brasileiro, de forma direta e objetiva.

BASE DE CONHECIMENTO:
{contexto}
"""

    messages = query.historico + [{"role": "user", "content": query.pergunta}]

    response = client.messages.create(
        model=settings.claude_model,
        max_tokens=1024,
        system=system_prompt,
        messages=messages
    )

    return SupportResponse(
        resposta=response.content[0].text,
        fontes=fontes,
        confianca=0.92
    )


@router.get("/knowledge-base")
async def listar_base_conhecimento(db: Session = Depends(get_db)):
    """Lista todos os documentos da base de conhecimento."""
    docs = db.query(KnowledgeBase).all()
    return [
        {
            "id": doc.id,
            "categoria": doc.categoria,
            "titulo": doc.titulo,
            "tags": doc.tags,
            "criado_em": doc.criado_em
        }
        for doc in docs
    ]


@router.post("/knowledge-base")
async def adicionar_documento(
    categoria: str,
    titulo: str,
    conteudo: str,
    tags: str = "",
    db: Session = Depends(get_db)
):
    """Adiciona novo documento à base de conhecimento."""
    doc = KnowledgeBase(
        categoria=categoria,
        titulo=titulo,
        conteudo=conteudo,
        tags=tags
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return {"id": doc.id, "mensagem": "Documento adicionado com sucesso"}
