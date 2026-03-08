from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, Boolean, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import enum

DATABASE_URL = "sqlite:///./imobiliaria.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ─── Enums ───────────────────────────────────────────────────────────────────

class LeadStatus(str, enum.Enum):
    novo = "novo"
    em_contato = "em_contato"
    reaquecido = "reaquecido"
    convertido = "convertido"
    perdido = "perdido"

class PropertyStatus(str, enum.Enum):
    disponivel = "disponivel"
    vendido = "vendido"
    alugado = "alugado"
    desatualizado = "desatualizado"
    validando = "validando"

class CaptureStatus(str, enum.Enum):
    capturado = "capturado"
    contatado = "contatado"
    negociando = "negociando"
    convertido = "convertido"
    sem_interesse = "sem_interesse"


# ─── Models ──────────────────────────────────────────────────────────────────

class Lead(Base):
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(200))
    telefone = Column(String(20))
    email = Column(String(200))
    interesse = Column(String(500))           # tipo de imóvel desejado
    bairro_interesse = Column(String(200))
    orcamento_min = Column(Float, nullable=True)
    orcamento_max = Column(Float, nullable=True)
    ultimo_contato = Column(DateTime, nullable=True)
    status = Column(String(50), default=LeadStatus.novo)
    historico = Column(Text, default="")      # JSON com histórico de interações
    score_reaquecimento = Column(Float, default=0.0)
    mensagem_ia = Column(Text, nullable=True) # última mensagem gerada pela IA
    criado_em = Column(DateTime, default=datetime.utcnow)
    atualizado_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Property(Base):
    __tablename__ = "properties"

    id = Column(Integer, primary_key=True, index=True)
    codigo = Column(String(50), unique=True, index=True)
    titulo = Column(String(500))
    tipo = Column(String(100))               # apartamento, casa, terreno, etc.
    endereco = Column(String(500))
    bairro = Column(String(200))
    cidade = Column(String(200))
    area_m2 = Column(Float, nullable=True)
    quartos = Column(Integer, nullable=True)
    banheiros = Column(Integer, nullable=True)
    vagas = Column(Integer, nullable=True)
    preco_venda = Column(Float, nullable=True)
    preco_aluguel = Column(Float, nullable=True)
    proprietario_nome = Column(String(200))
    proprietario_telefone = Column(String(20))
    status = Column(String(50), default=PropertyStatus.disponivel)
    ultima_validacao = Column(DateTime, nullable=True)
    resposta_proprietario = Column(Text, nullable=True)
    anuncio_ativo = Column(Boolean, default=True)
    criado_em = Column(DateTime, default=datetime.utcnow)
    atualizado_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CapturedListing(Base):
    __tablename__ = "captured_listings"

    id = Column(Integer, primary_key=True, index=True)
    portal = Column(String(100))             # olx, vivareal, zapimoveis
    url_anuncio = Column(String(1000))
    titulo = Column(String(500))
    tipo = Column(String(100))
    endereco = Column(String(500))
    bairro = Column(String(200))
    cidade = Column(String(200))
    preco = Column(Float, nullable=True)
    area_m2 = Column(Float, nullable=True)
    quartos = Column(Integer, nullable=True)
    proprietario_nome = Column(String(200), nullable=True)
    proprietario_telefone = Column(String(20), nullable=True)
    descricao = Column(Text, nullable=True)
    status = Column(String(50), default=CaptureStatus.capturado)
    mensagem_abordagem = Column(Text, nullable=True)
    capturado_em = Column(DateTime, default=datetime.utcnow)
    contatado_em = Column(DateTime, nullable=True)


class KnowledgeBase(Base):
    __tablename__ = "knowledge_base"

    id = Column(Integer, primary_key=True, index=True)
    categoria = Column(String(200))           # processo, estatuto, politica, regulamento
    titulo = Column(String(500))
    conteudo = Column(Text)
    tags = Column(String(500))
    criado_em = Column(DateTime, default=datetime.utcnow)
    atualizado_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ─── Init ─────────────────────────────────────────────────────────────────────

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)
    _seed_knowledge_base()


