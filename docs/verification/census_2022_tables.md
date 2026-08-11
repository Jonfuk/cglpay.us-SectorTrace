# Workforce census 2022 — extracted values for verification

Source: <https://www.hee.nhs.uk/sites/default/files/documents/Drug%20and%20Alcohol%20Workforce%20Census%202022%20Final%20Report%2020230301.pdf>

Every row below was read automatically from the PDF. **Check each parsed
value against the source text beside it before using any of these figures.**
Nothing here is marked verified in the database until you say so:

```sql
UPDATE workforce_census_metrics SET verified = 1 WHERE census_year = 2022;
```

Note: this census is not like-for-like between years — provider
participation varies, and the reports say so themselves. Do not difference
two years from this table without reading both years' participation notes.

| Page | Metric | Segment | Parsed | Unit | Source line |
| ---: | --- | --- | ---: | --- | --- |
| 5 | turnover_rate | all_staff | 11 | percent | Vacancy, sickness absence and turnover rates for all staff were 11%, 4% and 19% respectively. For alcohol and drug workers, the largest staff group, rates were 15%, 5% |
| 5 | turnover_rate | all_staff | 13 | percent | For alcohol and drug workers (the largest staff group) the turnover rates ranged from 13% (460 leavers) in the voluntary sector to 23% (52 leavers) in the NHS. For all staff the |
| 5 | turnover_rate | unspecified | 27 | percent | voluntary sector reported the highest turnover rate at 27%. NHS Digital reported a leaver rate of 11.9% for all NHS staff. |
| 5 | vacancy_rate | all_staff | 11 | percent | Vacancy rates ranged from 11% (voluntary sector) to 25% (LA-delivered treatment sector) for all staff. For the largest staff group, alcohol and drug workers, vacancy rates |
| 5 | wte_total | ambiguous | 11,851 | wte | Across all sectors 11,851 whole time equivalent (WTE) staff were reported, 11,269 WTE (95%) for the treatment provider workforce, 398 WTE (3%) commissioning staff |
| 7 | vacancy_rate | commissioning | 14 | percent | For commissioning roles specifically, the vacancy rate was 14%, turnover 11% and sickness absence 2%. The ethnicity profile for all local authority staff is generally in |
| 19 | vacancy_rate | unspecified | 14 | percent | responses results in a 14% vacancy rate, above the rate based on |
| 20 | turnover_rate | unspecified | 10 | percent | group responses results in a 10% turnover rate, |
| 31 | vacancy_rate | unspecified | 13 | percent | For alcohol and drug workers (the largest staff group) the vacancy rates ranged from 13% (220 vacancies) in the voluntary sector to 21% (81) in the NHS. Nursing |
| 33 | turnover_rate | unspecified | 13 | percent | For alcohol and drug workers (the largest staff group) the turnover rates ranged from 13% (460 leavers) in the voluntary sector to 23% (52 leavers) in the NHS. For all |
| 33 | turnover_rate | unspecified | 27 | percent | staff the voluntary sector reported the highest turnover rate at 27%. NHS Digital reported a leaver rate of 11.9% for all NHS staff between April 2021 and March 2022. |
| 40 | vacancy_rate | all_staff | 11 | percent | • Vacancy rates ranged from 11% (voluntary sector) to 25% (LA-delivered treatment sector) for all staff and for the largest staff group, alcohol and drug |
| 47 | vacancy_rate | unspecified | 14 | percent | 14% vacancy rate 2% sickness rate 11% turnover |
| 49 | vacancy_rate | commissioning | 14 | percent | • For commissioning roles specifically, the vacancy rate was 14%, turnover 11% and sickness absence 2%. These were generally in line or below the rates |
| 51 | wte_total | unspecified | 184 | wte | Lived experience recovery organisations (LEROs) reported 184 whole time equivalent (WTE) staff in |
| 53 | turnover_rate | unspecified | 20 | percent | The 20% turnover rate reported for peer |
| 53 | turnover_rate | unspecified | 40 | percent | reported a 40% turnover rate for this staff |
| 53 | vacancy_rate | unspecified | 42 | percent | The 42% vacancy rate reported for peer |
| 53 | vacancy_rate | unspecified | 11 | percent | compared to a vacancy rate of 11% for |
