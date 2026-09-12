/* The Search tab: a diagnostic workbench over /api/admin/search (BETA-046).
 *
 * The retrieval backend already exists — keyword (FTS), semantic (exact
 * cosine over one embedding model) and hybrid (RRF fusion) search of parsed
 * committee papers and CDP document chunks, from the semantic-analysis layer
 * (BETA-034A). This tab is only a window onto it, built so a reviewer can see
 * *how* each mode ranks before deciding whether to trust it:
 *
 *   * every result shows its score components (keyword rank, semantic rank,
 *     cosine, RRF score) so the ordering is inspectable, not magic;
 *   * the model identity and any fallback ("hybrid degraded to keyword-only",
 *     the deterministic stub embedder) are stated at the top of the results,
 *     not buried;
 *   * nothing here promotes, attributes or exports anything, and the copy
 *     says relevance order is retrieval behaviour, not evidential weight.
 *
 * An /api/admin/* tool: it reads the archive, no restricted_ data, and stays
 * behind the same network-trust boundary as the rest of the operator UI.
 */
import { el } from './dom.js';

const $ = (id) => document.getElementById(id);

async function api(path) {
  const response = await fetch(path);
  let payload = null;
  try { payload = await response.json(); } catch (e) { /* not JSON */ }
  if (!response.ok) {
    const error = new Error((payload && payload.error) || response.statusText);
    error.status = response.status;
    throw error;
  }
  return payload;
}

function queryString() {
  const params = new URLSearchParams();
  const q = $('search-q').value.trim();
  if (q) params.set('q', q);
  params.set('mode', $('search-mode').value);
  const source = $('search-source').value;
  if (source) params.set('source_system', source);
  const from = $('search-from').value;
  const to = $('search-to').value;
  if (from) params.set('date_from', from);
  if (to) params.set('date_to', to);
  params.set('limit', $('search-limit').value);
  return params.toString();
}

/* The score block for one result. `score` is a small object whose keys depend
 * on the mode: keyword_rank / semantic_rank / cosine for the single-mode
 * searches, plus rrf and both ranks for hybrid. Rendered as plain labelled
 * values so the ordering can be checked against them. */
function scoreBlock(score) {
  const labels = {
    rrf: 'RRF score',
    keyword_rank: 'keyword rank',
    semantic_rank: 'semantic rank',
    cosine: 'cosine similarity',
  };
  const parts = Object.entries(score || {}).map(([key, value]) =>
    el('span', { class: 'chip' }, `${labels[key] || key}: ${value}`));
  return el('div', { class: 'chips small' }, ...parts);
}

function resultCard(row) {
  const pages = row.page_start && row.page_end && row.page_start !== row.page_end
    ? `pages ${row.page_start}–${row.page_end}`
    : (row.page_start ? `page ${row.page_start}` : null);
  const meta = [row.document_type, row.source_system, pages,
    row.token_estimate ? `${row.token_estimate} tokens` : null]
    .filter(Boolean).join(' · ');

  return el('article', { class: 'panel' },
    el('div', { class: 'row', style: 'justify-content:space-between;gap:8px;align-items:baseline' },
      el('strong', { text: row.title || row.document_id }),
      el('span', { class: 'muted small', text: meta })),
    scoreBlock(row.score),
    el('p', { class: 'small', text: row.snippet || row.text || '' }),
    el('div', { class: 'row small', style: 'gap:12px;flex-wrap:wrap' },
      row.source_url
        ? el('a', { href: row.source_url, target: '_blank', rel: 'noopener' }, 'Source page')
        : null,
      row.published_at ? el('span', { class: 'muted', text: `published ${String(row.published_at).slice(0, 10)}` }) : null,
      row.retrieved_at ? el('span', { class: 'muted', text: `retrieved ${String(row.retrieved_at).slice(0, 10)}` }) : null));
}

function renderMeta(data) {
  const meta = $('search-meta');
  const bits = [
    el('span', { class: 'chip', text: `mode: ${data.mode}` }),
    el('span', { class: 'chip', text: `model: ${data.model_key || 'none (keyword only)'}` }),
    el('span', { class: 'chip', text: `${data.count} result${data.count === 1 ? '' : 's'}` }),
  ];
  const filters = data.filters || {};
  for (const [key, value] of Object.entries(filters)) {
    if (value) bits.push(el('span', { class: 'chip', text: `${key}: ${value}` }));
  }
  const rows = [el('div', { class: 'chips' }, ...bits)];
  // The fallback state, stated rather than implied. `notes` carries the
  // "degraded to keyword-only" and stub-embedder lines the backend emits.
  for (const note of data.notes || []) {
    rows.push(el('p', { class: 'small', style: 'margin:4px 0 0', text: `⚠ ${note}` }));
  }
  rows.push(el('p', { class: 'small muted', style: 'margin:4px 0 0', text: data.caveat || '' }));
  meta.replaceChildren(...rows);
  meta.hidden = false;
}

async function runSearch(event) {
  if (event) event.preventDefault();
  const status = $('search-status');
  const results = $('search-results');
  const qs = queryString();
  if (!/(^|&)q=/.test(qs)) {
    status.textContent = 'Enter a search term.';
    return;
  }
  status.textContent = 'Searching…';
  results.replaceChildren();
  $('search-meta').hidden = true;

  let data;
  try {
    data = await api(`/api/admin/search?${qs}`);
  } catch (error) {
    status.textContent = `Search failed: ${error.message}`;
    return;
  }

  renderMeta(data);
  const rows = data.results || [];
  status.textContent = rows.length
    ? `${rows.length} passage${rows.length === 1 ? '' : 's'} matched, in ${data.mode} mode.`
    : 'No passages matched this query.';
  results.replaceChildren(...rows.map(resultCard));
}

export function initSearch() {
  const panel = $('tab-search');
  if (!panel) return;
  const form = $('search-form');
  if (form) form.addEventListener('submit', runSearch);
}
