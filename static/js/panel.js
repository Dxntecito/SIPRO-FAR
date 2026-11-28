/* ==========================================================================
   SIPRO-FAR HEYSEN — Lógica del Panel, Curva en Vivo 2027-2030 y Roles
   ========================================================================== */

let shewhartChart = null;
let sesgoChart = null;
let proyeccionAnualChart = null;
let liveTimer = null;

function canEditFarmacia() {
  const rol = document.body.dataset.userRol || '';
  return rol === 'FARMACEUTICO' || rol === 'DIGITADOR';
}

function switchTab(name) {
  document.querySelectorAll('.tab-pane').forEach(el => el.classList.add('hidden'));
  const target = document.getElementById('tab-' + name);
  if (target) target.classList.remove('hidden');

  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.classList.remove('border-teal-400', 'text-teal-300');
    btn.classList.add('border-transparent', 'text-slate-300');
  });

  const active = document.getElementById('btn-' + name);
  if (active) {
    active.classList.remove('border-transparent', 'text-slate-300');
    active.classList.add('border-teal-400', 'text-teal-300');
  }

  if (name === 'control') { loadKPIs(); loadShewhart(); }
  if (name === 'conciliacion' || name === 'orden') loadConciliacion();
  if (name === 'simulador') { runProyeccionAnual(); runSimulacion(); }
  if (name === 'sesgo') loadSesgo();
  if (name === 'farmacia') { loadInventario(); loadAlertas(); loadReporteSemanal(); }
}

function switchFarmSub(sub) {
  document.querySelectorAll('.sub-pane').forEach(el => el.classList.add('hidden'));
  document.getElementById('sub-' + sub).classList.remove('hidden');
  document.querySelectorAll('.sub-btn').forEach(b => {
    b.classList.remove('bg-[#0B3954]', 'text-white');
    b.classList.add('bg-white', 'text-slate-700');
  });
  const btn = document.getElementById('subbtn-' + sub);
  btn.classList.remove('bg-white', 'text-slate-700');
  btn.classList.add('bg-[#0B3954]', 'text-white');
}

async function loadKPIs() {
  const r = await fetch('/api/kpis');
  const k = await r.json();
  document.getElementById('kpi-disp').textContent = k.disponibilidad_petitorio_pct + '%';
  document.getElementById('kpi-lotes-sub').textContent = `${k.lotes_disponibles} disp. · ${k.lotes_criticos} crít. · ${k.lotes_agotados} agot.`;
  document.getElementById('kpi-subest').textContent = k.subestimacion_depts_pct + '%';
  document.getElementById('kpi-alertas').textContent = `${k.alertas_pendientes} pend.`;
  document.getElementById('kpi-busq-sub').textContent = `Consultas sin stock (7d): ${k.busquedas_sin_stock_7d} | Por vencer: ${k.lotes_por_vencer}`;
  document.getElementById('kpi-r2').textContent = (k.r2 * 100).toFixed(1) + '%';
  document.getElementById('kpi-mae').textContent = `Error promedio: ±${k.mape_pct}%`;
}

async function loadShewhart() {
  const med = document.getElementById('sel-med').value;
  const dep = document.getElementById('sel-dep').value;
  const anio = document.getElementById('sel-anio').value;
  const r = await fetch(`/api/shewhart?med_id=${med}&dep_id=${dep}&anio=${anio}`);
  const d = await r.json();

  document.getElementById('lbl-ucl').textContent = d.ucl_ultimo.toLocaleString() + ' u.';
  document.getElementById('lbl-mu').textContent = d.media_ultimo.toLocaleString() + ' u.';
  document.getElementById('lbl-lcl').textContent = d.lcl_ultimo.toLocaleString() + ' u.';

  const alDiv = document.getElementById('shewhart-alerts');
  if (!d.alertas_detectadas.length) {
    alDiv.innerHTML = `<div class="bg-emerald-50 border border-emerald-300 p-3 text-emerald-900 font-semibold">Consumo estable dentro de rangos normales durante ${anio}.</div>`;
  } else {
    alDiv.innerHTML = d.alertas_detectadas.map(a => `
      <div class="p-2.5 border-l-4 ${a.tipo.includes('3') ? 'border-rose-600 bg-rose-50 text-rose-900' : 'border-amber-600 bg-amber-50 text-amber-900'} border border-slate-200">
        <div class="font-bold">${a.mes} ${anio} · ${a.tipo}</div>
        <div>Consumo: <strong class="font-mono">${a.consumo.toLocaleString()}</strong> (Techo: ${a.limite.toLocaleString()})</div>
      </div>
    `).join('');
  }

  const ctx = document.getElementById('shewhartChart').getContext('2d');
  if (shewhartChart) shewhartChart.destroy();
  shewhartChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: d.labels,
      datasets: [
        { label: 'Consumo Real', data: d.consumo, borderColor: '#0B3954', backgroundColor: 'rgba(11,57,84,0.08)', borderWidth: 2.5, tension: 0.18, pointRadius: 4 },
        { label: 'Pedido del Servicio', data: d.pedido, borderColor: '#64748B', borderDash: [3, 3], borderWidth: 1.5, tension: 0.18, pointRadius: 2 },
        { label: 'Techo de Alerta (+3σ)', data: d.ucl, borderColor: '#B91C1C', borderDash: [6, 4], borderWidth: 1.8, pointRadius: 0 },
        { label: 'Promedio 12m', data: d.media, borderColor: '#0F766E', borderWidth: 1.5, pointRadius: 0 }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 11 } } } }
    }
  });
}

