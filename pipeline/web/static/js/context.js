/* Typed context presenter — the shared copy for the operator UI's ES modules.
 *
 * A sibling of the one in /admin/app.js, not an import of it: app.js is a
 * classic script with no exports, and hanging helpers off `window` would make
 * load order part of the contract (dom.js carries the same note). The two
 * copies must agree on the four `_CTX_*` key regexes below; a test in
 * tests/test_web_candidate_workspace.py pins them byte-for-byte.
 *
 * BETA-052 introduced this for the review queue, where the input is the
 * `context_json` string. BETA-061 reuses it for candidate rows, where the
 * input is an already-parsed object — so `typedContext` now takes either.
 * Keys are sorted by name into the things a person actually reads (source,
 * entity, reason, evidence, navigation) and the complete input is kept under a
 * <details> so nothing is lost for audit.
 */
import { el } from './dom.js';

const _CTX_URL_KEYS = /url$|_url$|^url$|link$|href$/i;
const _CTX_EVIDENCE_KEYS = /^(sentence|evidence_span|snippet|excerpt|text|match_text|mention_text|contravention_text|description)$/i;
const _CTX_ENTITY_KEYS = /(provider_key|provider_name|subject_entity_id|entity_id|ons_code|authority|buyer|supplier|charity_number|company_number|board|register_name|recipient_name|employer_name)/i;
const _CTX_REASON_KEYS = /(reason|selection_reason|basis|match_basis|selection|rule|score|relation_score|confidence|assertion_status|status_reason)/i;

function formatContext(raw) {
  try {
    const value = typeof raw === 'string' ? JSON.parse(raw) : raw;
    return JSON.stringify(value, null, 2);
  } catch (e) {
    return String(raw);
  }
}

function _ctxRows(entries, valueNode) {
  return el('dl', { class: 'ctx-kv' }, entries.flatMap(([key, value]) => [
    el('dt', { text: key }),
    el('dd', {}, valueNode(key, value)),
  ]));
}

function _ctxScalar(key, value) {
  if (value === null || value === undefined) return el('span', { class: 'muted', text: '—' });
  const text = typeof value === 'object' ? JSON.stringify(value) : String(value);
  if (_CTX_URL_KEYS.test(key) && /^https?:\/\//i.test(text)) {
    return el('a', { href: text, target: '_blank', rel: 'noopener noreferrer', text });
  }
  return document.createTextNode(text);
}

/* A provider_key / ons_code in the context is a jump to that entity's portal
 * page — opened in a new tab, since the operator UI is a separate app. */
function _ctxNav(context) {
  const links = [];
  if (context.provider_key) {
    links.push(el('a', { href: `/#/providers/${encodeURIComponent(context.provider_key)}`,
      target: '_blank', rel: 'noopener', text: `provider: ${context.provider_key}` }));
  }
  const ons = context.ons_code || context.authority_ons_code || context.buyer_ons_code;
  if (ons && /^[A-Z][0-9]{8}$/.test(String(ons))) {
    links.push(el('a', { href: `/#/authorities/${ons}`,
      target: '_blank', rel: 'noopener', text: `authority: ${ons}` }));
  }
  return links.length ? el('div', { class: 'ctx-nav' }, ...links) : null;
}

/** Render `input` — a context_json string or a plain object — as typed
 *  sections. Returns null for an empty input, a <pre> for a string that will
 *  not parse or a non-object, and the typed block otherwise. */
export function typedContext(input) {
  if (input === null || input === undefined || input === '') return null;
  let context = input;
  if (typeof input === 'string') {
    try { context = JSON.parse(input); }
    catch (e) { return el('pre', { class: 'context', text: String(input) }); }
  }
  if (context === null || typeof context !== 'object' || Array.isArray(context)) {
    return el('pre', { class: 'context', text: formatContext(input) });
  }

  const buckets = { source: [], entity: [], reason: [], evidence: [], other: [] };
  for (const [key, value] of Object.entries(context)) {
    if (value === null || value === undefined || value === '') continue;
    if (_CTX_EVIDENCE_KEYS.test(key)) buckets.evidence.push([key, value]);
    else if (_CTX_URL_KEYS.test(key)) buckets.source.push([key, value]);
    else if (_CTX_ENTITY_KEYS.test(key)) buckets.entity.push([key, value]);
    else if (_CTX_REASON_KEYS.test(key)) buckets.reason.push([key, value]);
    else buckets.other.push([key, value]);
  }

  const sections = [];
  const add = (title, entries) => {
    if (entries.length) {
      sections.push(el('div', { class: 'ctx-section' },
        el('h4', { text: title }), _ctxRows(entries, _ctxScalar)));
    }
  };
  for (const [key, value] of buckets.evidence) {
    sections.push(el('div', { class: 'ctx-section' },
      el('h4', { text: key }),
      el('blockquote', { class: 'ctx-evidence', text: String(value ?? '') })));
  }
  add('Source', buckets.source);
  add('Entity', buckets.entity);
  add('Reason', buckets.reason);
  add('Other', buckets.other);

  const nav = _ctxNav(context);
  if (nav) sections.push(el('div', { class: 'ctx-section' },
    el('h4', { text: 'Open' }), nav));

  if (!sections.length) return null;

  return el('div', { class: 'ctx-typed' },
    ...sections,
    el('details', { class: 'ctx-raw' },
      el('summary', { text: 'Raw context (lossless)' }),
      el('pre', { class: 'context', text: formatContext(context) })));
}
