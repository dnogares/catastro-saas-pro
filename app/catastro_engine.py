import requests
import os
from pathlib import Path
import time
import xml.etree.ElementTree as ET
import json
from io import BytesIO

# Intentar importar PIL, pero continuar si no está disponible
try:
    from PIL import Image, ImageDraw
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False
    print("Pillow no disponible - se omitira la composicion de imagenes y contornos")


class CatastroDownloader:
    """
    Descarga documentacion del Catastro español a partir de referencias catastrales.
    Incluye generacion de mapas, KML, y capas de afecciones urbanisticas/ambientales.
    """

    def __init__(self, output_dir="descargas_catastro"):
        self.output_dir = output_dir
        self.base_url = "https://ovc.catastro.meh.es"
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        self._municipio_cache = {}

    def limpiar_referencia(self, ref):
        """Limpia la referencia catastral eliminando espacios."""
        return ref.replace(" ", "").strip()

    def extraer_del_mun(self, ref):
        """Extrae el codigo de delegacion (2 digitos) y municipio (3 digitos) de la referencia."""
        ref = self.limpiar_referencia(ref)
        if len(ref) >= 5:
            return ref[:2], ref[2:5]
        return "", ""

    def obtener_coordenadas(self, referencia):
        """Obtiene las coordenadas de la parcela desde el servicio del Catastro."""
        ref = self.limpiar_referencia(referencia)

        # Metodo 1: Servicio REST JSON
        try:
            url_json = (
                "http://ovc.catastro.meh.es/OVCServWeb/OVCWcfCallejero/"
                f"COVCCallejero.svc/json/Geo_RCToWGS84/{ref}"
            )
            response = requests.get(url_json, timeout=30)

            if response.status_code == 200:
                data = response.json()
                if (
                    "geo" in data
                    and "xcen" in data["geo"]
                    and "ycen" in data["geo"]
                ):
                    lon = float(data["geo"]["xcen"])
                    lat = float(data["geo"]["ycen"])
                    print(f"  Coordenadas obtenidas (JSON): Lon={lon}, Lat={lat}")
                    return {"lon": lon, "lat": lat, "srs": "EPSG:4326"}
        except Exception as e:
            pass

        # Metodo 2: Extraer del GML de parcela
        try:
            url_gml = "http://ovc.catastro.meh.es/INSPIRE/wfsCP.aspx"
            params = {
                "service": "wfs",
                "version": "2.0.0",
                "request": "GetFeature",
                "STOREDQUERY_ID": "GetParcel",
                "refcat": ref,
                "srsname": "EPSG:4326",
            }

            response = requests.get(url_gml, params=params, timeout=30)
            if response.status_code == 200:
                root = ET.fromstring(response.content)

                namespaces = {
                    "gml": "http://www.opengis.net/gml/3.2",
                    "cp": "http://inspire.ec.europa.eu/schemas/cp/4.0",
                    "gmd": "http://www.isotc211.org/2005/gmd",
                }

                for ns_uri in namespaces.values():
                    pos_list = root.findall(f".//{{{ns_uri}}}pos")
                    if pos_list:
                        coords_text = pos_list[0].text.strip().split()
                        if len(coords_text) >= 2:
                            v1 = float(coords_text[0])
                            v2 = float(coords_text[1])
                            if 36 <= v1 <= 44 and -10 <= v2 <= 5: 
                                lat, lon = v1, v2
                            elif 36 <= v2 <= 44 and -10 <= v1 <= 5:
                                lat, lon = v2, v1
                            else:
                                lat, lon = v1, v2
                                
                            print(f"  Coordenadas extraidas del GML: Lon={lon}, Lat={lat}")
                            return {"lon": lon, "lat": lat, "srs": "EPSG:4326"}
        except Exception as e:
            pass
        
        # Metodo 3: Servicio XML original
        try:
            url = (
                "http://ovc.catastro.meh.es/ovcservweb/ovcswlocalizacionrc/"
                "ovccoordenadas.asmx/Consulta_RCCOOR"
            )
            params = {"SRS": "EPSG:4326", "RC": ref}

            response = requests.get(url, params=params, timeout=30)
            if response.status_code == 200:
                root = ET.fromstring(response.content)
                coords_element = root.find(
                    ".//{http://www.catastro.meh.es/}coord"
                )
                if coords_element is not None:
                    geo = coords_element.find(
                        "{http://www.catastro.meh.es/}geo"
                    )
                    if geo is not None:
                        xcen = geo.find(
                            "{http://www.catastro.meh.es/}xcen"
                        )
                        ycen = geo.find(
                            "{http://www.catastro.meh.es/}ycen"
                        )

                        if xcen is not None and ycen is not None:
                            lon = float(xcen.text)
                            lat = float(ycen.text)
                            print(f"  Coordenadas obtenidas (XML): Lon={lon}, Lat={lat}")
                            return {"lon": lon, "lat": lat, "srs": "EPSG:4326"}
        except Exception as e:
            pass

        print("  No se pudieron obtener coordenadas por ningun metodo")
        return None

    def convertir_coordenadas_a_etrs89(self, lon, lat):
        """Convierte coordenadas WGS84 a ETRS89/UTM (aproximacion)."""
        if lon < -6:
            zona = 29
            epsg = 25829
        elif lon < 0:
            zona = 30
            epsg = 25830
        else:
            zona = 31
            epsg = 25831

        return {"epsg": epsg, "zona": zona}

    def calcular_bbox(self, lon, lat, buffer_metros=200):
        """Calcula un BBOX (WGS84) alrededor de un punto para WMS."""
        buffer_lon = buffer_metros / 85000
        buffer_lat = buffer_metros / 111000

        minx = lon - buffer_lon
        miny = lat - buffer_lat
        maxx = lon + buffer_lon
        maxy = lat + buffer_lat

        return f"{minx},{miny},{maxx},{maxy}"

    def generar_kml(self, referencia, coords, gml_coords=None):
        """Genera archivo KML con el punto central y el poligono de la parcela."""
        ref = self.limpiar_referencia(referencia)
        filename = f"{self.output_dir}/{ref}_parcela.kml"
        
        lon = coords["lon"]
        lat = coords["lat"]
        
        kml_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>Parcela Catastral {ref}</name>
    <description>Informacion catastral de la referencia {ref}</description>
    
    <Style id="parcela_style">
      <LineStyle>
        <color>ff0000ff</color>
        <width>3</width>
      </LineStyle>
      <PolyStyle>
        <color>4d0000ff</color>
      </PolyStyle>
    </Style>
    
    <Style id="punto_style">
      <IconStyle>
        <scale>1.2</scale>
        <Icon>
          <href>http://maps.google.com/mapfiles/kml/paddle/red-circle.png</href>
        </Icon>
      </IconStyle>
    </Style>
    
    <Placemark>
      <name>Centro Parcela {ref}</name>
      <description>
        <![CDATA[
        <b>Referencia Catastral:</b> {ref}<br/>
        <b>Coordenadas:</b> {lat:.6f}, {lon:.6f}<br/>
        <b>Enlace Catastro:</b> <a href="https://www1.sedecatastro.gob.es/Cartografia/mapa.aspx?refcat={ref}">Ver en Catastro</a><br/>
        <b>Google Maps:</b> <a href="https://www.google.com/maps/search/?api=1&query={lat},{lon}">Ver en Google Maps</a>
        ]]>
      </description>
      <styleUrl>#punto_style</styleUrl>
      <Point>
        <coordinates>{lon},{lat},0</coordinates>
      </Point>
    </Placemark>
