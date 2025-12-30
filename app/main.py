import os
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

# --- IMPORTACIONES SEGÚN TUS ARCHIVOS SUBIDOS ---
from app.catastro_engine import CatastroDownloader
from app.intersection_service import IntersectionService
from app.urban_analysis import AnalizadorUrbanistico
from app.new_analysis_module import AdvancedAnalysisModule
from app.schemas import QueryRequest

app = FastAPI()

# Directorios de trabajo
BASE_PATH = Path("/app/app")
OUTPUT_ROOT = Path("/app/app/outputs")
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

# Servir archivos para que el frontend pueda descargarlos
app.mount("/outputs", StaticFiles(directory=str(OUTPUT_ROOT)), name="outputs")

@app.post("/api/catastro/analisis-completo")
async def api_analisis_completo(request: QueryRequest):
    ref = request.referencia_catastral.strip().upper()
    
    try:
        # 1. CATASTRO: Obtener datos y geometría
        # Según tu catastro_engine.py, la clase se inicializa con output_dir
        catastro = CatastroDownloader(output_dir=str(OUTPUT_ROOT))
        datos_catastro = catastro.consultar_referencia(ref)
        
        # Guardamos el GeoJSON (necesario para los siguientes pasos)
        # Nota: Asegúrate de que descargar_geometria devuelva la ruta del archivo
        path_geojson = catastro.descargar_geometria(ref) 
        
        if not path_geojson:
            raise Exception("No se pudo obtener la geometría de Catastro")

        # 2. INTERSECCIONES: Cruce con GPKG/Capas locales
        # Según tu intersection_service.py, busca en /app/app/capas
        service_interseccion = IntersectionService(data_dir=str(BASE_PATH / "capas"))
        resultados_gis = service_interseccion.analyze_file(path_geojson, output_dir=str(OUTPUT_ROOT / ref))

        # 3. URBANISMO: Análisis WMS/WFS
        # Tu urban_analysis.py usa analizar_referencia
        analizador_urb = AnalizadorUrbanistico(normativa_dir=str(BASE_PATH / "normativa"))
        resultado_urb = analizador_urb.analizar_referencia(ref, geometria_path=path_geojson)

        # 4. ANÁLISIS AVANZADO: KML/GeoJSON Processing
        # Tu new_analysis_module.py tiene AdvancedAnalysisModule
        adv_module = AdvancedAnalysisModule(output_dir=str(OUTPUT_ROOT))
        resultado_adv = adv_module.procesar_archivos([path_geojson])

        return {
            "status": "success",
            "referencia": ref,
            "resultados": {
                "catastro": datos_catastro,
                "gis": resultados_gis,
                "urbanismo": resultado_urb,
                "avanzado": resultado_adv
            },
            "descargas": {
                "geojson": f"/outputs/{ref}/{ref}.geojson",
                "pdf_informe": f"/outputs/{ref}/informe_final.pdf" # Si lo generas
            }
        }

    except Exception as e:
        return {"status": "error", "detail": str(e)}
