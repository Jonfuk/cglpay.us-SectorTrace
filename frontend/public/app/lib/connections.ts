import type { ConnectionEdge, ConnectionNode } from '~/types/connections'
export function connectionNode(nodes: ConnectionNode[], id: string | null | undefined) {
  if (!id) return undefined
  const matches = nodes.filter(node => node.entity_id === id)
  return matches.length === 1 ? matches[0] : undefined
}
export function connectionName(nodes: ConnectionNode[], id: string | null | undefined) { return connectionNode(nodes, id)?.canonical_name ?? id ?? 'Identifier not supplied' }
// The endpoint supplies AWARDED_TO edges. Unknown or conflicting entity records
// cannot acquire a column from an identifier's spelling or a similar name.
export function drawableConnections(edges: ConnectionEdge[], nodes: ConnectionNode[]) {
  return edges.filter(edge => Boolean(edge.relationship_id) && connectionNode(nodes, edge.subject_entity_id)?.entity_type === 'LOCAL_AUTHORITY' && connectionNode(nodes, edge.object_entity_id)?.entity_type === 'PROVIDER')
}
export function connectionText(value: unknown) { return value == null || value === '' ? 'Not supplied' : typeof value === 'object' ? JSON.stringify(value) : String(value) }

export function connectionReferences(edges: ConnectionEdge[], nodes: ConnectionNode[]) {
  const sources: Array<[unknown, unknown, unknown]> = []
  const references = drawableConnections(edges, nodes).map((edge, index) => {
    // Only identical provenance tuples share a display reference. A shared URL
    // alone cannot establish that two edges came from the same retrieval.
    const source: [unknown, unknown, unknown] = [edge.source_url, edge.retrieved_at, edge.source_system]
    let sourceIndex = sources.findIndex(candidate => candidate.every((value, field) => value === source[field]))
    if (sourceIndex < 0) { sourceIndex = sources.length; sources.push(source) }
    return `Diagram edge ${index + 1}, relationship ${connectionText(edge.relationship_id)}. Valid from ${connectionText(edge.valid_from)}, valid to ${connectionText(edge.valid_to)}. Confidence ${connectionText(edge.confidence)}. Source reference ${sourceIndex + 1}.`
  })
  return ['Diagram numbers are display labels, not source identifiers.', ...references, ...sources.map((source, index) => `Source reference ${index + 1}. URL ${connectionText(source[0])}. Retrieved ${connectionText(source[1])}. Source system ${connectionText(source[2])}.`)].join('\n')
}
