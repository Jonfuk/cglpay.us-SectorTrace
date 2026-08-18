/* What we can say — the claims-to-evidence index.
 *
 * Workstream C (Phase 17). The difference between a data portal and an
 * evidence portfolio: claims as rows, each linked to the evidence that
 * supports it, with the caveats that travel with it.
 *
 * Three rules shape this page, and each is the phase plan's own:
 *
 *   * Nothing here is computed. The claim text is what a person wrote, the
 *     citations are rows a person picked, and the caveats are lines a person
 *     wrote about what may not be computed from it. The page renders the
 *     registry; it does not add, divide or derive anything.
 *   * Only published claims are shown, and publication is a named decision —
 *     the registry's triggers refuse a decided claim without a
 *     claim_verifications row behind it. The reviewer and the date travel
 *     with the claim, like every other judgement in this warehouse.
 *   * A citation that no longer resolves is rendered as unresolvable rather
 *     than dropped or guessed at: a module re-run can replace the row a
 *     citation names, and a reader deserves to see that the claim rests on
 *     rows the warehouse no longer holds.
 */
'use strict';

import { el, replace, fetchJSON, ago, sourceLink } from '/app.js';
import { section, pinnedCaveat, noData, errorCard, provenance,
          shareButton, findingBlock } from '/js/components.js';

export async function render(main) {
  let data;
  try {
    data = await fetchJSON('claims');
  } catch (error) {
    replace(main, errorCard(error.message, () => render(main)));
    return () => {};
  }

  const claims = data.claims || [];
  const page = el('div', {},
    el('div', { class: 'hero' },
      el('h1', { text: 'Evidence-backed claims' }),
      el('p', { class: 'lede' },
        'The claims the campaign makes, each linked to the evidence that ',
        'supports it and approved by a named reviewer. ',
        el('strong', { text: 'Nothing here is computed' }),
        ': a claim is a statement, and the linkage to its evidence is a ',
        'human judgement recorded like every other decision in this warehouse.'),
      el('div', { class: 'hero-actions' },
        shareButton({
          title: 'SectorTrace evidence-backed claims',
          text: 'Read campaign claims with their supporting evidence and caveats.',
          label: 'Share claims',
        }))),
    el('details', { class: 'read-first' },
      el('summary', { text: 'Use claims responsibly' }),
      el('p', { text: 'A claim is a campaign statement reviewed by a named person. Read its caveat and cited evidence before repeating it.' })),
    el('div', { id: 'claims' }));
  replace(main, page);

  renderClaims(page.querySelector('#claims'), data);

  return () => {};
}

function renderClaims(container, data) {
  const claims = data.claims || [];

  replace(container, section(
    'The claims',
    'Each one as it would be quoted, with the caveats that govern it and the '
      + 'evidence rows it rests on.',
    pinnedCaveat(data.caveat, 'Read this with every claim'),
    claims.length
      ? el('div', { class: 'claim-list' }, ...claims.map(renderClaim))
      : noData('published claims',
          'the claims registry is maintained by the campaign, in the '
          + 'review-and-decide workflow on /admin')));
}

function renderClaim(claim) {
  const caveats = (claim.caveats || []).filter(Boolean);

  const card = el('article', { class: 'claim' },
    el('div', { class: 'takeaway' },
      el('span', { class: 'badge good', text: 'PUBLISHED' }),
      el('blockquote', { class: 'claim-text', text: claim.claim_text })),
    findingBlock({
      finding: claim.claim_text,
      evidenceStatus: 'Human-reviewed',
      caveat: caveats.join(' ') || 'Read the supporting citations before repeating this claim.',
      sources: (claim.citations || []).map((citation) => citation.source_url).filter(Boolean),
      retrievedAt: (claim.citations || []).map((citation) => citation.retrieved_at).filter(Boolean).sort().pop()?.slice(0, 10),
    }),
    caveats.length
      ? el('div', { class: 'claim-caveats' },
          caveats.map((line) => pinnedCaveat(line, 'You may not compute this from it')))
      : null,
    el('div', { class: 'row wrap' },
      el('span', { class: 'muted small',
        text: `Approved by ${claim.published_by || '—'} · `
              + `${claim.published_at ? ago(claim.published_at) : '—'}`
              + (claim.note ? ` · ${claim.note}` : '') }),
      shareButton({
        title: 'SectorTrace evidence-backed claim',
        text: `${claim.claim_text}\nCaveat: ${caveats.join(' ')}`,
        label: 'Copy claim with citation',
      })));

  if (claim.citations && claim.citations.length) {
    card.append(el('details', { class: 'context-note claim-citations' },
      el('summary', { text: `Supporting evidence (${claim.citations.length})` }),
      el('ul', {}, ...claim.citations.map(renderCitation)),
      provenanceFromCitations(claim.citations)));
  }
  return card;
}

function renderCitation(citation) {
  const resolved = citation.resolved;
  if (!resolved) {
    // The honest half: the row a citation named is no longer in the
    // warehouse. Rendered as such rather than as a link that silently goes
    // somewhere else.
    return el('li', { class: 'citation' },
      el('span', { class: 'citation-unresolved', text:
        `${citation.table}: ${citation.key}` }),
      el('span', { class: 'muted small', text:
        ' — the row this cited is no longer in the warehouse' }));
  }
  return el('li', { class: 'citation' },
    resolved.url
      ? sourceLink(resolved.url, resolved.label)
      : el('span', { text: resolved.label }),
    el('span', { class: 'muted small',
      text: ` · ${citation.table}` }));
}

/* The drawer under the citations list, fed from the rows the payload already
 * resolved — the same shape every other section's provenance drawer takes. */
function provenanceFromCitations(citations) {
  const resolved = citations.map((c) => c.resolved).filter(Boolean);
  return provenance({
    sources: resolved.map((r) => r.source_url).filter(Boolean),
    retrievedAt: resolved.map((r) => r.retrieved_at).filter(Boolean)
      .sort().pop() || null,
    tables: ['claims', 'claim_citations', 'claim_verifications'],
  });
}
