const feed = document.querySelector('#feed');
const text = document.querySelector('#text');
const role = document.querySelector('#role');
const actor = document.querySelector('#actor');
const chat = document.querySelector('#chat');

function bubble(content, kind = 'bot', preview = false) {
  const el = document.createElement('div'); el.className = `bubble ${kind}${preview ? ' preview' : ''}`;
  el.textContent = content; feed.append(el); feed.scrollTop = feed.scrollHeight; return el;
}
async function state() {
  document.querySelector('#chat-label').textContent = chat.value;
  const r = await fetch(`/api/state?chat_id=${encodeURIComponent(chat.value)}`);
  document.querySelector('#state').textContent = JSON.stringify(await r.json(), null, 2);
}
async function ask() {
  const value = text.value.trim(); if (!value) return;
  bubble(`${actor.options[actor.selectedIndex].text}: ${value}`, 'user');
  const r = await fetch('/api/ask', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({chat_id: chat.value, user_id: actor.value, role: role.value, text: value, entry_point: 'mention'})});
  const data = await r.json(); const object = data.data?.deadline || data.data;
  const details = object?.title ? `\n${object.title} ${object.due_local || ''}${object.id ? ` · ID ${object.id}` : ''}` : '';
  const el = bubble(`${data.status}: ${data.message}${details}`, 'bot', data.status === 'preview');
  if (data.status === 'preview') { const b = document.createElement('button'); b.className = 'confirm'; b.textContent = 'Подтвердить действие'; b.onclick = () => confirmAction(data.data.pending_id); el.append(document.createElement('br'), b); }
  await state(); return data;
}
async function confirmAction(id) {
  const r = await fetch('/api/confirm', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({chat_id: chat.value, user_id: actor.value, role: role.value, pending_id: id, idempotency_key: `ui:${id}`})});
  const data = await r.json(); bubble(`${data.status}: ${data.message}`); await state();
}
document.querySelector('#send').onclick = ask;
document.querySelectorAll('[data-prompt]').forEach(b => b.onclick = () => { text.value = b.dataset.prompt; ask(); });
document.querySelector('#retrieve-other').onclick = () => { chat.value = 'demo-study-group'; actor.value = 'masha'; role.value = 'member'; text.value = '@gosha покажи дедлайны'; state(); ask(); };
document.querySelector('#prepare-correction').onclick = async () => {
  chat.value = 'demo-study-group'; actor.value = 'steward'; role.value = 'steward'; await state();
  const current = JSON.parse(document.querySelector('#state').textContent).deadlines.find(d => d.status === 'active');
  if (!current) { bubble('Сначала создайте и подтвердите дедлайн в основном чате.', 'bot'); return; }
  text.value = `@gosha исправь ${current.id} на 2026-08-21 19:00`; await ask();
};
document.querySelector('#cross-chat').onclick = () => { chat.value = 'demo-other-group'; actor.value = 'masha'; role.value = 'member'; text.value = '@gosha покажи дедлайны'; state(); ask(); };
chat.onchange = state; text.addEventListener('keydown', e => { if (e.key === 'Enter') ask(); }); state();