/* ─── SIMULADOR & CURVA EN VIVO 2027-2030 ─── */

function onSliderChange(labelId, val, suffix, decimals = 2) {
  document.getElementById(labelId).textContent = parseFloat(val).toFixed(decimals) + suffix;
  scheduleLiveUpdate();
}

function scheduleLiveUpdate(onlyCurve = false) {
  const badge = document.getElementById('sim-status-badge');
  badge.textContent = 'Recalculando...';
  badge.classList.remove('bg-teal-50', 'text-[#0F766E]');
  badge.classList.add('bg-amber-50', 'text-amber-800');

  clearTimeout(liveTimer);
  liveTimer = setTimeout(async () => {
    await runProyeccionAnual();
    if (!onlyCurve) await runSimulacion();
    badge.textContent = 'Actualizado en vivo';
    badge.classList.remove('bg-amber-50', 'text-amber-800');
    badge.classList.add('bg-teal-50', 'text-[#0F766E]');
  }, 220);
}

function getSimPayload() {
  return {
    anio_objetivo: parseInt(document.getElementById('sim-anio').value),
    departamento: document.getElementById('sim-dep').value,
    mes: parseInt(document.getElementById('sim-mes').value),
    medicamento_id: document.getElementById('sim-med-curva').value,
    nivel_dengue: parseFloat(document.getElementById('sim-dengue').value),
    evento_nino: parseFloat(document.getElementById('sim-nino').value),
    desembalse_almanzor: parseFloat(document.getElementById('sim-desemb').value),
    lluvia_mm: parseFloat(document.getElementById('sim-lluvia').value)
  };
}

async function runProyeccionAnual() {
  const payload = getSimPayload();
  const r = await fetch('/api/proyeccion-anual', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  const d = await r.json();

  document.getElementById('lbl-anio-sim').textContent = d.anio_objetivo;
  document.getElementById('lbl-curva-titulo').textContent = `Proyección ${d.anio_objetivo}: ${d.medicamento} (${d.departamento})`;
  document.getElementById('card-anual-u').textContent = `${d.total_anual_crisis.toLocaleString()} ${d.unidad}`;
  const vEl = document.getElementById('card-anual-var');
  vEl.textContent = `${d.variacion_anual_pct >= 0 ? '+' : ''}${d.variacion_anual_pct}% respecto a un año normal`;
  vEl.className = 'text-[11px] font-semibold mt-0.5 ' + (d.variacion_anual_pct > 5 ? 'text-rose-700' : 'text-emerald-700');

  document.getElementById('card-mes-pico').textContent = d.mes_pico;
  document.getElementById('card-val-pico').textContent = `Pico estimado: ${d.valor_pico.toLocaleString()} ${d.unidad}`;
  document.getElementById('card-costo-anual').textContent = 'S/ ' + d.costo_anual_crisis.toLocaleString('es-PE', { minimumFractionDigits: 2 });
  document.getElementById('card-meses-3s').textContent = `Meses en alerta crítica (+3σ): ${d.meses_en_alerta_3s} de 12`;

  if (proyeccionAnualChart) {
    // Actualización suave sin destruir el canvas (la curva se mueve en vivo!)
    proyeccionAnualChart.data.labels = d.labels;
    proyeccionAnualChart.data.datasets[0].label = `Demanda Proyectada ${d.anio_objetivo}`;
    proyeccionAnualChart.data.datasets[0].data = d.demanda_crisis;
    proyeccionAnualChart.data.datasets[1].label = `Escenario Normal ${d.anio_objetivo}`;
    proyeccionAnualChart.data.datasets[1].data = d.demanda_normal;
    proyeccionAnualChart.data.datasets[2].data = d.ucl_3sigma;
    proyeccionAnualChart.update();
  } else {
    const ctx = document.getElementById('proyeccionAnualChart').getContext('2d');
    proyeccionAnualChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: d.labels,
        datasets: [
          { label: `Demanda Proyectada ${d.anio_objetivo}`, data: d.demanda_crisis, borderColor: '#B91C1C', backgroundColor: 'rgba(185,28,28,0.10)', borderWidth: 2.6, fill: true, tension: 0.22, pointRadius: 4, pointHoverRadius: 6 },
          { label: `Escenario Normal ${d.anio_objetivo}`, data: d.demanda_normal, borderColor: '#0B3954', borderDash: [5, 4], borderWidth: 2, tension: 0.22, pointRadius: 3 },
          { label: 'Techo de Alerta (+3σ)', data: d.ucl_3sigma, borderColor: '#D97706', borderDash: [3, 3], borderWidth: 1.5, pointRadius: 0 }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 420 },
        interaction: { mode: 'index', intersect: false },
        plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 11 } } } }
      }
    });
  }
}

