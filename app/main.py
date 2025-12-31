import os
import json
from fastapi import FastAPI, Form, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional

# Tus módulos originales
from urban_analysis import AnalizadorUrbanistico
# Supongamos que tienes este para el PDF
# from report_generator import PDFGenerator 

app = FastAPI(title="Catastro SaaS API")

# Configuración de CORS para el frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Servir estáticos y asegurar carpetas de salida
app.mount("/static", StaticFiles(directory="."), name="static")
os.makedirs("outputs", exist_ok=True)
os.makedirs("uploads", exist_ok=True)

analizador = AnalizadorUrbanistico()

# --- MODELOS DE DATOS ---
class ReportRequest(BaseModel):
    ref: str
    tecnico: str
    colegiado: str
    notas: Optional[str] = ""
    logo: Optional[str] = None # Base64 del logo
    afecciones: List[dict]

# --- ENDPOINTS ---

@app.post("/api/analizar-referencia")
async def api_analizar_ref(ref: str = Form(...)):
    """Ejecuta el análisis urbanístico de una referencia"""
    try:
        # 1. Ejecutar tu lógica de urban_analysis.py
        resultado = analizador.analizar_referencia(ref)
        
        # 2. Aquí deberías obtener el GeoJSON real de la parcela
        # Por ahora enviamos una estructura válida para que Leaflet no de error
        geojson_mock = {
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [[[-3.70, 40.41], [-3.71, 40.41], [-3.71, 40.42], [-3.70, 40.41]]]},
            "properties": {"refcat": ref}
        }
        
        return {
            "status": "success",
            "datos": resultado,
            "geojson": geojson_mock
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/analizar-kml")
async def api_analizar_kml(file: UploadFile = File(...)):
    """Procesa archivos KML/GeoJSON (AdvancedAnalysisModule)"""
    file_path = f"uploads/{file.filename}"
    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())
    
    # Aquí llamarías a: AdvancedAnalysisModule.procesar(file_path)
    return {"status": "success", "message": f"Archivo {file.filename} analizado"}

@app.post("/api/procesar-lote")
async def api_procesar_lote(file: UploadFile = File(...)):
    """Maneja la carga masiva de CSV desde la tarjeta izquierda"""
    content = await file.read()
    # Lógica para iterar sobre las referencias del CSV
    return {"status": "success", "count": 10, "message": "Lote recibido"}

@app.post("/api/generar-pdf")
async def api_generar_pdf(request: ReportRequest):
    """Genera el informe final consolidado"""
    pdf_path = f"outputs/Informe_{request.ref}.pdf"
    
    # Aquí integrarías tu lógica de generación de PDF (ReportLab/FPDF)
    # Ejemplo:
    # pdf_gen = PDFGenerator(request)
    # pdf_gen.build(pdf_path)
    
    # Simulamos la creación de un archivo para que el endpoint funcione
    with open(pdf_path, "w") as f: f.write(f"Informe para {request.ref}")
    
    return FileResponse(path=pdf_path, filename=f"Informe_{request.ref}.pdf")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
