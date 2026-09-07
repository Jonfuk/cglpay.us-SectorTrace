import type { RelationshipEdge } from './api'
export interface ConnectionNode { entity_id: string | null; entity_type: string | null; canonical_name: string | null; [key: string]: unknown }
export interface ConnectionEdge extends RelationshipEdge { confidence?: string | null; source_url?: string | null; retrieved_at?: string | null; source_system?: string | null }
export interface ConnectionPayload { center?: ConnectionNode; neighbours?: ConnectionNode[]; edges?: ConnectionEdge[]; caveat?: string | null }
export interface ConnectionParty { entity_id?: string | null; name?: string | null; ons_code?: string | null; provider_key?: string | null }
export interface ConnectionEvent { relationship_id?: string | null; valid_from?: string | null; valid_to?: string | null; confidence?: string | null; source_url?: string | null; retrieved_at?: string | null; notice?: Record<string, unknown> | null }
export interface ConnectionDetail { relationship_id?: string; predicate?: string; authority?: ConnectionParty; provider?: ConnectionParty; timeline?: ConnectionEvent[]; edge_count?: number; truncated?: boolean; caveat?: string | null }