async function runSimulacion() {
  const payload = getSimPayload();
  const r = await fetch('/api/simular', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  const d = await r.json();

  document.getElementById('tbody-simulador').innerHTML = d.items.map(x => {
    const al = x.control_3sigma;
    const badge = al.nivel_alerta === 'ROJO'
      ? 'bg-rose-100 text-rose-900 border border-rose-400'
      : (al.nivel_alerta === 'AMBAR' ? 'bg-amber-100 text-amber-900 border border-amber-400' : 'bg-emerald-100 text-emerald-900 border border-emerald-400');
    return `
      <tr class="hover:bg-slate-50">
        <td class="p-2 border border-slate-200 font-semibold">${x.medicamento}</td>
        <td class="p-2 text-right font-mono border border-slate-200">${x.demanda_base_normal.toLocaleString()}</td>
        <td class="p-2 text-right font-mono font-bold text-[#0B3954] border border-slate-200">${x.demanda_proyectada_crisis.toLocaleString()}</td>
        <td class="p-2 text-right font-mono font-bold ${x.variacion_crisis_pct > 0 ? 'text-rose-700' : 'text-emerald-700'} border border-slate-200">${x.variacion_crisis_pct > 0 ? '+' : ''}${x.variacion_crisis_pct}%</td>
        <td class="p-2 text-right font-mono border border-slate-200">${(x.stock_actual || 0).toLocaleString()}</td>
        <td class="p-2 text-right font-mono font-bold text-[#0F766E] border border-slate-200">${x.requerimiento_sugerido.toLocaleString()}</td>
        <td class="p-2 text-right font-mono border border-slate-200">S/ ${x.costo_estimado_soles.toLocaleString('es-PE', { minimumFractionDigits: 2 })}</td>
        <td class="p-2 text-center border border-slate-200"><span class="px-2 py-0.5 text-[10px] font-bold ${badge}">${al.nivel_alerta}</span></td>
      </tr>`;
  }).join('');
}

async function loadConciliacion() {
  const mes = document.getElementById('sel-mes-conc').value;
  const r = await fetch(`/api/conciliacion?mes=${mes}`);
  const d = await r.json();

  document.getElementById('conc-tot-depts').textContent = 'S/ ' + d.total_depts_pen.toLocaleString('es-PE', { minimumFractionDigits: 2 });
  document.getElementById('conc-tot-ia').textContent = 'S/ ' + d.total_sugerido_pen.toLocaleString('es-PE', { minimumFractionDigits: 2 });
  document.getElementById('conc-tot-brecha').textContent = 'S/ ' + d.brecha_total_pen.toLocaleString('es-PE', { minimumFractionDigits: 2 });

  document.getElementById('tbody-conciliacion').innerHTML = d.items.map(x => `
    <tr class="hover:bg-slate-50">
      <td class="p-2 border border-slate-200 font-semibold">${x.medicamento}</td>
      <td class="p-2 text-right font-mono border border-slate-200">${x.suma_depts.toLocaleString()}</td>
      <td class="p-2 text-right font-mono font-bold text-[#0B3954] border border-slate-200">${x.demanda_ia.toLocaleString()}</td>
      <td class="p-2 text-right font-mono border border-slate-200">${x.stock_seguridad.toLocaleString()}</td>
      <td class="p-2 text-right font-mono font-bold text-[#0F766E] border border-slate-200">${x.req_sugerido.toLocaleString()}</td>
      <td class="p-2 text-right font-mono font-bold text-rose-700 border border-slate-200">${x.subestimacion_pct}%</td>
      <td class="p-2 text-right font-mono border border-slate-200">S/ ${x.brecha_pen.toLocaleString('es-PE', { minimumFractionDigits: 2 })}</td>
      <td class="p-2 text-center border border-slate-200">
        <span class="px-2 py-0.5 text-[10px] font-bold uppercase ${x.riesgo === 'CRÍTICO' ? 'bg-rose-100 text-rose-900 border border-rose-400' : 'bg-amber-100 text-amber-900 border border-amber-400'}">${x.riesgo}</span>
      </td>
    </tr>
  `).join('');

  document.getElementById('tbody-orden').innerHTML = d.items.map(x => `
    <tr>
      <td class="p-2 font-mono border border-slate-300">${x.medicamento_id}</td>
      <td class="p-2 border border-slate-300">${x.medicamento}</td>
      <td class="p-2 text-center border border-slate-300">${x.unidad}</td>
      <td class="p-2 text-right font-mono font-bold border border-slate-300">${x.req_sugerido.toLocaleString()}</td>
      <td class="p-2 text-right font-mono border border-slate-300">${x.costo_unitario.toFixed(2)}</td>
      <td class="p-2 text-right font-mono font-bold border border-slate-300">${x.total_sugerido_pen.toLocaleString('es-PE', { minimumFractionDigits: 2 })}</td>
    </tr>
  `).join('');
  document.getElementById('orden-total').textContent = 'S/ ' + d.total_sugerido_pen.toLocaleString('es-PE', { minimumFractionDigits: 2 });
}

async function loadSesgo() {
  const r = await fetch('/api/sesgo');
  const rows = await r.json();
  document.getElementById('tbody-sesgo').innerHTML = rows.map(x => `
    <tr>
      <td class="p-2.5 font-semibold border border-slate-200">${x.departamento}</td>
      <td class="p-2.5 text-right font-mono border border-slate-200">${x.total_pedido.toLocaleString()}</td>
      <td class="p-2.5 text-right font-mono border border-slate-200">${x.total_consumo.toLocaleString()}</td>
      <td class="p-2.5 text-right font-mono font-bold text-rose-700 border border-slate-200">${x.sesgo_vs_demanda_pct}%</td>
    </tr>
  `).join('');

  const ctx = document.getElementById('sesgoChart').getContext('2d');
  if (sesgoChart) sesgoChart.destroy();
  sesgoChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: rows.map(r => r.departamento),
      datasets: [{ label: 'Subestimación (%)', data: rows.map(r => Math.abs(r.sesgo_vs_demanda_pct)), backgroundColor: '#B91C1C' }]
    },
    options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } } }
  });
}

