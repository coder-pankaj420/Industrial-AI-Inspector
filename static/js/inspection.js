let file = null, current = null;
const MODELS = JSON.parse(document.getElementById("models-json").textContent);
const view = { s: 1, x: 0, y: 0 };
function applyView() { $$('.vp .layer').forEach(l => l.style.transform = `translate(${view.x}px,${view.y}px) scale(${view.s})`); }
function setupViewports() {
  $$('.vp').forEach(vp => {
    let drag = null;
    vp.addEventListener('wheel', e => { e.preventDefault(); zoom(e.deltaY < 0 ? 1.15 : 1 / 1.15, e, vp); }, { passive: false });
    vp.addEventListener('pointerdown', e => { drag = { x: e.clientX - view.x, y: e.clientY - view.y }; vp.classList.add('drag'); vp.setPointerCapture(e.pointerId); });
    vp.addEventListener('pointermove', e => { if (!drag) return; view.x = e.clientX - drag.x; view.y = e.clientY - drag.y; applyView(); });
    vp.addEventListener('pointerup', () => { drag = null; vp.classList.remove('drag'); });
  });
}
function zoom(f, e, vp) {
  const ns = Math.min(8, Math.max(1, view.s * f)); const k = ns / view.s;
  const r = (vp || $('.vp')).getBoundingClientRect(), cx = e ? e.clientX - r.left : r.width / 2, cy = e ? e.clientY - r.top : r.height / 2;
  view.x = cx - (cx - view.x) * k; view.y = cy - (cy - view.y) * k; view.s = ns;
  if (ns === 1) { view.x = view.y = 0; } applyView();
}
function pick(f) {
  const ext = f.name.split('.').pop().toLowerCase();
  if (!['jpg', 'jpeg', 'png'].includes(ext)) return toast('Unsupported file type. Use JPG, JPEG or PNG.', true);
  if (f.size > DEFAULTS.maxmb * 1048576) return toast(`File exceeds the ${DEFAULTS.maxmb} MB limit.`, true);
  file = f; const url = URL.createObjectURL(f), img = $('#prev-img');
  img.onload = () => { $('#finfo').textContent = `${f.name} · ${img.naturalWidth}×${img.naturalHeight}px · ${(f.size / 1024).toFixed(0)} KB · ${f.type}`; };
  img.src = url; $('#preview').style.display = 'block'; $('#drop').style.display = 'none'; $('#run').disabled = false;
}
function clearFile() { file = null; $('#file').value = ''; $('#preview').style.display = 'none'; $('#drop').style.display = 'block'; $('#run').disabled = true; }
const drop = $('#drop');
drop.onclick = () => $('#file').click(); drop.onkeydown = e => { if (e.key === 'Enter') $('#file').click(); };
$('#file').onchange = e => e.target.files[0] && pick(e.target.files[0]);
['dragover', 'dragenter'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add('over'); }));
['dragleave', 'drop'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove('over'); }));
drop.addEventListener('drop', e => e.dataTransfer.files[0] && pick(e.dataTransfer.files[0]));
$('#replace').onclick = () => $('#file').click(); $('#remove').onclick = clearFile;
$('#model').onchange = () => { const m = MODELS.find(x => x.key === $('#model').value); $('#model-note').textContent = m ? m.reason : ''; };
$('#model').onchange();

async function run(sampleKey, cat) {
  const fd = new FormData();
  fd.append('category', cat || $('#category').value); fd.append('model', $('#model').value); fd.append('mode', $('#mode').value);
  if (sampleKey) fd.append('sample', sampleKey); else { if (!file) return toast('Choose an image first', true); fd.append('image', file); }
  $('#placeholder').style.display = 'none'; $('#out').style.display = 'none'; $('#progress').style.display = 'block';
  $$('#run,.try').forEach(b => b.disabled = true);
  try { const j = await api('/api/inspect', { method: 'POST', body: fd }); render(j.inspection); history.replaceState(null, '', '?id=' + j.inspection.id); }
  catch (e) { toast(e.message, true); $('#placeholder').style.display = 'block'; }
  finally { $('#progress').style.display = 'none'; $$('.try').forEach(b => b.disabled = false); $('#run').disabled = !file; }
}
$('#run').onclick = () => run();
$$('.try').forEach(b => b.onclick = () => { $('#category').value = b.dataset.cat; run(b.dataset.key, b.dataset.cat); });

