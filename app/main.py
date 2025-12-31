from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn
import json

# Importamos tus clases existentes
from urban_analysis import AnalizadorUrbanistico
# from advanced_analysis import AdvancedAnalysisModule # Asegúrate de que el nombre coincida

app = FastAPI()

# Permitir que el frontend se comunique con el backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Servir archivos estáticos (HTML, CSS, JS)
app.mount("/static", StaticFiles(directory="."), name="static")

# Instanciar tus analizadores
urban_tool = AnalizadorUrbanistico()

@app.post("/api/analizar-referencia")
async def api_analizar_ref(referencia: str = Form(...)):
    """
    Llama a urban_analysis.py para obtener datos de la parcela
    """
    # Aquí llamarías a la lógica que descarga el GML de catastro y lo analiza
    # Simulamos la respuesta que espera Leaflet (GeoJSON)
    resultado = urban_tool.analizar_referencia(referencia)
    
    # Para el mapa, necesitamos devolver la geometría en formato GeoJSON
    return {
        "status": "success",
        "datos": resultado,
        "geojson": {
            "type": "Feature",
            "geometry": { "type": "Polygon", "coordinates": [[[...]]] }, # Aquí irían las coordenadas reales
            "properties": { "refcat": referencia }
        }
    }

@app.post("/api/analizar-kml")
async def api_analizar_kml(file: UploadFile = File(...)):
    """
    Llama a AdvancedAnalysisModule para procesar archivos geográficos
    """
    contents = await file.read()
    # Guardar temporalmente y procesar con tu módulo
    # resultado = advanced_tool.procesar_archivo(contents)
    
    return {"status": "success", "message": "KML procesado correctamente"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