async function loadInventario() {
  const editable = canEditFarmacia();
  const r = await fetch('/api/inventario');
  const rows = await r.json();
  document.getElementById('tbody-inventario').innerHTML = rows.map(x => {
    const badge = x.estado_stock === 'DISPONIBLE'
      ? 'bg-emerald-100 text-emerald-900 border border-emerald-400'
      : (x.estado_stock === 'AGOTADO' ? 'bg-rose-100 text-rose-900 border border-rose-400' : 'bg-amber-100 text-amber-900 border border-amber-400');

    if (editable) {
      return `
        <tr class="hover:bg-slate-50">
          <td class="p-2 border border-slate-200"><span class="font-mono font-bold text-[#0B3954]">${x.codigo_lote}</span><br><span class="text-[11px] text-slate-600">${x.medicamento}</span></td>
          <td class="p-2 border border-slate-200">${x.departamento}</td>
          <td class="p-2 border border-slate-200 text-right"><input id="st-${x.lote_id}" type="number" min="0" value="${x.stock_actual}" class="w-20 px-1.5 py-1 border border-slate-400 text-right font-mono"></td>
          <td class="p-2 border border-slate-200 text-right"><input id="sm-${x.lote_id}" type="number" min="0" value="${x.stock_minimo}" class="w-20 px-1.5 py-1 border border-slate-400 text-right font-mono"></td>
          <td class="p-2 border border-slate-200 text-center"><input id="fv-${x.lote_id}" type="date" value="${x.fecha_vencimiento}" class="px-1.5 py-1 border border-slate-400 font-mono text-[11px]"></td>
          <td class="p-2 border border-slate-200 text-center"><span class="px-2 py-0.5 text-[10px] font-bold uppercase ${badge}">${x.estado_stock}</span></td>
          <td class="p-2 border border-slate-200 text-center"><button onclick="saveLote(${x.lote_id}, '${x.gestion_vencimiento}')" class="bg-[#0F766E] hover:bg-teal-800 text-white text-[11px] font-bold px-2.5 py-1">Guardar</button></td>
        </tr>`;
    }
    return `
      <tr class="hover:bg-slate-50">
        <td class="p-2 border border-slate-200"><span class="font-mono font-bold text-[#0B3954]">${x.codigo_lote}</span><br><span class="text-[11px] text-slate-600">${x.medicamento}</span></td>
        <td class="p-2 border border-slate-200">${x.departamento}</td>
        <td class="p-2 border border-slate-200 text-right font-mono font-bold">${x.stock_actual.toLocaleString()}</td>
        <td class="p-2 border border-slate-200 text-right font-mono text-slate-500">${x.stock_minimo.toLocaleString()}</td>
        <td class="p-2 border border-slate-200 text-center font-mono text-[11px]">${x.fecha_vencimiento}</td>
        <td class="p-2 border border-slate-200 text-center"><span class="px-2 py-0.5 text-[10px] font-bold uppercase ${badge}">${x.estado_stock}</span></td>
      </tr>`;
  }).join('');
}

