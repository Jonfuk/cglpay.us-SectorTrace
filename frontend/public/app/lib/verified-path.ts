export interface VerifiedPathNode { node?: string | null; type?: string | null; id?: string | null; label?: string | null; [key: string]: unknown }
export interface VerifiedHop { from?: string | null; to?: string | null; relationship?: string | null; relationship_label?: string | null; basis?: string | null; source_url?: string | null; retrieved_at?: string | null; [key: string]: unknown }
export interface VerifiedPath { found?: boolean; hops?: number; max_hops?: number; verified_only?: boolean; note?: string; reason?: string; path?: VerifiedHop[]; nodes?: VerifiedPathNode[]; from?: VerifiedPathNode; to?: VerifiedPathNode; [key: string]: unknown }
export function verifiedNode(nodes: VerifiedPathNode[], identifier: string | null | undefined) {
  if (!identifier) return undefined
  const matches = nodes.filter(node => node.node === identifier)
  return matches.length === 1 ? matches[0] : undefined
}
export function verifiedProfile(node: VerifiedPathNode | undefined) {
  if (!node?.id) return undefined
  if (node.type === 'provider') return `/providers/${encodeURIComponent(node.id)}`
  if (node.type === 'authority') return `/authorities/${encodeURIComponent(node.id)}`
  return undefined
}
export const verifiedPathLimitations = 'The search traverses edges in either direction. Original edge direction is not returned, so relationship labels are source metadata rather than directional statements about this sequence. Repeated source edges are deduplicated by endpoint pair and relationship. This is not an award count or a relationship-strength measure. Payload hashes and edge dates are not supplied.'
export function pathInputError(query: Record<string, string>) {
  if (!['provider', 'authority', 'supplier'].includes(query.from_type ?? '') || !['provider', 'authority', 'supplier'].includes(query.to_type ?? '')) return 'Choose a supported type for both endpoints.'
  if (!query.from_id || !query.to_id) return 'Choose a start and an end entity.'
  if (!/^[1-6]$/.test(query.max_hops ?? '')) return 'Choose a hop bound from 1 to 6. The saved value has not been silently changed.'
  return ''
}