def _seed_knowledge_base():
    """Popula a base de conhecimento com dados iniciais de demonstração."""
    db = SessionLocal()
    try:
        if db.query(KnowledgeBase).count() > 0:
            return

        entries = [
            KnowledgeBase(
                categoria="processo",
                titulo="Processo de Captação de Imóveis",
                conteudo="""
                Processo padrão de captação de imóveis:
                1. Identificar proprietário e validar interesse em venda/locação
                2. Agendar visita de avaliação com corretor
                3. Realizar avaliação de mercado (CMA - Comparative Market Analysis)
                4. Apresentar proposta de comissão (padrão: 6% venda, 10% aluguel/mês)
                5. Assinar contrato de exclusividade (recomendado 90 dias)
                6. Produção de material fotográfico profissional
                7. Cadastro nos portais: ZAP, Viva Real, OLX Pro
                8. Ativar campanha no Meta Ads com budget mínimo de R$ 500/mês
                """,
                tags="captação,processo,corretor,contrato"
            ),
            KnowledgeBase(
                categoria="regulamento",
                titulo="CRECI - Regulamentação da Profissão",
                conteudo="""
                Principais regulamentações do CRECI (Conselho Regional de Corretores de Imóveis):
                - Lei 6.530/78: Regulamenta a profissão de corretor de imóveis
                - Resolução COFECI 326/92: Tabela de honorários
                - Comissão de venda: mínimo 6% sobre valor da transação
                - Comissão de locação: equivalente a 1 aluguel
                - Obrigatoriedade de registro no CRECI para intermediação
                - Contrato de prestação de serviços deve ser formalizado por escrito
                - Prazo de exclusividade máximo recomendado: 180 dias
                """,
                tags="creci,regulamento,comissão,lei"
            ),
            KnowledgeBase(
                categoria="politica",
                titulo="Política de Atendimento ao Cliente",
                conteudo="""
                Diretrizes de atendimento:
                - Responder leads em até 5 minutos durante horário comercial (8h-18h)
                - Retorno obrigatório em até 2h para mensagens fora do horário
                - Follow-up semanal para leads em negociação
                - Documentar todas as interações no CRM
                - SLA de visita: agendar em até 48h após solicitação
                - NPS mínimo aceitável: 8/10
                - Clientes VIP (acima de R$ 1M): atendimento prioritário, corretor sênior
                """,
                tags="atendimento,sla,cliente,follow-up"
            ),
            KnowledgeBase(
                categoria="processo",
                titulo="Documentação para Compra e Venda",
                conteudo="""
                Documentos necessários para transação de compra e venda:
                VENDEDOR (Pessoa Física):
                - RG e CPF (autenticados)
                - Certidão de nascimento ou casamento
                - Comprovante de residência
                - Certidão negativa de débitos (SRF, PGFN, Trabalhista)

                IMÓVEL:
                - Matrícula atualizada (máx. 30 dias) - Cartório de Registro de Imóveis
                - IPTU quitado
                - Certidão de ônus reais
                - Habite-se (para imóveis urbanos)
                - ART/RRT de responsabilidade técnica

                COMPRADOR:
                - RG, CPF e comprovante de renda
                - Extrato bancário dos últimos 3 meses
                - IR completo dos últimos 2 anos
                """,
                tags="documentação,compra,venda,matrícula"
            ),
            KnowledgeBase(
                categoria="estatuto",
                titulo="Comissões e Honorários Internos",
                conteudo="""
                Tabela interna de comissões:
                VENDA:
                - Captador: 30% da comissão total
                - Vendedor: 40% da comissão total
                - Imobiliária: 30% da comissão total
                - Venda própria (mesmo corretor capta e vende): 70% para o corretor

                LOCAÇÃO:
                - Taxa de administração mensal: 10% do aluguel
                - Taxa de corretagem: 1 aluguel pago pelo locatário
                - Renovação de contrato: 50% da taxa de corretagem original

                BONIFICAÇÕES:
                - Meta mensal individual atingida: bônus de 5% sobre comissões do mês
                - Melhor captador do mês: R$ 500 bônus
                """,
                tags="comissão,honorários,bonificação,meta"
            ),
        ]

        db.add_all(entries)
        db.commit()
    finally:
        db.close()
