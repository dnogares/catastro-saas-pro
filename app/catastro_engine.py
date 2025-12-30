import os
import json
import zipfile
import requests
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional
import logging
import geopandas as gpd
from shapely.geometry import Polygon, Point
logger = logging.getLogger(__name__)
class CatastroDownloader:
    BASE_URL = "https://ovc.catastro.es/ovc/Proxy.ashx"
    GEO_URL = "https://ovc.catastro.es/ovc/Geo.ashx"
    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"[CatastroDownloader] Inicializado en: {output_dir}")
    def consultar_referencia(self, referencia: str) -> Dict:
        params = {"SRS": "EPSG:4326", "refcat": referencia, "format": "json"}
        try:
            response = requests.get(self.BASE_URL, params=params, timeout=30)
            if response.status_code == 200:
                data = response.json()
                return {"success": True, "data": data, "referencia": referencia, "timestamp": datetime.now().isoformat()}
            return {"success": False, "error": f"Error HTTP {response.status_code}", "referencia": referencia}
        except Exception as e:
            return {"success": False, "error": str(e), "referencia": referencia}
    def descargar_geometria(self, referencia: str) -> Optional[str]:
        try:
            geojson_url = f"{self.GEO_URL}?refcat={referencia}&format=geojson"
            response = requests.get(geojson_url, timeout=30)
            if response.status_code == 200:
                geojson_path = self.output_dir / f"{referencia}.geojson"
                content = response.text
                if content and len(content) > 10:
                    with open(geojson_path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    return str(geojson_path)
            return None
        except Exception as e:
            logger.error(f"[CatastroDownloader] Error: {e}")
            return None
    def descargar_datos_bienes(self, referencia: str) -> Optional[Dict]:
        resultado = self.consultar_referencia(referencia)
        if resultado.get("success") and resultado.get("data"):
            json_path = self.output_dir / f"{referencia}_datos.json"
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(resultado["data"], f, indent=2, ensure_ascii=False)
            return resultado["data"]
        return None
    def descargar_todo(self, referencia: str, crear_zip: bool = True) -> Dict:
        logger.info(f"[CatastroDownloader] Descargando: {referencia}")
        resultado = {"referencia": referencia, "timestamp": datetime.now().isoformat(), "consulta": None, "geojson_path": None, "zip_path": None, "success": False}
        resultado["consulta"] = self.consultar_referencia(referencia)
        geojson_path = self.descargar_geometria(referencia)
        if geojson_path:
            resultado["geojson_path"] = geojson_path
        datos_bienes = self.descargar_datos_bienes(referencia)
        if crear_zip:
            zip_path = self._crear_zip(referencia, resultado)
            resultado["zip_path"] = str(zip_path)
        resultado["success"] = resultado["consulta"].get("success", False) or geojson_path is not None
        return resultado
    def _crear_zip(self, referencia: str, resultado: Dict) -> Path:
        zip_path = self.output_dir / f"{referencia}_datos.zip"
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            consulta = resultado.get("consulta", {})
            if consulta.get("data"):
                zf.writestr(f"{referencia}_consulta.json", json.dumps(consulta["data"], indent=2))
            geojson_path = resultado.get("geojson_path")
            if geojson_path and Path(geojson_path).exists():
                zf.write(geojson_path, f"{referencia}.geojson")
            metadata = {"referencia": referencia, "timestamp": resultado["timestamp"]}
            zf.writestr(f"{referencia}_metadata.json", json.dumps(metadata, indent=2))
        return zip_path
class GeneradorInformeCatastral:
    def __init__(self, referencia: str, output_dir: str):
        self.referencia = referencia
        self.output_dir = Path(output_dir)
        self.datos = {}
        self._cargar_datos()
    def _cargar_datos(self):
        json_path = self.output_dir / f"{self.referencia}_datos.json"
        geojson_path = self.output_dir / f"{self.referencia}.geojson"
        if json_path.exists():
            with open(json_path, 'r', encoding='utf-8') as f:
                self.datos = json.load(f)
    def generar_pdf(self, output_path: str):
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib import colors
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
            from reportlab.lib.units import inch
            doc = SimpleDocTemplate(output_path, pagesize=A4, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=72)
            styles = getSampleStyleSheet()
            elementos = []
            elementos.append(Paragraph(f"Informe Catastral: {self.referencia}", styles['Heading1']))
            elementos.append(Spacer(1, 20))
            elementos.append(Paragraph(f"Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M')}", styles['Normal']))
            elementos.append(Spacer(1, 30))
            consulta_data = self.datos.get('rc', {})
            if consulta_data:
                tabla_datos = [["Referencia:", self.referencia], ["Localidad:", consulta_data.get('ni', 'No disponible')], ["Municipio:", consulta_data.get('nm', 'No disponible')]]
                t = Table(tabla_datos, colWidths=[2*inch, 4*inch])
                t.setStyle(TableStyle([('FONTNAME', (0, 0), (-1, -1), 'Helvetica'), ('GRID', (0, 0), (-1, -1), 1, colors.grey), ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey)]))
                elementos.append(t)
            doc.build(elementos)
            logger.info(f"[GeneradorInforme] PDF generado: {output_path}")
        except ImportError:
            self._generar_txt(output_path.replace('.pdf', '.txt'))
    def _generar_txt(self, output_path: str):
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(f"Informe Catastral: {self.referencia}\n")
            f.write(f"Fecha: {datetime.now().isoformat()}\n\n")
            if self.datos:
                f.write(json.dumps(self.datos, indent=2))
