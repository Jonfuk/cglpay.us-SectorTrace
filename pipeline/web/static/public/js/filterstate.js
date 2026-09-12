/* One typed definition of the portal's shared filter state (BETA-072).
 *
 * Before this, the global filters (provider, year range) were read from
 * `location.hash` and written back in several ad-hoc shapes, and each page's
 * own query keys were parsed by hand again. This module is the single place
 * the shared state is parsed, validated, serialised and labelled. A filter is
 * added by adding a field to `FILTER_SCHEMA` — its query-param name, its type,
 * and how it renders as a chip — not by reading the hash in a new way.
 *
 * It owns only the *shared* keys. A page keeps its own keys in the same hash
 * query (contracts `q`, pay `source`), and `serializeFilters` carries those
 * through untouched, so one URL still restores both.
 */
'use strict';

export const YEAR_MIN = 2000;
export const yearMax = () => new Date().getFullYear() + 1;

export const FILTER_SCHEMA = {
  provider: { param: 'provider', type: 'string', label: 'Provider' },
  yearFrom: { param: 'yearFrom', type: 'year', label: 'From' },
  yearTo: { param: 'yearTo', type: 'year', label: 'To' },
};

const SHARED_PARAMS = new Set(Object.values(FILTER_SCHEMA).map((d) => d.param));

function coerce(type, raw) {
  if (type === 'year') {
    const n = parseInt(raw, 10);
    return Number.isFinite(n) ? String(n) : null;
  }
  return String(raw);
}

/** Shared filter state from a URLSearchParams. Unknown/blank -> null. */
export function parseFilters(searchParams) {
  const out = {};
  for (const [key, def] of Object.entries(FILTER_SCHEMA)) {
    const raw = searchParams.get(def.param);
    out[key] = (raw === null || raw === '') ? null : coerce(def.type, raw);
  }
  return out;
}

/** Human-readable problems with a state. Empty array means it is usable. */
export function validateFilters(state) {
  const errors = [];
  const max = yearMax();
  for (const key of ['yearFrom', 'yearTo']) {
    const value = state[key];
    if (value == null || value === '') continue;
    const n = parseInt(value, 10);
    if (!Number.isFinite(n) || n < YEAR_MIN || n > max) {
      errors.push(`${FILTER_SCHEMA[key].label} year must be between ${YEAR_MIN} and ${max}.`);
    }
  }
  if (state.yearFrom && state.yearTo
      && parseInt(state.yearFrom, 10) > parseInt(state.yearTo, 10)) {
    errors.push('The “from” year is after the “to” year.');
  }
  return errors;
}

/** Serialise shared state into a URLSearchParams, preserving any page-owned
 *  keys already present in `existing`. */
export function serializeFilters(state, existing = null) {
  const params = new URLSearchParams();
  for (const [key, def] of Object.entries(FILTER_SCHEMA)) {
    const value = state[key];
    if (value != null && value !== '') params.set(def.param, value);
  }
  if (existing) {
    for (const key of existing.keys()) {
      if (!SHARED_PARAMS.has(key)) {
        for (const value of existing.getAll(key)) params.append(key, value);
      }
    }
  }
  return params;
}

export function isSharedParam(name) {
  return SHARED_PARAMS.has(name);
}

/** Active shared filters as {key, text} chips. `providerName` resolves the
 *  provider key to its canonical name where the caller knows it. */
export function chipLabels(state, { providerName = null } = {}) {
  const chips = [];
  if (state.provider) {
    chips.push({ key: 'provider', text: `Provider: ${providerName || state.provider}` });
  }
  if (state.yearFrom) chips.push({ key: 'yearFrom', text: `From ${state.yearFrom}` });
  if (state.yearTo) chips.push({ key: 'yearTo', text: `To ${state.yearTo}` });
  return chips;
}
