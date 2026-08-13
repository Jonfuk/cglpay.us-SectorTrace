/* Light, dark, or whatever the OS says.
 *
 * The stylesheet has always followed prefers-color-scheme. What it could not
 * do is disagree with it, and the reason to want that here is mundane: this
 * tool gets used on a machine set to dark at a desk that is not, and read
 * beside a projector that wants the opposite of both.
 *
 * Three states, not two. "System" is a real choice and the default one, so
 * the toggle cycles through it rather than latching to whichever side the OS
 * happened to be on when someone first clicked.
 */
import { store } from './dom.js';

const KEY = 'cglpay.theme';
const ORDER = ['system', 'light', 'dark'];

const LABEL = {
  system: { glyph: '◐', text: 'Theme: follow system' },
  light: { glyph: '☀', text: 'Theme: light' },
  dark: { glyph: '☾', text: 'Theme: dark' },
};

function current() {
  const saved = store.get(KEY, 'system');
  return ORDER.includes(saved) ? saved : 'system';
}

/* The attribute drives the stylesheet; its absence means "no opinion", which
 * is what leaves the media query in charge. */
function apply(mode) {
  const root = document.documentElement;
  if (mode === 'system') root.removeAttribute('data-theme');
  else root.setAttribute('data-theme', mode);
}

function paintButton(button, mode) {
  button.textContent = LABEL[mode].glyph;
  button.title = `${LABEL[mode].text} — click to change`;
  button.setAttribute('aria-label', LABEL[mode].text);
}

/** Advance to the next mode and return it. Exported for the command palette,
 *  which offers the same action by name. */
export function cycleTheme() {
  const next = ORDER[(ORDER.indexOf(current()) + 1) % ORDER.length];
  store.set(KEY, next);
  apply(next);
  const button = document.getElementById('theme-toggle');
  if (button) paintButton(button, next);
  return next;
}

export function initTheme() {
  // Before anything else paints: a flash of the wrong theme on every load is
  // worse than the problem this feature solves.
  apply(current());

  const button = document.getElementById('theme-toggle');
  if (!button) return;
  paintButton(button, current());
  button.addEventListener('click', cycleTheme);
}
