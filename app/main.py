import os
import shutil
from pathlib import Path
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

# Importación de tus módulos lógicos
from app.config import settings
from app.schemas import QueryRequest, CatastroResponse
from app.catastro_engine import CatastroDownloader, GeneradorInformeCatastral
from app.intersection_service import IntersectionService
from app.urban_analysis import AnalizadorUrbanistico
from app.new_analysis_module import AdvancedAnalysisModule

app = FastAPI(title=settings.API_TITLE, version=settings.API_VERSION)

# Configuración de CORS y Directorios
app.add_middleware(CORSMiddleware, allow_origins=settings.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])

for folder in [settings.OUTPUT_DIR, settings.TEMP_DIR]:
    Path(folder).mkdir(parents=True, exist_ok=True)

# Montaje de archivos estáticos para descargas y visor
app.mount("/outputs", StaticFiles(directory=settings.OUTPUT_DIR), name="outputs")

# Inicialización del Servicio GIS (Carga capas GPKG en memoria)
gis_service = IntersectionService(data_dir=settings.CAPAS_DIR)

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return """
    <!DOCTYPE html><html lang="es"><head>
    <meta charset="UTF-8"><title>Catastro SaaS Pro - Dashboard</title>
    <style>
        :root { --dark: #2c3e50; --blue: #3498db; --bg: #f8f9fa; }
        body { font-family: 'Segoe UI', sans-serif; margin: 0; display: flex; background: var(--bg); }
        .sidebar { width: 280px; background: var(--dark); color: white; height: 100vh; padding: 25px; position: fixed; }
        .main { margin-left: 310px; padding: 30px; width: 100%; }
        .card { background: white; padding: 25px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); margin-bottom: 30px; }
        input, button { padding: 12px; border-radius: 6px; border: 1px solid #ddd; font-size: 14px; }
        button { background: var(--blue); color: white; border: none; cursor: pointer; font-weight: bold; transition: 0.3s; }
        button:hover { background: #2980b9; }
        
        /* VISOR MODAL */
        .modal { display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.85); }
        .modal-content { background: white; margin: 2% auto; padding: 25px; width: 90%; max-height: 90vh; border-radius: 12px; overflow-y: auto; }
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
        iframe { width: 100%; height: 550px; border: 1px solid #eee; border-radius: 8px; }
        .afecciones { background: #fdfdfd; padding: 15px; border: 1px solid #eee; border-radius: 8px; }
    </style>
    </head><body>
    <div class="sidebar">
        <h2>Catastro Pro</h2>
        <p>Servicio GIS Activo</p>
        <hr style="opacity: 0.2">
        <nav>
            <p>🏠 Dashboard</p>
            <p>📂 Procesamiento KML</p>
            <p>⚖️ Normativa Urbanística</p>
        </nav>
    </div>
    <div class="main">
        <div class="card">
            <h2>🔎 Análisis de Parcela</h2>
            <p>Introduce la referencia para consulta catastral, cruce de capas GIS e informe PDF.</p>
            <input type="text" id="refInput" placeholder="Ej: 9812301XF4691S0001PI" style="width: 50%;">
            <button onclick="lanzarProceso()">Iniciar Análisis</button>
            <div id="status" style="margin-top: 15px;"></div>
        </div>

        <div class="card">
            <h2>📤 Carga de Geometrías (KML / GeoJSON)</h2>
            <input type="file" id="fileUpload" multiple>
            <button onclick="subirFicheros()" style="background: #27ae60;">Analizar Archivos</button>
        </div>
    </div>

    <div id="visorModal" class="modal">
        <div class="modal-content">
            <span onclick="cerrarVisor()" style="float:right; cursor:pointer; font-size:28px;">&times;</span>
            <h2 id="vTitle">Resultado del Análisis</h2>
            <div class="grid">
                <div>
                    <h3>🗺️ Mapa Interactivo</h3>
                    <iframe id="vMapa"></iframe>
                </div>
                <div class="afecciones">
                    <h3>📑 Datos y Afecciones</h3>
                    <div id="vData"></div>
                    <hr>
                    <a id="vPdf" href="" target="_blank" style="display:block; text-align:center; padding:15px; background:var(--blue); color:white; text-decoration:none; border-radius:6px;">Descargar Informe PDF</a>
                </div>
            </div>
        </div>
    </div>

    <script>
        async function lanzarProceso() {
            const ref = document.getElementById('refInput').value;
            const status = document.getElementById('status');
            status.innerHTML = "⏳ <b>Procesando...</b> (Descargando Catastro y cruzando capas GIS)";
            
            try {
                const r = await fetch('/api/analizar', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({referencia_catastral: ref})
                });
                const res = await r.json();
                if(res.status === 'success') {
                    status.innerHTML = "✅ Análisis completado con éxito.";
                    abrirVisor(res.data);
                } else { status.innerHTML = "❌ Error: " + res.detail; }
            } catch(e) { status.innerHTML = "❌ Error de conexión con el servidor."; }
        }

        function abrirVisor(data) {
            document.getElementById('visorModal').style.display = 'block';
            document.getElementById('vTitle').innerText = "Parcela: " + data.referencia;
            document.getElementById('vMapa').src = data.descargas.mapa;
            document.getElementById('vPdf').href = data.descargas.pdf;
            
            let html = `<p><b>Superficie:</b> ${data.superficie_m2} m²</p><h4>Cruce de Capas GIS:</h4><ul>`;
            data.afecciones.forEach(a => {
                html += `<li><b>${a.capa}:</b> ${a.elementos_encontrados} intersecciones</li>`;
            });
            document.getElementById('vData').innerHTML = html + "</ul>";
        }

        function cerrarVisor() { document.getElementById('visorModal').style.display = 'none'; }
    </script>
    </body></html>
    """

@app.post("/api/analizar", response_model=CatastroResponse)
async def api_analizar(request: QueryRequest):
    ref = request.referencia_catastral.upper().strip()
    path_ref = Path(settings.OUTPUT_DIR) / ref
    path_ref.mkdir(parents=True, exist_ok=True)

    try:
        # 1. Catastro: GeoJSON y Datos
        catastro = CatastroDownloader(str(path_ref))
        res_cat = catastro.descargar_todo(ref)
        geojson_p = res_cat.get("geojson_path")

        # 2. GIS: Intersección con GPKG
        gis_res = gis_service.analyze_file(geojson_p, output_dir=str(path_ref))

        # 3. Urbanismo: Análisis de normativa
        urb = AnalizadorUrbanistico(capas_service=gis_service)
        urb_res = urb.analizar_referencia(ref, geometria_path=geojson_p)

        # 4. Leaflet: Mapa Interactivo
        adv = AdvancedAnalysisModule(output_dir=str(settings.OUTPUT_DIR))
        adv.procesar_archivos([str(geojson_p)])

        # 5. ReportLab: Generación de PDF
        informe = GeneradorInformeCatastral(ref, str(path_ref))
        pdf_path = path_ref / f"Informe_{ref}.pdf"
        informe.generar_pdf(str(pdf_path))

        return CatastroResponse(status="success", data={
            "referencia": ref,
            "superficie_m2": urb_res.get("superficie", {}).get("valor"),
            "afecciones": gis_res.get("intersecciones", []),
            "descargas": {
                "pdf": f"/outputs/{ref}/Informe_{ref}.pdf",
                "mapa": f"/outputs/{ref}/{ref}_mapa.html"
            }
        })
    except Exception as e:
        return CatastroResponse(status="error", detail=str(e))

@app.get("/health")
async def health():
    return {"status": "ok", "capas": str(settings.CAPAS_DIR)}
