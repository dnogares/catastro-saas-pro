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

# Directorios
for d in [settings.OUTPUT_DIR, settings.TEMP_DIR]:
    Path(d).mkdir(parents=True, exist_ok=True)

app.mount("/outputs", StaticFiles(directory=settings.OUTPUT_DIR), name="outputs")

# Servicios
gis_service = IntersectionService(data_dir=settings.CAPAS_DIR)
adv_module = AdvancedAnalysisModule(output_dir=settings.OUTPUT_DIR)

# Función interna de procesamiento (para reutilizar en individual y lote)
async def procesar_referencia_core(ref: str):
    ref = ref.upper().strip()
    out_dir = Path(settings.OUTPUT_DIR) / ref
    out_dir.mkdir(parents=True, exist_ok=True)
    
    cat = CatastroDownloader(str(out_dir))
    res_cat = cat.descargar_todo(ref)
    geojson_p = res_cat.get("geojson_path")
    
    if not geojson_p or not os.path.exists(geojson_p):
        raise Exception(f"Referencia {ref}: No se obtuvo geometría.")

    # Simular espera de escritura
    await asyncio.sleep(0.5)

    gis_res = gis_service.analyze_file(geojson_p, output_dir=str(out_dir))
    urb = AnalizadorUrbanistico(capas_service=gis_service)
    urb_res = urb.analizar_referencia(ref, geometria_path=geojson_p)
    adv_module.procesar_archivos([str(geojson_p)])
    
    pdf_gen = GeneradorInformeCatastral(ref, str(out_dir))
    pdf_path = out_dir / f"Informe_{ref}.pdf"
    pdf_gen.generar_pdf(str(pdf_path))
    
    return {
        "referencia": ref,
        "superficie_m2": urb_res.get("superficie", {}).get("valor", 0) if urb_res else 0,
        "afecciones": gis_res.get("intersecciones", []),
        "descargas": {
            "pdf": f"/outputs/{ref}/Informe_{ref}.pdf",
            "mapa": f"/outputs/{ref}/{ref}_mapa.html"
        }
    }

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    # El HTML incluye ahora la lógica de Lotes
    return """
    <!DOCTYPE html><html lang="es"><head>
    <meta charset="UTF-8"><title>Catastro SaaS Pro - Lotes</title>
    <style>
        :root { --dark: #2c3e50; --blue: #3498db; --bg: #f4f7f6; }
        body { font-family: 'Segoe UI', sans-serif; margin: 0; display: flex; background: var(--bg); height: 100vh; }
        .sidebar { width: 250px; background: var(--dark); color: white; padding: 20px; flex-shrink: 0; }
        .menu-item { padding: 12px; cursor: pointer; border-radius: 6px; margin-bottom: 5px; }
        .menu-item.active { background: var(--blue); }
        .main { flex-grow: 1; padding: 30px; overflow-y: auto; }
        .card { background: white; padding: 25px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); margin-bottom: 25px; }
        .section { display: none; } .section.active { display: block; }
        textarea { width: 100%; height: 150px; border-radius: 6px; border: 1px solid #ddd; padding: 10px; margin-bottom: 10px; }
        .progress-item { padding: 10px; border-bottom: 1px solid #eee; display: flex; justify-content: space-between; }
    </style>
    </head><body>
    <div class="sidebar">
        <h2>Catastro Pro</h2>
        <div class="menu-item active" onclick="nav('sec-single', this)">🔎 Análisis Único</div>
        <div class="menu-item" onclick="nav('sec-batch', this)">📦 Procesar Lote</div>
    </div>
    <div class="main">
        <div id="sec-single" class="section active">
            <div class="card">
                <h2>Buscador Individual</h2>
                <input type="text" id="refInput" placeholder="Referencia..." style="width: 300px; padding: 12px;">
                <button onclick="lanzarIndividual()" style="padding: 12px 20px; background:var(--blue); color:white; border:none; border-radius:6px; cursor:pointer;">Analizar</button>
                <div id="status-single"></div>
            </div>
        </div>
        <div id="sec-batch" class="section">
            <div class="card">
                <h2>Procesamiento Masivo</h2>
                <p>Pega una lista de referencias (una por línea):</p>
                <textarea id="batchInput" placeholder="9812301XF4691S0001PI&#10;8712302XF4691S0001PI"></textarea>
                <button onclick="lanzarLote()" style="padding: 12px 25px; background: #27ae60; color:white; border:none; border-radius:6px; cursor:pointer;">🚀 Iniciar Lote de Trabajo</button>
                <div id="batchProgress" style="margin-top:20px;"></div>
            </div>
        </div>
    </div>

    <script>
        function nav(id, el) {
            document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
            document.querySelectorAll('.menu-item').forEach(m => m.classList.remove('active'));
            document.getElementById(id).classList.add('active'); el.classList.add('active');
        }

        async function lanzarIndividual() {
            const ref = document.getElementById('refInput').value;
            const status = document.getElementById('status-single');
            status.innerHTML = "⏳ Procesando...";
            const r = await fetch('/api/analizar', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({referencia_catastral: ref})
            });
            const res = await r.json();
            if(res.status === 'success') { status.innerHTML = "✅ ¡Listo! Mira los archivos en outputs/" + ref; }
            else { status.innerHTML = "❌ " + res.detail; }
        }

        async function lanzarLote() {
            const refs = document.getElementById('batchInput').value.split('\\n').filter(r => r.trim() !== "");
            const container = document.getElementById('batchProgress');
            container.innerHTML = "<h3>Progreso del Lote:</h3>";
            
            for(let ref of refs) {
                const item = document.createElement('div');
                item.className = 'progress-item';
                item.innerHTML = `<span>${ref}</span><span id="st-${ref}">⏳ Esperando...</span>`;
                container.appendChild(item);

                try {
                    const r = await fetch('/api/analizar', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({referencia_catastral: ref})
                    });
                    const res = await r.json();
                    document.getElementById('st-'+ref).innerText = res.status === 'success' ? "✅ Ok" : "❌ Error";
                } catch(e) {
                    document.getElementById('st-'+ref).innerText = "❌ Fallo conexión";
                }
            }
        }
    </script>
    </body></html>
    """

@app.post("/api/analizar", response_model=CatastroResponse)
async def api_analizar(request: QueryRequest):
    try:
        data = await procesar_referencia_core(request.referencia_catastral)
        return CatastroResponse(status="success", data=data)
    except Exception as e:
        return CatastroResponse(status="error", detail=str(e))

@app.post("/api/analizar-lote")
async def api_lote(request: BatchRequest, background_tasks: BackgroundTasks):
    # Esta opción es para procesos pesados en segundo plano
    for ref in request.referencias:
        background_tasks.add_task(procesar_referencia_core, ref)
    return {"message": f"Iniciado procesamiento de {len(request.referencias)} referencias en segundo plano."}
