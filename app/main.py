from fastapi import FastAPI
from app.catastro_engine import CatastroDownloader
from app.intersection_service import IntersectionService
import uvicorn
app = FastAPI(title="Catastro SaaS Pro")
@app.get("/")
async def root():
    return {"message": "Servidor activo", "status": "ok"}
if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)