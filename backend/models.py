from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime


# ─── Support ─────────────────────────────────────────────────────────────────

class SupportQuery(BaseModel):
    pergunta: str
    historico: Optional[List[dict]] = []   # [{"role": "user/assistant", "content": "..."}]


class SupportResponse(BaseModel):
    resposta: str
    fontes: List[str] = []
    confianca: float = 0.0


# ─── Leads ───────────────────────────────────────────────────────────────────

class LeadCreate(BaseModel):
    nome: str
    telefone: str
    email: Optional[str] = None
    interesse: Optional[str] = None
    bairro_interesse: Optional[str] = None
    orcamento_min: Optional[float] = None
    orcamento_max: Optional[float] = None
    historico: Optional[str] = ""


class LeadResponse(BaseModel):
    id: int
    nome: str
    telefone: str
    email: Optional[str]
    interesse: Optional[str]
    bairro_interesse: Optional[str]
    orcamento_min: Optional[float]
    orcamento_max: Optional[float]
    ultimo_contato: Optional[datetime]
    status: str
    score_reaquecimento: float
    mensagem_ia: Optional[str]
    criado_em: datetime

    class Config:
        from_attributes = True


class ReactivationRequest(BaseModel):
    lead_ids: Optional[List[int]] = None   # None = processar todos os frios
    enviar_whatsapp: bool = False


class ReactivationResult(BaseModel):
    lead_id: int
    nome: str
    telefone: str
    score: float
    mensagem: str
    status_envio: str


# ─── Properties ──────────────────────────────────────────────────────────────

class PropertyCreate(BaseModel):
    codigo: str
    titulo: str
    tipo: str
    endereco: str
    bairro: str
    cidade: str
    area_m2: Optional[float] = None
    quartos: Optional[int] = None
    banheiros: Optional[int] = None
    vagas: Optional[int] = None
    preco_venda: Optional[float] = None
    preco_aluguel: Optional[float] = None
    proprietario_nome: str
    proprietario_telefone: str


class PropertyResponse(BaseModel):
    id: int
    codigo: str
    titulo: str
    tipo: str
    endereco: str
    bairro: str
    cidade: str
    preco_venda: Optional[float]
    preco_aluguel: Optional[float]
    proprietario_nome: str
    proprietario_telefone: str
    status: str
    ultima_validacao: Optional[datetime]
    resposta_proprietario: Optional[str]
    anuncio_ativo: bool

    class Config:
        from_attributes = True


class ValidationRequest(BaseModel):
    property_ids: Optional[List[int]] = None  # None = validar todos desatualizados
    enviar_whatsapp: bool = False


class ValidationResult(BaseModel):
    property_id: int
    codigo: str
    titulo: str
    proprietario_telefone: str
    mensagem: str
    status_envio: str
    status_atual: str


# ─── Capture ─────────────────────────────────────────────────────────────────

class ScrapeRequest(BaseModel):
    portal: str                            # olx, vivareal, zapimoveis
    cidade: str
    tipo_imovel: str                       # apartamento, casa, terreno
    preco_max: Optional[float] = None
    limite: int = 10


class CapturedListingResponse(BaseModel):
    id: int
    portal: str
    url_anuncio: str
    titulo: str
    tipo: str
    bairro: Optional[str]
    cidade: str
    preco: Optional[float]
    area_m2: Optional[float]
    quartos: Optional[int]
    proprietario_telefone: Optional[str]
    status: str
    mensagem_abordagem: Optional[str]
    capturado_em: datetime

    class Config:
        from_attributes = True


class OutreachRequest(BaseModel):
    listing_ids: Optional[List[int]] = None
    canal: str = "whatsapp"               # whatsapp, ligacao, ambos


class OutreachResult(BaseModel):
    listing_id: int
    titulo: str
    telefone: Optional[str]
    mensagem: str
    canal: str
    status_envio: str
