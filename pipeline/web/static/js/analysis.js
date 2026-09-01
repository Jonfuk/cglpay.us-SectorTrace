const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const get = async path => { const response = await fetch(path); if (!response.ok) throw new Error(await response.text()); return response.json(); };
const row = value => `<div class="small">${esc(value)}</div>`;
async function load() {
  try {
    const [overview, domains, themes, signals] = await Promise.all([
      get('/api/admin/analysis/overview'), get('/api/admin/analysis/domains'),
      get('/api/admin/analysis/themes?limit=12'), get('/api/admin/analysis/signals?limit=20')]);
    document.querySelector('#analysis-cards').innerHTML = Object.entries(overview.counts).map(([key, value]) => `<div class="card"><strong>${esc(value)}</strong><span>${esc(key.replaceAll('_', ' '))}</span></div>`).join('');
    document.querySelector('#analysis-domains').innerHTML = domains.domains.map(item => `<div class="listrow"><strong>${esc(item.domain_id)}</strong>${row(item.status)}${row(item.source_tables.join(', '))}</div>`).join('');
    document.querySelector('#analysis-themes').innerHTML = themes.themes.length ? themes.themes.map(item => `<div class="listrow"><strong>${esc(item.theme_key)}</strong>${row(`${item.status} · ${item.passage_count} passages`)}</div>`).join('') : row('No emerging themes recorded.');
    document.querySelector('#analysis-signals').innerHTML = signals.signals.length ? signals.signals.map(item => `<div class="listrow"><strong>${esc(item.signal_type)}</strong>${row(`${item.domain_id} · ${item.subject_id} · ${item.direction}`)}</div>`).join('') : row('No automated signals recorded.');
  } catch (error) { document.querySelector('main').insertAdjacentHTML('afterbegin', `<p class="error">${esc(error.message)}</p>`); }
}
load();
