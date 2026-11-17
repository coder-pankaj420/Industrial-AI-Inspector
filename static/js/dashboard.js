const COL = ['#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8b5cf6', '#06b6d4', '#ec4899', '#84cc16'];
const charts = {};
Chart.defaults.color = '#94A3B8'; Chart.defaults.borderColor = 'rgba(148,163,184,.15)'; Chart.defaults.maintainAspectRatio = false;
function draw(id, type, labels, datasets, opts = {}) {
  charts[id]?.destroy();
  charts[id] = new Chart($('#' + id), { type, data: { labels, datasets }, options: { plugins: { legend: { display: ['pie', 'doughnut'].includes(type) || datasets.length > 1, position: 'bottom' } }, ...opts } });
}
async function load() {
  const a = await api('/api/analytics');
  $('#m-total').textContent = a.total; $('#m-pass').textContent = a.passed; $('#m-fail').textContent = a.total - a.passed;
  $('#m-def').textContent = a.defects; $('#m-time').textContent = a.total ? a.avg_time + ' s' : '–';
  $('#dash-empty').style.display = a.total ? 'none' : 'block';
  const sc = { y: { beginAtZero: true, ticks: { precision: 0 } } };
  draw('c-time', 'line', a.daily.map(d => d.date), [
    { label: 'Inspections', data: a.daily.map(d => d.total), borderColor: COL[0], backgroundColor: 'rgba(59,130,246,.15)', fill: true, tension: .35 },
    { label: 'Flagged', data: a.daily.map(d => d.flagged), borderColor: COL[3], tension: .35 }], { scales: sc });
  draw('c-pf', 'pie', ['Pass', 'Fail', 'Review'], [{ data: [a.passed, a.failed, a.review], backgroundColor: [COL[1], COL[3], COL[2]], borderWidth: 0 }]);
  const dt = Object.entries(a.defect_types);
  draw('c-def', 'doughnut', dt.map(x => x[0]), [{ data: dt.map(x => x[1]), backgroundColor: COL, borderWidth: 0 }]);
  const sv = ['None', 'Low', 'Medium', 'High'];
  draw('c-sev', 'bar', sv, [{ data: sv.map(s => a.severity[s] || 0), backgroundColor: ['#64748b', COL[0], COL[2], COL[3]], borderRadius: 6 }], { scales: sc });
  const ct = Object.entries(a.category_counts);
  draw('c-cat', 'bar', ct.map(x => x[0]), [{ data: ct.map(x => x[1]), backgroundColor: COL[4], borderRadius: 6 }], { scales: sc, indexAxis: 'y' });
  const r = await api('/api/inspections?per_page=8');
  $('#recent').innerHTML = r.inspections.length ? r.inspections.map(i => `<tr><td class="mono">${esc(i.inspection_code)}</td><td>${esc(i.category)}</td>
    <td><img class="thumb" src="${mediaUp(i.original_image)}" alt=""></td><td>${fmtDate(i.created_at)}</td><td>${badge(i.status)}</td><td>${i.defect_count}</td>
    <td>${badge(i.severity)}</td><td><a class="btn sm" href="/inspection?id=${i.id}">View</a></td></tr>`).join('') : '<tr><td colspan="8" class="empty">No inspections yet.</td></tr>';
}
if ($("#m-total")) load().catch(e => toast(e.message, true));
