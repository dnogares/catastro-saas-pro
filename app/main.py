import os
import shutil
import json
import asyncio
from typing import List
from pathlib import Path
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse

# Importamos tus clases y funciones
from app.catastro_engine import CatastroDownloader, GeneradorInformeCatastral, procesar_y_comprimir

app = FastAPI(title="Catastro SaaS Pro - Suite de Ingeniería")

# Configuración de rutas
BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "outputs"
TEMP_DIR = BASE_DIR / "temp"

# Crear carpetas si no existen
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# Configurar CORS para que el navegador no bloquee las peticiones
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Servir los archivos generados (PDFs, ZIPs, Imágenes) para que sean accesibles vía URL
app.mount("/outputs", StaticFiles(directory=str(OUTPUT_DIR)), name="outputs")

# --- ENDPOINTS DE LA API ---

@app.post("/api/analizar")
async def api_analizar(data: dict):
    """Analiza una sola referencia catastral"""
    referencia = data.get("referencia_catastral")
    if not referencia:
        raise HTTPException(status_code=400, detail="Falta la referencia")
    
    try:
        # Usamos tu función procesar_y_comprimir que hace todo el trabajo sucio
        zip_path, resultados = procesar_y_comprimir(referencia, directorio_base=str(OUTPUT_DIR))
        
        if not zip_path:
             return {"status": "error", "detail": "No se pudo procesar la referencia"}

        # Construimos las URLs de retorno
        ref_clean = referencia.replace(" ", "").strip()
        return {
            "status": "success",
            "data": {
                "referencia": ref_clean,
                "zip_url": f"/outputs/{os.path.basename(zip_path)}",
                "pdf_url": f"/outputs/{ref_clean}/{ref_clean}_Informe_Analisis_Espacial.pdf",
                "resultados": resultados
            }
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@app.post("/api/upload-vector")
async def api_upload_vector(files: List[UploadFile] = File(...)):
    """Maneja la subida de KML o GeoJSON"""
    processed = []
    for file in files:
        file_path = TEMP_DIR / file.filename
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Aquí podrías añadir lógica para cruzar el KML con tus capas GIS
        processed.append(file.filename)
    
    return {"status": "success", "processed_files": processed}

# --- INTERFAZ DE USUARIO (DASHBOARD) ---

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <title>Panel de Control - Catastro Pro</title>
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; background: #f0f2f5; display: flex; height: 100vh; }}
            .sidebar {{ width: 280px; background: #1a202c; color: white; padding: 20px; flex-shrink: 0; }}
            .main {{ flex-grow: 1; padding: 40px; overflow-y: auto; }}
            .card {{ background: white; padding: 25px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); margin-bottom: 20px; }}
            h2 {{ color: #2d3748; margin-top: 0; }}
            input, textarea {{ width: 100%; padding: 12px; margin: 10px 0; border: 1px solid #cbd5e0; border-radius: 6px; box-sizing: border-box; }}
            button {{ background: #3182ce; color: white; border: none; padding: 12px 24px; border-radius: 6px; cursor: pointer; font-weight: bold; transition: 0.3s; }}
            button:hover {{ background: #2b6cb0; }}
            .btn-batch {{ background: #38a169; }}
            .result-item {{ padding: 15px; border-left: 4px solid #3182ce; background: #ebf8ff; margin-top: 10px; display: flex; justify-content: space-between; align-items: center; }}
            .loader {{ border: 4px solid #f3f3f3; border-top: 4px solid #3498db; border-radius: 50%; width: 20px; height: 20px; animation: spin 2s linear infinite; display: inline-block; vertical-align: middle; margin-right: 10px; }}
            @keyframes spin {{ 0% {{ transform: rotate(0deg); }} 100% {{ transform: rotate(360deg); }} }}
            .hidden {{ display: none; }}
        </style>
    </head>
    <body>
        <div class="sidebar">
            <h1>GIS Catastro</h1>
            <p>Suite de Análisis Territorial</p>
            <hr style="opacity: 0.2">
            <div style="margin-top: 20px;">
                <p>📍 <b>Modos:</b></p>
                <ul style="list-style: none; padding: 0;">
                    <li>✓ Análisis Individual</li>
                    <li>✓ Procesamiento en Lote</li>
                    <li>✓ Cruce de KML/GeoJSON</li>
                </ul>
            </div>
        </div>

        <div class="main">
            <div class="card">
                <h2>🔎 Consulta Individual</h2>
                <div style="display: flex; gap: 10px;">
                    <input type="text" id="refInput" placeholder="Introduce Referencia Catastral (ej: 9812301XF4691S0001PI)">
                    <button onclick="analizarSimple()">Analizar</button>
                </div>
                <div id="loading" class="hidden" style="margin-top: 10px;">
                    <div class="loader"></div> Procesando datos, mapas y afecciones...
                </div>
                <div id="resultado" class="hidden">
                    <div class="result-item">
                        <span id="resText"></span>
                        <div>
                            <a id="btnPdf" href="#" target="_blank" style="margin-right:10px; color:#2c5282;">📄 Ver Informe</a>
                            <a id="btnZip" href="#" style="background:#38a169; color:white; padding:8px 12px; border-radius:4px; text-decoration:none;">📦 Descargar Todo (.ZIP)</a>
                        </div>
                    </div>
                </div>
            </div>

            <div class="card">
                <h2>📦 Procesamiento por Lote</h2>
                <p>Pega múltiples referencias (una por línea):</p>
                <textarea id="batchInput" rows="6" placeholder="Referencia 1&#10;Referencia 2..."></textarea>
                <button class="btn-batch" onclick="analizarLote()">🚀 Iniciar Procesamiento Masivo</button>
                <div id="batchProgress" style="margin-top: 15px;"></div>
            </div>

            <div class="card">
                <h2>📤 Cargar KML / GeoJSON</h2>
                <input type="file" id="fileInput" multiple accept=".kml,.geojson">
                <button onclick="subirArchivos()" style="background: #4a5568;">Analizar Geometrías Externas</button>
            </div>
        </div>

        <script>
            async function analizarSimple() {{
                const ref = document.getElementById('refInput').value;
                if(!ref) return alert("Escribe una referencia");
                
                document.getElementById('loading').classList.remove('hidden');
                document.getElementById('resultado').classList.add('hidden');

                const response = await fetch('/api/analizar', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ referencia_catastral: ref }})
                }});
                
                const data = await response.json();
                document.getElementById('loading').classList.add('hidden');

                if(data.status === 'success') {{
                    document.getElementById('resultado').classList.remove('hidden');
                    document.getElementById('resText').innerText = "Referencia " + data.data.referencia + " procesada.";
                    document.getElementById('btnPdf').href = data.data.pdf_url;
                    document.getElementById('btnZip').href = data.data.zip_url;
                }} else {{
                    alert("Error: " + data.detail);
                }}
            }}

            async function analizarLote() {{
                const refs = document.getElementById('batchInput').value.split('\\n').filter(r => r.trim());
                const progress = document.getElementById('batchProgress');
                progress.innerHTML = "<b>Iniciando cola de trabajo...</b><br>";

                for(const ref of refs) {{
                    const line = document.createElement('div');
                    line.innerHTML = "⏳ Procesando " + ref + "...";
                    progress.appendChild(line);

                    const response = await fetch('/api/analizar', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify({{ referencia_catastral: ref }})
                    }});
                    const data = await response.json();
                    
                    if(data.status === 'success') {{
                        line.innerHTML = "✅ " + ref + " -> <a href='" + data.data.zip_url + "'>Descargar ZIP</a>";
                    }} else {{
                        line.innerHTML = "❌ " + ref + " -> Error";
                    }}
                }}
            }}

            async function subirArchivos() {{
                const files = document.getElementById('fileInput').files;
                const formData = new FormData();
                for(let file of files) formData.append('files', file);

                const response = await fetch('/api/upload-vector', {{
                    method: 'POST',
                    body: formData
                }});
                const data = await response.json();
                alert("Procesados: " + data.processed_files.join(', '));
            }}
        </script>
    </body>
    </html>
    """
