import os
import shutil
import re
import json
import xml.etree.ElementTree as ET
from typing import List
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

# Librerías de Geometría
from shapely.geometry import shape, mapping
from shapely import wkt

# Importamos tu motor (ajusta el nombre del archivo si es necesario)
from app.catastro_engine import CatastroDownloader, procesar_y_comprimir

app = FastAPI(title="Catastro GIS Pro - Fixed")

# --- RUTAS ---
BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/outputs", StaticFiles(directory=str(OUTPUT_DIR)), name="outputs")

# --- LÓGICA DE GEOMETRÍA CORREGIDA ---

def analizar_geometrias_directo(geojson_path, wkt_catastro):
    """
    Parche: Lee el archivo JSON manualmente para evitar errores de formato de Fiona.
    """
    try:
        # Leer el GeoJSON del disco
        with open(geojson_path, 'r') as f:
            data = json.load(f)
        
        # Extraer la geometría (asumiendo formato FeatureCollection o Feature)
        if data.get('type') == 'FeatureCollection':
            geom_usuario = shape(data['features'][0]['geometry'])
        else:
            geom_usuario = shape(data.get('geometry') or data)

        poly_catastro = wkt.loads(wkt_catastro)

        # Validación
        if not poly_catastro.is_valid: poly_catastro = poly_catastro.buffer(0)
        if not geom_usuario.is_valid: geom_usuario = geom_usuario.buffer(0)

        # Cálculo
        interseccion = poly_catastro.intersection(geom_usuario)
        
        return {
            "area_solape": round(interseccion.area, 2),
            "porcentaje": round((interseccion.area / poly_catastro.area) * 100, 2)
        }
    except Exception as e:
        return {"error": f"Fallo en geometría: {str(e)}"}

# --- ENDPOINTS ---

@app.post("/api/analizar")
async def api_analizar(data: dict):
    ref = data.get("referencia_catastral", "").upper()
    # Tu motor ya está funcionando bien según los logs
    zip_path, resultados = procesar_y_comprimir(ref, directorio_base=str(OUTPUT_DIR))
    
    ref_clean = ref.replace(" ", "")
    return {
        "status": "success",
        "data": {
            "zip_url": f"/outputs/{os.path.basename(zip_path)}",
            "pdf_url": f"/outputs/{ref_clean}/{ref_clean}_Informe_Analisis_Espacial.pdf",
            "resultados": resultados
        }
    }

@app.post("/api/upload-vector")
async def api_upload_vector(files: List[UploadFile] = File(...)):
    res_list = []
    for file in files:
        content = await file.read()
        text = content.decode("utf-8", errors="ignore")
        
        # Extraer referencias del KML/GeoJSON
        refs = list(set(re.findall(r'[0-9]{7}[A-Z]{2}[0-9]{4}[A-Z]{1}[0-9]{4}[A-Z]{2}', text)))
        
        for r in refs:
            # Forzamos el procesado
            zip_p, info = procesar_y_comprimir(r, directorio_base=str(OUTPUT_DIR))
            res_list.append({
                "archivo": file.filename,
                "referencia": r,
                "zip": f"/outputs/{os.path.basename(zip_p)}"
            })
    return {"status": "success", "analisis": res_list}

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    # El dashboard que ya tenemos con el mapa Leaflet
    # (Mantener el código anterior del dashboard aquí)
    return "CÓDIGO DEL DASHBOARD ANTERIOR"
