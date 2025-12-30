import os
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

# --- IMPORTACIONES DE TUS MÓDULOS ---
from app.config import settings
from app.schemas import QueryRequest, CatastroResponse
from app.catastro_engine import CatastroDownloader, GeneradorInformeCatastral
from app.intersection_service import IntersectionService
from app.urban_analysis import AnalizadorUrbanistico
from app.new_analysis_module import AdvancedAnalysisModule

app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    debug=settings.DEBUG
)

# 1. CONFIGURACIÓN DE CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. DIRECTORIOS Y ARCHIVOS ESTÁTICOS
Path(settings.OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
# Montamos la carpeta de resultados para que los PDFs/Mapas sean accesibles por URL
app.mount("/outputs", StaticFiles(directory=settings.OUTPUT_DIR), name="outputs")

# 3. INICIALIZACIÓN DE SERVICIOS (Singleton para caché de capas)
# El IntersectionService carga los GPKG de 4.8GB en memoria según se necesitan
intersection_service = IntersectionService(data_dir=settings.CAPAS_DIR)

# 4. RUTA PARA TU PÁGINA DE BIENVENIDA (INDEX)
@app.get("/", response_class=HTMLResponse)
async def read_index():
    return """
    <!DOCTYPE html><html lang="es"><head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Catastro SaaS Pro - Sistema de Analisis Catastral</title>
    <style>
        body { font-family: sans-serif; line-height: 1.6; margin: 0; color: #333; }
        .hero { background: #2c3e50; color: white; padding: 60px 20px; text-align: center; }
        .container { max-width: 1000px; margin: auto; padding: 20px; }
        .btn { display: inline-block; background: #3498db; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; }
        .feature-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-top: 40px; }
        .feature-card { border: 1px solid #ddd; padding: 20px; border-radius: 8px; text-align: center; }
    </style></head><body>
    <header class="hero"><div class="container">
    <h1>Catastro SaaS Pro</h1><p>Sistema profesional de análisis catastral y consultas de parcelas</p>
    <a href="/docs" class="btn">Ver Documentación API (Swagger)</a>
    </div></header>
    <section class="container"><h2>Funcionalidades</h2><div class="feature-grid">
    <div class="feature-card"><h3>Análisis GIS</h3><p>Cruce espacial con capas GPKG.</p></div>
    <div class="feature-card"><h3>Urbanismo</h3><p>Normativa y afecciones.</p></div>
    <div class="feature-card"><h3>Informes</h3><p>Generación de PDF automático.</p></div>
    </div></section>
    </body></html>
    """

# 5. ENDPOINT PRINCIPAL DE ANÁLISIS
@app.post("/api/analizar", response_model=CatastroResponse)
async def endpoint_analizar(request: QueryRequest):
    ref = request.referencia_catastral.upper().strip()
    
    # Carpeta temporal para los archivos de esta consulta
    path_salida_ref = Path(settings.OUTPUT_DIR) / ref
    path_salida_ref.mkdir(parents=True, exist_ok=True)

    try:
        # FASE 1: Obtener datos oficiales (Catastro)
        downloader = CatastroDownloader(output_dir=str(path_salida_ref))
        res_catastro = downloader.descargar_todo(ref)
        
        path_geojson = res_catastro.get("geojson_path")
        if not path_geojson or not Path(path_geojson).exists():
            raise HTTPException(status_code=404, detail="Referencia no encontrada o sin geometría")

        # FASE 2: Intersección con capas locales (GPKG de 4.8GB)
        res_gis = intersection_service.analyze_file(path_geojson, output_dir=str(path_salida_ref))

        # FASE 3: Análisis Urbanístico
        analizador_urb = AnalizadorUrbanistico(capas_service=intersection_service)
        res_urb = analizador_urb.analizar_referencia(ref, geometria_path=path_geojson)

        # FASE 4: Visualización (Mapa HTML interactivo Leaflet)
        adv_module = AdvancedAnalysisModule(output_dir=str(settings.OUTPUT_DIR))
        adv_module.procesar_archivos([str(path_geojson)])

        # FASE 5: Informe Final PDF
        generador_pdf = GeneradorInformeCatastral(ref, str(path_salida_ref))
        path_pdf = path_salida_ref / f"Informe_{ref}.pdf"
        generador_pdf.generar_pdf(str(path_pdf))

        # RESPUESTA CONSOLIDADA
        return CatastroResponse(
            status="success",
            data={
                "referencia": ref,
                "superficie": res_urb.get("superficie"),
                "intersecciones": res_gis.get("intersecciones", []),
                "descargas": {
                    "pdf": f"/outputs/{ref}/Informe_{ref}.pdf",
                    "mapa": f"/outputs/{ref}/{ref}_mapa.html"
                }
            }
        )

    except Exception as e:
        return CatastroResponse(
            status="error",
            detail=f"Error interno: {str(e)}"
        )

# 6. HEALTH CHECK
@app.get("/api/health")
async def health_check():
    return {"status": "online", "env": settings.ENV, "version": settings.API_VERSION}
