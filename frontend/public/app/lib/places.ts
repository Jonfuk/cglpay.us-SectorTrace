import type { GeographyFeature } from '~/types/api'
export const atlasKeys = ['grant_drug_alcohol', 'grant_total', 'grant_per_head', 'budget_public_health', 'treatment_numbers', 'contract_value', 'cqc_locations', 'coverage'] as const
export interface AtlasLayer { key: string; label: string; kind: 'choropleth' | 'points' | 'authority'; unit: string; legend: string; caveat: string }
export interface MapLocation { location_id: string; location_name?: string | null; latitude: number; longitude: number; ons_code?: string | null; region?: string | null; overall_rating?: string | null }

// Geography may return several observations for one authority without enough
// metadata to distinguish their cohorts. Even equal values do not establish
// that these are the same observation. Retain them in the list, not a fill.
export function authorityObservations(features: GeographyFeature[]) {
  const grouped = new Map<string, GeographyFeature[]>()
  for (const row of features) if (row.ons_code) grouped.set(row.ons_code, [...(grouped.get(row.ons_code) ?? []), row])
  const mapped = [...grouped.values()].filter(rows => rows.length === 1).flat()
  return { grouped, mapped, ambiguous: [...grouped].filter(([, rows]) => rows.length > 1).map(([code]) => code) }
}
export function validLocation(row: Record<string, unknown>): row is Record<string, unknown> & MapLocation {
  return typeof row.location_id === 'string' && typeof row.latitude === 'number' && Number.isFinite(row.latitude) && Math.abs(row.latitude) <= 90
    && typeof row.longitude === 'number' && Number.isFinite(row.longitude) && Math.abs(row.longitude) <= 180
}
