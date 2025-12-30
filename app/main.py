import os
import shutil
from pathlib import Path
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

from app.config import settings
from app.schemas import QueryRequest, CatastroResponse
from app.catastro_engine import CatastroDownloader, GeneradorInformeCatastral
from app.intersection_service import IntersectionService
from app.urban_analysis import AnalizadorUrbanistico
from app.new_analysis_module import AdvancedAnalysisModule

app = FastAPI(title=settings.API_TITLE)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Crear carpetas necesarias
for d in [settings.OUTPUT_DIR, settings.TEMP_DIR]:
    Path(d).mkdir(parents=True, exist_ok=True)

app.mount("/outputs", StaticFiles(directory=settings.OUTPUT_DIR), name="outputs")

# Inicializar servicios
gis_service = IntersectionService(data_dir=settings.CAPAS_DIR)

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return """
    <!DOCTYPE html><html lang="es"><head>
    <meta charset="UTF-8"><title>Catastro SaaS Pro</title>
    <style>
        body { font-family: sans-serif; background: #f4f7f6; margin: 0; display: flex; }
        .sidebar { width: 250px; background: #2c3e50; color: white; height: 100vh; padding: 20px; position: fixed; }
        .main { margin-left: 290px; padding: 40px; width: 100%; }
        .card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); margin-bottom: 20px; }
        button { background: #3498db; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer; }
        .modal { display: none; position: fixed; z-index: 100; left: 0; top: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); }
        .modal-content { background: white; margin: 5% auto; padding: 20px; width: 80%; border-radius: 10px; }
    </style>
    </head><body>
    <div class="sidebar"><h2>Menu</h2><p>Dashboard</p><p>Historial</p></div>
    <div class="main">
        <div class="card">
            <h2>🔎 Analizar Referencia</h2>
            <input type="text" id="refInput" style="padding:10px; width:300px;">
            <button onclick="lanzarProceso()">Analizar</button>
            <div id="status"></div>
        </div>
        <div class="card">
            <h2>📤 Subir KML / GeoJSON</h2>
            <input type="file" id="fileUpload" multiple>
            <button onclick="subirFicheros()">Procesar Archivos</button>
        </div>
    </div>

    <div id="visor" class="modal">
        <div class="modal-content">
            <span onclick="this.parentElement.parentElement.style.display='none'" style="float:right; cursor:pointer;">&times;</span>
            <h2 id="vTitle"></h2>
            <iframe id="vMapa" style="width:100%; height:500px; border:none;"></iframe>
            <a id="vPdf" href="" target="_blank">📥 Descargar Informe PDF</a>
        </div>
    </div>

    <script>
        async function lanzarProceso() {
            const ref = document.getElementById('refInput').value;
            const status = document.getElementById('status');
            status.innerHTML = "⏳ Procesando...";
            const r = await fetch('/api/analizar', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({referencia_catastral: ref})
            });
            const res = await r.json();
            if(res.status === 'success') {
                status.innerHTML = "✅ Listo";
                document.getElementById('visor').style.display='block';
                document.getElementById('vTitle').innerText = ref;
                document.getElementById('vMapa').src = res.data.descargas.mapa;
                document.getElementById('vPdf').href = res.data.descargas.pdf;
            } else { status.innerHTML = "❌ Error: " + res.detail; }
        }

        async function subirFicheros() {
            const files = document.getElementById('fileUpload').files;
            if(files.length === 0) return alert("Selecciona archivos");
            alert("Subiendo " + files.length + " archivos para análisis vectorial...");
            // Aquí podrías implementar el bucle de fetch a /api/upload-analysis
        }
    </script>
    </body></html>
    """

@app.post("/api/analizar", response_model=CatastroResponse)
async def api_analizar(request: QueryRequest):
    ref = request.referencia_catastral.upper().strip()
    out_dir = Path(settings.OUTPUT_DIR) / ref
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        # 1. Catastro (Validar que no devuelva None)
        down = CatastroDownloader(str(out_dir))
        c_data = down.descargar_todo(ref)
        if not c_data or not c_data.get("geojson_path"):
            return CatastroResponse(status="error", detail="Catastro no devolvió geometría para esta referencia")
        
        geojson = c_data["geojson_path"]

        # 2. GIS
        gis_res = gis_service.analyze_file(geojson, output_dir=str(out_dir))

        # 3. Urbanismo
        urb = AnalizadorUrbanistico(capas_service=gis_service)
        urb_res = urb.analizar_referencia(ref, geometria_path=geojson)

        # 4. Leaflet
        adv = AdvancedAnalysisModule(output_dir=str(settings.OUTPUT_DIR))
        adv.procesar_archivos([str(geojson)])

        # 5. PDF
        pdf_gen = GeneradorInformeCatastral(ref, str(out_dir))
        pdf_path = out_dir / f"Informe_{ref}.pdf"
        pdf_gen.generar_pdf(str(pdf_path))

        return CatastroResponse(status="success", data={
            "referencia": ref,
            "superficie_m2": urb_res.get("superficie", {}).get("valor", 0) if urb_res.get("superficie") else 0,
            "afecciones": gis_res.get("intersecciones", []),
            "descargas": {
                "pdf": f"/outputs/{ref}/Informe_{ref}.pdf",
                "mapa": f"/outputs/{ref}/{ref}_mapa.html"
            }
        })
    except Exception as e:
        return CatastroResponse(status="error", detail=f"Error en el motor: {str(e)}")
