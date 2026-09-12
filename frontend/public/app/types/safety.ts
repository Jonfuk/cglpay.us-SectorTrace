import type { SafetyRow } from '~/lib/safety'
export interface SafetyLegalPayload { events?: SafetyRow[]; truncated?: boolean; counts?: { by_source?: Record<string, number>; by_relationship?: Record<string, number> }; sources?: string[]; labels?: Record<string, string>; caveats?: Record<string, string | null>; note?: string | null }
export interface SafetyCorpus { totals?: Record<string, number | null>; mentions?: Record<string, number | null>; recent?: SafetyRow[]; by_year?: SafetyRow[]; by_coroner_area?: SafetyRow[]; by_board?: SafetyRow[]; concern_terms?: SafetyRow[]; caveats?: Record<string, string | null> }
export interface PfdCorpus extends SafetyCorpus { sar?: SafetyCorpus }
export interface HseCorpus { notices?: SafetyRow[]; total?: number; by_type?: SafetyRow[]; by_provider?: SafetyRow[]; caveat?: string | null }
