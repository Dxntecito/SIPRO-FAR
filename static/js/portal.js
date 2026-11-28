/* ==========================================================================
   SIPRO-FAR HEYSEN — Lógica del Portal Público de Transparencia de Stock
   ========================================================================== */

function badgeClass(estado) {
  if (estado === 'DISPONIBLE') return 'bg-emerald-100 text-emerald-900 border border-emerald-400';
  if (estado === 'AGOTADO') return 'bg-rose-100 text-rose-900 border border-rose-400';
  return 'bg-amber-100 text-amber-900 border border-amber-400';
}

async function buscarStock(q = '', receta = '') {
  const params = new URLSearchParams();
  if (q) params.set('q', q);
  if (receta) params.set('receta', receta);

  const container = document.getElementById('results-container');
  try {
    const res = await fetch('/api/publico/buscar?' + params.toString());
    const data = await res.json();

    const alertBox = document.getElementById('alert-sin-stock');
    if (data.registrado_sin_stock) alertBox.classList.remove('hidden');
    else alertBox.classList.add('hidden');

    document.getElementById('count-items').textContent = data.items.length;

    if (!data.items.length) {
      container.innerHTML = `
        <div class="bg-white border border-rose-300 p-6 text-center">
          <p class="text-sm font-bold text-rose-800">No se encontró "${q}" en el petitorio crítico con stock disponible.</p>
          <p class="text-xs text-slate-600 mt-1">La búsqueda fue registrada automáticamente para el reporte semanal de Farmacia.</p>
        </div>`;
      return;
    }

    container.innerHTML = data.items.map(item => `
      <div class="bg-white border border-slate-300">
        <div class="px-4 py-3 bg-slate-50 border-b border-slate-200 flex flex-wrap justify-between items-center gap-3">
          <div>
            <div class="flex items-center gap-2">
              <span class="font-mono text-xs font-bold bg-[#0B3954] text-white px-2 py-0.5">${item.medicamento_id}</span>
              <h4 class="font-bold text-sm text-slate-900">${item.nombre}</h4>
            </div>
            <p class="text-xs text-slate-500 mt-0.5">${item.categoria} · Unidad: ${item.unidad}</p>
          </div>
          <div class="flex items-center gap-4">
            <div class="text-right">
              <span class="block text-[10px] uppercase font-bold text-slate-500">Stock Hospital</span>
              <span class="font-mono text-sm font-bold text-slate-900">${item.stock_total.toLocaleString()} ${item.unidad}</span>
            </div>
            <span class="px-2.5 py-1 text-xs font-bold uppercase ${badgeClass(item.estado_general)}">${item.estado_general}</span>
          </div>
        </div>
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 divide-y sm:divide-y-0 sm:divide-x divide-slate-200 text-xs">
          ${item.detalle_areas.map(a => `
            <div class="p-3 flex flex-col justify-between">
              <span class="font-semibold text-slate-700 leading-tight">${a.departamento}</span>
              <div class="mt-2 flex items-center justify-between">
                <span class="font-mono font-bold text-slate-900">${a.stock_actual.toLocaleString()} u.</span>
                <span class="px-1.5 py-0.5 text-[10px] font-bold uppercase ${badgeClass(a.estado_stock)}">${a.estado_stock}</span>
              </div>
            </div>
          `).join('')}
        </div>
      </div>
    `).join('');
  } catch (err) {
    container.innerHTML = `
      <div class="bg-rose-50 border border-rose-300 p-4 text-xs text-rose-900">
        Error al consultar el servidor. Verifique la conexión a MySQL.
      </div>`;
  }
}

function resetSearch() {
  document.getElementById('input-q').value = '';
  document.getElementById('input-receta').value = '';
  buscarStock();
}

document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('search-form');
  if (form) {
    form.addEventListener('submit', e => {
      e.preventDefault();
      buscarStock(
        document.getElementById('input-q').value.trim(),
        document.getElementById('input-receta').value.trim()
      );
    });
  }
  buscarStock();
});
