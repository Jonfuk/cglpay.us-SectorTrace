export const adminGroups = [
  {
    label: 'Overview',
    items: [{ to: '/', label: 'Operator desk', icon: '◈' }],
  },
  {
    label: 'Review',
    items: [
      { to: '/review', label: 'Review queue', icon: '▤' },
      { to: '/candidates', label: 'Candidates', icon: '▧' },
      { to: '/census', label: 'Workforce census', icon: '▥' },
      { to: '/claimreview', label: 'Claim review', icon: '✓' },
    ],
  },
  {
    label: 'Evidence',
    items: [
      { to: '/claims', label: 'Claims', icon: '≡' },
      { to: '/search', label: 'Search', icon: '⌕' },
      { to: '/exports', label: 'Exports', icon: '↓' },
    ],
  },
  {
    label: 'Operations',
    items: [
      { to: '/pipeline', label: 'Pipeline', icon: '▷' },
      { to: '/analysis', label: 'Analysis', icon: '◇' },
    ],
  },
  {
    label: 'Quality',
    items: [
      { to: '/health', label: 'Health', icon: '♡' },
      { to: '/aliases', label: 'Alias resolution', icon: '⇄' },
      { to: '/qc', label: 'QC sampling', icon: '⊞' },
      { to: '/parser-replay', label: 'Parser replay', icon: '↺' },
      { to: '/review-analytics', label: 'Review analytics', icon: '▥' },
    ],
  },
  {
    label: 'Data',
    items: [
      { to: '/database', label: 'Database', icon: '▦' },
      { to: '/sql', label: 'SQL', icon: '⌘' },
      { to: '/lineage', label: 'Data lineage', icon: '⑂' },
    ],
  },
]
export const adminNavigation = adminGroups.flatMap((g) =>
  g.items.map((i) => ({ ...i, group: g.label })),
)
export function adminPath(value: string): string {
  const raw = value.replace(/^\/admin\/?/, '').replace(/^#/, '')
  const path = raw.startsWith('/') ? raw : `/${raw}`
  return path.replace(/^\/overview(?=\?|$)/, '/')
}
