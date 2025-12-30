import os
import re
import json
from typing import List
from pathlib import Path
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

# Importamos tu motor de ingeniería
from app.catastro_engine import CatastroDownloader, procesar_y_comprimir

app = FastAPI(title="Catastro GIS Pro - Visualizador Integrado")

# --- CONFIGURACIÓN DE RUTAS ---
BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/outputs", StaticFiles(directory=str(OUTPUT_DIR)), name="outputs")

# --- ENDPOINTS ---

@app.post("/api/upload-vector")
async def api_upload_vector(files: List[UploadFile] = File(...)):
    """
    Procesa archivos vectoriales, extrae geometrías para el mapa 
    y dispara el análisis completo de cada referencia encontrada.
    """
    lote_resultados = []
    
    for file in files:
        content = await file.read()
        text = content.decode("utf-8", errors="ignore")
        
        # 1. Extraer Referencias Catastrales (Regex 20 caracteres)
        refs = list(set(re.findall(r'[0-9]{7}[A-Z]{2}[0-9]{4}[A-Z]{1}[0-9]{4}[A-Z]{2}', text)))
        
        for r in refs:
            try:
                # 2. Ejecutar módulo de análisis completo (new_analysis_module)
                zip_path, resultados = procesar_y_comprimir(r, directorio_base=str(OUTPUT_DIR))
                
                lote_resultados.append({
                    "referencia": r,
                    "zip_url": f"/outputs/{os.path.basename(zip_path)}",
                    "pdf_url": f"/outputs/{r.replace(' ', '')}/{r.replace(' ', '')}_Informe_Analisis_Espacial.pdf",
                    "coords": {"lat": resultados.get('lat'), "lon": resultados.get('lon')},
                    "geojson": resultados.get('geojson_data') # Asumiendo que tu motor devuelve la geometría
                })
            except Exception as e:
                print(f"Error procesando {r}: {e}")
                continue
                
    return {"status": "success", "data": lote_resultados}

# --- DASHBOARD CON VISUALIZACIÓN DE VECTORES ---

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return """
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <title>GIS Pro | Visualizador de Análisis</title>
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
        <style>
            :root { --primary: #10b981; --bg: #0f172a; }
            body { font-family: 'Segoe UI', sans-serif; margin: 0; display: flex; height: 100vh; background: var(--bg); color: white; }
            .sidebar { width: 420px; border-right: 1px solid #334155; display: flex; flex-direction: column; overflow: hidden; }
            #map { flex-grow: 1; z-index: 1; }
            .card { background: #1e293b; padding: 15px; border-radius: 8px; margin: 10px; border: 1px solid #334155; }
            .btn-green { background: #10b981; color: white; width: 100%; padding: 12px; border: none; border-radius: 6px; font-weight: bold; cursor: pointer; }
            #results-list { overflow-y: auto; flex-grow: 1; padding: 10px; }
            .item-card { background: #0f172a; border: 1px solid #334155; padding: 12px; border-radius: 6px; margin-bottom: 10px; font-size: 13px; }
            .item-card a { color: #34d399; text-decoration: none; margin-right: 10px; font-weight: bold; }
        </style>
    </head>
    <body>
        <div class="sidebar">
            <div class="card" style="border-bottom: 2px solid var(--primary)">
                <h2 style="margin:0; font-size: 18px;">📦 CARGA DE PROYECTOS</h2>
                <p style="font-size: 11px; color: #94a3b8;">Sube KML/GeoJSON para visualizar y analizar</p>
                <input type="file" id="fileInput" multiple style="margin-top:10px; font-size:12px;">
                <button onclick="subirYVisualizar()" class="btn-green" style="margin-top:15px;">ANALIZAR Y DIBUJAR EN MAPA</button>
            </div>
            <div id="results-list"></div>
        </div>
        <div id="map"></div>

        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <script>
            const map = L.map('map').setView([40.41, -3.70], 6);
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(map);
            
            // Capa para los dibujos del KML
            const vectorLayer = L.featureGroup().addTo(map);

            async function subirYVisualizar() {
                const files = document.getElementById('fileInput').files;
                if(files.length === 0) return;

                const formData = new FormData();
                for(let f of files) formData.append('files', f);

                const res = await fetch('/api/upload-vector', { method: 'POST', body: formData });
                const json = await res.json();

                if(json.status === 'success') {
                    json.data.forEach(item => {
                        // 1. Agregar a la lista lateral
                        const div = document.createElement('div');
                        div.className = 'item-card';
                        div.innerHTML = `
                            <strong>REF: ${item.referencia}</strong><br>
                            <div style="margin-top:8px;">
                                <a href="${item.pdf_url}" target="_blank">📄 PDF</a>
                                <a href="${item.zip_url}">📦 ZIP</a>
                            </div>
                        `;
                        document.getElementById('results-list').prepend(div);

                        // 2. Dibujar en el mapa si hay coordenadas
                        if(item.coords.lat) {
                            const marker = L.circleMarker([item.coords.lat, item.coords.lon], {
                                color: '#10b981', radius: 8
                            }).addTo(vectorLayer)
                              .bindPopup(`<b>Analizado:</b> ${item.referencia}`);
                        }
                    });

                    // Ajustar vista a los nuevos elementos
                    if (vectorLayer.getLayers().length > 0) {
                        map.fitBounds(vectorLayer.getBounds());
                    }
                }
            }
        </script>
    </body>
    </html>
    """
