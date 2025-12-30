import os
import shutil
import re
import json
from typing import List
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

# Importamos tu motor
from app.catastro_engine import CatastroDownloader, procesar_y_comprimir

app = FastAPI(title="Catastro GIS Pro")

# --- CONFIGURACIÓN DE RUTAS ---
BASE_DIR = Path(__file__).resolve().parent.parent
# Aseguramos que la ruta de salida sea accesible
OUTPUT_DIR = BASE_DIR / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Servir archivos estáticos
app.mount("/outputs", StaticFiles(directory=str(OUTPUT_DIR)), name="outputs")

# --- ENDPOINTS API ---

@app.post("/api/analizar")
async def api_analizar(data: dict):
    ref = data.get("referencia_catastral", "").upper().strip()
    if not ref:
        raise HTTPException(status_code=400, detail="Referencia requerida")
    
    try:
        # Llamada a tu motor
        zip_path, resultados = procesar_y_comprimir(ref, directorio_base=str(OUTPUT_DIR))
        
        # --- CORRECCIÓN CRÍTICA ---
        # Aseguramos que resultados contenga 'lat' y 'lon' para Leaflet
        # Si tu motor usa 'latitude'/'longitude', los renombramos aquí:
        lat = resultados.get('lat') or resultados.get('latitude')
        lon = resultados.get('lon') or resultados.get('longitude')
        
        if lat is None or lon is None:
            # Si el motor falló al extraer coordenadas, usamos un fallback 
            # o lanzamos error para evitar el crash de Leaflet
            print(f"⚠️ Warning: Coordenadas no encontradas para {ref}")

        ref_clean = ref.replace(" ", "")
        
        return {
            "status": "success",
            "data": {
                "referencia": ref,
                "zip_url": f"/outputs/{os.path.basename(zip_path)}",
                "pdf_url": f"/outputs/{ref_clean}/{ref_clean}_Informe_Analisis_Espacial.pdf",
                "resultados": {
                    "lat": lat,
                    "lon": lon,
                    "superficie": resultados.get('superficie', 'N/A'),
                    "afecciones": resultados.get('afecciones', [])
                }
            }
        }
    except Exception as e:
        print(f"❌ Error en api_analizar: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# --- DASHBOARD CON VISOR GIS CORREGIDO ---

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return """
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <title>Catastro GIS Pro</title>
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
        <style>
            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; display: flex; height: 100vh; background: #f0f2f5; }
            .sidebar { width: 380px; background: white; border-right: 1px solid #ddd; padding: 20px; display: flex; flex-direction: column; z-index: 1000; box-shadow: 2px 0 5px rgba(0,0,0,0.1); }
            #map { flex-grow: 1; height: 100%; }
            .card { background: #f9f9f9; padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid #eee; }
            input { width: 100%; padding: 10px; margin: 10px 0; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box; }
            button { width: 100%; padding: 12px; background: #2563eb; color: white; border: none; border-radius: 4px; cursor: pointer; font-weight: bold; }
            button:hover { background: #1d4ed8; }
            #results-container { margin-top: 20px; overflow-y: auto; }
            .badge { background: #dcfce7; color: #166534; padding: 4px 8px; border-radius: 4px; font-size: 12px; }
        </style>
    </head>
    <body>
        <div class="sidebar">
            <h2>🛰️ Catastro GIS Pro</h2>
            <div class="card">
                <strong>Referencia Catastral</strong>
                <input type="text" id="refInput" placeholder="Ej: 2289738XH6028N0001RY">
                <button onclick="buscarFinca()">Analizar Parcela</button>
            </div>
            <div id="results-container"></div>
        </div>

        <div id="map"></div>

        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <script>
            // Inicialización del mapa
            const map = L.map('map').setView([40.4167, -3.7037], 6);
            
            const osm = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(map);
            const pnoa = L.tileLayer.wms("https://www.ign.es/wms-inspire/pnoa-ma", {
                layers: 'OI.OrthoimageCoverage', format: 'image/png', transparent: false, attribution: "IGN"
            });
            const catastroWMS = L.tileLayer.wms("https://ovc.catastro.meh.es/ovcservweb/OVCSWMS.asmx", {
                layers: 'Catastro', format: 'image/png', transparent: true, attribution: "Catastro"
            }).addTo(map);

            L.control.layers({"Callejero": osm, "Satélite": pnoa}, {"Catastro": catastroWMS}).addTo(map);

            async function buscarFinca() {
                const ref = document.getElementById('refInput').value;
                const container = document.getElementById('results-container');
                container.innerHTML = "⌛ Procesando...";

                try {
                    const response = await fetch('/api/analizar', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({referencia_catastral: ref})
                    });
                    const res = await response.json();

                    if (res.status === 'success') {
                        const info = res.data.resultados;
                        
                        // --- VALIDACIÓN DE COORDENADAS ANTES DE FLYTO ---
                        if (info.lat && info.lon) {
                            map.flyTo([info.lat, info.lon], 18);
                            L.marker([info.lat, info.lon]).addTo(map)
                                .bindPopup(`<b>Ref: ${res.data.referencia}</b><br><a href="${res.data.pdf_url}" target="_blank">📄 Ver Informe</a>`)
                                .openPopup();
                        } else {
                            alert("⚠️ El motor procesó la finca pero no devolvió coordenadas válidas para el mapa.");
                        }

                        container.innerHTML = `
                            <div class="card">
                                <strong>✅ Analizado</strong><br>
                                <small>${res.data.referencia}</small><br><br>
                                <a href="${res.data.pdf_url}" target="_blank">📄 Ver Informe PDF</a><br><br>
                                <a href="${res.data.zip_url}" style="color: green; font-weight: bold;">📦 Descargar ZIP</a>
                            </div>
                        `;
                    } else {
                        container.innerHTML = "❌ Error: " + res.detail;
                    }
                } catch (error) {
                    container.innerHTML = "❌ Error de conexión";
                    console.error(error);
                }
            }
        </script>
    </body>
    </html>
    """
