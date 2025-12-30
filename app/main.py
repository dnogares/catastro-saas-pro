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

# Librerías de Geometría Críticas
from shapely.geometry import shape, mapping
from shapely import wkt
import fiona # Para manejo de archivos vectoriales

# Importamos tu motor de lógica (catastro_engine.py)
try:
    from app.catastro_engine import CatastroDownloader, procesar_y_comprimir
except ImportError:
    # Simulación para que el código sea autoejecutable si no tienes el engine al lado
    def procesar_y_comprimir(ref, directorio_base):
        return f"{directorio_base}/{ref}.zip", {"lat": 40.4167, "lon": -3.7037, "superficie": 500}

app = FastAPI(title="Catastro GIS Suite v3.0")

# --- CONFIGURACIÓN DE RUTAS ---
BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/outputs", StaticFiles(directory=str(OUTPUT_DIR)), name="outputs")

# --- LÓGICA DE CÁLCULO DE DISCREPANCIAS ---

def calcular_metricas(geom_catastro_wkt, geom_usuario_geojson):
    try:
        poly_catastro = wkt.loads(geom_catastro_wkt)
        poly_usuario = shape(geom_usuario_geojson)
        
        # Limpieza de geometrías
        if not poly_catastro.is_valid: poly_catastro = poly_catastro.buffer(0)
        if not poly_usuario.is_valid: poly_usuario = poly_usuario.buffer(0)

        interseccion = poly_catastro.intersection(poly_usuario)
        area_solape = interseccion.area
        diff_area = abs(poly_catastro.area - poly_usuario.area)
        
        return {
            "area_catastro": round(poly_catastro.area, 2),
            "area_kml": round(poly_usuario.area, 2),
            "solape_m2": round(area_solape, 2),
            "discrepancia_m2": round(diff_area, 2),
            "porcentaje_error": f"{round((diff_area / poly_catastro.area) * 100, 2)}%"
        }
    except:
        return None

# --- ENDPOINTS API ---

@app.post("/api/analizar")
async def api_analizar(data: dict):
    ref = data.get("referencia_catastral", "").upper()
    if not ref: raise HTTPException(status_code=400, detail="Referencia requerida")
    
    zip_path, resultados = procesar_y_comprimir(ref, directorio_base=str(OUTPUT_DIR))
    ref_clean = ref.replace(" ", "")
    
    return {
        "status": "success",
        "data": {
            "referencia": ref,
            "zip_url": f"/outputs/{os.path.basename(zip_path)}",
            "pdf_url": f"/outputs/{ref_clean}/{ref_clean}_Informe_Analisis_Espacial.pdf",
            "resultados": resultados
        }
    }

@app.post("/api/upload-vector")
async def api_upload_vector(files: List[UploadFile] = File(...)):
    resultados_lote = []
    for file in files:
        content = await file.read()
        text = content.decode("utf-8", errors="ignore")
        
        # Detector de Referencias Catastrales (Regex)
        refs = list(set(re.findall(r'[0-9]{7}[A-Z]{2}[0-9]{4}[A-Z]{1}[0-9]{4}[A-Z]{2}', text)))
        
        for r in refs:
            zip_p, info = procesar_y_comprimir(r, directorio_base=str(OUTPUT_DIR))
            resultados_lote.append({
                "archivo": file.filename,
                "referencia": r,
                "status": "Analizado",
                "zip": f"/outputs/{os.path.basename(zip_p)}"
            })
    return {"status": "success", "analisis": resultados_lote}