'''
        
        if gml_coords and len(gml_coords) > 2:
            kml_content += '''
    <Placemark>
      <name>Contorno Parcela {}</name>
      <description>Limite de la parcela catastral</description>
      <styleUrl>#parcela_style</styleUrl>
      <Polygon>
        <outerBoundaryIs>
          <LinearRing>
            <coordinates>
'''.format(ref)
            
            for coord in gml_coords:
                v1, v2 = coord
                if 36 <= v1 <= 44 and -10 <= v2 <= 5:
                    kml_content += f"              {v2},{v1},0\n"
                elif 36 <= v2 <= 44 and -10 <= v1 <= 5:
                    kml_content += f"              {v1},{v2},0\n"
                else:
                    kml_content += f"              {v2},{v1},0\n"
            
            first_coord = gml_coords[0]
            v1, v2 = first_coord
            if 36 <= v1 <= 44 and -10 <= v2 <= 5:
                kml_content += f"              {v2},{v1},0\n"
            elif 36 <= v2 <= 44 and -10 <= v1 <= 5:
                kml_content += f"              {v1},{v2},0\n"
            else:
                kml_content += f"              {v2},{v1},0\n"
            
            kml_content += '''            </coordinates>
          </LinearRing>
        </outerBoundaryIs>
      </Polygon>
    </Placemark>
