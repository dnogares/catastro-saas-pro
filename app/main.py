import os
import re
import json
from typing import List
from pathlib import Path
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

# Importación de tu motor lógico
try:
    from app.catastro_engine import CatastroDownloader, procesar_y_comprimir
except ImportError:
    # Fallback para pruebas si el motor no está en la ruta
    def procesar_y_comprimir(ref, directorio_base):
        return f"{directorio_base}/{ref}.zip", {"lat": 40.41, "lon": -3.70}

app = FastAPI(title="Catastro GIS Pro - Fixed")

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

# --- ENDPOINTS ---

@app.post("/api/analizar")
async def api_analizar(data: dict):
    ref = data.get("referencia_catastral", "").upper().strip()
    if not ref:
        raise HTTPException(status_code=400, detail="Falta la referencia")
    
    try:
        zip_path, resultados = procesar_y_comprimir(ref, directorio_base=str(OUTPUT_DIR))
        ref_clean = ref.replace(" ", "")
        
        return {
            "status": "success",
            "data": {
                "referencia": ref,
                "zip_url": f"/outputs/{os.path.basename(zip_path)}",
                "pdf_url": f"/outputs/{ref_clean}/{ref_clean}_Informe_Analisis_Espacial.pdf",
                "coords": {
                    "lat": resultados.get("lat"),
                    "lon": resultados.get("lon")
                }
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/upload-vector")
async def api_upload_vector(files: List[UploadFile] = File(...)):
    lote = []
    for file in files:
        content = await file.read()
        text = content.decode("utf-8", errors="ignore")
        refs = list(set(re.findall(r'[0-9]{7}[A-Z]{2}[0-9]{4}[A-Z]{1}[0-9]{4}[A-Z]{2}', text)))
        for r in refs:
            try:
                zip_p, _ = procesar_y_comprimir(r, directorio_base=str(OUTPUT_DIR))
                lote.append({"ref": r, "zip": f"/outputs/{os.path.basename(zip_p)}"})
            except: continue
    return {"status": "success", "analisis": lote}

# --- DASHBOARD (CORREGIDO SIN F-STRING PARA EVITAR SYNTAX ERROR) ---

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    html_content = """
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <title>Catastro GIS Pro | Engineering Dashboard</title>
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
        <style>
            :root { --primary: #2563eb; --bg: #0f172a; --card: #1e293b; }
            body { font-family: 'Segoe UI', sans-serif; margin: 0; display: flex; height: 100vh; background: var(--bg); color: white; }
            .sidebar { width: 400px; border-right: 1px solid #334155; display: flex; flex-direction: column; background: #0f172a; }
            .p-4 { padding: 20px; }
            .card { background: var(--card); padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid #334155; }
            input[type="text"] { width: 100%; padding: 12px; border-radius: 6px; border: 1px solid #475569; background: #0f172a; color: white; box-sizing: border-box; }
            button { width: 100%; padding: 12px; margin-top: 10px; background: var(--primary); border: none; color: white; font-weight: bold; border-radius: 6px; cursor: pointer; }
            #results { flex-grow: 1; overflow-y: auto; padding: 20px; }
            .res-card { background: #1e293b; border-left: 4px solid var(--primary); padding: 12px; margin-bottom: 10px; border-radius: 4px; }
            .res-card a { color: #60a5fa; text-decoration: none; font-weight: bold; font-size: 13px; margin-right: 10px; }
            #map { flex-grow: 1; }
            .loader { border: 3px solid #f3f3f3; border-top: 3px solid #3498db; border-radius: 50%; width: 16px; height: 16px; animation: spin 1s linear infinite; display: inline-block; }
            @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
            .hidden { display: none; }
        </style>
    </head>
    <body>
        <div class="sidebar">
            <div class="p-4" style="border-bottom: 1px solid #334155;">
                <h1 style="margin:0; font-size: 20px;">CAT PRO <span style="color: var(--primary)">GIS</span></h1>
            </div>
            <div class="p-4">
                <div class="card">
                    <input type="text" id="refInput" placeholder="Referencia Catastral...">
                    <button onclick="procesar()">ANALIZAR FINCA</button>
                    <div id="load-info" class="hidden" style="margin-top:10px; color: #60a5fa; font-size: 13px;">
                        <div class="loader"></div> Procesando datos...
                    </div>
                </div>
                <div class="card" style="border-color: #059669;">
                    <input type="file" id="fileInput" multiple style="font-size: 11px;">
                    <button onclick="subirLote()" style="background: #059669;">SUBIR KML / GEOJSON</button>
                </div>
            </div>
            <div id="results"></div>
        </div>
        <div id="map"></div>

        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <script>
            const map = L.map('map').setView([40.41, -3.70], 6);
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(map);
            const catastro = L.tileLayer.wms("https://ovc.catastro.meh.es/ovcservweb/OVCSWMS.asmx", {
                layers: 'Catastro', format: 'image/png', transparent: true
            }).addTo(map);

            async function procesar() {
                const ref = document.getElementById('refInput').value;
                if(!ref) return;
                document.getElementById('load-info').classList.remove('hidden');
                
                try {
                    const response = await fetch('/api/analizar', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({referencia_catastral: ref})
                    });
                    const res = await response.json();
                    document.getElementById('load-info').classList.add('hidden');
                    
                    if(res.status === 'success') {
                        if(res.data.coords.lat) {
                            map.flyTo([res.data.coords.lat, res.data.coords.lon], 18);
                            L.marker([res.data.coords.lat, res.data.coords.lon]).addTo(map).bindPopup(ref).openPopup();
                        }
                        agregarTarjeta(res.data);
                    }
                } catch(e) { alert("Error de conexión"); }
            }

            function agregarTarjeta(data) {
                const div = document.createElement('div');
                div.className = 'res-card';
                div.innerHTML = `
                    <div style="font-weight:bold; margin-bottom:5px;">${data.referencia}</div>
                    <a href="${data.pdf_url}" target="_blank">📄 PDF
