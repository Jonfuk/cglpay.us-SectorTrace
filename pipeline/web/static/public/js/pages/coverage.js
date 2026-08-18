/* Coverage and limitations.
 *
 * A capture of public evidence is not a census of the sector. This page makes
 * that boundary visible without turning the navigation into a list of module
 * names, and keeps status language separate from the strength of a claim.
 */
'use strict';

import { el, replace, fetchJSON, ago } from '/app.js';
import { section, pinnedCaveat, errorCard, shareButton } from '/js/components.js';

const SOURCE_LABELS = {
  'Contracts Finder': 'Contracts Finder',
  'NHS job adverts': 'NHS Jobs adverts',
  'LA revenue budgets': 'Local-authority revenue budgets',
  'Fingertips values': 'OHID Fingertips treatment indicators',
  'Workforce census': 'Workforce census indicators',
  'NDTMS statistics': 'NDTMS statistics',
  'PFD reports': 'Coroners’ reports',
  'CQC locations': 'CQC locations and inspections',
  'Charity financials': 'Charity financial statements',
  'Company filings': 'Companies House filings',
  'Annual report disclosure': 'Provider-published reports',
  'Tribunal cases': 'Employment tribunal cases',
  Authorities: 'Local authorities',
};

const STATUS = [
  ['Published evidence', 'A source figure or document that has passed the pipeline’s human review and is available on this portal.'],
  ['Not yet human-verified', 'An extraction found by the pipeline that must not be treated as published evidence until a person checks it.'],
  ['Candidate awaiting human review', 'A possible match retained for review in the operator interface. Candidates do not appear in the public evidence library.'],
  ['Missing because not collected', 'The pipeline has not collected this source or field. It is not a zero.'],
  ['Collected but unavailable or unparseable', 'The source was reached, but its value was unavailable or could not be reliably read.'],
  ['Suppressed by the source', 'The publisher deliberately withholds the value; this is distinct from an absent record.'],
];

export async function render(main) {
  const page = el('div', {},
    el('div', { class: 'hero' },
      el('h1', { text: 'Trust centre' }),
      el('p', { class: 'lede', text: 'How to read SectorTrace evidence, its source coverage, and the difference between published, missing and unverified records.' }),
      el('div', { class: 'hero-actions' },
        shareButton({
          title: 'SectorTrace coverage and limitations',
          text: 'Read how SectorTrace evidence status and source coverage work.',
          label: 'Share this guide',
        }))),
    el('details', { class: 'read-first' },
      el('summary', { text: 'What this guide is for' }),
      el('p', { text: 'It explains what the portal holds and how the pipeline labels evidence. It is not a scorecard of providers, authorities, or the sector.' })),
    el('div', { id: 'meaning' }),
    el('div', { id: 'boundaries' }),
    el('div', { id: 'freshness' }));
  replace(main, page);

  const statusCards = STATUS.map(([title, description]) =>
    el('article', { class: 'coverage-status' },
      el('h3', { text: title }),
      el('p', { text: description })));
  replace(page.querySelector('#meaning'), section(
    'Evidence-state glossary',
    'The status of a record says what has happened to it in the pipeline. It does not make unlike sources comparable.',
    el('div', { class: 'coverage-statuses' }, statusCards)));

  replace(page.querySelector('#boundaries'), section(
    'Method and limits',
    'Evidence layers are kept separate so that a published number remains defensible in its own terms.',
    el('details', { class: 'context-note', open: true },
      el('summary', { text: 'What this portal does not calculate' }),
      pinnedCaveat(
        'SectorTrace does not calculate cross-layer composite scores, claims per employee, treatment-to-workforce ratios, workforce census trends, annualised hourly pay, or percentages above the minimum wage. Missing values are never treated as zero.',
        'Important limits'),
      el('p', { class: 'muted', text: 'The organisation list is a capture of names found in the pipeline’s sources, not a census or a claimed measure of sector size.' }))));

  const freshness = page.querySelector('#freshness');
  replace(freshness, section('Sources and latest updates', 'The latest successful retrieval recorded for each public source layer.', el('p', { class: 'muted', text: 'Loading source updates…' })));
  try {
    const data = await fetchJSON('freshness');
    const rows = data.tables || [];
    const freshnessCards = rows.map((row) => el('article', { class: 'freshness-item' },
      el('strong', { text: SOURCE_LABELS[row.label] || row.label }),
      el('span', { class: 'small', text: row.retrieved_at
        ? `Last retrieved ${ago(row.retrieved_at)}` : 'Not collected yet' })));
    replace(freshness, section(
      'Sources and latest updates',
      'The latest successful retrieval recorded for each public source layer.',
      data.caveat ? pinnedCaveat(data.caveat, 'About freshness') : null,
      el('div', { class: 'freshness-list' }, freshnessCards)));
  } catch (error) {
    replace(freshness, errorCard(error.message, () => render(main)));
  }
  return () => {};
}
