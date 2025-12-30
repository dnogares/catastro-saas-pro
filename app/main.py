import os
from pathlib import Path
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# --- IMPORTACIONES DE TUS ARCHIVOS ---
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

# Configuración de CORS para que tu Frontend pueda conectar
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Montar carpeta de descargas para que los archivos sean accesibles por URL
app.mount("/outputs", StaticFiles(directory=settings.OUTPUT_DIR), name="outputs")

# Inicializar servicios globales (Singleton para aprovechar la caché de capas)
intersection_service = IntersectionService(data_dir=settings.CAPAS_DIR)

@app.post("/api/analizar", response_model=CatastroResponse)
async def endpoint_analisis_completo(request: QueryRequest):
    ref = request.referencia_catastral.upper().strip()
    
    # Crear subcarpeta específica para esta consulta
    path_salida_ref = Path(settings.OUTPUT_DIR) / ref
    path_salida_ref.mkdir(parents=True, exist_ok=True)

    try:
        # 1. MOTOR CATASTRAL: Descarga de Geometría y Datos
        downloader = CatastroDownloader(output_dir=str(path_salida_ref))
        res_catastro = downloader.descargar_todo(ref, crear_zip=False)
        
        path_geojson = res_catastro.get("geojson_path")
        if not path_geojson:
            raise HTTPException(status_code=404, detail="No se encontró la referencia en Catastro")

        # 2. MOTOR DE INTERSECCIONES: Cruce con tus 4.8GB de GPKG
        # Analiza inundabilidad, protecciones, etc.
        res_gis = intersection_service.analyze_file(path_geojson, output_dir=str(path_salida_ref))

        # 3. MOTOR URBANÍSTICO: Cálculo de superficies y zonas
        # Le pasamos el servicio de intersecciones para que use las mismas capas
        analizador_urb = AnalizadorUrbanistico(capas_service=intersection_service)
        res_urbanismo = analizador_urb.analizar_referencia(ref, geometria_path=path_geojson)

        # 4. MOTOR AVANZADO: Generación de Mapa HTML Interactivo (Leaflet)
        adv_module = AdvancedAnalysisModule(output_dir=str(settings.OUTPUT_DIR))
        res_visual = adv_module.procesar_archivos([path_geojson])

        # 5. GENERACIÓN DE INFORME PDF FINAL
        path_pdf = path_salida_ref / f"Informe_{ref}.pdf"
        generador_pdf = GeneradorInformeCatastral(ref, str(path_salida_ref))
        generador_pdf.generar_pdf(str(path_pdf))

        # Construir respuesta consolidada
        return CatastroResponse(
            status="success",
            data={
                "referencia": ref,
                "superficie": res_urbanismo.get("superficie"),
                "afecciones_detectadas": res_gis.get("intersecciones"),
                "urls": {
                    "pdf": f"/outputs/{ref}/Informe_{ref}.pdf",
                    "mapa_interactivo": f"/outputs/{ref}/{ref}_mapa.html",
                    "geojson": f"/outputs/{ref}/{ref}.geojson"
                }
            }
        )

    except Exception as e:
        return CatastroResponse(
            status="error",
            detail=f"Error en el proceso: {str(e)}"
        )

@app.get("/api/health")
async def health_check():
    return {"status": "online", "capas_dir": settings.CAPAS_DIR}
