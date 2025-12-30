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

# Crear carpetas si no existen
for d in [settings.OUTPUT_DIR, settings.TEMP_DIR]:
    Path(d).mkdir(parents=True, exist_ok=True)

app.mount("/outputs", StaticFiles(directory=settings.OUTPUT_DIR), name="outputs")
gis_service = IntersectionService(data_dir=settings.CAPAS_DIR)

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return """
    <!DOCTYPE html><html lang="es"><head>
    <meta charset="UTF-8"><title>Catastro Pro - Visor</title>
    <style>
        :root { --dark: #2c3e50; --blue: #3498db; --bg: #f4f7f6; }
        body { font-family: 'Segoe UI', sans-serif; margin: 0; display: flex; background: var(--bg); height: 100vh; overflow: hidden; }
        .sidebar { width: 250px; background: var(--dark); color: white; padding: 20px; }
        .main { flex-grow: 1; padding: 30px; overflow-y: auto; }
        .card { background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); margin-bottom: 20px; }
        .menu-item { padding: 12px; cursor: pointer; border-radius: 4px; margin-bottom: 5px; }
        .menu-item.active { background: var(--blue); }
        
        /* ESTILOS DEL VISOR MODAL */
        .modal { display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.9); }
        .modal-content { background: white; margin: 2% auto; padding: 20px; width: 90%; height: 85vh; border-radius: 12px; display: flex; flex-direction: column; }
        .visor-body { display: grid; grid-template-columns: 1fr 350px; gap: 20px; flex-grow: 1; overflow: hidden; }
        iframe { width: 100%; height: 100%; border: 1px solid #ddd; border-radius: 8px; }
        .details-panel { background: #f8f9fa; padding: 20px; border-radius: 8px; overflow-y: auto; border: 1px solid #eee; }
        .close-btn { float: right; font-size: 30px; cursor: pointer; color: #666; }
    </style>
    </head><body>
    <div class="sidebar">
        <h2>Catastro Pro</h2>
        <div class="menu-item active">🔎 Análisis Principal</div>
        <div class="menu-item">📂 Mis Informes</div>
    </div>
    <div class="main">
        <div class="card">
            <h2>🔎 Nueva Consulta</h2>
            <input type="text" id="refInput" placeholder="Introduce Referencia Catastral" style="width: 50%; padding: 12px;">
            <button onclick="lanzarAnalisis()" style="padding: 12px 20px; background: var(--blue); color:white; border:none; border-radius:5px; cursor:pointer;">Analizar Ahora</button>
            <div id="status" style="margin-top:15px; font-weight:bold;"></div>
        </div>
    </div>

    <div id="visorModal" class="modal">
        <div class="modal-content">
            <div>
                <span class="close-btn" onclick="cerrarVisor()">&times;</span>
                <h2 id="vTitle" style="margin-top:0;">Visor de Resultados</h2>
            </div>
            <div class="visor-body">
                <iframe id="vMapa" src=""></iframe>
                <div class="details-panel">
                    <h3>📊 Datos Detectados</h3>
                    <div id="vData">Cargando datos...</div>
                    <hr>
                    <a id="vPdf" href="" target="_blank" style="display:block; padding:15px; background:var(--blue); color:white; text-align:center; text-decoration:none; border-radius:6px; font-weight:bold;">📥 Descargar Informe PDF</a>
                </div>
            </div>
        </div>
    </div>

    <script>
        async function lanzarAnalisis() {
            const ref = document.getElementById('refInput').value.trim();
            const status = document.getElementById('status');
            if(!ref) return alert("Referencia obligatoria");
            
            status.innerHTML = "⏳ <b>Procesando...</b> Por favor espera (Catastro + GIS + PDF)";
            try {
                const r = await fetch('/api/analizar', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({referencia_catastral: ref})
                });
                const res = await r.json();
                if(res.status === 'success') {
                    status.innerHTML = "✅ ¡Análisis completado!";
                    abrirVisor(res.data);
                } else { status.innerHTML = "❌ Error: " + res.detail; }
            } catch(e) { status.innerHTML = "❌ Fallo de conexión."; }
        }

        function abrirVisor(data) {
            document.getElementById('visorModal').style.display = 'block';
            document.getElementById('vTitle').innerText = "Parcela: " + data.referencia;
            // IMPORTANTE: La ruta del mapa debe coincidir con lo que genera AdvancedAnalysisModule
            document.getElementById('vMapa').src = data.descargas.mapa + "?t=" + new Date().getTime();
            document.getElementById('vPdf').href = data.descargas.pdf;
            
            let html = `<p><b>Superficie:</b> ${data.superficie_m2} m²</p><h4>Cruce de Capas:</h4><ul>`;
            data.afecciones.forEach(a => {
                html += `<li><b>${a.capa}:</b> ${a.elementos_encontrados} cruces</li>`;
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
        # 1. Catastro
        cat = CatastroDownloader(str(path_ref))
        res_cat = cat.descargar_todo(ref)
        if not res_cat or not res_cat.get("geojson_path"):
            return CatastroResponse(status="error", detail="No se obtuvo geometría de Catastro.")
        
        geojson_p = res_cat["geojson_path"]

        # 2. GIS
        gis_res = gis_service.analyze_file(geojson_p, output_dir=str(path_ref))
        
        # 3. Urbanismo
        urb = AnalizadorUrbanistico(capas_service=gis_service)
        urb_res = urb.analizar_referencia(ref, geometria_path=geojson_p)

        # 4. Mapa Leaflet (Genera el .html)
        adv = AdvancedAnalysisModule(output_dir=str(settings.OUTPUT_DIR))
        adv.procesar_archivos([str(geojson_p)])

        # 5. Generar PDF
        pdf_gen = GeneradorInformeCatastral(ref, str(path_ref))
        pdf_path = path_ref / f"Informe_{ref}.pdf"
        pdf_gen.generar_pdf(str(pdf_path))

        return CatastroResponse(status="success", data={
            "referencia": ref,
            "superficie_m2": urb_res.get("superficie", {}).get("valor", 0),
            "afecciones": gis_res.get("intersecciones", []),
            "descargas": {
                "pdf": f"/outputs/{ref}/Informe_{ref}.pdf",
                "mapa": f"/outputs/{ref}/{ref}_mapa.html" # Asegúrate de que AdvancedAnalysisModule use este nombre
            }
        })
    except Exception as e:
        return CatastroResponse(status="error", detail=str(e))
