import os
import io
import shutil
import tempfile
import pandas as pd
from pathlib import Path
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import uvicorn

# --- 1. CONFIGURACIÓN DE RUTAS ---
BASE_PATH = Path(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_ROOT = Path("descargas_sistema")
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

# --- 2. IMPORTACIONES DE MÓDULOS ---
try:
    from app.catastro_engine import CatastroDownloader, procesar_y_comprimir
    from app.intersection_service import IntersectionService
    from app.urban_analysis import AnalizadorUrbanistico
    from app.schemas import QueryRequest, CatastroResponse
    print("[INFO] Módulos cargados con éxito.")
except ImportError as e:
    print(f"[ERROR] Error de importación: {e}")
    raise

# --- 3. INICIALIZACIÓN ---
app = FastAPI(title="Catastro SaaS Pro")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Montar carpetas
app.mount("/static", StaticFiles(directory=str(BASE_PATH / "static")), name="static")
app.mount("/outputs", StaticFiles(directory=str(OUTPUT_ROOT)), name="outputs")
templates = Jinja2Templates(directory=str(BASE_PATH / "templates"))

# Inicializar Motores
try:
    intersector = IntersectionService(data_dir=str(BASE_PATH / "capas"))
except Exception as e:
    print(f"[WARN] IntersectionService no cargado: {e}")
    intersector = None

# --- 4. LÓGICA DE FLUJO PROFESIONAL ---
def ejecutar_flujo_completo(ref: str):
    ref = ref.strip().upper()
    # A. Catastro Base
    zip_path, res_cat = procesar_y_comprimir(ref, str(OUTPUT_ROOT))
    dir_ref = OUTPUT_ROOT / ref
    path_geojson = dir_ref / f"{ref}.geojson"

    # B. Intersección (GPKG)
    if intersector and path_geojson.exists():
        intersector.analyze_file(str(path_geojson), output_dir=str(dir_ref))

    # C. Urbanismo (WMS)
    if path_geojson.exists():
        analizador_urb = AnalizadorUrbanistico(str(path_geojson), str(dir_ref))
        analizador_urb.ejecutar_analisis_completo()

    return {
        "referencia": ref,
        "zip_name": Path(zip_path).name if zip_path else None
    }

# --- 5. ENDPOINTS ---
@app.get("/")
async def get_dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})

@app.post("/api/catastro/query")
async def api_query(request: QueryRequest):
    try:
        res = ejecutar_flujo_completo(request.referencia_catastral)
        return {
            "status": "success",
            "data": {
                "zip_url": f"/outputs/{res['zip_name']}",
                "referencia": res["referencia"]
            }
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})

@app.post("/api/catastro/batch")
async def api_batch(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        df = pd.read_excel(io.BytesIO(contents)) if file.filename.endswith('.xlsx') else pd.read_csv(io.BytesIO(contents))
        if 'referencia' not in df.columns:
            throw HTTPException(400, "Falta columna 'referencia'")
        
        for ref in df['referencia'].dropna().unique():
            try: ejecutar_flujo_completo(str(ref))
            except: continue
        return {"status": "success", "msg": "Procesamiento masivo iniciado"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