'''
        
        kml_content += '''  </Document>
</kml>'''
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(kml_content)
            print(f"  Archivo KML generado: {filename}")
            return True
        except Exception as e:
            print(f"  Error generando KML: {e}")
            return False

    def descargar_capas_afecciones(self, referencia, bbox_wgs84, width=1600, height=1600):
        """Descarga capas de afecciones territoriales sobre la parcela."""
        ref = self.limpiar_referencia(referencia)
        print("\n  Descargando capas de afecciones...")
        
        coords_list = bbox_wgs84.split(",")
        bbox_wms13 = f"{coords_list[1]},{coords_list[0]},{coords_list[3]},{coords_list[2]}"
        
        capas_disponibles = {
            "catastro_parcelas": {
                "url": "http://ovc.catastro.meh.es/Cartografia/WMS/ServidorWMS.aspx",
                "version": "1.1.1",
                "layers": "Catastro",
                "srs_param": "SRS",
                "bbox": bbox_wgs84,
                "descripcion": "Plano catastral con parcelas"
            },
            "planeamiento_urbanistico": {
                "url": "https://www.idee.es/wms/IDEE-Planeamiento/IDEE-Planeamiento",
                "version": "1.3.0",
                "layers": "PlaneamientoGeneral",
                "srs_param": "CRS",
                "bbox": bbox_wms13,
                "descripcion": "Planeamiento urbanistico general"
            },
            "catastro_zonas_valor": {
                "url": "http://ovc.catastro.meh.es/Cartografia/WMS/ServidorWMS.aspx",
                "version": "1.1.1",
                "layers": "ZonasValor",
                "srs_param": "SRS",
                "bbox": bbox_wgs84,
                "descripcion": "Zonas de valor catastral"
            },
            "red_natura_2000": {
                "url": "https://wms.mapama.gob.es/sig/Biodiversidad/EENNPPZZ/wms.aspx",
                "version": "1.3.0",
                "layers": "RedNatura2000",
                "srs_param": "CRS",
                "bbox": bbox_wms13,
                "descripcion": "Espacios Red Natura 2000"
            },
            "dominio_publico_hidraulico": {
                "url": "https://servicios.idee.es/wms-inspire/hidrografia",
                "version": "1.3.0",
                "layers": "HY.PhysicalWaters.Waterbodies",
                "srs_param": "CRS",
                "bbox": bbox_wms13,
                "descripcion": "Hidrografia y zonas inundables"
            },
            "dominio_maritimo": {
                "url": "https://ideihm.covam.es/wms-c/mapas/Demarcaciones",
                "version": "1.3.0",
                "layers": "Demarcaciones",
                "srs_param": "CRS",
                "bbox": bbox_wms13,
                "descripcion": "Dominio publico maritimo-terrestre"
            },
            "montes_utilidad_publica": {
                "url": "https://wms.mapama.gob.es/sig/Biodiversidad/MUP/wms.aspx",
                "version": "1.3.0",
                "layers": "MUP",
                "srs_param": "CRS",
                "bbox": bbox_wms13,
                "descripcion": "Montes de Utilidad Publica"
            },
            "vias_pecuarias": {
                "url": "https://wms.mapama.gob.es/sig/Biodiversidad/ViaPecuaria/wms.aspx",
                "version": "1.3.0",
                "layers": "ViasPecuarias",
                "srs_param": "CRS",
                "bbox": bbox_wms13,
                "descripcion": "Vias pecuarias"
            },
        }
        
        capas_descargadas = []
        
        for nombre_capa, config in capas_disponibles.items():
            try:
                params = {
                    "SERVICE": "WMS",
                    "VERSION": config["version"],
                    "REQUEST": "GetMap",
                    "LAYERS": config["layers"],
                    "STYLES": "",
                    config["srs_param"]: "EPSG:4326",
                    "BBOX": config["bbox"],
                    "WIDTH": str(width),
                    "HEIGHT": str(height),
                    "FORMAT": "image/png",
                    "TRANSPARENT": "TRUE",
                }
                
                response = requests.get(config["url"], params=params, timeout=60)
                
                if response.status_code == 200 and len(response.content) > 1000:
                    if b'PNG' in response.content[:100] or b'JFIF' in response.content[:100]:
                        filename = f"{self.output_dir}/{ref}_afeccion_{nombre_capa}.png"
                        with open(filename, 'wb') as f:
                            f.write(response.content)
                        print(f"    Correcto - {config['descripcion']}: {filename}")
                        capas_descargadas.append({
                            "nombre": nombre_capa,
                            "descripcion": config["descripcion"],
                            "archivo": filename
                        })
                    else:
                        print(f"    Atencion - {config['descripcion']}: Sin datos en esta zona")
                else:
                    print(f"    Atencion - {config['descripcion']}: No disponible")
                    
            except Exception as e:
                print(f"    Atencion - {config['descripcion']}: Error - {str(e)[:50]}")
        
        if capas_descargadas:
            informe_file = f"{self.output_dir}/{ref}_afecciones_info.json"
            with open(informe_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "referencia": ref,
                    "capas_disponibles": capas_descargadas,
                    "total_capas": len(capas_descargadas)
                }, f, indent=2, ensure_ascii=False)
            print(f"\n  Informe de afecciones guardado: {informe_file}")
        
        return len(capas_descargadas) > 0

    def descargar_consulta_descriptiva_pdf(self, referencia):
        """Descarga el PDF oficial de consulta descriptiva"""
        ref = self.limpiar_referencia(referencia)
        del_code = ref[:2]
        mun_code = ref[2:5]
        
        url = f"https://www1.sedecatastro.gob.es/CYCBienInmueble/SECImprimirCroquisYDatos.aspx?del={del_code}&mun={mun_code}&refcat={ref}"
        filename = f"{self.output_dir}/{ref}_consulta_oficial.pdf"
        
        if os.path.exists(filename):
            print(f"  El PDF oficial ya existe")
            return True
        
        try:
            response = requests.get(url, timeout=30)
            if response.status_code == 200 and response.headers.get("Content-Type", "").startswith("application/pdf"):
                with open(filename, "wb") as f:
                    f.write(response.content)
                print(f"  PDF oficial descargado: {filename}")
                return True
            else:
                print(f"  PDF oficial fallo (Status {response.status_code})")
                return False
        except Exception as e:
            print(f"  Error descargando PDF: {e}")
            return False

    def extraer_coordenadas_gml(self, gml_file):
        """Extrae las coordenadas del poligono desde el archivo GML."""
        try:
            tree = ET.parse(gml_file)
            root = tree.getroot()
            coords = []
            for pos_list in root.findall(".//{http://www.opengis.net/gml/3.2}posList"):
                parts = pos_list.text.strip().split()
                for i in range(0, len(parts), 2):
                    if i + 1 < len(parts):
                         coords.append((float(parts[i]), float(parts[i + 1])))
            if not coords:
                for pos in root.findall(".//{http://www.opengis.net/gml/3.2}pos"):
                    parts = pos.text.strip().split()
                    if len(parts) >= 2:
                        coords.append((float(parts[0]), float(parts[1])))
            if coords:
                print(f"  Extraidas {len(coords)} coordenadas del GML")
                return coords
            print("  Atencion - No se encontraron coordenadas en el GML")
            return None
        except Exception as e:
            print(f"  Atencion - Error extrayendo coordenadas del GML: {e}")
            return None

    def convertir_coordenadas_a_pixel(self, coords, bbox, width, height):
        """Convierte coordenadas a pixeles de la imagen según BBOX WGS84."""
        try:
            minx, miny, maxx, maxy = [float(x) for x in bbox.split(",")]
            pixels = []
            LAT_RANGE, LON_RANGE = (36, 44), (-10, 5)

            for v1, v2 in coords:
                lat, lon = v1, v2
                if LAT_RANGE[0] <= v1 <= LAT_RANGE[1] and LON_RANGE[0] <= v2 <= LON_RANGE[1]: 
                     lat, lon = v1, v2
                elif LON_RANGE[0] <= v1 <= LON_RANGE[1] and LAT_RANGE[0] <= v2 <= LAT_RANGE[1]: 
                     lon, lat = v1, v2
                else: 
                     lat, lon = v1, v2

                x_norm = (lon - minx) / (maxx - minx) if maxx != minx else 0.5
                y_norm = (maxy - lat) / (maxy - miny) if maxy != miny else 0.5
                x = max(0, min(width - 1, int(x_norm * width)))
                y = max(0, min(height - 1, int(y_norm * height)))
                pixels.append((x, y))
            return pixels
        except Exception as e:
            print(f"  Atencion - Error convirtiendo coordenadas a pixeles: {e}")
            return None

    def dibujar_contorno_en_imagen(self, imagen_path, pixels, output_path, color=(255, 0, 0), width=4):
        """Dibuja el contorno de la parcela sobre una imagen existente."""
        if not PILLOW_AVAILABLE:
            print("  Atencion - Pillow no disponible, no se puede dibujar contorno")
            return False
        try:
            img = Image.open(imagen_path).convert("RGBA")
            overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)
            if len(pixels) > 2:
                if pixels[0] != pixels[-1]:
                    pixels = pixels + [pixels[0]]
                draw.line(pixels, fill=color + (255,), width=width)
            result = Image.alpha_composite(img, overlay).convert("RGB")
            result.save(output_path)
            print(f"  Contorno dibujado en {output_path}")
            return True
        except Exception as e:
            print(f"  Atencion - Error dibujando contorno: {e}")
            return False

    def superponer_contorno_parcela(self, ref, bbox_wgs84):
        """Superpone el contorno de la parcela sobre plano, ortofoto y composicion."""
        ref = self.limpiar_referencia(ref)
        gml_file = f"{self.output_dir}/{ref}_parcela.gml"
        if not os.path.exists(gml_file):
            print("  Atencion - No existe GML de parcela, no se puede dibujar contorno")
            return False
        coords = self.extraer_coordenadas_gml(gml_file)
        if not coords: return False
        exito = False
        imagenes = [
            (f"{self.output_dir}/{ref}_ortofoto_pnoa.jpg", f"{self.output_dir}/{ref}_ortofoto_pnoa_contorno.jpg"),
            (f"{self.output_dir}/{ref}_plano_catastro.png", f"{self.output_dir}/{ref}_plano_catastro_contorno.png"),
            (f"{self.output_dir}/{ref}_plano_con_ortofoto.png", f"{self.output_dir}/{ref}_plano_con_ortofoto_contorno.png"),
        ]
        for in_path, out_path in imagenes:
            if os.path.exists(in_path):
                try:
                    with Image.open(in_path) as img:
                        w, h = img.size
                    pixels = self.convertir_coordenadas_a_pixel(coords, bbox_wgs84, w, h)
                    if pixels and self.dibujar_contorno_en_imagen(in_path, pixels, out_path):
                        exito = True
                except Exception as e:
                    print(f"  Atencion - Error procesando imagen {in_path}: {e}")
        return exito

    def descargar_plano_ortofoto(self, referencia):
        """Descarga el plano con ortofoto usando servicios WMS y guarda geolocalizacion."""
        ref = self.limpiar_referencia(referencia)
        print("  Obteniendo coordenadas...")
        coords = self.obtener_coordenadas(ref)
        if not coords:
            print("  No se pudieron obtener coordenadas para generar el plano")
            return False
        lon, lat = coords["lon"], coords["lat"]
        bbox_wgs84 = self.calcular_bbox(lon, lat, buffer_metros=200)
        coords_list = bbox_wgs84.split(",")
        bbox_wms13 = f"{coords_list[1]},{coords_list[0]},{coords_list[3]},{coords_list[2]}"
        print("  Generando mapa con ortofoto...")
        wms_url = "http://ovc.catastro.meh.es/Cartografia/WMS/ServidorWMS.aspx"
        params = {
            "SERVICE": "WMS", "VERSION": "1.1.1", "REQUEST": "GetMap", "LAYERS": "Catastro",
            "STYLES": "", "SRS": "EPSG:4326", "BBOX": bbox_wgs84, "WIDTH": "1600", "HEIGHT": "1600",
            "FORMAT": "image/png", "TRANSPARENT": "FALSE",
        }
        try:
            response_catastro = requests.get(wms_url, params=params, timeout=60)
            plano_descargado = False
            filename_catastro = f"{self.output_dir}/{ref}_plano_catastro.png"
            if response_catastro.status_code == 200 and len(response_catastro.content) > 1000:
                with open(filename_catastro, "wb") as f:
                    f.write(response_catastro.content)
                print(f"  Plano catastral descargado: {filename_catastro}")
                plano_descargado = True
            
            ortofotos_descargadas = False
            try:
                wms_pnoa_url = "http://www.ign.es/wms-inspire/pnoa-ma"
                params_pnoa = {
                    "SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetMap", "LAYERS": "OI.OrthoimageCoverage",
                    "STYLES": "", "CRS": "EPSG:4326", "BBOX": bbox_wms13, "WIDTH": "1600", "HEIGHT": "1600", "FORMAT": "image/jpeg",
                }
                response_pnoa = requests.get(wms_pnoa_url, params=params_pnoa, timeout=60)
                if response_pnoa.status_code == 200 and len(response_pnoa.content) > 5000:
                    filename_ortofoto = f"{self.output_dir}/{ref}_ortofoto_pnoa.jpg"
                    with open(filename_ortofoto, "wb") as f:
                        f.write(response_pnoa.content)
                    print(f"  Ortofoto PNOA descargada: {filename_ortofoto}")
                    ortofotos_descargadas = True
                    if PILLOW_AVAILABLE and response_catastro.status_code == 200:
                        img_ortofoto = Image.open(BytesIO(response_pnoa.content))
                        img_catastro = Image.open(BytesIO(response_catastro.content))
                        resultado = Image.blend(img_ortofoto.convert("RGB"), img_catastro.convert("RGB"), alpha=0.6)
                        resultado.save(f"{self.output_dir}/{ref}_plano_con_ortofoto.png", "PNG")
                        print(f"  Composicion creada")
            except Exception as e:
                print(f"  Atencion - PNOA no disponible: {e}")

            geo_info = {
                "referencia": ref, "coordenadas": coords, "bbox": bbox_wgs84,
                "url_visor_catastro": f"https://www1.sedecatastro.gob.es/Cartografia/mapa.aspx?refcat={ref}",
                "url_google_maps": f"https://www.google.com/maps/search/?api=1&query={lat},{lon}",
                "url_google_earth": f"https://earth.google.com/web/@{lat},{lon},100a,500d,35y,0h,0t,0r",
            }
            with open(f"{self.output_dir}/{ref}_geolocalizacion.json", "w", encoding="utf-8") as f:
                json.dump(geo_info, f, indent=2, ensure_ascii=False)
            self.superponer_contorno_parcela(ref, bbox_wgs84)
            return plano_descargado
        except Exception as e:
            print(f"  Error descargando plano con ortofoto: {e}")
            return False

    def descargar_consulta_pdf(self, referencia):
        return self.descargar_consulta_descriptiva_pdf(referencia)

    def descargar_parcela_gml(self, referencia):
        """Descarga la geometria de la parcela en formato GML"""
        ref = self.limpiar_referencia(referencia)
        url = "http://ovc.catastro.meh.es/INSPIRE/wfsCP.aspx"
        params = {'service': 'wfs', 'version': '2.0.0', 'request': 'GetFeature', 'STOREDQUERY_ID': 'GetParcel', 'refcat': ref, 'srsname': 'EPSG:4326'}
        try:
            response = requests.get(url, params=params, timeout=30)
            if response.status_code == 200:
                if b'ExceptionReport' in response.content: return False
                with open(f"{self.output_dir}/{ref}_parcela.gml", 'wb') as f:
                    f.write(response.content)
                return True
            return False
        except: return False
    
    def descargar_edificio_gml(self, referencia):
        """Descarga la geometria del edificio en formato GML"""
        ref = self.limpiar_referencia(referencia)
        url = "http://ovc.catastro.meh.es/INSPIRE/wfsCP.aspx"
        params = {'service': 'wfs', 'version': '2.0.0', 'request': 'GetFeature', 'STOREDQUERY_ID': 'GetBuilding', 'refcat': ref, 'srsname': 'EPSG:4326'}
        try:
            response = requests.get(url, params=params, timeout=30)
            if response.status_code == 200 and b'ExceptionReport' not in response.content:
                with open(f"{self.output_dir}/{ref}_edificio.gml", 'wb') as f:
                    f.write(response.content)
                return True
            return False
        except: return False

    def descargar_todo(self, referencia, crear_zip=False):
        """Descarga todos los documentos para una referencia catastral."""
        print(f"\nProcesando referencia: {referencia}")
        ref = self.limpiar_referencia(referencia)
        ref_dir = Path(self.output_dir) / ref
        ref_dir.mkdir(exist_ok=True)
        old_dir, self.output_dir = self.output_dir, str(ref_dir)

        coords = self.obtener_coordenadas(ref)
        parcela_gml_descargado = self.descargar_parcela_gml(ref)
        gml_coords = self.extraer_coordenadas_gml(f"{self.output_dir}/{ref}_parcela.gml") if parcela_gml_descargado else None
        
        resultados = {
            'consulta_descriptiva': self.descargar_consulta_pdf(ref),
            'plano_ortofoto': self.descargar_plano_ortofoto(ref),
            'parcela_gml': parcela_gml_descargado, 
            'edificio_gml': self.descargar_edificio_gml(ref),
            'kml_generado': self.generar_kml(ref, coords, gml_coords) if coords else False,
            'capas_afecciones': self.descargar_capas_afecciones(ref, self.calcular_bbox(coords["lon"], coords["lat"])) if coords else False,
        }

        try:
            generador = GeneradorInformeCatastral(ref, self.output_dir)
            generador.cargar_datos()
            generador.generar_pdf(f"{self.output_dir}/{ref}_Informe_Analisis_Espacial.pdf")
            resultados['informe_pdf'] = True
        except: resultados['informe_pdf'] = False

        if crear_zip:
            resultados['zip_path'] = crear_zip_referencia(ref, old_dir)
            resultados['zip_generado'] = bool(resultados['zip_path'])
        
        self.output_dir = old_dir
        time.sleep(2)
        return resultados

    def procesar_lista(self, lista_referencias):
        """Procesa una lista de referencias catastrales"""
        for ref in lista_referencias:
            self.descargar_todo(ref)


from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from datetime import datetime

class GeneradorInformeCatastral:
    def __init__(self, referencia, directorio_datos):
        self.referencia = referencia
        self.directorio = directorio_datos
        self.styles = getSampleStyleSheet()
        self._crear_estilos_personalizados()
    
    def _crear_estilos_personalizados(self):
        self.styles.add(ParagraphStyle(name='TituloInforme', parent=self.styles['Heading1'], fontSize=18, textColor=colors.HexColor('#003366'), spaceAfter=12, alignment=TA_CENTER))
        self.styles.add(ParagraphStyle(name='Subtitulo', parent=self.styles['Heading2'], fontSize=14, textColor=colors.HexColor('#0066cc'), spaceAfter=8, spaceBefore=12))
        self.styles.add(ParagraphStyle(name='TextoNormal', parent=self.styles['Normal'], fontSize=10, alignment=TA_JUSTIFY, spaceAfter=6))
    
    def cargar_datos(self):
        with open(f"{self.directorio}/{self.referencia}_geolocalizacion.json", 'r', encoding='utf-8') as f:
            self.datos_geo = json.load(f)
        afecciones_file = f"{self.directorio}/{self.referencia}_afecciones_info.json" 
        self.datos_afecciones = json.load(open(afecciones_file, 'r', encoding='utf-8')) if os.path.exists(afecciones_file) else {'capas_disponibles': []}
    
    def generar_pdf(self, output_path):
        doc = SimpleDocTemplate(output_path, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
        elementos = []
        elementos.extend(self._crear_portada())
        elementos.extend(self._crear_datos_descriptivos())
        elementos.extend(self._crear_seccion_mapa())
        elementos.extend(self._crear_analisis_afectaciones())
        elementos.extend(self._crear_leyenda_anotaciones())
        doc.build(elementos)
    
    def _crear_portada(self):
        return [Paragraph(f"INFORME ANALISIS ESPACIAL<br/>Referencia Catastral {self.referencia}", self.styles['TituloInforme']), Spacer(1, 1*cm), Paragraph(f"<b>Fecha de generacion:</b> {datetime.now().strftime('%d/%m/%Y')}", self.styles['TextoNormal']), Spacer(1, 2*cm)]
    
    def _crear_datos_descriptivos(self):
        coords = self.datos_geo.get('coordenadas', {})
        datos_tabla = [['Referencia Catastral', self.referencia], ['Coordenadas (WGS84)', f"Lon: {coords.get('lon', 'N/A')}, Lat: {coords.get('lat', 'N/A')}"], ['BBOX', self.datos_geo.get('bbox', 'N/A')]]
        tabla = Table(datos_tabla, colWidths=[6*cm, 10*cm])
        tabla.setStyle(TableStyle([('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#e6f2ff')), ('GRID', (0, 0), (-1, -1), 0.5, colors.grey), ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, -1), 9)]))
        return [Paragraph("DATOS DESCRIPTIVOS", self.styles['Subtitulo']), tabla, Spacer(1, 1*cm)]
    
    def _crear_seccion_mapa(self):
        elementos = [Paragraph("REPRESENTACION CARTOGRAFICA", self.styles['Subtitulo'])]
        img_path = f"{self.directorio}/{self.referencia}_plano_con_ortofoto_contorno.png"
        if os.path.exists(img_path):
            elementos.append(RLImage(img_path, width=15*cm, height=15*cm))
        else:
            elementos.append(Paragraph("Imagen no disponible", self.styles['TextoNormal']))
        elementos.extend([Spacer(1, 0.5*cm), Paragraph("<b>LEYENDA:</b> Geometria de Analisis (contorno rojo)", self.styles['TextoNormal']), Spacer(1, 1*cm)])
        return elementos
    
    def _crear_analisis_afectaciones(self):
        elementos = [Paragraph("ANALISIS DE AFECTACION ESPACIAL", self.styles['Subtitulo'])]
        capas = self.datos_afecciones.get('capas_disponibles', [])
        if capas:
            for capa in capas:
                tabla = Table([['Tipologia', capa.get('nombre', 'N/A').upper()], ['Descripcion', capa.get('descripcion', 'N/A')]], colWidths=[4*cm, 12*cm])
                tabla.setStyle(TableStyle([('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#fff3cd')), ('GRID', (0, 0), (-1, -1), 0.5, colors.grey), ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold')]))
                elementos.extend([tabla, Spacer(1, 0.5*cm)])
        else:
            elementos.append(Paragraph("No se han detectado afecciones territoriales.", self.styles['TextoNormal']))
        return elementos
    
    def _crear_leyenda_anotaciones(self):
        texto = "<b>Normativa aplicable:</b> Directiva 92/43/CEE, Ley 42/2007, RD Legislativo 7/2015. El informe puede no ser exhaustivo."
        return [Paragraph("ANOTACIONES DEL INFORME", self.styles['Subtitulo']), Paragraph(texto, self.styles['TextoNormal'])]


import zipfile

def crear_zip_referencia(referencia, directorio_base):
    ref_limpia = referencia.replace(" ", "").strip()
    directorio_ref = f"{directorio_base}/{ref_limpia}"
    if not os.path.exists(directorio_ref): return None
    zip_filename = f"{directorio_base}/{ref_limpia}_completo.zip"
    try:
        with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, _, files in os.walk(directorio_ref):
                for file in files:
                    zipf.write(os.path.join(root, file), os.path.relpath(os.path.join(root, file), directorio_base))
        return zip_filename
    except: return None

def procesar_y_comprimir(referencia, directorio_base="descargas_catastro"):
    downloader = CatastroDownloader(output_dir=directorio_base)
    resultados = downloader.descargar_todo(referencia, crear_zip=True)
    return resultados.get('zip_path'), resultados
