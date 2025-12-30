import os
import shutil
import json
import time
import asyncio
from pathlib import Path
from typing import List
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

from app.config import settings
from app.schemas import QueryRequest, CatastroResponse, BatchRequest
from app.catastro_engine import CatastroDownloader, GeneradorInformeCatastral
from app.intersection_service import IntersectionService
from app.urban_analysis import AnalizadorUrbanistico
from app.new_analysis_module import AdvancedAnalysisModule

app = FastAPI(title=settings.API_TITLE)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Asegurar directorios
for d in [settings.OUTPUT_DIR, settings.TEMP_DIR]:
    Path(d).mkdir(parents=True, exist_ok=True)

app.mount("/outputs", StaticFiles(directory=settings.OUTPUT_DIR), name="outputs")

# Servicios globales
gis_service = IntersectionService(data_dir=settings.CAPAS_DIR)
adv_module = AdvancedAnalysisModule(output_dir=settings.OUTPUT_DIR)

# LÓGICA DE PROCESAMIENTO REUTILIZABLE
async def procesar_core(ref: str, input_file_path: str = None):
    """Maneja el flujo completo para una referencia o un archivo geométrico"""
    ref_clean = ref.upper().strip()
    out_dir = Path(settings.OUTPUT_DIR) / ref_clean
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Si no hay archivo de entrada, descargamos de Catastro
    if not input_file_path:
        cat = CatastroDownloader(str(out_dir))
        res_cat = cat.descargar_todo(ref_clean)
        geojson_p = res_cat.get("geojson_path")
    else:
        # Si viene de un KML/GeoJSON subido, usamos ese archivo
        geojson_p = input_file_path

    if not geojson_p or not os.path.exists(geojson_p):
        raise Exception(f"Error: No se pudo obtener la geometría para {ref_clean}")

    await asyncio.sleep(0.5) # Pausa técnica para escritura en disco

    # 1. Análisis Espacial (GPKG 4.8GB)
    gis_res = gis_service.analyze_file(geojson_p, output_dir=str(out_dir))
    
    # 2. Análisis Urbanístico
    urb = AnalizadorUrbanistico(capas_service=gis_service)
    urb_res = urb.analizar_referencia(ref_clean, geometria_path=geojson_p)
    
    # 3. Generar Mapa Interactivo HTML
    adv_module.procesar_archivos([str(geojson_p)])
    
    # 4. Generar Informe PDF
    pdf_gen = GeneradorInformeCatastral(ref_clean, str(out_dir))
    pdf_path = out_dir / f"Informe_{ref_clean}.pdf"
    pdf_gen.generar_pdf(str(pdf_path))
    
    return {
        "referencia": ref_clean,
        "superficie_m2": urb_res.get("superficie", {}).get("valor", 0) if urb_res else 0,
        "afecciones": gis_res.get("intersecciones", []),
        "descargas": {
            "pdf": f"/outputs/{ref_clean}/Informe_{ref_clean}.pdf",
            "mapa": f"/outputs/{ref_clean}/{ref_clean}_mapa.html"
        }
    }

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return """
    <!DOCTYPE html><html lang="es"><head>
    <meta charset="UTF-8"><title>Catastro SaaS Pro - Suite Completa</title>
    <style>
        :root { --dark: #2c3e50; --blue: #3498db; --green: #27ae60; --bg: #f4f7f6; }
        body { font-family: 'Segoe UI', sans-serif; margin: 0; display: flex; background: var(--bg); height: 100vh; overflow: hidden; }
        .sidebar { width: 260px; background: var(--dark); color: white; padding: 20px; flex-shrink: 0; }
        .menu-item { padding: 15px; cursor: pointer; border-radius: 8px; margin-bottom: 8px; transition: 0.3s; }
        .menu-item:hover { background: rgba(255,255,255,0.1); }
        .menu-item.active { background: var(--blue); font-weight: bold; }
        .main { flex-grow: 1; padding: 35px; overflow-y: auto; }
        .card { background: white; padding: 30px; border-radius: 15px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); margin-bottom: 30px; }
        .section { display: none; } .section.active { display: block; }
        input, textarea, button { padding: 12px; border-radius: 8px; border: 1px solid #ddd; margin-top: 10px; }
        button { background: var(--blue); color: white; border: none; cursor: pointer; font-weight: bold; }
        button.btn-batch { background: var(--green); }
        
        /* VISOR MODAL */
        .modal { display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.85); }
        .modal-content { background: white; margin: 2% auto; width: 92%; height: 88vh; border-radius: 15px; display: flex; flex-direction: column; overflow: hidden; }
        .modal-body { display: flex; flex-grow: 1; overflow: hidden; }
        iframe { flex-grow: 1; border: none; background: #eee; }
        .v-side { width: 380px; padding: 25px; background: #fdfdfd; border-left: 1px solid #eee; overflow-y: auto; }
        .badge-afeccion { background: #fee2e2; color: #991b1b; padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; margin-bottom: 5px; display: inline-block; }
    </style>
    </head><body>
    <div class="sidebar">
        <h2>Catastro SaaS Pro</h2>
        <div class="menu-item active" onclick="nav('sec-single', this)">🔎 Análisis Individual</div>
        <div class="menu-item" onclick="nav('sec-batch', this)">📦 Procesar Lote (Lista)</div>
        <div class="menu-item" onclick="nav('sec-files', this)">📤 Subir KML / GeoJSON</div>
    </div>

    <div class="main">
        <div id="sec-single" class="section active">
            <div class="card">
                <h2>🔎 Consulta de Referencia</h2>
                <input type="text" id="refSingle" placeholder="Ej: 2289738XH6028N0001RY" style="width: 70%;">
                <button onclick="runIndividual()">Analizar Parcela</button>
                <div id="status-single" style="margin-top:15px;"></div>
            </div>
        </div>

        <div id="sec-batch" class="section">
            <div class="card">
                <h2>📦 Procesamiento Masivo</h2>
                <p>Introduce las referencias catastrales separadas por saltos de línea:</p>
                <textarea id="batchList" placeholder="Referencia 1&#10;Referencia 2&#10;Referencia 3" style="width:100%; height:180px;"></textarea>
                <button class="btn-batch" onclick="runBatch()">🚀 Iniciar Proceso por Lote</button>
                <div id="batchProgress" style="margin-top:20px;"></div>
            </div>
        </div>

        <div id="sec-files" class="section">
            <div class="card">
                <h2>📤 Carga de Archivos Vectoriales</h2>
                <p>Sube tus propios archivos <b>KML</b> o <b>GeoJSON</b> para cruzarlos con la base de datos GIS.</p>
                <input type="file" id="vectorFiles" multiple accept=".kml,.geojson,.json">
                <button onclick="uploadFiles()" style="background:var(--dark)">Analizar Archivos</button>
                <div id="fileStatus" style="margin-top:15px;"></div>
            </div>
        </div>
    </div>

    <div id="visor" class="modal">
        <div class="modal-content">
            <div style="padding:15px 25px; border-bottom:1px solid #eee; display:flex; justify-content:space-between; align-items:center; background:var(--dark); color:white;">
                <h3 id="vTitle" style="margin:0;">Visor GIS</h3>
                <button onclick="closeVisor()" style="background:#e74c3c; padding:8px 15px;">Cerrar Visor</button>
            </div>
            <div class="modal-body">
                <iframe id="vMapa" src=""></iframe>
                <div class="v-side">
                    <h4>📊 Resultado del Análisis</h4>
                    <div id="vInfo"></div>
                    <hr>
                    <a id="vPdf" href="#" target="_blank" style="display:block; text-align:center; background:var(--blue); color:white; padding:15px; border-radius:8px; text-decoration:none; font-weight:bold;">📄 Descargar Informe PDF</a>
                </div>
            </div>
        </div>
    </div>

    <script>
        function nav(id, el) {
            document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
            document.querySelectorAll('.menu-item').forEach(m => m.classList.remove('active'));
            document.getElementById(id).classList.add('active'); el.classList.add('active');
        }

        function closeVisor() { document.getElementById('visor').style.display = 'none'; }

        function openVisor(data) {
            document.getElementById('visor').style.display = 'block';
            document.getElementById('vTitle').innerText = "Resultados: " + data.referencia;
            document.getElementById('vMapa').src = data.descargas.mapa + "?t=" + Date.now();
            document.getElementById('vPdf').href = data.descargas.pdf;
            let info = `<p><b>Superficie m²:</b> ${data.superficie_m2}</p><h5>Capas Detectadas:</h5>`;
            data.afecciones.forEach(a => {
                info += `<div class="badge-afeccion">${a.capa} (${a.elementos_encontrados})</div><br>`;
            });
            document.getElementById('vInfo').innerHTML = info;
        }

        async function runIndividual() {
            const ref = document.getElementById('refSingle').value;
            const status = document.getElementById('status-single');
            status.innerHTML = "⏳ Procesando...";
            const r = await fetch('/api/analizar', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({referencia_catastral: ref})
            });
            const res = await r.json();
            if(res.status === 'success') { status.innerHTML = "✅ Éxito"; openVisor(res.data); }
            else { status.innerHTML = "❌ " + res.detail; }
        }

        async function runBatch() {
            const lines = document.getElementById('batchList').value.split('\\n').filter(l => l.trim() !== "");
            const container = document.getElementById('batchProgress');
            container.innerHTML = "<h3>Cola de trabajo:</h3>";
            for(let ref of lines) {
                const row = document.createElement('div');
                row.innerHTML = `⏳ Analizando ${ref}...`;
                container.appendChild(row);
                const r = await fetch('/api/analizar', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({referencia_catastral: ref})
                });
                const res = await r.json();
                row.innerHTML = res.status === 'success' ? `✅ ${ref} - Completado` : `❌ ${ref} - Falló`;
            }
        }

        async function uploadFiles() {
            const files = document.getElementById('vectorFiles').files;
            const status = document.getElementById('fileStatus');
            if(files.length === 0) return alert("Selecciona archivos");
            
            status.innerHTML = "⏳ Subiendo y procesando vectores...";
            const formData = new FormData();
            for(let f of files) formData.append("files", f);

            try {
                const r = await fetch('/api/upload-vector', { method: 'POST', body: formData });
                const res = await r.json();
                status.innerHTML = `✅ ${res.processed} archivos procesados. Revisa la carpeta de outputs.`;
            } catch(e) { status.innerHTML = "❌ Error en la carga."; }
        }
    </script>
    </body></html>
    """

@app.post("/api/analizar", response_model=CatastroResponse)
async def api_analizar(request: QueryRequest):
    try:
        data = await procesar_core(request.referencia_catastral)
        return CatastroResponse(status="success", data=data)
    except Exception as e:
        return CatastroResponse(status="error", detail=str(e))

@app.post("/api/upload-vector")
async def api_upload_vector(files: List[UploadFile] = File(...)):
    processed_count = 0
    for file in files:
        temp_path = Path(settings.TEMP_DIR) / file.filename
        with temp_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Procesamos el archivo como una "referencia" basada en su nombre
        await procesar_core(file.filename.split('.')[0], input_file_path=str(temp_path))
        processed_count += 1
        
    return {"status": "success", "processed": processed_count}
