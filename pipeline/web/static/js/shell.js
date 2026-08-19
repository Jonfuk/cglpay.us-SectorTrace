/* Entry point for the operator UI's module half.
 *
 * app.js -- the tabs, the queue, the table browser -- stays a classic script;
 * it works, and rewriting working review tooling to change how it is loaded
 * would be a risk taken for no visible gain. Everything added since is an ES
 * module, loaded alongside it, the way the public portal is built.
 *
 * The two halves do not call each other. This one reaches the page through
 * the DOM and through the URL hash, both of which app.js already treats as
 * inputs from outside, so nothing here depends on its internals or on which
 * of the two scripts finished first.
 */
import { initCandidates } from './candidates.js';
import { initCensus } from './census.js';
import { initClaims } from './claims.js';
import { initExports } from './exports.js';
import { initHealth } from './health.js';
import { initPalette } from './palette.js';
import { initPipeline } from './pipeline.js';
import { initProviderResearch } from './provider-research.js';
import { initTheme } from './theme.js';

initTheme();
initPalette();
initPipeline();
initProviderResearch();
initHealth();
initExports();
initCandidates();
initCensus();
initClaims();
