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
    # Simulación para evitar errores de arranque si el archivo no está en la ruta
    def procesar_y_comprimir(ref, directorio_base):
        return f"{directorio_base}/{ref}_completo.zip", {"lat": 40.41, "lon": -3.70, "superficie": "Pendiente"}

app = FastAPI(title="Catastro GIS Pro - Business Suite")

# --- RUTAS DE SISTEMA ---
BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/outputs", StaticFiles(directory=str(OUTPUT_DIR)), name="outputs")

# --- ENDPOINTS ---

@app.post("/api/analizar")
async def api_analizar(data: dict):
    ref = data.get("referencia_catastral", "").upper().strip()
    if not ref: raise HTTPException(status_code=400, detail="Referencia vacía")
    
    try:
        zip_path, resultados = procesar_y_comprimir(ref, directorio_base=str(OUTPUT_DIR))
        ref_clean = ref.replace(" ", "")
        
        return {
            "status": "success",
            "data": {
                "referencia": ref,
                "zip_url": f"/outputs/{os.path.basename(zip_path)}",
                "pdf_url": f"/outputs/{ref_clean}/{ref_clean}_Informe_Analisis_Espacial.pdf",
                "coords": {"lat": resultados.get('lat'), "lon": resultados.get('lon')},
                "stats": resultados
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/upload-vector")
async def api_upload_vector(files: List[UploadFile] = File(...)):
    results = []
    for file in files:
        content = await file.read()
        text = content.decode("utf-8", errors="ignore")
        refs = list(set(re.findall(r'[0-9]{7}[A-Z]{2}[0-9]{4}[A-Z]{1}[0-9]{4}[A-Z]{2}', text)))
        for r in refs:
            zip_p, _ = procesar_y_comprimir(r, directorio_base=str(OUTPUT_DIR))
            results.append({"archivo": file.filename, "ref": r, "zip": f"/outputs/{os.path.basename(zip_p)}"})
    return {"status": "success", "analisis": results}

# --- INTERFAZ PREMIUM ---

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return """
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>GIS Catastro Pro | Engineering Suite</title>
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
        <script src="https://cdn.tailwindcss.com"></script>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap');
            body { font-family: 'Inter', sans-serif; background-color: #0f172a; color: #f8fafc; }
            #map { height: 100%; width: 100%; border-left: 1px solid #334155; }
            .sidebar { background: rgba(30, 41, 59, 0.8); backdrop-filter: blur(12px); border-right: 1px solid #334155; }
            .glass-card { background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 12px; transition: all 0.3s; }
            .glass-card:hover { border-color: #3b82f6; background: rgba(59, 130, 246, 0.05); }
            ::-webkit-scrollbar { width: 6px; }
            ::-webkit-scrollbar-thumb { background: #334155; border-radius: 10px; }
        </style>
    </head>
    <body class="flex overflow-hidden">
        
        <div class="sidebar w-[450px] flex flex-col h-screen z-50">
            <div class="p-6 border-b border-slate-700">
                <h1 class="text-2xl font-bold bg-gradient-to-r from-blue-400 to-emerald-400 bg-clip-text text-transparent">
                    CAT PRO GIS
                </h1>
                <p class="text-xs text-slate-400 uppercase tracking-widest mt-1 font-semibold">Engineering Suite v3.2</p>
            </div>

            <div class="flex-grow overflow-y-auto p-6 space-y-6">
                
                <div class="space-y-3">
                    <label class="text-sm font-medium text-slate-300">Referencia Catastral</label>
                    <div class="relative">
                        <input type="text" id="refInput" placeholder="Ej: 2289738XH6028N0001RY" 
                               class="w-full bg-slate-900 border border-slate-700 rounded-lg p-3 text-white focus:ring-2 focus:ring-blue-500 outline-none transition-all">
                    </div>
                    <button onclick="buscarFinca()" class="w-full bg-blue-600 hover:bg-blue-500 text-white font-bold py-3 rounded-lg shadow-lg shadow-blue-900/20 transition-all flex items-center justify-center gap-2">
                        <span>🚀 Analizar Parcela</span>
                    </button>
                </div>

                <div class="glass-card p-4">
                    <h3 class="text-sm font-bold text-slate-200 mb-2">📥 Análisis Espacial Externo</h3>
                    <input type="file" id="fileInput" class="text-xs text-slate-400 mb-2 block w-full" multiple>
                    <button onclick="subirKML()" class="w-full bg-emerald-600 hover:bg-emerald-500 text-white text-sm py-2 rounded-md font-semibold transition-all">
                        Cargar KML / GeoJSON
                    </button>
                </div>

                <div id="loading" class="hidden text-center p-4">
                    <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400"></div>
                    <p class="mt-2 text-sm text-blue-400">Consultando Sede Electrónica...</p>
                </div>

                <div id="log-list" class="space-y-4">
                    </div>
            </div>

            <div class="p-4 border-t border-slate-700 bg-slate-900/50">
                <p class="text-[10px] text-slate-500 text-center">Datos oficiales: Sede Electrónica del Catastro & IGN España</p>
            </div>
        </div>

        <div id="map"></div>

        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <script>
            // Mapa Base con estilo oscuro
            const map = L.map('map', { zoomControl: false }).setView([40.41, -3.70], 6);
            L.control.zoom({ position: 'bottomright' }).addTo(map);

            const cartoDark = L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
                attribution: '©OpenStreetMap, ©CartoDB'
            }).addTo(map);

            const pnoa = L.tileLayer.wms("https://www.ign.es/wms-inspire/pnoa-ma", {
                layers: 'OI.OrthoimageCoverage', format: 'image/png', transparent: false, attribution: "IGN"
            });

            const catastroWMS = L.tileLayer.wms("https://ovc.catastro.meh.es/ovcservweb/OVCSWMS.asmx", {
                layers: 'Catastro', format: 'image/png', transparent: true, attribution: "Sede Catastro"
            }).addTo(map);

            L.control.layers({"Nocturno": cartoDark, "Satélite Real": pnoa}, {"Capa Catastral": catastroWMS}).addTo(map);

            async function buscarFinca() {
                const ref = document.getElementById('refInput').value;
                if(!ref) return;
                
                document.getElementById('loading').classList.remove('hidden');
                
                try {
                    const res = await fetch('/api/analizar', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({referencia_catastral: ref})
                    });
                    const result = await res.json();
                    document.getElementById('loading').classList.add('hidden');

                    if(result.status === 'success') {
                        const { lat, lon } = result.data.coords;
                        if(lat && lon) {
                            map.flyTo([lat, lon], 18, { animate: true, duration: 2 });
                            L.circleMarker([lat, lon], { color: '#3b82f6', radius: 10 }).addTo(map)
                             .bindPopup(`<b>${result.data.referencia}</b>`).openPopup();
                        }
                        renderResult(result.data);
                    }
                } catch(e) { 
                    alert("Error en el servidor");
                    document.getElementById('loading').classList.add('hidden');
                }
            }

            function renderResult(data) {
                const list = document.getElementById('log-list');
                const card = document.createElement('div');
                card.className = "glass-card p-4 border-l-4 border-blue-500 animate-fade-in";
                card.innerHTML = `
                    <div class="flex justify-between items-start mb-3">
                        <div>
                            <h4 class="font-bold text-white text-sm">${data.referencia}</h4>
                            <span class="text-[10px] bg-blue-900/50 text-blue-300 px-2 py-1 rounded">PROCESADO</span>
                        </div>
                        <span class="text-[10px] text-slate-500">${new Date().toLocaleTimeString()}</span>
                    </div>
                    <div class="grid grid-cols-2 gap-2 mt-4">
                        <a href="${data.pdf_url}" target="_blank" class="text-center text-xs bg-slate-800 hover:bg-slate-700 p-2 rounded border border-slate-600">📄 Informe PDF</a>
                        <a href="${data.zip_url}" class="text-center text-xs bg-blue-600 hover:bg-blue-500 p-2 rounded font-bold">📦 Pack ZIP</a>
                    </div>
                `;
                list.prepend(card);
            }

            async function subirKML() {
                const files = document.getElementById('fileInput').files;
                if(files.length === 0) return;
                const formData = new FormData();
                for(let f of files) formData.append('files', f);
                
                const res = await fetch('/api/upload-vector', { method: 'POST', body: formData });
                const data = await res.json();
                data.analisis.forEach(item => {
                    renderResult({referencia: item.ref, zip_url: item.zip, pdf_url: "#"});
                });
            }
        </script>
    </body>
    </html>
    """
