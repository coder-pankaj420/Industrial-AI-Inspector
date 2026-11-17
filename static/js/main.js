const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(url, opts = {}) {
  let r; try { r = await fetch(url, opts); } catch (e) { throw new Error('Cannot reach the server'); }
  let j = {}; try { j = await r.json(); } catch (e) {}
  if (!r.ok || j.ok === false) throw new Error(j.error || `Request failed (${r.status})`);
  return j;
}
function toast(msg, err) {
  const t = document.createElement('div'); t.className = 'toast' + (err ? ' err' : ''); t.textContent = msg;
  document.body.appendChild(t); setTimeout(() => t.remove(), 4200);
}
function confirmDialog(title, text, yesLabel = 'Delete') {
  return new Promise(res => {
    $('#modal-title').textContent = title; $('#modal-text').textContent = text; $('#modal-yes').textContent = yesLabel;
    const m = $('#modal'); m.classList.add('show');
    const done = v => { m.classList.remove('show'); res(v); };
    $('#modal-yes').onclick = () => done(true); $('#modal-no').onclick = () => done(false);
  });
}
const badge = (v, cls) => `<span class="badge b-${esc(cls || (v === 'REVIEW REQUIRED' ? 'REVIEW' : v))}">${esc(v)}</span>`;
const fmtDate = s => s ? s.replace(' ', ' · ').slice(0, 18) : '';
const mediaUp = n => `/media/uploads/${n}`, mediaPr = n => `/media/processed/${n}`;
$('#menu-btn')?.addEventListener('click', () => $('#sidebar').classList.toggle('open'));
$('#bell')?.addEventListener('click', () => $('#pop').classList.toggle('show'));
(async () => {
  if (!$('#sys-dot')) return;
  try {
    const h = await api('/api/health'); $('#sys-dot').classList.add('on');
    $('#sys-text').textContent = `System ${h.status} · ${h.llm.active === 'gemini' ? 'Gemini' : 'local explainer'}`;
    const f = await api('/api/inspections?status=FAIL&per_page=5');
    if (f.total) { $('#bell-n').style.display = 'inline'; $('#bell-n').textContent = f.total; }
    $('#pop-body').innerHTML = f.inspections.length ? f.inspections.map(i => `<div style="padding:.3rem 0"><a href="/inspection?id=${i.id}">${esc(i.inspection_code)}</a> ${badge(i.status)} <span class="muted">${esc(i.category)}</span></div>`).join('') : 'No failed inspections.';
  } catch (e) { $('#sys-text').textContent = 'System offline'; }
})();
