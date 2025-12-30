#!/bin/bash
mkdir -p /app/app/capas/gpkg /app/app/capas/shapefiles /app/app/capas/wms /app/app/outputs
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