function render(r) {
  current = r; $('#out').style.display = 'grid'; $('#placeholder').style.display = 'none';
  const vcls = r.status === 'REVIEW REQUIRED' ? 'REVIEW' : r.status;
  $('#verdict').className = 'verdict v-' + vcls; $('#verdict').textContent = r.status;
  $('#kv').innerHTML = [['Anomaly score', r.anomaly_score.toFixed(3)], ['Defects', r.defect_count], ['Severity', r.severity], ['Time', r.processing_time + ' s'],
    ['Model', r.model_name], ['Category', r.category], ['Code', r.inspection_code]].map(([k, v]) => `<div><span>${k}</span><b style="font-size:${String(v).length > 14 ? '.8rem' : '1.1rem'}">${esc(v)}</b></div>`).join('');
  $('#modeline').innerHTML = `Inference mode: <b>${esc(r.inference_mode)}</b> · ${esc(r.created_at)} UTC · ${r.width}×${r.height}px working size`;
  $('#stages').innerHTML = (r.stages || []).map(s => `<span><span class="stage done"><i class="dot"></i>${esc(s.name)} <span class="muted">${s.ms} ms</span></span></span>`).join('');
  const ar = r.width / r.height;
  $$('.vp,.cmp').forEach(v => v.style.aspectRatio = ar);
  $$('.vp img').forEach(i => { i.style.objectFit = 'fill'; });
  $('#p-orig').src = $('#p-loc').src = $('#c-a').src = mediaUp(r.original_image);
  $('#p-heat').src = $('#p-annheat').src = $('#c-b').src = mediaPr(r.heatmap_image);
  $('#p-ann').src = mediaPr(r.annotated_image);
  $('#boxes').innerHTML = r.defects.map((d, i) => `<div class="box ${d.severity}" style="left:${d.x / r.width * 100}%;top:${d.y / r.height * 100}%;width:${d.width / r.width * 100}%;height:${d.height / r.height * 100}%"><span>#${i + 1} ${esc(d.defect_type)} · ${esc(d.severity)} (${d.x},${d.y})</span></div>`).join('');
  $('#boxes').style.display = $('#tg-box').checked ? 'block' : 'none';
  $('#dtable').innerHTML = r.defects.length ? r.defects.map((d, i) => `<tr title="${esc(d.description)}"><td>${i + 1}</td><td>${esc(d.defect_type)}</td><td>${badge(d.severity)}</td><td>${d.confidence}</td><td class="mono">${d.x},${d.y},${d.width},${d.height}</td></tr>`).join('') : '<tr><td colspan="5" class="empty">No localised defects.</td></tr>';
  $('#explain').innerHTML = esc(r.explanation || '').replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/(^|\s)_(.+?)_(\s|$)/g, '$1<i>$2</i>$3');
  $('#exsrc').textContent = r.explanation_source === 'gemini' ? 'Generated by Gemini' : 'Local template engine';
  $('#dl-heat').href = mediaPr(r.heatmap_image) + '?download=1'; $('#dl-ann').href = mediaPr(r.annotated_image) + '?download=1'; $('#dl-pdf').href = `/api/reports/${r.id}`;
  view.s = 1; view.x = view.y = 0; applyView(); window.currentInspection = r;
  $('#out').scrollIntoView({ behavior: 'smooth', block: 'start' });
}
$('#tg-box').onchange = e => $('#boxes').style.display = e.target.checked ? 'block' : 'none';
$('#tg-heat').oninput = e => $('#p-annheat').style.opacity = e.target.value / 100;
$('#zin').onclick = () => zoom(1.3); $('#zout').onclick = () => zoom(1 / 1.3); $('#zreset').onclick = () => { view.s = 1; view.x = view.y = 0; applyView(); };
$('#cmp-r').oninput = e => $('#c-b').style.clipPath = `inset(0 ${100 - e.target.value}% 0 0)`;
setupViewports();
const qid = new URLSearchParams(location.search).get('id');
if (qid) api('/api/inspections/' + encodeURIComponent(qid)).then(j => render(j.inspection)).catch(e => toast(e.message, true));