async function saveLote(loteId, gestVenc) {
  const payload = {
    stock_actual: parseInt(document.getElementById('st-' + loteId).value || 0),
    stock_minimo: parseInt(document.getElementById('sm-' + loteId).value || 50),
    fecha_vencimiento: document.getElementById('fv-' + loteId).value,
    gestion_vencimiento: gestVenc
  };
  await fetch('/api/inventario/' + loteId, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  const toast = document.getElementById('crud-toast');
  toast.classList.remove('hidden');
  setTimeout(() => toast.classList.add('hidden'), 2200);
  loadInventario();
}

async function loadAlertas() {
  const editable = canEditFarmacia();
  const r = await fetch('/api/alertas');
  const rows = await r.json();
  document.getElementById('tbody-alertas').innerHTML = rows.map(a => `
    <tr>
      <td class="p-2 border border-slate-200"><strong>${a.medicamento}</strong><br><span class="text-[10px] text-slate-500">${a.departamento}</span></td>
      <td class="p-2 text-center border border-slate-200"><span class="px-1.5 py-0.5 text-[10px] font-bold ${a.nivel === 'ROJO' ? 'bg-rose-100 text-rose-900 border border-rose-400' : 'bg-amber-100 text-amber-900 border border-amber-400'}">${a.tipo_alerta}</span></td>
      <td class="p-2 border border-slate-200 text-[11px] text-slate-700">${a.mensaje}</td>
      <td class="p-2 text-center border border-slate-200 font-bold text-[10px]">${a.estado}</td>
      ${editable ? `<td class="p-2 text-center border border-slate-200">
        ${a.estado === 'PENDIENTE'
          ? `<button onclick="atenderAlerta(${a.alerta_id})" class="bg-[#0B3954] hover:bg-slate-800 text-white text-[10px] font-bold px-2.5 py-1">Atender</button>`
          : `<span class="text-[10px] text-emerald-700 font-semibold">✓ Atendida</span>`}
      </td>` : ''}
    </tr>
  `).join('');
}

async function atenderAlerta(id) {
  await fetch(`/api/alertas/${id}/atender`, { method: 'POST' });
  loadAlertas();
}

async function loadReporteSemanal() {
  const r = await fetch('/api/reporte-semanal');
  const d = await r.json();
  document.getElementById('tbody-reporte-sem').innerHTML = d.ranking.map(x => `
    <tr>
      <td class="p-2 font-mono font-bold border border-slate-200">${x.medicamento_id}</td>
      <td class="p-2 border border-slate-200 font-semibold">${x.medicamento}</td>
      <td class="p-2 text-right font-mono font-bold text-rose-700 border border-slate-200">${x.total_busquedas}</td>
      <td class="p-2 text-right text-[11px] text-slate-500 border border-slate-200">${x.ultima_busqueda}</td>
    </tr>
  `).join('');
}

document.addEventListener('DOMContentLoaded', () => {
  if (canEditFarmacia()) {
    loadInventario();
    loadAlertas();
    loadReporteSemanal();
  } else {
    loadKPIs();
    loadShewhart();
  }
});
