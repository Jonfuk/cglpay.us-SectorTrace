export const navigationGroups = [
  { label: 'Explore', items: [
    ['/', 'Overview', 'Ov'], ['/search', 'Search', 'Se'], ['/providers', 'Providers', 'Pr'],
    ['/authorities', 'Authorities', 'Au'], ['/geography', 'Places', 'Pl'],
  ] },
  { label: 'Evidence', items: [
    ['/contracts', 'Contracts and payments', 'Co'], ['/pay', 'Pay and workforce', 'Pa'],
    ['/treatment', 'Treatment', 'Tr'], ['/cqc', 'CQC registrations', 'CQ'],
    ['/pfd', 'Safety and legal', 'Sa'], ['/documents', 'Documents', 'Do'],
    ['/claims', 'Evidence-backed statements', 'St'],
  ] },
  { label: 'Research', items: [
    ['/compare', 'Compare', 'Cm'], ['/relationships', 'Connections', 'Cn'],
    ['/research-tools', 'Verification tools', 'Ve'],
  ] },
  { label: 'Your work', items: [
    ['/saved', 'Saved views', 'Sv'], ['/notebook', 'Notebook', 'No'], ['/journey', 'Recent visits', 'Re'],
  ] },
  { label: 'Evidence coverage', items: [
    ['/coverage', 'Coverage guide', 'Gu'], ['/catalogue', 'Catalogue', 'Ca'],
    ['/timeline', 'History', 'Hi'], ['/calendar', 'Publication calendar', 'Pc'], ['/changes', 'Recorded changes', 'Ch'],
  ] },
] as const

export function navigationLabel(path: string): string {
  const items = navigationGroups.flatMap(g => [...g.items])
  return items.find(item => item[0] === path)?.[1]
    ?? items.find(item => item[0] !== '/' && path.startsWith(`${item[0]}/`))?.[1]
    ?? 'Evidence'
}
