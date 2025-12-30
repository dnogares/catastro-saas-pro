from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.catastro_engine import CatastroDownloader
from app.schemas import QueryRequest, CatastroResponse
import uvicorn
import os

app = FastAPI(title="Catastro SaaS Pro")

# Configuración de directorios y servicios
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")
downloader = CatastroDownloader(output_dir="app/outputs")

@app.get("/")
async def read_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/dashboard")
async def read_dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})

@app.get("/health")
async def health_check():
    return {"status": "ok"}

# --- RUTA QUE SOLUCIONA EL ERROR 404 ---
@app.post("/api/catastro/consultar", response_model=CatastroResponse)
async def consultar_catastro(query: QueryRequest):
    try:
        # 1. Consultar datos básicos
        resultado = downloader.consultar_referencia(query.referencia_catastral)
        
        if not resultado["success"]:
            return {"status": "error", "detail": resultado.get("error", "Error desconocido")}

        # 2. Intentar descargar geometría para el mapa
        geojson_path = downloader.descargar_geometria(query.referencia_catastral)
        
        # Estructuramos la respuesta para el main.js
        return {
            "status": "success",
            "data": {
                "referencia": query.referencia_catastral,
                "direccion": resultado["data"].get("lddf", "Dirección no disponible"),
                "superficie": "Pendiente de cálculo",
                "uso": "Residencial / Otros",
                "geojson": geojson_path # Aquí podrías cargar el contenido del archivo si fuera necesario
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
