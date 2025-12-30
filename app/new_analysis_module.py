import os
import json
from pathlib import Path
from typing import Dict, List
import logging
import geopandas as gpd

logger = logging.getLogger(__name__)

class AdvancedAnalysisModule:
    def __init__(self, output_dir: str = "/app/app/outputs"):
        # Aseguramos que la ruta sea absoluta y exista
        self.output_dir = Path(output_dir).absolute()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"[AdvancedAnalysisModule] Inicializado en {self.output_dir}")

    def procesar_archivos(self, archivos_entrada: List[str]) -> List[Dict]:
        resultados = []
        for archivo in archivos_entrada:
            try:
                resultado = self._procesar_archivo(archivo)
                resultados.append(resultado)
            except Exception as e:
                logger.error(f"[AdvancedAnalysisModule] Error procesando {archivo}: {e}")
                resultados.append({"archivo": archivo, "error": str(e)})
        return resultados

    def _procesar_archivo(self, archivo: str) -> Dict:
        archivo_path = Path(archivo)
        logger.info(f"[AdvancedAnalysisModule] Procesando: {archivo_path.name}")

        # 1. Parsing según extensión
        if archivo_path.suffix.lower() == '.kml':
            geojson = self._parsear_kml(archivo_path)
        elif archivo_path.suffix.lower() in ['.geojson', '.json']:
            geojson = self._parsear_geojson(archivo_path)
        else:
            raise ValueError(f"Formato no soportado: {archivo_path.suffix}")

        # 2. Definir carpeta de salida (por referencia/nombre de archivo)
        # Usamos el stem (nombre sin extensión) como ID de carpeta
        ref_id = archivo_path.stem
        carpeta_salida = self.output_dir / ref_id
        carpeta_salida.mkdir(parents=True, exist_ok=True)

        # 3. Guardar GeoJSON procesado
        geojson_path = carpeta_salida / f"{ref_id}.geojson"
        with open(geojson_path, 'w', encoding='utf-8') as f:
            json.dump(geojson, f, indent=2)

        # 4. Generar Mapa HTML y Análisis
        analisis = self._generar_analisis(geojson)
        path_mapa = carpeta_salida / f"{ref_id}_mapa.html"
        self._generar_mapa_html(geojson, path_mapa, ref_id)

        return {
            "referencia": ref_id,
            "archivo": archivo_path.name,
            "carpeta_salida": str(carpeta_salida),
            "geojson": str(geojson_path),
            "mapa_html": str(path_mapa),
            "analisis": analisis
        }

    def _parsear_kml(self, kml_path: Path) -> Dict:
        try:
            # Intento con Geopandas (requiere fiona instalado)
            gdf = gpd.read_file(str(kml_path))
            return json.loads(gdf.to_json())
        except Exception as e:
            logger.warning(f"Fallo Geopandas en KML, intentando fallback manual: {e}")
            return self._parsear_kml_manual(kml_path)

    def _parsear_kml_manual(self, kml_path: Path) -> Dict:
        import re
        with open(kml_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Regex básico para extraer coordenadas de Polígonos
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
                features.append({
                    "type": "Feature",
                    "geometry": {"type": "Polygon", "coordinates": [coords]},
                    "properties": {"id": i, "source": "manual_kml_parser"}
                })
        
        return {"type": "FeatureCollection", "features": features}

    def _parsear_geojson(self, geojson_path: Path) -> Dict:
        with open(geojson_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _generar_analisis(self, geojson: Dict) -> Dict:
        features = geojson.get('features', [])
        analisis = {"total_features": len(features), "tipos_geometria": {}}
        
        for feature in features:
            geom_type = feature.get('geometry', {}).get('type', 'desconocido')
            analisis["tipos_geometria"][geom_type] = analisis["tipos_geometria"].get(geom_type, 0) + 1
            
        return analisis

    def _generar_mapa_html(self, geojson: Dict, output_path: Path, ref_id: str):
        # Mapa con auto-zoom al cargar (fitBounds)
        html_template = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Mapa de Análisis - {ref_id}</title>
            <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
            <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
            <style>
                body {{ margin: 0; padding: 0; }}
                #map {{ height: 100vh; width: 100%; }}
                .info-box {{ position: absolute; top: 10px; left: 50px; z-index: 1000; background: white; padding: 10px; border-radius: 5px; box-shadow: 0 0 15px rgba(0,0,0,0.2); font-family: sans-serif; }}
            </style>
        </head>
        <body>
            <div class="info-box">Ref: {ref_id}</div>
            <div id="map"></div>
            <script>
                var map = L.map('map');
                
                L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
                    attribution: '© OpenStreetMap'
                }}).addTo(map);

                var data = {json.dumps(geojson)};
                var geojsonLayer = L.geoJSON(data, {{
                    style: {{
                        color: '#3498db',
                        weight: 3,
                        opacity: 0.8,
                        fillColor: '#3498db',
                        fillOpacity: 0.2
                    }},
                    onEachFeature: function(f, l) {{
                        if (f.properties) {{
                            l.bindPopup("<pre>" + JSON.stringify(f.properties, null, 2) + "</pre>");
                        }}
                    }}
                }}).addTo(map);

                // Auto-zoom a la geometría
                if (data.features.length > 0) {{
                    map.fitBounds(geojsonLayer.getBounds());
                }} else {{
                    map.setView([40.4167, -3.7037], 6);
                }}
            </script>
        </body>
        </html>
        """
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_template)

def procesar_parcelas_custom(archivos_entrada: List[str], directorio_salida: str) -> List[Dict]:
    modulo = AdvancedAnalysisModule(output_dir=directorio_salida)
    return modulo.procesar_archivos(archivos_entrada)
