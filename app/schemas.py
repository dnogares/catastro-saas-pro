from typing import List, Optional, Dict
from pydantic import BaseModel, Field

class QueryRequest(BaseModel):
    referencia_catastral: str = Field(..., min_length=14, max_length=20)

class CatastroResponse(BaseModel):
    status: str
    data: Optional[Dict] = None
    detail: Optional[str] = None

class BatchRequest(BaseModel):
    referencias: List[str]
