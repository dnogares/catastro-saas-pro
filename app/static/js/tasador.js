// Dentro del objeto UI en tasador.js
async analizarCatastro() {
    const ref = document.getElementById('ref-input').value.toUpperCase();
    if (ref.length < 14) return alert("Referencia no válida");
    
    this.addLog(`🚀 Enviando consulta al servidor: ${ref}`);

    try {
        const formData = new FormData();
        formData.append('referencia', ref);

        const response = await fetch('http://localhost:8000/api/analizar-referencia', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (data.status === 'success') {
            // 1. Dibujar en el mapa
            MapViewer.drawParcel(data.geojson);
            
            // 2. Actualizar tarjeta de afecciones a la derecha
            this.actualizarPanelAfecciones(data.datos.zonas_afectadas);
            
            this.addLog(`✅ Análisis completado para ${ref}`);
        }
    } catch (error) {
        this.addLog(`❌ Error en el servidor: ${error.message}`);
    }
},

actualizarPanelAfecciones(afecciones) {
    const container = document.getElementById('afecciones-container');
    container.innerHTML = ""; // Limpiar
    
    afecciones.forEach(af => {
        const div = document.createElement('div');
        div.className = "widget-card mt-sm";
        div.style.borderLeft = "4px solid var(--color-danger)";
        div.innerHTML = `
            <div class="text-sm font-bold">${af.nota || 'Afección detectada'}</div>
            <div class="text-xs text-muted">Capa: ${af.capa || 'Normativa'}</div>
        `;
        container.appendChild(div);
    });
}
