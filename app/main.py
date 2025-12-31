import os
import json
import shutil
from typing import List
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fpdf import FPDF

# Importar tus clases de los archivos que ya tienes
from kml_processor import AdvancedAnalysisModule
from vector_analyzer import procesar_parcelas, listar_capas_wms, cargar_config_titulos

app = FastAPI()

# Configuración de directorios
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")
CAPAS_DIR = os.path.join(BASE_DIR, "capas")

@app.post("/api/report/generate")
async def generate_report(
    ref: str = Form(...),
    empresa: str = Form(...),
    tecnico: str = Form(...),
    colegiado: str = Form(...),
    notas: str = Form(""),
    incluir_archivos: str = Form(...), # JSON string con array de rutas
    logo: UploadFile = File(None)
):
    try:
        # 1. Preparar PDF
        pdf = FPDF()
        pdf.add_page()
        
        # 2. Manejo de Logo
        if logo:
            logo_path = os.path.join(OUTPUT_DIR, f"temp_logo_{ref}.png")
            with open(logo_path, "wb") as buffer:
                shutil.copyfileobj(logo.file, buffer)
            pdf.image(logo_path, 10, 8, 33)
            pdf.ln(20)

        # 3. Encabezado
        pdf.set_font("Arial", 'B', 16)
        pdf.cell(0, 10, f"INFORME TÉCNICO DE AFECCIONES", 0, 1, 'C')
        pdf.set_font("Arial", '', 12)
        pdf.cell(0, 10, f"Referencia: {ref}", 0, 1, 'C')
        pdf.ln(10)

        # 4. Datos del Técnico
        pdf.set_fill_color(240, 240, 240)
        pdf.cell(0, 10, " DATOS DEL PROFESIONAL", 0, 1, 'L', True)
        pdf.set_font("Arial", '', 11)
        pdf.cell(0, 8, f"Empresa: {empresa}", 0, 1)
        pdf.cell(0, 8, f"Técnico: {tecnico}", 0, 1)
        pdf.cell(0, 8, f"Nº Colegiado: {colegiado}", 0, 1)
        pdf.ln(5)

        if notas:
            pdf.set_font("Arial", 'I', 10)
            pdf.multi_cell(0, 5, f"Notas adicionales: {notas}")
            pdf.ln(10)

        # 5. Insertar Mapas Seleccionados (Punto 3 y 4)
        lista_mapas = json.loads(incluir_archivos)
        for img_path in lista_mapas:
            # Limpiar la ruta para que sea local
            local_img = img_path.split("/outputs/")[-1]
            full_path = os.path.join(OUTPUT_DIR, local_img)
            
            if os.path.exists(full_path):
                pdf.add_page()
                pdf.set_font("Arial", 'B', 12)
                pdf.cell(0, 10, f"PLANO: {os.path.basename(full_path)}", 0, 1)
                pdf.image(full_path, x=10, y=30, w=190)

        # 6. Guardar y retornar
        report_name = f"Informe_{ref}.pdf"
        report_path = os.path.join(OUTPUT_DIR, ref, report_name)
        os.makedirs(os.path.dirname(report_path), exist_ok=True)
        pdf.output(report_path)

        return {"status": "success", "pdf_url": f"/outputs/{ref}/{report_name}"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
