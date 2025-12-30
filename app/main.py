import os
import re
import json
from typing import List
from pathlib import Path
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

# Importación de tu motor
try:
    from app.catastro_engine import CatastroDownloader, procesar_y_comprimir
except ImportError:
    def procesar_y_comprimir(ref, directorio_base):
        # Simulación de respaldo para evitar errores de arranque
        return f"{directorio_base}/{ref}.zip", {"lat": 40.41, "lon": -3.70, "superficie": "1250"}

app = FastAPI(title="Catastro GIS Pro - Suite Completa")

# --- CONFIGURACIÓN DE RUTAS ---
BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/outputs", StaticFiles(directory=str(OUTPUT_DIR)), name="outputs")

# --- ENDPOINTS API ---

@app.post("/api/analizar")
async def api_analizar(data: dict):
    ref = data.get("referencia_catastral", "").upper().strip()
    if not ref: raise HTTPException(status_code=400, detail="Referencia requerida")
    try:
        zip_path, resultados = procesar_y_comprimir(ref, directorio_base=str(OUTPUT_DIR))
        return {
            "status": "success",
            "data": {
                "referencia": ref,
                "zip_url": f"/outputs/{os.path.basename(zip_path)}",
                "pdf_url": f"/outputs/{ref.replace(' ', '')}/{ref.replace(' ', '')}_Informe_Analisis_Espacial.pdf",
                "coords": {"lat": resultados.get('lat'), "lon": resultados.get('lon')},
                "stats": resultados
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/upload-vector")
async def api_upload_vector(files: List[UploadFile] = File(...)):
    lote_resultados = []
    for file in files:
        content = await file.read()
        text = content.decode("utf-8", errors="ignore")
        refs = list(set(re.findall(r'[0-9]{7}[A-Z]{2}[0-9]{4}[A-Z]{1}[0-9]{4}[A-Z]{2}', text)))
        for r in refs:
            try:
                zip_path, resultados = procesar_y_comprimir(r, directorio_base=str(OUTPUT_DIR))
                lote_resultados.append({
                    "referencia": r,
                    "zip_url": f"/outputs/{os.path.basename(zip_path)}",
                    "pdf_url": f"/outputs/{r.replace(' ', '')}/{r.replace(' ', '')}_Informe_Analisis_Espacial.pdf",
                    "coords": {"lat": resultados.get('lat'), "lon": resultados.get('lon')}
                })
            except: continue
    return {"status": "success", "data": lote_resultados}

# --- DASHBOARD INTEGRADO ---

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    # Usamos un return simple para evitar conflictos de llaves de Python f-strings
    return """
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <title>Catastro GIS Pro | Suite de Ingeniería</title>
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
        <style>
            :root { --primary: #3b82f6; --success: #10b981; --bg: #0f172a; --panel: #1e293b; }
            body { font-family: 'Inter', sans-serif; margin: 0; display: flex; height: 100vh; background: var(--bg); color: #f8fafc; }
            
            /* Sidebar */
            .sidebar { width: 420px; border-right: 1px solid #334155; display: flex; flex-direction: column; background: #0f172a; z-index: 1000; }
            .p-6 { padding: 24px; }
            .scroll-area { flex-grow: 1; overflow-y: auto; padding: 0 24px 24px 24px; }
            
            /* UI Components */
            .card { background: var(--panel); border: 1px solid #334155; border-radius: 12px; padding: 16px; margin-bottom: 20px; }
            h2 { font-size: 14px; text-transform: uppercase; color: #94a3b8; margin-bottom: 15px; letter-spacing: 1px; }
            input[type="text"] { width: 100%; background: #0f172a; border: 1px solid #475569; padding: 12px; border-radius: 8px; color: white; margin-bottom: 10px; box-sizing: border-box; }
            button { width: 100%; padding: 12px; border-radius: 8px; border: none; font-weight: bold; cursor: pointer; transition: 0.2s; color: white; }
            .btn-blue { background: var(--primary); }
            .btn-green { background: var(--success); margin-top: 10px; }
            
            /* Results */
            .res-card { background: #0f172a; border: 1px solid #334155; border-left: 4px solid var(--primary); padding: 15px; border-radius: 8px; margin-bottom: 12px; animation: slideIn 0.3s ease-out; }
            .res-card strong { display: block; margin-bottom: 8px; color: #60a5fa; }
            .links { display: flex; gap: 10px; }
            .links a { font-size: 12px; text-decoration: none; color: #94a3b8; border: 1px solid #334155; padding: 4px 8px; border-radius: 4px; }
            .links a:hover { background: #334155; color: white; }
            
            #map { flex-grow: 1; }
            .loader { border: 3px solid #f3f3f3; border-top: 3px solid #3b82f6; border-radius: 50%; width: 18px; height: 18px; animation: spin 1s linear infinite; display: inline-block; margin-right: 10px; vertical-align: middle; }
            @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
            @keyframes slideIn { from { opacity: 0; transform: translateX(-20px); } to { opacity: 1; transform: translateX(0); } }
            .hidden { display: none; }
        </style>
    </head>
    <body>
        <div class="sidebar">
            <div class="p-6">
                <h1 style="font-size: 22px; margin: 0; font-weight: 800; color: #3b82f6;">CAT PRO GIS</h1>
                <p style="font-size: 11px; color: #64748b; margin-top: 4px;">ENGINEERING & ANALYSIS SUITE</p>
            </div>

            <div class="scroll-area">
                <div class="card">
                    <h2>🔍 Análisis Individual</h2>
                    <input type="text" id="refInput" placeholder="Referencia Catastral (20 caracteres)">
                    <button onclick="buscarManual()" class="btn-blue">ANALIZAR PARCELA</button>
                </div>

                <div class="card" style="border-color: var(--success)">
                    <h2>📦 Carga de Proyectos</h2>
                    <input type="file" id="fileInput" multiple style="font-size: 12px; color: #94a3b8; margin-bottom: 10px;">
                    <button onclick="procesarLote()" class="btn-green">CARGAR KML / GEOJSON</button>
                </div>

                <div id="status" class="hidden" style="text-align: center; padding: 10px; color: #60a5fa; font-size: 13px;">
                    <div class="loader"></div> <span id="status-text">Procesando...</span>
                </div>

                <div id="results-list">
                    <h2>📋 Resultados del Análisis</h2>
                    </div>
            </div>
        </div>

        <div id="map"></div>

        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <script>
            const map = L.map('map', { zoomControl: false }).setView([40.41, -3.70], 6);
            L.control.zoom({ position: 'bottomright' }).addTo(map);

            const osm = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(map);
            const pnoa = L.tileLayer.wms("https://www.ign.es/wms-inspire/pnoa-ma", { layers: 'OI.OrthoimageCoverage', format: 'image/png' });
            const catastro = L.tileLayer.wms("https://ovc.catastro.meh.es/ovcservweb/OVCSWMS.asmx", { layers: 'Catastro', format: 'image/png', transparent: true }).addTo(map);

            L.control.layers({"Mapa": osm, "Satélite": pnoa}, {"Catastro": catastro}).addTo(map);
            
            const vectorLayer = L.featureGroup().addTo(map);

            function showStatus(text) {
                document.getElementById('status').classList.remove('hidden');
                document.getElementById('status-text').innerText = text;
            }

            function hideStatus() {
                document.getElementById('status').classList.add('hidden');
            }

            function addResultCard(item) {
                const list = document.getElementById('results-list');
                const card = document.createElement('div');
                card.className = 'res-card';
                card.innerHTML = '<strong>' + item.referencia + '</strong>' +
                                '<div class="links">' +
                                '<a href="' + item.pdf_url + '" target="_blank">📄 VER INFORME</a>' +
                                '<a href="' + item.zip_url + '" style="color: #10b981">📦 PACK ZIP</a>' +
                                '</div>';
                list.insertBefore(card, list.firstChild.nextSibling);

                if(item.coords && item.coords.lat) {
                    L.circleMarker([item.coords.lat, item.coords.lon], { color: '#3b82f6', radius: 10 }).addTo(vectorLayer)
                     .bindPopup('<b>' + item.referencia + '</b>');
                    map.flyTo([item.coords.lat, item.coords.lon], 17);
                }
            }

            async function buscarManual() {
                const ref = document.getElementById('refInput').value;
                if(!ref) return;
                showStatus("Analizando finca...");
                try {
                    const res = await fetch('/api/analizar', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({referencia_catastral: ref})
                    });
                    const result = await res.json();
                    if(result.status === 'success') addResultCard(result.data);
                } catch(e) { console.error(e); }
                hideStatus();
            }

            async function procesarLote() {
                const files = document.getElementById('fileInput').files;
                if(files.length === 0) return;
                showStatus("Analizando archivos masivos...");
                const formData = new FormData();
                for(let f of files) formData.append('files', f);

                try {
                    const res = await fetch('/api/upload-vector', { method: 'POST', body: formData });
                    const result = await res.json();
                    if(result.status === 'success') {
                        result.data.forEach(item => addResultCard(item));
                        if(vectorLayer.getLayers().length > 0) map.fitBounds(vectorLayer.getBounds());
                    }
                } catch(e) { console.error(e); }
                hideStatus();
            }
        </script>
    </body>
    </html>
    """
