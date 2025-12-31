import os
import shutil
import uuid
import pandas as pd
from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse
from typing import List, Optional

# Importamos tus módulos (asumiendo que los guardas con estos nombres)
from kml_processor import AdvancedAnalysisModule
from vector_analyzer import procesar_parcelas, listar_capas_wms, cargar_config_titulos
from urban_analysis import AnalizadorUrbanistico

app = FastAPI(title="Catastro SaaS Pro - Ultimate Edition")

# --- ENDPOINTS MÓDULO 1: GESTIÓN CATASTRO (Lotes y Referencias) ---

@app.post("/api/catastro/batch")
async def batch_process(file: UploadFile = File(...), group_by: str = Form("referencia")):
    """
    Recibe CSV/TXT con multitud de referencias. 
    Genera GML, KML e Imágenes por cada una.
    """
    filename = f"batch_{uuid.uuid4()}.csv"
    temp_path = f"datos_origen/{filename}"
    
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # Aquí se dispararía la lógica de iteración sobre el CSV
    # Llamando a AnalizadorUrbanistico por cada fila
    return {"status": "success", "message": f"Procesando lote agrupado por {group_by}"}

# --- ENDPOINTS MÓDULO 2: ANÁLISIS KML AVANZADO ---

@app.post("/api/analysis/kml-advanced")
async def kml_advanced(files: List[UploadFile] = File(...)):
    """Responde al código de AdvancedAnalysisModule"""
    processor = AdvancedAnalysisModule(output_dir="outputs/kml_analysis")
    saved_paths = []
    
    for file in files:
        path = f"datos_origen/{file.filename}"
        with open(path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        saved_paths.append(path)
    
    resultados = processor.procesar_archivos(saved_paths)
    return {"status": "success", "data": resultados}

# --- ENDPOINTS MÓDULO 3: AFECCIONES VECTORIALES (El script largo) ---

@app.post("/api/analysis/vectorial")
async def run_vector_analysis(background_tasks: BackgroundTasks):
    """
    Ejecuta el script de cálculo de % de afección, 
    generación de títulos dinámicos y mapas con IGN-Base.
    """
    # Configuraciones requeridas por tu script
    capas_wms = listar_capas_wms("capas/wms/capas_wms.csv")
    config_titulos = cargar_config_titulos("capas/wms/titulos.csv")
    
    # Ejecutamos la función de tu punto 3
    # Nota: En producción, esto debería ser asíncrono (BackgroundTasks)
    try:
        procesar_parcelas(None, None, capas_wms, "EPSG:25830", config_titulos)
        return {"status": "success", "message": "Análisis vectorial completado"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

# --- ENDPOINT MÓDULO 5: GENERADOR DE INFORME PERSONALIZADO ---

@app.post("/api/report/generate")
async def generate_final_report(
    ref: str = Form(...),
    empresa: str = Form(...),
    tecnico: str = Form(...),
    colegiado: str = Form(...),
    notas: str = Form(""),
    incluir_archivos: str = Form(...), # JSON con IDs de mapas seleccionados
    logo: UploadFile = File(None)
):
    """Genera el PDF final uniendo datos de los 3 módulos anteriores"""
    # Lógica de FPDF para crear el informe con los JPGs generados en el módulo 3
    return {"status": "success", "pdf_url": f"/outputs/{ref}/informe_final.pdf"}
