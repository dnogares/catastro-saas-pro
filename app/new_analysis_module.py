import os
import json
from pathlib import Path
from typing import Dict, List
from datetime import datetime
import logging
import geopandas as gpd
logger = logging.getLogger(__name__)
class AdvancedAnalysisModule:
    def __init__(self, output_dir: str = "/app/app/outputs"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        logger.info("[AdvancedAnalysisModule] Inicializado")
    def procesar_archivos(self, archivos_entrada: List[str]) -> List[Dict]:
        resultados = []
        for archivo in archivos_entrada:
            try:
                resultado = self._procesar_archivo(archivo)
                resultados.append(resultado)
            except Exception as e:
                logger.error(f"[AdvancedAnalysisModule] Error: {e}")
                resultados.append({"archivo": archivo, "error": str(e)})
        return resultados
    def _procesar_archivo(self, archivo: str) -> Dict:
        archivo_path = Path(archivo)
        logger.info(f"[AdvancedAnalysisModule] Procesando: {archivo_path.name}")
        if archivo_path.suffix.lower() == '.kml':
            geojson = self._parsear_kml(archivo_path)
        elif archivo_path.suffix.lower() in ['.geojson', '.json']:
            geojson = self._parsear_geojson(archivo_path)
        else:
            raise ValueError(f"Formato no soportado: {archivo_path.suffix}")
        carpeta_salida = self.output_dir / archivo_path.stem
        carpeta_salida.mkdir(parents=True, exist_ok=True)
        geojson_path = carpeta_salida / f"{archivo_path.stem}.geojson"
        with open(geojson_path, 'w', encoding='utf-8') as f:
            json.dump(geojson, f, indent=2)
        analisis = self._generar_analisis(geojson)
        self._generar_mapa_html(geojson, carpeta_salida / f"{archivo_path.stem}_mapa.html")
        return {"archivo": archivo_path.name, "carpeta_salida": str(carpeta_salida), "geojson": str(geojson_path), "analisis": analisis}
    def _parsear_kml(self, kml_path: Path) -> Dict:
        try:
            gdf = gpd.read_file(str(kml_path))
            return json.loads(gdf.to_json())
        except Exception:
            return self._parsear_kml_manual(kml_path)
    def _parsear_kml_manual(self, kml_path: Path) -> Dict:
        import re
        with open(kml_path, 'r', encoding='utf-8') as f:
            content = f.read()
        coord_pattern = r'<coordinates>([\d\s,\.\-]+)</coordinates>'
        matches = re.findall(coord_pattern, content)
        features = []
        for i, coords_str in enumerate(matches):
            coords = []
            for point in coords_str.strip().split():
                parts = point.split(',')
                if len(parts) >= 2:
                    try:
                        coords.append([float(parts[0]), float(parts[1])])
                    except ValueError:
                        continue
            if len(coords) >= 3:
                features.append({"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [coords]}, "properties": {"id": i}})
        return {"type": "FeatureCollection", "features": features}
    def _parsear_geojson(self, geojson_path: Path) -> Dict:
        with open(geojson_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    def _generar_analisis(self, geojson: Dict) -> Dict:
        features = geojson.get('features', [])
        analisis = {"total_features": len(features), "tipos_geometria": {}}
        bounding_boxes = []
        for feature in features:
            geom_type = feature.get('geometry', {}).get('type', 'desconocido')
            analisis["tipos_geometria"][geom_type] = analisis["tipos_geometria"].get(geom_type, 0) + 1
            geom = feature.get('geometry', {})
            if geom.get('type') == 'Polygon':
                coords = geom.get('coordinates', [[]])[0]
                if coords:
                    bounding_boxes.append({"min_lon": min(c[0] for c in coords), "max_lon": max(c[0] for c in coords), "min_lat": min(c[1] for c in coords), "max_lat": max(c[1] for c in coords)})
        if bounding_boxes:
            analisis["bounding_box"] = {"min_lon": min(b["min_lon"] for b in bounding_boxes), "max_lon": max(b["max_lon"] for b in bounding_boxes), "min_lat": min(b["min_lat"] for b in bounding_boxes), "max_lat": max(b["max_lat"] for b in bounding_boxes)}
        return analisis
    def _generar_mapa_html(self, geojson: Dict, output_path: Path):
        html = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>Mapa de Analisis</title><link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" /><script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script><style>body{margin:0;padding:20px;font-family:Arial;}#map{height:600px;width:100%;}</style></head><body><h1>Analisis de Parcelas</h1><div id="map"></div><script>var map = L.map('map').setView([40.0, -3.0], 6);L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {attribution: '© OpenStreetMap'}).addTo(map);var data = """ + json.dumps(geojson) + """;L.geoJSON(data, {style: {color: '#3388ff', weight: 2}, onEachFeature: function(f,l){if(f.properties){l.bindPopup(JSON.stringify(f.properties));}}}).addTo(map);</script></body></html>"""
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)
def procesar_parcelas_custom(archivos_entrada: List[str], directorio_salida: str, base_capas_path: str = "/app/app/capas") -> List[Dict]:
    modulo = AdvancedAnalysisModule(output_dir=directorio_salida)
    return modulo.procesar_archivos(archivos_entrada)
