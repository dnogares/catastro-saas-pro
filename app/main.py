import os
import io
import shutil
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse
import uvicorn

# --- IMPORTACIONES DE TUS MÓDULOS ---
from app.catastro_engine import CatastroDownloader, procesar_y_comprimir
from app.intersection_service import IntersectionService
from app.urban_analysis import AnalizadorUrbanistico
from app.advanced_analysis import AnalizadorAfeccionesAmbientales
from app.schemas import QueryRequest

# --- CONFIGURACIÓN ---
BASE_PATH = Path(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_ROOT = Path("descargas_sistema")
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Catastro SaaS Pro API")

# Montar estáticos y plantillas
app.mount("/static", StaticFiles(directory=str(BASE_PATH / "static")), name="static")
app.mount("/outputs", StaticFiles(directory=str(OUTPUT_ROOT)), name="outputs")
templates = Jinja2Templates(directory=str(BASE_PATH / "templates"))

# Inicializar servicios
intersector = IntersectionService(data_dir=str(BASE_PATH / "capas"))

# --- EL ORQUESTADOR (LO QUE PIDIÓ EL USUARIO) ---
def flujo_total_analisis(ref: str):
    ref = ref.strip().upper()
    dir_ref = OUTPUT_ROOT / ref
    dir_ref.mkdir(parents=True, exist_ok=True)

    # 1. CATASTRO ENGINE: Descarga base y GeoJSON/KML
    # Usamos procesar_y_comprimir que ya tienes en catastro_engine.py
    zip_inicial, data_catastro = procesar_y_comprimir(ref, str(OUTPUT_ROOT))
    
    path_geojson = dir_ref / f"{ref}.geojson"
    path_kml = dir_ref / f"{ref}.kml"

    # 2. INTERSECTION SERVICE: Análisis de GPKG locales (Capas pesadas)
    if intersector and path_geojson.exists():
        intersector.analyze_file(str(path_geojson), output_dir=str(dir_ref))

    # 3. URBAN ANALYSIS: Conexión WMS/WFS (Urbanismo de la Región)
    if path_geojson.exists():
        urb = AnalizadorUrbanistico(str(path_geojson), str(dir_ref))
        urb.ejecutar_analisis_completo()

    # 4. ADVANCED ANALYSIS: Afecciones Ambientales (Shapefiles)
    if path_kml.exists():
        amb = AnalizadorAfeccionesAmbientales(str(path_kml), data_dir=str(BASE_PATH / "capas"))
        amb.ejecutar_analisis()
        amb.generar_pdf(str(dir_ref / f"Informe_Ambiental_{ref}.pdf"))

    # 5. RE-COMPRESIÓN FINAL: Incluir todos los nuevos mapas y PDFs en el ZIP
    zip_final, _ = procesar_y_comprimir(ref, str(OUTPUT_ROOT))
    
    return {
        "referencia": ref,
        "zip_url": f"/outputs/{Path(zip_final).name}",
        "pdf_ambiental": f"/outputs/{ref}/Informe_Ambiental_{ref}.pdf",
        "geojson": f"/outputs/{ref}/{ref}.geojson"
    }

# --- ENDPOINTS ---
@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/dashboard")
async def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})

@app.post("/api/catastro/analisis-completo")
async def api_analisis_completo(request: QueryRequest):
    try:
        # Ejecutamos toda la lógica de tus archivos .py
        resultado = flujo_total_analisis(request.referencia_catastral)
        return {"status": "success", "data": resultado}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "detail": str(e)})

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
