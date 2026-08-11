# Workforce census 2023 — extracted values for verification

Source: <https://s3.eu-west-2.amazonaws.com/nhsbn-static/Drugs%20&%20Alcohol%20Workforce/2023/Drug%20and%20Alcohol%20Workforce%20Census%202023%20-%20V3.pdf>

Every row below was read automatically from the PDF. **Check each parsed
value against the source text beside it before using any of these figures.**
Nothing here is marked verified in the database until you say so:

```sql
UPDATE workforce_census_metrics SET verified = 1 WHERE census_year = 2023;
```

Note: this census is not like-for-like between years — provider
participation varies, and the reports say so themselves. Do not difference
two years from this table without reading both years' participation notes.

| Page | Metric | Segment | Parsed | Unit | Source line |
| ---: | --- | --- | ---: | --- | --- |
| 3 | turnover_rate | unspecified | 25 | percent | 10% Vacancy rate 25% Turnover rate 12% Vacancy rate |
| 3 | vacancy_rate | unspecified | 10 | percent | 10% Vacancy rate 25% Turnover rate 12% Vacancy rate |
| 5 | turnover_rate | all_staff | 19 | percent | comparisons, this data should not be used to infer that the workforce size overall line with 2022 whereas the turnover rate was 19% in 2022 and 25% in 2023. For |
| 5 | vacancy_rate | unspecified | 11 | percent | For drug and alcohol workers, the largest staff group, vacancy rates were 11% |
| 5 | vacancy_rate | all_staff | 10 | percent | • An overall vacancy rate of 10% was reported ranging from 1% (LA delivered |
| 5 | vacancy_rate | unspecified | 3 | percent | 2022 2023 Change % largest staff group, drug and alcohol workers, vacancy rates ranged from 3% |
| 6 | turnover_rate | treatment_provider | 11 | percent | down from 12% in 2022. There was a higher proportion of staff on bands 1-3 for treatment provider staff. Turnover rates had increased from 11% in |
| 6 | vacancy_rate | unspecified | 23 | percent | • LEROs reported a vacancy rate of 23% (47 WTE vacancies), a sickness rate |
| 6 | vacancy_rate | commissioning | 12 | percent | • The commissioning workforce reported a vacancy rate of 12% in 2023, |
| 21 | vacancy_rate | commissioning | 12 | percent | The 12% vacancy rate for commissioning staff was slightly |
| 21 | vacancy_rate | unspecified | 11 | percent | vacancy rates reported were 11% (15% 2022), 6% (8% 2022) |
| 42 | vacancy_rate | all_staff | 10 | percent | • The overall vacancy rate was 10%, ranging from 1% (LA-delivered treatment • 11% of the workforce reported a disability compared to 10% in 2022. |
| 48 | turnover_rate | commissioning | 25 | percent | drug commissioner (adults), reported a 25% turnover rate. |
| 48 | vacancy_rate | commissioning | 12 | percent | The commissioning workforce reported a vacancy rate of 12% in 2023, a Commissioning staff reported a 1% staff sickness rate, lower than 2022 (2%). |
| 51 | turnover_rate | ambiguous | 11 | percent | ten roles, the largest of which was ‘commissioners (adult)’ at 31% (33% treatment provider staff. Turnover rates had increased from 11% in 2022 to |
| 51 | vacancy_rate | commissioning | 12 | percent | • The commissioning workforce reported a vacancy rate 12% in 2023, a |
| 53 | wte_total | unspecified | 469 | wte | Lived experience recovery organisations (LEROs) reported 469 whole time equivalent (WTE) staff in |
| 55 | turnover_rate | all_staff | 29 | percent | An overall turnover rate of 29% was above the 8% reported in |
| 55 | vacancy_rate | all_staff | 23 | percent | LEROs reported an overall vacancy rate of 23% compared to the |
| 55 | vacancy_rate | treatment_provider | 10 | percent | 10% vacancy rate reported by treatment providers. |
| 58 | vacancy_rate | unspecified | 23 | percent | • LEROs reported a vacancy rate of 23% (47 WTE vacancies), a sickness rate |
