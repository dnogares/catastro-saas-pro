@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Catastro GIS Pro - Visor Inteligente</title>
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
        <style>
            body { font-family: 'Segoe UI', sans-serif; margin: 0; display: flex; height: 100vh; background: #f0f2f5; }
            .panel-control { width: 400px; padding: 20px; overflow-y: auto; background: white; box-shadow: 2px 0 10px rgba(0,0,0,0.1); z-index: 1000; }
            #map { flex-grow: 1; height: 100%; }
            .card { background: #fafafa; border: 1px solid #eee; padding: 15px; border-radius: 8px; margin-bottom: 15px; }
            .btn { width: 100%; padding: 10px; border: none; border-radius: 4px; cursor: pointer; font-weight: bold; margin-top: 5px; }
            .btn-blue { background: #0056b3; color: white; }
            .btn-green { background: #28a745; color: white; }
            input { width: 100%; padding: 10px; box-sizing: border-box; margin: 10px 0; border: 1px solid #ddd; }
            .leaflet-control-layers { font-size: 14px; }
        </style>
    </head>
    <body>
        <div class="panel-control">
            <h2>🛠️ GIS Catastro Pro</h2>
            <div class="card">
                <label>Referencia Catastral:</label>
                <input type="text" id="ref" placeholder="Ej: 9812301XF4691S0001PI">
                <button class="btn btn-blue" onclick="analizarYMostrar()">Localizar y Analizar</button>
            </div>

            <div class="card">
                <label>Cargar KML/GeoJSON:</label>
                <input type="file" id="fileInput" accept=".kml,.geojson">
                <button class="btn btn-green" onclick="subirYVisualizar()">Superponer en Mapa</button>
            </div>

            <div id="resultados">
                <p style="color: #666;">Introduce una referencia para ver los datos y el solape geométrico.</p>
            </div>
        </div>

        <div id="map"></div>

        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <script>
            // Inicializar Mapa centrado en España
            const map = L.map('map').setView([40.4167, -3.7037], 6);

            // Capa 1: Satélite (PNOA)
            const pnoa = L.tileLayer.wms("https://www.ign.es/wms-inspire/pnoa-ma", {
                layers: 'OI.OrthoimageCoverage',
                format: 'image/png',
                transparent: false,
                attribution: "IGN"
            });

            // Capa 2: Catastro (WMS Oficial)
            const catastro = L.tileLayer.wms("https://ovc.catastro.meh.es/ovcservweb/OVCSWMS.asmx", {
                layers: 'Catastro',
                format: 'image/png',
                transparent: true,
                attribution: "Sede Electrónica del Catastro"
            }).addTo(map);

            L.control.layers({ "Satélite (PNOA)": pnoa, "Mapa Base": L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(map) }, 
                             { "Capa Catastral": catastro }).addTo(map);

            async function analizarYMostrar() {
                const ref = document.getElementById('ref').value;
                const response = await fetch('/api/analizar', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({referencia_catastral: ref})
                });
                const data = await response.json();
                
                if(data.status === 'success') {
                    const info = data.data.resultados;
                    // Mover el mapa a las coordenadas de la finca
                    if(info.lat && info.lon) {
                        map.setView([info.lat, info.lon], 18);
                        L.marker([info.lat, info.lon]).addTo(map)
                            .bindPopup(`<b>Ref: ${ref}</b><br><a href="${data.data.pdf_url}" target="_blank">Informe PDF</a>`)
                            .openPopup();
                    }
                    
                    document.getElementById('resultados').innerHTML = `
                        <div class="card" style="border-left: 5px solid #28a745;">
                            <h4>✅ Finca Localizada</h4>
                            <p>Superficie: ${info.superficie || 'Ver PDF'} m²</p>
                            <a href="${data.data.zip_url}">📦 Descargar ZIP completo</a>
                        </div>
                    `;
                }
            }

            // Aquí se integraría la lógica para dibujar el GeoJSON que devuelve Shapely
            async function subirYVisualizar() {
                alert("Archivo cargado. Procesando solape con Shapely...");
                // Aquí llamarías a api/upload-vector y usarías L.geoJSON(data).addTo(map)
            }
        </script>
    </body>
    </html>
    """
