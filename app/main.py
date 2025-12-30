import os
import shutil
from pathlib import Path
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

# Importaciones de tus módulos de lógica
from app.config import settings
from app.schemas import QueryRequest, CatastroResponse
from app.catastro_engine import CatastroDownloader, GeneradorInformeCatastral
from app.intersection_service import IntersectionService
from app.urban_analysis import AnalizadorUrbanistico
from app.new_analysis_module import AdvancedAnalysisModule

app = FastAPI(title=settings.API_TITLE, version=settings.API_VERSION)

# Configuración de CORS y Carpetas
app.add_middleware(CORSMiddleware, allow_origins=settings.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])
for d in [settings.OUTPUT_DIR, settings.TEMP_DIR]:
    Path(d).mkdir(parents=True, exist_ok=True)

app.mount("/outputs", StaticFiles(directory=settings.OUTPUT_DIR), name="outputs")

# Inicialización de servicios (Carga de capas GIS)
intersection_service = IntersectionService(data_dir=settings.CAPAS_DIR)

@app.get("/", response_class=HTMLResponse)
async def dashboard_principal():
    return """
    <!DOCTYPE html><html lang="es"><head>
    <meta charset="UTF-8"><title>Catastro SaaS Pro - Dashboard</title>
    <style>
        :root { --dark: #2c3e50; --blue: #3498db; --green: #27ae60; --gray: #f4f7f6; }
        body { font-family: 'Segoe UI', sans-serif; margin: 0; display: flex; background: var(--gray); }
        .sidebar { width: 260px; background: var(--dark); color: white; height: 100vh; padding: 20px; position: fixed; }
        .main { margin-left: 300px; padding: 30px; width: calc(100% - 340px); }
        .card { background: white; padding: 20px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); margin-bottom: 25px; }
        input, button { padding: 12px; border-radius: 6px; border: 1px solid #ddd; margin-top: 10px; }
        button { background: var(--blue); color: white; border: none; cursor: pointer; font-weight: bold; }
        button:hover { opacity: 0.9; }
        
        /* MODAL VISOR */
        .modal { display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); }
        .modal-content { background: white; margin: 2% auto; padding: 20px; width: 90%; max-height: 90vh; border-radius: 10px; overflow-y: auto; }
        .grid-visor { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
        iframe { width: 100%; height: 500px; border: 1px solid #eee; border-radius: 8px; }
        img { width: 100%; border-radius: 8px; }
    </style>
    </head><body>
    <div class="sidebar">
        <h2>Catastro SaaS Pro</h2>
        <hr>
        <p>📊 Dashboard Activo</p>
        <p>🗺️ Capas GIS: Conectadas</p>
    </div>
    <div class="main">
        <div class="card">
            <h2>🔎 Análisis por Referencia Catastral</h2>
            <input type="text" id="refInput" placeholder="Inserte referencia (14-20 caracteres)" style="width: 60%;">
            <button onclick="ejecutarAnalisis()">Iniciar Análisis Completo</button>
            <div id="status"></div>
        </div>

        <div class="card">
            <h2>📂 Carga de Archivos (KML / GeoJSON)</h2>
            <p>Sube archivos para cruzar con la base de datos GIS de 4.8GB.</p>
            <input type="file" id="fileInput" multiple>
            <button onclick="subirArchivo()" style="background: var(--green);">Analizar Documentos</button>
        </div>
    </div>

    <div id="visor" class="modal">
        <div class="modal-content">
            <span onclick="this.parentElement.parentElement.style.display='none'" style="float:right; cursor:pointer; font-size:24px;">&times;</span>
            <h2 id="visorTitle">Visor de Resultados</h2>
            <div class="grid-visor">
                <div>
                    <h3>Mapa Interactivo</h3>
                    <iframe id="visorMapa"></iframe>
                </div>
                <div>
                    <h3>Imagen de Situación / Catastro</h3>
                    <img id="visorImg" src="">
                    <div id="visorAfecciones" style="margin-top:20px; padding:15px; background:#f9f9f9; border-radius:8px;"></div>
                </div>
            </div>
            <div style="text-align:center; margin-top:20px;">
                <a id="linkPdf" href="" target="_blank" style="font-size:18px; color:var(--blue); font-weight:bold;">📄 Descargar Informe PDF Oficial</a>
            </div>
        </div>
    </div>

    <script>
        async function ejecutarAnalisis() {
            const ref = document.getElementById('refInput').value;
            const status = document.getElementById('status');
            status.innerHTML = "⏳ Procesando... consultando Catastro y cruce GIS.";
            
            try {
                const res = await fetch('/api/analizar', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({referencia_catastral: ref})
                });
                const data = await res.json();
                if(data.status === 'success') {
                    status.innerHTML = "✅ ¡Análisis completado!";
                    mostrarVisor(data.data);
                } else { status.innerHTML = "❌ Error: " + data.detail; }
            } catch (e) { status.innerHTML = "❌ Error de conexión."; }
        }

        function mostrarVisor(data) {
            document.getElementById('visor').style.display = 'block';
            document.getElementById('visorTitle').innerText = "Resultados: " + data.referencia;
            document.getElementById('visorMapa').src = data.descargas.mapa;
            document.getElementById('visorImg').src = `/outputs/${data.referencia}/mapa_situacion.jpg`; // Si el motor genera JPG
            document.getElementById('linkPdf').href = data.descargas.pdf;
            
            let afeccionHtml = "<h4>Afecciones Detectadas:</h4><ul>";
            data.afecciones.forEach(a => {
                afeccionHtml += `<li><b>${a.capa}</b>: ${a.elementos_encontrados} elementos</li>`;
            });
            document.getElementById('visorAfecciones').innerHTML = afeccionHtml + "</ul>";
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
        # 1. Catastro
        down = CatastroDownloader(str(out_dir))
        c_data = down.descargar_todo(ref)
        geojson = c_data.get("geojson_path")

        # 2. Cruce GIS (GPKG)
        gis_res = intersection_service.analyze_file(geojson, output_dir=str(out_dir))

        # 3. Urbanismo
        urb = AnalizadorUrbanistico(capas_service=intersection_service)
        urb_res = urb.analizar_referencia(ref, geometria_path=geojson)

        # 4. Mapa Interactivo HTML
        adv = AdvancedAnalysisModule(output_dir=str(settings.OUTPUT_DIR))
        adv.procesar_archivos([str(geojson)])

        # 5. PDF
        pdf_gen = GeneradorInformeCatastral(ref, str(out_dir))
        pdf_path = out_dir / f"Informe_{ref}.pdf"
        pdf_gen.generar_pdf(str(pdf_path))

        return CatastroResponse(status="success", data={
            "referencia": ref,
            "afecciones": gis_res.get("intersecciones", []),
            "superficie_m2": urb_res.get("superficie", {}).get("valor"),
            "descargas": {
                "pdf": f"/outputs/{ref}/Informe_{ref}.pdf",
                "mapa": f"/outputs/{ref}/{ref}_mapa.html"
            }
        })
    except Exception as e:
        return CatastroResponse(status="error", detail=str(e))

@app.post("/api/batch")
async def batch_process(request: BatchRequest):
    # Lógica para procesar múltiples referencias una tras otra
    resultados = []
    for ref in request.referencias:
        # Aquí llamarías a la lógica de api_analizar para cada una
        pass
    return {"status": "success", "processed": len(request.referencias)}
