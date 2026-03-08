"""
Imobiliária IA Platform
═══════════════════════
Plataforma de IA para otimização de marketing e operações imobiliárias.

Módulos:
  1. Suporte Interno IA     → /api/support
  2. Reaquecimento de Leads → /api/leads
  3. Atualização de Imóveis → /api/properties
  4. Captação de Anúncios   → /api/capture
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from backend.database import init_db
from backend.config import get_settings
from backend.modules.support.router import router as support_router
from backend.modules.lead_reactivation.router import router as leads_router
from backend.modules.property_update.router import router as properties_router
from backend.modules.property_capture.router import router as capture_router

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=__doc__,
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(support_router, prefix="/api")
app.include_router(leads_router, prefix="/api")
app.include_router(properties_router, prefix="/api")
app.include_router(capture_router, prefix="/api")


# Frontend
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

    @app.get("/")
    async def serve_frontend():
        return FileResponse(os.path.join(frontend_dir, "index.html"))


@app.on_event("startup")
async def startup_event():
    init_db()
    print(f"\n{'='*50}")
    print(f"  {settings.app_name} v{settings.app_version}")
    print(f"{'='*50}")
    print(f"  API Docs: http://localhost:8000/api/docs")
    print(f"  Dashboard: http://localhost:8000")
    print(f"{'='*50}\n")


@app.get("/api/health")
async def health_check():
    return {
        "status": "online",
        "versao": settings.app_version,
        "modulos": {
            "suporte_interno": "ativo",
            "reaquecimento_leads": "ativo",
            "atualizacao_imoveis": "ativo",
            "captacao_anuncios": "ativo"
        },
        "modo": "demo" if not settings.anthropic_api_key else "producao"
    }
