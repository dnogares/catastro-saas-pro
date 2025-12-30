import os
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# --- IMPORTACIONES CORREGIDAS ---
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

# Configuración de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Asegurar que existan los directorios base
Path(settings.OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

# Montar carpeta de descargas (para acceder a PDFs y Mapas vía URL)
app.mount("/outputs", StaticFiles(directory=settings.OUTPUT_DIR), name="outputs")

# Inicializar Servicio GIS (Carga las capas GPKG en memoria una sola vez)
intersection_service = IntersectionService(data_dir=settings.CAPAS_DIR)

@app.post("/api/analizar", response_model=CatastroResponse)
async def analizar_completo(request: QueryRequest):
    ref = request.referencia_catastral.upper().strip()
    
    # Carpeta específica para los resultados de esta parcela
    path_salida_ref = Path(settings.OUTPUT_DIR) / ref
    path_salida_ref.mkdir(parents=True, exist_ok=True)

    try:
        # 1. MOTOR CATASTRAL: Bajar GeoJSON y Datos oficiales
        downloader = CatastroDownloader(output_dir=str(path_salida_ref))
        res_catastro = downloader.descargar_todo(ref, crear_zip=True)
        
        path_geojson = res_catastro.get("geojson_path")
        if not path_geojson or not Path(path_geojson).exists():
            raise HTTPException(status_code=404, detail="No se pudo obtener la geometría de Catastro")

        # 2. MOTOR GIS: Cruce con capas de inundabilidad/medio ambiente
        # Usa el servicio global para no recargar los 4.8GB cada vez
        res_gis = intersection_service.analyze_file(path_geojson, output_dir=str(path_salida_ref))

        # 3. MOTOR URBANÍSTICO: Superficies y Afecciones Locales
        analizador_urb = AnalizadorUrbanistico(capas_service=intersection_service)
        res_urbanismo = analizador_urb.analizar_referencia(ref, geometria_path=path_geojson)

        # 4. MOTOR VISUAL: Generar el Mapa Web Interactivo (Leaflet)
        # Nota: AdvancedAnalysisModule procesa el geojson y crea el .html
        adv_module = AdvancedAnalysisModule(output_dir=str(settings.OUTPUT_DIR))
        res_visual = adv_module.procesar_archivos([path_geojson])

        # 5. GENERACIÓN DEL INFORME PDF PROFESIONAL
        path_pdf = path_salida_ref / f"Informe_{ref}.pdf"
        generador_pdf = GeneradorInformeCatastral(ref, str(path_salida_ref))
        generador_pdf.generar_pdf(str(path_pdf))

        # Construir respuesta para el Frontend
        return CatastroResponse(
            status="success",
            data={
                "referencia": ref,
                "superficie_m2": res_urbanismo.get("superficie", {}).get("valor"),
                "afecciones": res_gis.get("intersecciones", []),
                "descargas": {
                    "pdf": f"/outputs/{ref}/Informe_{ref}.pdf",
                    "mapa_interactivo": f"/outputs/{ref}/{ref}_mapa.html",
                    "zip_completo": f"/outputs/{ref}_datos.zip"
                }
            }
        )

    except Exception as e:
        return CatastroResponse(
            status="error",
            detail=f"Error en el proceso: {str(e)}"
        )

@app.get("/api/health")
async def health():
    return {"status": "ok", "env": settings.ENV}
