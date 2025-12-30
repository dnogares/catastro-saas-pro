import os
import json
import csv
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import logging
import geopandas as gpd
from shapely.ops import unary_union
from shapely.geometry import Point
logger = logging.getLogger(__name__)
class IntersectionService:
    def __init__(self, data_dir: str = "/app/app/capas"):
        self.data_dir = Path(data_dir)
        self.capas_cache = {}
        self._verificar_estructura()
        logger.info(f"[IntersectionService] Inicializado: {data_dir}")
    def _verificar_estructura(self):
        for subdir in ["gpkg", "shapefiles", "wms"]:
            path = self.data_dir / subdir
            if not path.exists():
                path.mkdir(parents=True, exist_ok=True)
    def cargar_capa(self, nombre_capa: str) -> Optional[gpd.GeoDataFrame]:
        if nombre_capa in self.capas_cache:
            return self.capas_cache[nombre_capa]
        for fmt in [".gpkg", ".shp"]:
            gpkg_path = self.data_dir / "gpkg" / f"{nombre_capa}{fmt}"
            if gpkg_path.exists():
                try:
                    gdf = gpd.read_file(str(gpkg_path))
                    self.capas_cache[nombre_capa] = gdf
                    return gdf
                except Exception as e:
                    logger.error(f"[IntersectionService] Error: {e}")
        return None
    def listar_capas(self) -> List[Dict]:
        capas = []
        gpkg_dir = self.data_dir / "gpkg"
        if gpkg_dir.exists():
            for f in gpkg_dir.glob("*.gpkg"):
                try:
                    gdf = gpd.read_file(str(f))
                    capas.append({"nombre": f.stem, "tipo": "gpkg", "archivo": f.name, "elementos": len(gdf)})
                except Exception as e:
                    capas.append({"nombre": f.stem, "tipo": "gpkg", "error": str(e)})
        wms_csv = self.data_dir / "wms" / "capas_wms.csv"
        if wms_csv.exists():
            with open(wms_csv, 'r', encoding='utf-8') as f:
                for row in csv.DictReader(f):
                    if row.get("nombre"):
                        capas.append({"nombre": row["nombre"], "tipo": "wms", "url": row.get("ruta_wms", "")})
        return capas
    def analyze_file(self, file_path: str, output_dir: str = None) -> Dict:
        logger.info(f"[IntersectionService] Analizando: {file_path}")
        try:
            entrada_gdf = gpd.read_file(file_path)
            if entrada_gdf.crs is None:
                entrada_gdf = entrada_gdf.set_crs("EPSG:4326")
            entrada_gdf = entrada_gdf.to_crs("EPSG:4326")
            resultado = {"archivo_entrada": file_path, "timestamp": datetime.now().isoformat(), "elementos_entrada": len(entrada_gdf), "capas_analizadas": [], "intersecciones": []}
            geometria_union = unary_union(entrada_gdf.geometry.tolist())
            capas = self.listar_capas()
            resultado["capas_analizadas"] = [c["nombre"] for c in capas]
            for capa in capas:
                if capa.get("tipo") in ["gpkg", "shapefile"]:
                    capa_gdf = self.cargar_capa(capa["nombre"])
                    if capa_gdf is not None and not capa_gdf.empty:
                        try:
                            capa_crs = capa_gdf.to_crs("EPSG:4326")
                            joined = gpd.sjoin(entrada_gdf, capa_crs, how='inner', predicate='intersects')
                            resultado["intersecciones"].append({"capa": capa["nombre"], "elementos_encontrados": len(joined)})
                        except Exception as e:
                            resultado["intersecciones"].append({"capa": capa["nombre"], "error": str(e)})
            if output_dir:
                output_path = Path(output_dir) / "intersecciones.json"
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(resultado, f, indent=2)
            return resultado
        except Exception as e:
            return {"error": str(e), "archivo_entrada": file_path}
    def verificar_punto(self, lon: float, lat: float) -> Dict:
        punto = Point(lon, lat)
        punto_gdf = gpd.GeoDataFrame(geometry=[punto], crs="EPSG:4326")
        resultado = {"punto": {"lon": lon, "lat": lat}, "capas_afectadas": []}
        for capa in self.listar_capas():
            if capa.get("tipo") in ["gpkg", "shapefile"]:
                capa_gdf = self.cargar_capa(capa["nombre"])
                if capa_gdf is not None:
                    try:
                        intersectado = gpd.sjoin(punto_gdf, capa_gdf, how='inner', predicate='within')
                        if len(intersectado) > 0:
                            resultado["capas_afectadas"].append({"capa": capa["nombre"], "elementos": len(intersectado)})
                    except Exception:
                        pass
        return resultado
