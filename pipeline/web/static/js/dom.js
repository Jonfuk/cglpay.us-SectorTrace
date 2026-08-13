/* The element builder, for the operator UI's ES modules.
 *
 * A copy of the one in /admin/app.js rather than an import of it: app.js is a
 * classic script with no exports, and the alternative -- hanging helpers off
 * window so modules can reach them -- makes the load order part of the
 * contract. Twenty lines duplicated is the cheaper of the two.
 *
 * The rule it exists to enforce is the same one: values that came out of the
 * warehouse reach the page as text nodes, never as markup. `html` is rejected
 * outright so that "just this once" has to be a deliberate edit here.
 */
export function el(tag, props, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = value;
    else if (key === 'html') throw new Error('no raw HTML');
    else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
    else if (key === 'dataset') Object.assign(node.dataset, value);
    else node.setAttribute(key, value === true ? '' : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

/** localStorage that cannot throw. Private-browsing windows and a filled quota
 *  both raise on write, and none of what this UI stores is worth an exception
 *  reaching the page. */
export const store = {
  get(key, fallback = null) {
    try { const v = localStorage.getItem(key); return v === null ? fallback : v; }
    catch (e) { return fallback; }
  },
  set(key, value) {
    try { localStorage.setItem(key, value); } catch (e) { /* nothing to do */ }
  },
};