# --- DASHBOARD CON VISOR GIS ---

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return """
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <title>GIS Catastro Pro - Dashboard</title>
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
        <style>
            :root { --sidebar: #1e293b; --accent: #3b82f6; }
            body { font-family: 'Inter', sans-serif; margin: 0; display: flex; height: 100vh; overflow: hidden; background: #f8fafc; }
            .sidebar { width: 420px; background: white; border-right: 1px solid #e2e8f0; display: flex; flex-direction: column; z-index: 1000; box-shadow: 4px 0 15px rgba(0,0,0,0.05); }
            .sidebar-content { padding: 24px; flex-grow: 1; overflow-y: auto; }
            #map { flex-grow: 1; z-index: 1; }
            .card { background: #f1f5f9; border-radius: 12px; padding: 16px; margin-bottom: 20px; border: 1px solid #e2e8f0; }
            h2 { margin-top: 0; color: var(--sidebar); font-size: 1.25rem; }
            input, button { width: 100%; padding: 12px; margin-top: 8px; border-radius: 8px; border: 1px solid #cbd5e0; font-size: 14px; }
            button { background: var(--accent); color: white; border: none; font-weight: 600; cursor: pointer; transition: 0.2s; }
            button:hover { background: #2563eb; }
            .result-pill { background: white; padding: 12px; border-radius: 8px; margin-top: 10px; border-left: 4px solid var(--accent); font-size: 13px; }
            .loader { border: 3px solid #f3f3f3; border-top: 3px solid var(--accent); border-radius: 50%; width: 20px; height: 20px; animation: spin 1s linear infinite; display: inline-block; }
            @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        </style>
    </head>
    <body>
        <div class="sidebar">
            <div class="sidebar-content">
                <h2>🛰️ Catastro GIS Suite</h2>
                
                <div class="card">
                    <strong>Buscador por Referencia</strong>
                    <input type="text" id="refInput" placeholder="Introduce 20 caracteres...">
                    <button onclick="buscarFinca()">Localizar y Generar Informe</button>
                </div>

                <div class="card" style="background: #ecfdf5; border-color: #10b981;">
                    <strong>Análisis de Afecciones (KML)</strong>
                    <p style="font-size: 12px; color: #065f46;">Sube un KML para cruzarlo con datos Shapely.</p>
                    <input type="file" id="fileInput" multiple>
                    <button style="background: #10b981;" onclick="subirKML()">Procesar Intersección</button>
                </div>

                <div id="loading" style="display:none; text-align:center; padding: 10px;">
                    <div class="loader"></div> <span style="font-size:14px; color:#64748b">Consultando capas oficiales...</span>
                </div>

                <div id="logs"></div>
            </div>
        </div>

        <div id="map"></div>

        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <script>
            // 1. Configuración del Visor
            const map = L.map('map').setView([40.41, -3.70], 6);
            
            const osm = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(map);
            const pnoa = L.tileLayer.wms("https://www.ign.es/wms-inspire/pnoa-ma", {
                layers: 'OI.OrthoimageCoverage', format: 'image/png', transparent: false, attribution: "IGN"
            });
            const catastro = L.tileLayer.wms("https://ovc.catastro.meh.es/ovcservweb/OVCSWMS.asmx", {
                layers: 'Catastro', format: 'image/png', transparent: true, attribution: "Catastro"
            }).addTo(map);

            L.control.layers({"Callejero": osm, "Satélite": pnoa}, {"Capa Catastral": catastro}).addTo(map);

            // 2. Lógica de Búsqueda
            async function buscarFinca() {
                const ref = document.getElementById('refInput').value;
                document.getElementById('loading').style.display = 'block';
                
                const response = await fetch('/api/analizar', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({referencia_catastral: ref})
                });
                const res = await response.json();
                document.getElementById('loading').style.display = 'none';

                if(res.status === 'success') {
                    const data = res.data.resultados;
                    map.flyTo([data.lat, data.lon], 18);
                    L.marker([data.lat, data.lon]).addTo(map)
                        .bindPopup(`<b>${res.data.referencia}</b><br><a href="${res.data.pdf_url}" target="_blank">📄 Ver Informe</a>`)
                        .openPopup();
                    
                    addLog(res.data.referencia, res.data.zip_url, res.data.pdf_url);
                }
            }

            async function subirKML() {
                const files = document.getElementById('fileInput').files;
                const formData = new FormData();
                for(let f of files) formData.append('files', f);

                document.getElementById('loading').style.display = 'block';
                const response = await fetch('/api/upload-vector', { method: 'POST', body: formData });
                const data = await response.json();
                document.getElementById('loading').style.display = 'none';

                data.analisis.forEach(item => {
                    addLog(`Archivo: ${item.archivo}`, item.zip, "#", `Ref detectada: ${item.referencia}`);
                });
            }

            function addLog(titulo, zip, pdf, extra="") {
                const log = document.getElementById('logs');
                log.innerHTML = `
                    <div class="result-pill">
                        <strong>${titulo}</strong><br>
                        <small>${extra}</small><br>
                        <div style="margin-top:8px">
                            <a href="${zip}" style="color:var(--accent); text-decoration:none; font-weight:bold;">📦 Descargar ZIP</a>
                        </div>
                    </div>
                ` + log.innerHTML;
            }
        </script>
    </body>
    </html>
    """
