import os
import re
import json
from typing import List
from pathlib import Path
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

# Importamos tu motor lógico
from app.catastro_engine import CatastroDownloader, procesar_y_comprimir

app = FastAPI(title="Catastro GIS Pro - Enterprise")

# --- CONFIGURACIÓN DE MARCA (Personaliza esto) ---
CONFIG_EMPRESA = {
    "nombre": "TU CONSULTORÍA TÉCNICA",
    "web": "www.tuingenieria.com",
    "color_primario": "#3b82f6"
}

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/outputs", StaticFiles(directory=str(OUTPUT_DIR)), name="outputs")

# --- ENDPOINTS ---

@app.post("/api/analizar")
async def api_analizar(data: dict):
    ref = data.get("referencia_catastral", "").upper().strip()
    if not ref: raise HTTPException(status_code=400, detail="Referencia requerida")
    
    try:
        # El motor procesa la finca y genera los archivos
        zip_path, resultados = procesar_y_comprimir(ref, directorio_base=str(OUTPUT_DIR))
        
        # Calculamos discrepancia si el motor nos da superficie real vs catastral
        sup_cat = resultados.get('superficie', 0)
        sup_medida = resultados.get('superficie_grafica', sup_cat) # Simulado si no hay medición externa
        discrepancia = abs(float(sup_cat) - float(sup_medida)) if sup_cat != 'N/A' else 0

        return {
            "status": "success",
            "empresa": CONFIG_EMPRESA,
            "data": {
                "referencia": ref,
                "zip_url": f"/outputs/{os.path.basename(zip_path)}",
                "pdf_url": f"/outputs/{ref.replace(' ', '')}/{ref.replace(' ', '')}_Informe_Analisis_Espacial.pdf",
                "coords": {"lat": resultados.get('lat'), "lon": resultados.get('lon')},
                "metricas": {
                    "catastral": f"{sup_cat} m²",
                    "discrepancia": f"{round(discrepancia, 2)} m²",
                    "alerta": discrepancia > (float(sup_cat or 0) * 0.05) # Alerta si supera el 5%
                }
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- DASHBOARD DE ALTO IMPACTO ---

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <title>GIS Enterprise | {CONFIG_EMPRESA['nombre']}</title>
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
        <script src="https://cdn.tailwindcss.com"></script>
        <style>
            .sidebar-blur {{ background: rgba(15, 23, 42, 0.9); backdrop-filter: blur(10px); }}
            .card-gradient {{ background: linear-gradient(135deg, rgba(59,130,246,0.1) 0%, rgba(15,23,42,1) 100%); }}
        </style>
    </head>
    <body class="flex h-screen bg-slate-950 text-slate-200 overflow-hidden">
        
        <aside class="sidebar-blur w-[450px] border-r border-slate-800 flex flex-col z-50">
            <div class="p-8 border-b border-slate-800">
                <div class="flex items-center gap-3">
                    <div class="w-10 h-10 bg-blue-600 rounded-lg flex items-center justify-center font-bold text-xl">G</div>
                    <div>
                        <h1 class="font-bold text-lg tracking-tight uppercase">{CONFIG_EMPRESA['nombre']}</h1>
                        <p class="text-[10px] text-blue-400 font-mono tracking-widest uppercase">Sistema de Inteligencia Territorial</p>
                    </div>
                </div>
            </div>

            <div class="flex-grow overflow-y-auto p-8 space-y-8">
                <div class="space-y-4">
                    <h3 class="text-xs font-bold text-slate-500 uppercase tracking-tighter">Nueva Consulta de Activos</h3>
                    <input type="text" id="refInput" placeholder="Referencia Catastral..." 
                           class="w-full bg-slate-900/50 border border-slate-700 rounded-xl p-4 text-white focus:border-blue-500 outline-none transition-all shadow-inner">
                    <button onclick="ejecutarAnalisis()" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-4 rounded-xl transition-all active:scale-95 shadow-lg shadow-blue-900/20">
                        EJECUTAR ANÁLISIS COMPLETO
                    </button>
                </div>

                <div id="resultsFeed" class="space-y-4">
                    <p class="text-xs text-slate-600 text-center italic">Esperando entrada de datos...</p>
                </div>
            </div>

            <div class="p-4 bg-slate-900/80 border-t border-slate-800 flex justify-between items-center">
                <span class="text-[10px] text-slate-500">v3.5 Stable Release</span>
                <span class="text-[10px] text-blue-500 font-bold">{CONFIG_EMPRESA['web']}</span>
            </div>
        </aside>

        <main id="map" class="flex-grow"></main>

        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <script>
            const map = L.map('map', {{ zoomControl: false }}).setView([40.41, -3.70], 6);
            
            // Capas WMS e Híbridas
            const baseMap = L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png').addTo(map);
            const pnoa = L.tileLayer.wms("https://www.ign.es/wms-inspire/pnoa-ma", {{ layers: 'OI.OrthoimageCoverage', format: 'image/png' }});
            const catastro = L.tileLayer.wms("https://ovc.catastro.meh.es/ovcservweb/OVCSWMS.asmx", {{ layers: 'Catastro', format: 'image/png', transparent: true }}).addTo(map);

            L.control.layers({{ "Vista Nocturna": baseMap, "Ortofoto Satélite": pnoa }}, {{ "Catastro Oficial": catastro }}).addTo(map);

            async function ejecutarAnalisis() {{
                const ref = document.getElementById('refInput').value;
                if(!ref) return;

                const response = await fetch('/api/analizar', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ referencia_catastral: ref }})
                }});
                const res = await response.json();

                if(res.status === 'success') {{
                    const data = res.data;
                    map.flyTo([data.coords.lat, data.coords.lon], 18);
                    
                    const feed = document.getElementById('resultsFeed');
                    if(feed.querySelector('p')) feed.innerHTML = ''; // Limpiar mensaje inicial

                    const card = document.createElement('div');
                    card.className = "card-gradient border border-slate-700 p-5 rounded-2xl animate-in slide-in-from-left duration-500";
                    card.innerHTML = `
                        <div class="flex justify-between items-start mb-4">
                            <div>
                                <h4 class="font-bold text-blue-400">${{data.referencia}}</h4>
                                <p class="text-[10px] text-slate-400">Superficie: ${{data.metricas.catastral}}</p>
                            </div>
                            <span class="${{data.metricas.alerta ? 'bg-red-900/30 text-red-400' : 'bg-green-900/30 text-green-400'}} text-[9px] font-bold px-2 py-1 rounded">
                                ${{data.metricas.alerta ? 'DISCREPANCIA DETECTADA' : 'GEOMETRÍA OK'}}
                            </span>
                        </div>
                        <div class="grid grid-cols-1 gap-2">
                            <a href="${{data.pdf_url}}" target="_blank" class="block text-center text-xs bg-white/5 hover:bg-white/10 py-3 rounded-lg border border-white/10 transition-all">ABRIR INFORME TÉCNICO</a>
                            <a href="${{data.zip_url}}" class="block text-center text-xs bg-blue-600 hover:bg-blue-500 font-bold py-3 rounded-lg shadow-lg">DESCARGAR PAQUETE ZIP</a>
                        </div>
                    `;
                    feed.prepend(card);
                }
            }}
        </script>
    </body>
    </html>
    """
