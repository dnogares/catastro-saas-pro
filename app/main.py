import os
import json
import base64
import shutil
import uuid
from fastapi import FastAPI, Form, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from fpdf import FPDF

# Importación de tu lógica original
from urban_analysis import AnalizadorUrbanistico

app = FastAPI(title="Catastro SaaS Pro API")

# Configuración de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Directorios de trabajo
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")

for d in [UPLOAD_DIR, OUTPUT_DIR]:
    os.makedirs(d, exist_ok=True)

# Servir archivos estáticos (para que el frontend pueda ver los mapas generados)
app.mount("/outputs", StaticFiles(directory=OUTPUT_DIR), name="outputs")

analizador = AnalizadorUrbanistico()

# --- MODELOS DE DATOS ---
class ReportRequest(BaseModel):
    ref: str
    tecnico: str
    colegiado: str
    notas: Optional[str] = ""
    logo: Optional[str] = None # Base64 string
    datos: dict

# --- MOTOR DE PDF PROFESIONAL ---
class InformePDF(FPDF):
    def header(self):
        if hasattr(self, 'logo_path') and os.path.exists(self.logo_path):
            self.image(self.logo_path, 10, 8, 33)
        self.set_font('Arial', 'B', 15)
        self.set_text_color(30, 58, 95)
        self.cell(0, 10, 'INFORME TÉCNICO DE AFECCIONES', 0, 1, 'C')
        self.set_font('Arial', 'I', 9)
        self.set_text_color(100)
        self.cell(0, 5, f'ID Informe: {datetime.now().strftime("%Y%m%d")}-PRO', 0, 1, 'C')
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Página {self.page_no()} | Catastro SaaS Pro v2.0', 0, 0, 'C')

# --- ENDPOINTS ---

@app.post("/api/analizar-referencia")
async def api_analizar_ref(ref: str = Form(...)):
    """Analiza una referencia y devuelve datos + geometría"""
    try:
        # 1. Llamada a tu script original
        resultado = analizador.analizar_referencia(ref)
        
        # 2. Simulación de GeoJSON (aquí deberías integrar la salida de tu clase)
        geojson_data = {
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [[[-3.70, 40.41], [-3.71, 40.41], [-3.71, 40.42], [-3.70, 40.41]]]},
            "properties": {"refcat": ref}
        }
        
        return {"status": "success", "datos": resultado, "geojson": geojson_data}
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": str(e)})

@app.post("/api/analizar-kml")
async def api_analizar_kml(file: UploadFile = File(...)):
    """Procesa archivos KML externos"""
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return {"status": "success", "filename": file.filename}

@app.post("/api/procesar-lote")
async def api_procesar_lote(file: UploadFile = File(...)):
    """Procesa un CSV con múltiples referencias"""
    content = await file.read()
    # Aquí iría la lógica de iteración sobre el CSV
    return {"status": "success", "message": "Lote recibido y en proceso"}

@app.post("/api/generar-pdf")
async def api_generar_pdf(req: ReportRequest):
    """Genera el documento PDF final"""
    try:
        pdf = InformePDF()
        
        # Procesar logo temporal
        temp_logo = None
        if req.logo and "base64," in req.logo:
            temp_logo = os.path.join(UPLOAD_DIR, f"logo_{uuid.uuid4()}.png")
            img_data = base64.b64decode(req.logo.split(",")[1])
            with open(temp_logo, "wb") as f:
                f.write(img_data)
            pdf.logo_path = temp_logo

        pdf.add_page()
        
        # Bloque Datos del Inmueble
        pdf.set_fill_color(230, 235, 245)
        pdf.set_font('Arial', 'B', 12)
        pdf.cell(0, 10, f" 1. IDENTIFICACIÓN DE LA PARCELA: {req.ref}", 1, 1, 'L', True)
        
        pdf.set_font('Arial', '', 11)
        pdf.cell(50, 8, "Técnico:", 1)
        pdf.cell(0, 8, req.tecnico, 1, 1)
        pdf.cell(50, 8, "Colegiado:", 1)
        pdf.cell(0, 8, req.colegiado, 1, 1)
        
        # Bloque Afecciones
        pdf.ln(5)
        pdf.set_font('Arial', 'B', 12)
        pdf.cell(0, 10, " 2. RESULTADOS DEL ANÁLISIS DE AFECCIONES", 1, 1, 'L', True)
        
        pdf.set_font('Arial', '', 10)
        zonas = req.datos.get('zonas_afectadas', [])
        if not zonas:
            pdf.cell(0, 8, "No se han detectado afecciones normativas.", 1, 1)
        else:
            for z in zonas:
                pdf.multi_cell(0, 8, f"• {z.get('nota', 'Afección sin descripción')}", 1)

        # Observaciones
        if req.notas:
            pdf.ln(5)
            pdf.set_font('Arial', 'B', 12)
            pdf.cell(0, 10, " 3. OBSERVACIONES TÉCNICAS", 1, 1, 'L', True)
            pdf.set_font('Arial', '', 10)
            pdf.multi_cell(0, 8, req.notas, 1)

        filename = f"Informe_{req.ref}.pdf"
        output_path = os.path.join(OUTPUT_DIR, filename)
        pdf.output(output_path)

        if temp_logo and os.path.exists(temp_logo):
            os.remove(temp_logo)

        return FileResponse(output_path, media_type='application/pdf', filename=filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
