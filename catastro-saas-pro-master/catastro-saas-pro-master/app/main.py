from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pathlib import Path
import logging

from app.config import settings
from app.catastro_engine import CatastroDownloader
from app.intersection_service import IntersectionService
from app.urban_analysis import AnalizadorUrbanistico
from app.schemas import QueryRequest

# Configuración de logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Catastro SaaS Pro", version="2.5.0")

# CORS y Estáticos
app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"], 
    allow_methods=["*"], 
    allow_headers=["*"]
)

# Montar estáticos para CSS y JS
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Inicializar servicios con las rutas del volumen
# En Easypanel/Docker, el volumen se monta en /app/capas y /app/outputs
catastro = CatastroDownloader(output_dir="/app/outputs")
intersector = IntersectionService(data_dir="/app/capas")
analizador_pdf = AnalizadorUrbanistico(outputs_dir="/app/outputs")

@app.get("/", response_class=HTMLResponse)
async def home():
    return FileResponse("app/templates/index.html")

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    return FileResponse("app/templates/dashboard.html")

@app.post("/api/analizar")
async def analizar_referencia(request: QueryRequest):
    try:
        ref = request.referencia_catastral
        logger.info(f"Procesando referencia: {ref}")

        # 1. Obtener datos oficiales del Catastro
        info_catastro = catastro.consultar_referencia(ref)
        if not info_catastro["success"]:
            raise HTTPException(status_code=404, detail="Referencia no encontrada")

        # 2. Descargar geometría para el análisis espacial
        geo_path = catastro.descargar_geometria(ref)
        
        # 3. Cruzar con tus capas locales (GPKG en el volumen)
        import geopandas as gpd
        gdf_parcela = gpd.read_file(geo_path)
        afecciones = intersector.realizar_interseccion(gdf_parcela)

        # 4. Generar el Informe PDF técnico
        pdf_name = analizador_pdf.generar_informe_pdf(
            datos_parcela=info_catastro['data'].get('rc', {}),
            afecciones=afecciones,
            referencia=ref
        )

        return {
            "status": "success",
            "data": {
                "info": info_catastro["data"],
                "afecciones": afecciones,
                "pdf_url": f"/api/descargar/{pdf_name}",
                "geometria": gdf_parcela.__geo_interface__
            }
        }
    except Exception as e:
        logger.error(f"Error en el servidor: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/descargar/{file_name}")
async def descargar(file_name: str):
    file_path = Path("/app/outputs") / file_name
    if file_path.exists():
        return FileResponse(path=file_path, filename=file_name)
    raise HTTPException(status_code=404, detail="Archivo no encontrado")
