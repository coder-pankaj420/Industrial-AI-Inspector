const QS = ['What defects were detected?', 'Why did this component fail?', 'Which region is most suspicious?', 'What should be inspected next?', 'Compare this inspection with the previous one.', 'Explain the anomaly heatmap.'];
$('#chips').innerHTML = QS.map(q => `<button type="button" class="chip">${q}</button>`).join('');
async function ask(q) {
  if (!window.currentInspection) return toast('Run or open an inspection first', true);
  const chat = $('#chat'); chat.insertAdjacentHTML('beforeend', `<div class="msg u">${esc(q)}</div>`); chat.scrollTop = chat.scrollHeight;
  try {
    const j = await api('/api/assistant', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question: q, inspection_id: window.currentInspection.id }) });
    chat.insertAdjacentHTML('beforeend', `<div class="msg a">${esc(j.answer)}<div class="small muted">${j.source === 'gemini' ? 'Gemini' : 'Local engine'}</div></div>`);
  } catch (e) { chat.insertAdjacentHTML('beforeend', `<div class="msg a">Error: ${esc(e.message)}</div>`); }
  chat.scrollTop = chat.scrollHeight;
}
$$('#chips .chip').forEach(c => c.onclick = () => ask(c.textContent));
$('#chat-form').onsubmit = e => { e.preventDefault(); const v = $('#chat-in').value.trim(); if (v) { $('#chat-in').value = ''; ask(v); } };
