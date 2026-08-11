# Workforce census 2024 — extracted values for verification

Source: <https://www.wfbenchmarking.nhs.uk/s/DA-workforce-census-FINAL-report-2024.pdf>

Every row below was read automatically from the PDF. **Check each parsed
value against the source text beside it before using any of these figures.**
Nothing here is marked verified in the database until you say so:

```sql
UPDATE workforce_census_metrics SET verified = 1 WHERE census_year = 2024;
```

Note: this census is not like-for-like between years — provider
participation varies, and the reports say so themselves. Do not difference
two years from this table without reading both years' participation notes.

| Page | Metric | Segment | Parsed | Unit | Source line |
| ---: | --- | --- | ---: | --- | --- |
| 6 | full_time_share | treatment_provider | 68 | percent | • 68% of the treatment provider workforce was contracted to work full time, a reduction from 72% in 2023 and 69% in 2022 |
| 6 | turnover_rate | delivery | 19 | percent | • 19% turnover rate in the delivery workforce (treatment provider and LERO combined) lower than the position in 2023 (25%), and a return to the position |
| 6 | turnover_rate | commissioning | 13 | percent | • 13% turnover rate for the commissioning workforce, lower than the rate in 2023 (22%) and in line with the reported position in 2022 (11%) |
| 6 | vacancy_rate | delivery | 8 | percent | • 8% vacancy rate in the delivery workforce (treatment provider and LERO combined) in line with the 10% reported in 2023 and 11% reported in 2022 |
| 6 | vacancy_rate | commissioning | 9 | percent | • 9% vacancy rate for the commissioning workforce, lower than the rate in previous years (2023, 12%, / 2022, 14%) |
| 6 | voluntary_sector_share | treatment_provider | 86 | percent | • 86% of the treatment provider workforce was in the voluntary sector, compared to 80% in 2023 and 78% reported in 2022. |
| 6 | volunteer_share | treatment_provider | 11 | percent | • 11% of the treatment provider workforce were unpaid or volunteers, an increase from 7% in 2023 and in line with the position in 2022 (12%) |
| 6 | wte_total | treatment_provider | 14,121 | wte | • There were 14,121 whole time equivalents (WTEs) reported in the 2024 census, 96% of the WTEs were in delivery services (treatment providers or |
| 9 | turnover_rate | commissioning | 19 | percent | turnover rate was 19%, lower than the position in 2023 (25%), and a return to the position reported in 2022 (19%). For commissioning staff, the vacancy |
| 9 | turnover_rate | unspecified | 13 | percent | rate was 9% and the turnover rate was 13%. This was a reduction on the position in 2023 (22%) and a return to the rate in 2022 (11%). Sickness rates |
| 9 | turnover_rate | unspecified | 24 | percent | • For drug and alcohol workers, the largest staff group, the vacancy rate was 10% (2023, 11% / 2022, 15%), and the turnover rate was 24% (2023, 29% / |
| 9 | turnover_rate | treatment_provider | 20 | percent | group for LEROs and treatment providers were 5% and 3% respectively, and the turnover rates were 20% and 4% respectively. |
| 9 | vacancy_rate | unspecified | 10 | percent | • For drug and alcohol workers, the largest staff group, the vacancy rate was 10% (2023, 11% / 2022, 15%), and the turnover rate was 24% (2023, 29% / |
| 10 | turnover_rate | unspecified | 8 | percent | staff group) the turnover rates varied from 8% in independent / private sector to 25% in the voluntary sector (1,236 leavers). |
| 10 | vacancy_rate | all_staff | 8 | percent | • The overall vacancy rate was 8%, this continued the reduction in the reported rate from 13% in 2022 and 10% in 2023. The vacancy rate ranged from 6% |
| 10 | vacancy_rate | unspecified | 6 | percent | vacancy rate ranged from 6% (LA delivered treatment) to 13% (NHS). |
| 11 | vacancy_rate | commissioning | 9 | percent | • The commissioning workforce reported a vacancy rate of 9% a reduction on the previous years (2023, 12% / 2022, 14%). This was above the 8% reported for |
| 12 | turnover_rate | unspecified | 19 | percent | • LEROs reported a 19% turnover rate (72 WTE leavers). This is below the 29% reported in 2023, and above the position in 2022 (8%). |
| 12 | vacancy_rate | unspecified | 7 | percent | • LEROs reported a vacancy rate of 7%, this is a reduction of the position reported in 23% in 2023 and a return to the position return in 2022 (8%). |
| 52 | turnover_rate | all_staff | 20 | percent | 20% turnover rate overall, with the voluntary sector having the highest rate at 21% (123 leavers) compared to 17% in the NHS (33 leavers) and 17% in the independent sector |
| 57 | vacancy_rate | all_staff | 8 | percent | • The overall vacancy rate was 8%, this continued the reduction in the reported rate from 13% in 2022 and 10% in 2023. The vacancy rate ranged from 6% in LA |
| 57 | vacancy_rate | unspecified | 6 | percent | the vacancy rate ranged from 6% (LA delivered treatment) to 14% (NHS). |
| 65 | vacancy_rate | commissioning | 9 | percent | The commissioning workforce reported a vacancy rate of 9% a reduction on the previous years (2023, 12% / 2022, 14%). This was above the 8% reported for delivery |
| 65 | vacancy_rate | commissioning | 7 | percent | commissioner (adults), reported a 7% vacancy rate. |
| 66 | turnover_rate | commissioning | 8 | percent | administrators. The largest workforce group, alcohol and drug commissioner (adults), reported an 8% turnover rate. |
| 69 | vacancy_rate | commissioning | 10 | percent | • The commissioning workforce reported a vacancy rate of 10%, a reduction on the previous years (2023, 12% / 2022, 14%). This was above the 8% reported |
| 73 | turnover_rate | ambiguous | 19 | percent | An overall turnover rate of 19% was reported, a decrease from 29% in 2023 (2022, 8%) and in line with the 19% reported by treatment providers in 2024. |
| 73 | vacancy_rate | all_staff | 7 | percent | LEROs reported an overall vacancy rate of 7%, a notable reduction on the 23% reported in 2023 and a return to the position reported in 2022 (8%). |
| 76 | vacancy_rate | unspecified | 8 | percent | • LEROs reported a vacancy rate of 8%, a sickness rate of 2% and a 20% (72 WTE leavers) turnover rate. |
