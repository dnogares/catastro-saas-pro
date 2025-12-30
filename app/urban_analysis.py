import json
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import logging
import geopandas as gpd
from shapely.ops import unary_union
logger = logging.getLogger(__name__)
class AnalizadorUrbanistico:
    def __init__(self, normativa_dir: str = None, capas_service = None):
        self.normativa_dir = normativa_dir
        self.capas_service = capas_service
        logger.info("[AnalizadorUrbanistico] Inicializado")
    def analizar_referencia(self, referencia: str, geometria_path: str = None) -> Dict:
        logger.info(f"[AnalizadorUrbanistico] Analizando: {referencia}")
        resultado = {"referencia": referencia, "timestamp": datetime.now().isoformat(), "superficie": None, "zonas_afectadas": [], "parametros_urbanisticos": {}, "afecciones": [], "recomendaciones": []}
        if geometria_path and Path(geometria_path).exists():
            try:
                gdf = gpd.read_file(geometria_path)
                if gdf.crs:
                    gdf_meters = gdf.to_crs(epsg=25830)
                    area_total = gdf_meters.geometry.area.sum()
                    resultado["superficie"] = {"valor": round(area_total, 2), "unidad": "m²", "valor_ha": round(area_total / 10000, 4)}
            except Exception as e:
                resultado["error"] = str(e)
        resultado["zonas_afectadas"] = self._analizar_zonas(geometria_path)
        resultado["parametros_urbanisticos"] = self._calcular_parametros(resultado)
        resultado["afecciones"] = self._analizar_afecciones(geometria_path)
        resultado["recomendaciones"] = self._generar_recomendaciones(resultado)
        return resultado
    def _analizar_zonas(self, geometria_path: str = None) -> List[Dict]:
        zonas = []
        if not geometria_path:
            return [{"nota": "Sin geometria para analisis"}]
        try:
            entrada_gdf = gpd.read_file(geometria_path).to_crs("EPSG:4326")
            if self.capas_service:
                for capa in self.capas_service.listar_capas():
                    try:
                        capa_gdf = self.capas_service.cargar_capa(capa["nombre"])
                        if capa_gdf is not None:
                            intersectado = gpd.sjoin(entrada_gdf, capa_gdf.to_crs("EPSG:4326"), how='inner', predicate='intersects')
                            if len(intersectado) > 0:
                                zonas.append({"capa": capa["nombre"], "elementos": len(intersectado)})
                    except Exception:
                        pass
        except Exception as e:
            logger.error(f"[AnalizadorUrbanistico] Error: {e}")
        return zonas if zonas else [{"nota": "No se encontraron capas de zonificacion"}]
    def _calcular_parametros(self, analisis: Dict) -> Dict:
        params = {"superficie_parcela": analisis.get("superficie", {})}
        superficie = analisis.get("superficie", {}).get("valor_ha", 0)
        if superficie > 0:
            params["coeficiente_ocupacion"] = {"valor": 0.5, "nota": "50% (valor generico)"}
            params["edificabilidad"] = {"valor": round(superficie * 1.5, 2), "nota": "1.5 m²/m² (valor generico)"}
            params["altura_maxima"] = {"valor": 12, "nota": "12 metros (valor generico)"}
        return params
    def _analizar_afecciones(self, geometria_path: str = None) -> List[Dict]:
        afecciones = []
        if not geometria_path:
            return [{"nota": "Sin geometria para analisis"}]
        try:
            entrada_gdf = gpd.read_file(geometria_path).to_crs("EPSG:4326")
            if self.capas_service:
                for capa in self.capas_service.listar_capas():
                    nombre = capa["nombre"].lower()
                    if any(p in nombre for p in ["afeccion", "riesgo", "proteccion", "dominio"]):
                        try:
                            capa_gdf = self.capas_service.cargar_capa(capa["nombre"])
                            if capa_gdf is not None:
                                intersectado = gpd.sjoin(entrada_gdf, capa_gdf.to_crs("EPSG:4326"), how='inner', predicate='intersects')
                                if len(intersectado) > 0:
                                    afecciones.append({"tipo": "general", "capa": capa["nombre"], "elementos": len(intersectado)})
                        except Exception:
                            pass
        except Exception as e:
            logger.error(f"[AnalizadorUrbanistico] Error: {e}")
        return afecciones if afecciones else [{"nota": "No se detectaron afecciones"}]
    def _generar_recomendaciones(self, analisis: Dict) -> List[str]:
        return ["Consultar el Plan General de Ordenacion Urbana vigente.", "Verificar correspondencia con el registro de la propiedad.", "Confirmar parametros con el ayuntamiento.", "Este analisis tiene caracter informativo."]
    def generar_certificado(self, analisis: Dict, output_path: str):
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("CERTIFICADO DE ANALISIS URBANISTICO\n")
            f.write("=" * 80 + "\n\n")
            f.write(f"Referencia Catastral: {analisis.get('referencia', 'N/A')}\n")
            f.write(f"Fecha: {analisis.get('timestamp', 'N/A')}\n\n")
            superf = analisis.get('superficie', {})
            f.write(f"Superficie: {superf.get('valor', 'N/A')} {superf.get('unidad', 'm²')}\n\n")
            f.write("ZONAS AFECTADAS:\n")
            for zona in analisis.get('zonas_afectadas', []):
                f.write(f"  - {zona.get('nota', zona.get('capa', 'N/A'))}\n")
            f.write("\nRECOMENDACIONES:\n")
            for rec in analisis.get('recomendaciones', []):
                f.write(f"  - {rec}\n")
            f.write("\n" + "=" * 80 + "\n")
            f.write("GENERADO POR Catastro SaaS Pro\n")
