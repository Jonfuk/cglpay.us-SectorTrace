/* "My area" — one council a reader keeps as a local starting point (BETA-073).
 *
 * No account. `localStorage` holds ONLY the nine-character ONS code, nothing
 * else — no name, no postcode, no personal data — and every figure in the
 * card comes from the existing `/api/v1/authorities/:code` payload, each count
 * linking back to its section on the authority workbench. If localStorage is
 * unavailable (private mode) the feature simply does not appear.
 */
'use strict';

import { el, replace, fetchJSON, num } from '/app.js';

const KEY = 'sectortrace.my_area';
const ONS = /^[A-Z][0-9]{8}$/;

export function getMyArea() {
  try {
    const value = localStorage.getItem(KEY);
    return ONS.test(value || '') ? value : null;
  } catch (e) {
    return null;
  }
}

export function setMyArea(code) {
  if (!ONS.test(code || '')) return;
  try { localStorage.setItem(KEY, code); } catch (e) { /* private mode */ }
  window.dispatchEvent(new CustomEvent('myareachange'));
}

export function clearMyArea() {
  try { localStorage.removeItem(KEY); } catch (e) { /* private mode */ }
  window.dispatchEvent(new CustomEvent('myareachange'));
}

/** A star toggle for the authority workbench: set this authority as my area,
 *  or clear it if it already is. */
export function myAreaToggle(code, name) {
  const btn = el('button', { class: 'btn ghost', type: 'button' });
  const paint = () => {
    const mine = getMyArea() === code;
    btn.textContent = mine ? '★ This is my area' : '☆ Set as my area';
    btn.title = mine
      ? `Remove ${name || code} as your saved area`
      : `Keep ${name || code} as your local starting point (this browser only)`;
    btn.setAttribute('aria-pressed', String(mine));
  };
  btn.addEventListener('click', () => {
    if (getMyArea() === code) clearMyArea(); else setMyArea(code);
    paint();
  });
  window.addEventListener('myareachange', paint);
  paint();
  return btn;
}

function latestRetrieval(data) {
  let latest = null;
  const walk = (value) => {
    if (Array.isArray(value)) { value.forEach(walk); return; }
    if (value && typeof value === 'object') {
      if (typeof value.retrieved_at === 'string'
          && (!latest || value.retrieved_at > latest)) latest = value.retrieved_at;
      Object.values(value).forEach(walk);
    }
  };
  walk(data);
  return latest ? latest.slice(0, 10) : null;
}

/** Render the "My area" card into `container`. With no saved area it is a
 *  prompt; with one, a compact availability summary linking into the
 *  authority workbench. */
export async function renderMyAreaCard(container) {
  const code = getMyArea();

  if (!code) {
    replace(container, el('div', { class: 'myarea-card myarea-empty' },
      el('h2', { text: 'My area' }),
      el('p', { class: 'small' },
        'Pick a council to turn the England-wide evidence into a local '
        + 'starting point. Only the area code is stored, in this browser.'),
      el('a', { class: 'btn', href: '#/geography' }, 'Choose on the map')));
    return;
  }

  replace(container, el('div', { class: 'myarea-card' },
    el('p', { class: 'small muted', text: 'Loading your area…' })));

  let data;
  try {
    data = await fetchJSON(`authorities/${encodeURIComponent(code)}`);
  } catch (e) {
    replace(container, el('div', { class: 'myarea-card' },
      el('h2', { text: 'My area' }),
      el('p', { class: 'small' }, `The saved area ${code} could not be loaded. `,
        el('button', { class: 'linklike', type: 'button',
          onclick: () => { clearMyArea(); renderMyAreaCard(container); } },
        'Clear it')),
      (e && e.detail) ? el('p', { class: 'small muted', text: e.detail.message } ) : null));
    return;
  }

  const a = data.authority || {};
  const comparators = ['rough_sleeping', 'statutory_homelessness', 'temporary_accommodation']
    .filter((k) => (data.comparators?.[k]?.rows || []).length).length;
  const treatmentInd = (data.treatment?.fingertips?.indicators || []).length;
  const freshness = latestRetrieval(data);

  const stat = (count, label, anchor) => el('a', {
    class: 'myarea-stat', href: `#/authorities/${code}${anchor}`,
  },
    el('span', { class: 'myarea-stat-n', text: num(count) }),
    el('span', { class: 'myarea-stat-l', text: label }));

  replace(container, el('div', { class: 'myarea-card' },
    el('div', { class: 'myarea-head' },
      el('h2', {}, 'My area: ',
        el('a', { href: `#/authorities/${code}` }, a.name || code)),
      el('button', { class: 'linklike', type: 'button',
        onclick: () => { clearMyArea(); renderMyAreaCard(container); } }, 'Change')),
    el('p', { class: 'small muted', text:
      `${a.type || 'Local authority'} · ${a.region || 'region not recorded'}`
      + (freshness ? ` · evidence retrieved to ${freshness}` : '') }),
    el('div', { class: 'myarea-stats' },
      stat(data.grant?.rows?.length || 0, 'grant years', '#grant-budget'),
      stat(data.budget?.rows?.length || 0, 'budget years', '#grant-budget'),
      stat(treatmentInd, 'treatment indicators', '#treatment'),
      stat(data.contracts?.total || 0, 'contract notices', '#contracts'),
      stat(comparators, 'homelessness comparators', '#comparators')),
    el('p', { class: 'small' },
      el('a', { href: `#/authorities/${code}` }, 'Open the full workbench →'),
      ' · ',
      el('a', { href: `#/compare?ons_code=${code}` }, 'Compare with others →'),
      ' · ',
      el('a', { href: `#/relationships?ons_code=${code}` }, 'Who it commissions →'))));
}
