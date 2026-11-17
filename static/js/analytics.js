async function loadA() {
  const p = new URLSearchParams(); if ($('#df').value) p.set('date_from', $('#df').value); if ($('#dt').value) p.set('date_to', $('#dt').value);
  const a = await api('/api/analytics?' + p);
  $('#k-total').textContent = a.total; $('#k-rate').textContent = a.total ? Math.round(a.passed / a.total * 100) + '%' : '–';
  $('#k-time').textContent = a.total ? a.avg_time + ' s' : '–'; $('#k-score').textContent = a.total ? a.avg_score : '–';
  $('#a-empty').style.display = a.total ? 'none' : 'block';
  const sc = { y: { beginAtZero: true, ticks: { precision: 0 } } }, kv = o => [Object.keys(o), Object.values(o)];
  draw('a-daily', 'bar', a.daily.map(d => d.date), [{ label: 'Inspections', data: a.daily.map(d => d.total), backgroundColor: COL[0], borderRadius: 5 }, { label: 'Flagged', data: a.daily.map(d => d.flagged), backgroundColor: COL[3], borderRadius: 5 }], { scales: sc });
  draw('a-weekly', 'line', a.weekly.map(d => d.week), [{ label: 'Inspections', data: a.weekly.map(d => d.total), borderColor: COL[0], tension: .3 }, { label: 'Flagged', data: a.weekly.map(d => d.flagged), borderColor: COL[3], tension: .3 }], { scales: sc });
  let [l, v] = kv(a.defects_by_category); draw('a-catdef', 'bar', l, [{ data: v, backgroundColor: COL[4], borderRadius: 5 }], { scales: sc });
  [l, v] = kv(a.defect_types); draw('a-types', 'bar', l, [{ data: v, backgroundColor: COL[2], borderRadius: 5 }], { scales: sc, indexAxis: 'y' });
  [l, v] = kv(a.severity); draw('a-sev', 'doughnut', l, [{ data: v, backgroundColor: COL, borderWidth: 0 }]);
  draw('a-pf', 'pie', ['Pass', 'Fail', 'Review'], [{ data: [a.passed, a.failed, a.review], backgroundColor: [COL[1], COL[3], COL[2]], borderWidth: 0 }]);
  [l, v] = kv(a.model_usage); draw('a-model', 'bar', l, [{ data: v, backgroundColor: COL[5], borderRadius: 5 }], { scales: sc });
}
$('#apply').onclick = () => loadA().catch(e => toast(e.message, true));
$('#clear').onclick = () => { $('#df').value = $('#dt').value = ''; loadA(); };
loadA().catch(e => toast(e.message, true));
