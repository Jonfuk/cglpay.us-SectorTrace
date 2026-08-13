# Combating Drugs Partnership document candidates

Each row is a link that *looked* like a CDP strategy, needs assessment or
outcomes framework. **None of it is in the evidence base yet.** Open each
one, and mark the good ones verified:

```sql
UPDATE cdp_document_candidates SET verified = 1, verified_at = datetime('now')
 WHERE authority_ons_code = 'E10000016' AND candidate_url = '...';
```

Confidence counts matching signals (vocabulary, substance hint, file type).
It is a triage aid, not a probability, and does not mean a document is what
its link text claims.

## East Midlands

| Authority | Type (guess) | Conf. | Title | URL |
| --- | --- | ---: | --- | --- |
| Derbyshire | needs_assessment | 0.25 | Skip to content | <https://www.derbyshire.gov.uk/jsna> |
| Leicester | needs_assessment | 0.50 | Current adults' JSNA | <https://www.leicester.gov.uk/about-council/policies-plans-and-strategies/public-health/data-reports-and-strategies/joint-strategic-needs-assessment/adults-joint-strategic-needs-assessments> |
| Leicester | needs_assessment | 0.50 | Current children's JSNA | <https://www.leicester.gov.uk/about-council/policies-plans-and-strategies/public-health/data-reports-and-strategies/joint-strategic-needs-assessment/children-and-young-peoples-jsna> |
| Leicester | needs_assessment | 0.25 | Skip to main content | <https://www.leicester.gov.uk/jsna> |
| Nottinghamshire | needs_assessment | 0.25 | Skip to main content | <https://www.nottinghamshire.gov.uk/jsna> |

## East of England

| Authority | Type (guess) | Conf. | Title | URL |
| --- | --- | ---: | --- | --- |
| Bedford | needs_assessment | 0.50 | JSNA website | <https://www.bedford.gov.uk/social-care-and-health/public-health/bedford-borough-jsna> |
| Bedford | needs_assessment | 0.25 | Skip to main content | <https://www.bedford.gov.uk/jsna> |
| Central Bedfordshire | needs_assessment | 0.75 | Joint Strategic Needs Assessment - JSNA | <https://www.centralbedfordshire.gov.uk/public-health/joint-strategic-needs-assessment-jsna> |
| Hertfordshire | needs_assessment | 0.50 | What is the JSNA? | <https://www.hertfordshire.gov.uk/microsites/jsna/what-is-the-joint-strategic-needs-assessment.aspx> |
| Hertfordshire | needs_assessment | 0.50 | JSNA documents | <https://www.hertfordshire.gov.uk/microsites/jsna/jsna-documents.aspx> |
| Hertfordshire | needs_assessment | 0.50 | New JSNA Reports | <https://www.hertfordshire.gov.uk/microsites/jsna/new-jsna-reports.aspx> |
| Hertfordshire | needs_assessment | 0.50 | Request a needs assessment | <https://www.hertfordshire.gov.uk/microsites/jsna/request-a-needs-assessment.aspx> |
| Hertfordshire | needs_assessment | 0.25 | Skip to content | <https://www.hertfordshire.gov.uk/jsna> |
| Hertfordshire | needs_assessment | 0.25 | Home | <https://www.hertfordshire.gov.uk/microsites/jsna/hertfordshires-joint-strategic-needs-assessment.aspx> |
| Hertfordshire | needs_assessment | 0.25 | Accessibility Statement | <https://www.hertfordshire.gov.uk/microsites/jsna/accessibility-statement.aspx> |
| Luton | needs_assessment | 0.75 | JSNA overview health social care needs 2024 ( PDF , 9.95MB ) | <https://www.luton.gov.uk/sites/default/files/2026-05/JSNA%20overview%20health%20social%20care%20needs%202024_1.pdf> |
| Luton | needs_assessment | 0.25 | Skip to main content | <https://www.luton.gov.uk/jsna> |
| Thurrock | needs_assessment | 1.00 | JSNA – Special educational needs and disabilities, update to 2018 assessment ( PDF 1.36MB  | <https://www.thurrock.gov.uk/sites/default/files/assets/documents/jsna-send-update-202401-v01.pdf> |
| Thurrock | needs_assessment | 1.00 | Needs assessment – alcohol and substance abuse ( PDF 4MB ) | <https://www.thurrock.gov.uk/sites/default/files/assets/documents/alcoholsubstanceabuse-needs-2022-v01.pdf> |
| Thurrock | needs_assessment | 1.00 | JSNA – Children and Young People, update to 2017 assessment ( PDF 315.09KB ) | <https://www.thurrock.gov.uk/sites/default/files/assets/documents/jsna-children-young-people-update-202109-v01.pdf> |
| Thurrock | needs_assessment | 1.00 | Needs assessment – young persons substance misuse ( PDF 2.92MB ) | <https://www.thurrock.gov.uk/sites/default/files/assets/documents/na-youngpersonssubstancemisuse-201811-v01.pdf> |
| Thurrock | needs_assessment | 0.75 | JSNA – Whole systems tobacco control ( PDF 2.77MB ) | <https://www.thurrock.gov.uk/sites/default/files/assets/documents/jsna-tobacco-2021-v01.pdf> |
| Thurrock | needs_assessment | 0.75 | JSNA – Self-care in the context of living with long-term conditions ( PDF 3.1MB ) | <https://www.thurrock.gov.uk/sites/default/files/assets/documents/jsna-selfcarelongtermconditions-2020-v01.pdf> |
| Thurrock | needs_assessment | 0.75 | JSNA – Sexual violence and abuse ( PDF 4.88MB ) | <https://www.thurrock.gov.uk/sites/default/files/assets/documents/jsna-sexual-violence-abuse-202001-v01.pdf> |
| Thurrock | needs_assessment | 0.75 | JSNA – Work and health ( PDF 2.13MB ) | <https://www.thurrock.gov.uk/sites/default/files/assets/documents/jsna-work-health-2020-v01.pdf> |
| Thurrock | needs_assessment | 0.75 | JSNA – Special educational needs and disabilities ( PDF 4.08MB ) | <https://www.thurrock.gov.uk/sites/default/files/assets/documents/jsna-send-201809-v01.pdf> |
| Thurrock | needs_assessment | 0.75 | JSNA – Special educational needs and disabilities, summary ( PDF 1.67MB ) | <https://www.thurrock.gov.uk/sites/default/files/assets/documents/jsna-send-201809-summary-v01.pdf> |
| Thurrock | needs_assessment | 0.75 | JSNA – Adult mental health ( PDF 7.12MB ) | <https://www.thurrock.gov.uk/sites/default/files/assets/documents/jsna-adult-mental-health-201802-v01.pdf> |
| Thurrock | needs_assessment | 0.75 | JSNA – Adult mental health, summary ( PDF 3.11MB ) | <https://www.thurrock.gov.uk/sites/default/files/assets/documents/jsna-adult-mental-health-201802-summary-v01.pdf> |
| Thurrock | needs_assessment | 0.75 | JSNA – Children and young people's mental health ( PDF 4.27MB ) | <https://www.thurrock.gov.uk/sites/default/files/assets/documents/jsna-cyp-mental-health-201806-v01.pdf> |
| Thurrock | needs_assessment | 0.75 | JSNA – Children and young people's mental health, summary ( PDF 2.58MB ) | <https://www.thurrock.gov.uk/sites/default/files/assets/documents/jsna-cyp-mental-health-201806-summary-v01.pdf> |
| Thurrock | needs_assessment | 0.75 | JSNA – Whole systems obesity ( PDF 6.23MB ) | <https://www.thurrock.gov.uk/sites/default/files/assets/documents/jsna-obesity-201709-v01.pdf> |
| Thurrock | needs_assessment | 0.75 | JSNA – Children and Young People, 2017 ( PDF 3.74MB ) | <https://www.thurrock.gov.uk/sites/default/files/assets/documents/jsna-children-young-people-201707-v01.pdf> |
| Thurrock | needs_assessment | 0.75 | JSNA – Purfleet Integrated Healthy Living Centre ( PDF 5.29MB ) | <https://www.thurrock.gov.uk/sites/default/files/assets/documents/jsna-ihlc-purfleet-201602-v01.pdf> |
| Thurrock | needs_assessment | 0.75 | JSNA – Tilbury Integrated Healthy Living Centre ( PDF 7.18MB ) | <https://www.thurrock.gov.uk/sites/default/files/assets/documents/jsna-ihlc-tilbury-201511-v01.pdf> |
| Thurrock | needs_assessment | 0.75 | JSNA – Demographics and Population Change ( PDF 1.82MB ) | <https://www.thurrock.gov.uk/sites/default/files/assets/documents/jsna-demographics-population-v02.pdf> |
| Thurrock | needs_assessment | 0.75 | JSNA – Cancer Deep Dive ( PDF 5.28MB ) | <https://www.thurrock.gov.uk/sites/default/files/assets/documents/jsna-cancer-201511-v01.pdf> |
| Thurrock | needs_assessment | 0.75 | JSNA – Children and Young People, 2015 ( PDF 3.68MB ) | <https://www.thurrock.gov.uk/sites/default/files/assets/documents/jsna-children-young-people-201605-v01.pdf> |
| Thurrock | needs_assessment | 0.75 | JSNA – product for clinical commissioning groups ( PDF 6.33MB ) | <https://www.thurrock.gov.uk/sites/default/files/assets/documents/JSNA-product-clinical-commissioning-groups.pdf> |
| Thurrock | needs_assessment | 0.75 | JSNA – cover, contents and summary ( PDF 1.31MB ) | <https://www.thurrock.gov.uk/sites/default/files/assets/documents/JSNA-2012-pt0.pdf> |
| Thurrock | needs_assessment | 0.75 | JSNA – Chapter 1: Population ( PDF 1.14MB ) | <https://www.thurrock.gov.uk/sites/default/files/assets/documents/JSNA-2012-pt1.pdf> |
| Thurrock | needs_assessment | 0.75 | JSNA – Chapter 2: Wider Determinants of Health and Wellbeing ( PDF 4.49MB ) | <https://www.thurrock.gov.uk/sites/default/files/assets/documents/JSNA-2012-pt2.pdf> |
| Thurrock | needs_assessment | 0.75 | JSNA – Chapter 3: Lifestyles ( PDF 2.62MB ) | <https://www.thurrock.gov.uk/sites/default/files/assets/documents/JSNA-2012-pt3.pdf> |
| Thurrock | needs_assessment | 0.75 | JSNA – Chapter 4: Screening and Immunisation ( PDF 1.24MB ) | <https://www.thurrock.gov.uk/sites/default/files/assets/documents/JSNA-2012-pt4.pdf> |
| Thurrock | needs_assessment | 0.75 | JSNA – Chapter 5: Health and Wellbeing Status ( PDF 3.32MB ) | <https://www.thurrock.gov.uk/sites/default/files/assets/documents/JSNA-2012-pt5.pdf> |
| Thurrock | needs_assessment | 0.75 | JSNA – Chapter 6: Service Utilisation ( PDF 4.08MB ) | <https://www.thurrock.gov.uk/sites/default/files/assets/documents/JSNA-2012-pt6.pdf> |
| Thurrock | needs_assessment | 0.75 | JSNA – Chapter 7: Residents Opinions ( PDF 745.94KB ) | <https://www.thurrock.gov.uk/sites/default/files/assets/documents/JSNA-2012-pt7.pdf> |
| Thurrock | needs_assessment | 0.25 | Skip to main content | <https://www.thurrock.gov.uk/jsna> |

## London

| Authority | Type (guess) | Conf. | Title | URL |
| --- | --- | ---: | --- | --- |
| Bromley | needs_assessment | 0.75 | Special Educational Needs and Disability (SEND) Joint Strategic Needs Assessment (JSNA) 20 | <https://www.bromley.gov.uk/downloads/file/3899/special-educational-needs-and-disability-send-joint-strategic-needs-assessment-jsna-2025-to-2026> |
| Bromley | needs_assessment | 0.75 | Armed Forces Joint Strategic Needs Assessment (JSNA) 2025 (PDF - 2.53 MB) | <https://www.bromley.gov.uk/downloads/file/3884/armed-forces-joint-strategic-needs-assessment-jsna-2025> |
| Bromley | needs_assessment | 0.75 | Mortality and Morbidity Joint Strategic Needs Assessment (JSNA) chapter 2025 (PDF - 4.8 MB | <https://www.bromley.gov.uk/downloads/file/3468/mortality-and-morbidity-joint-strategic-needs-assessment-jsna-chapter-2025> |
| Bromley | needs_assessment | 0.50 | Bromley All-Age Mental Health and Wellbeing and Adults Learning Disabilities Needs Assessm | <https://www.bromley.gov.uk/downloads/file/3475/joint-strategic-needs-assessment-jsna-bromley-all-age-mental-health-and-wellbeing-and-adults-learning-disabilities-needs-assessment-phast-report> |
| Bromley | needs_assessment | 0.50 | Demography JSNA Chapter update 2024 | <https://www.bromley.gov.uk/downloads/download/375/joint-strategic-needs-assessment-jsna-demography> |
| Bromley | needs_assessment | 0.50 | Bromley suicide audit 2024 JSNA - Executive summary (PDF - 213.14 KB) | <https://www.bromley.gov.uk/downloads/file/3395/bromley-suicide-audit-2024-executive-summary> |
| Bromley | needs_assessment | 0.50 | COVID-19 Pandemic JSNA Chapter update 2024 (PDF - 562.46 KB) | <https://www.bromley.gov.uk/downloads/file/3217/covid-19-pandemic-jsna-chapter-2024> |
| Bromley | needs_assessment | 0.50 | Substance Misuse JSNA - Executive Summary 2022 (PDF - 218.92 KB) | <https://www.bromley.gov.uk/downloads/file/1961/substance-misuse-jsna-executive-summary> |
| Bromley | needs_assessment | 0.50 | Alcohol JSNA for 2022 (PDF - 2.76 MB) | <https://www.bromley.gov.uk/downloads/file/2364/joint-strategic-needs-assessment-jsna-alcohol-2022> |
| Bromley | needs_assessment | 0.50 | Sexual Health JSNA for 2019 (PDF - 2.04 MB) | <https://www.bromley.gov.uk/downloads/file/1963/sexual-health-jsna> |
| Bromley | needs_assessment | 0.50 | Children and Young People JSNA for 2024 | <https://www.bromley.gov.uk/downloads/download/378/children-and-young-people-joint-strategic-needs-assessment-jsna-2024> |
| Bromley | needs_assessment | 0.50 | Older people JSNA 2024 (PDF - 335.27 KB) | <https://www.bromley.gov.uk/downloads/file/3435/jsna-older-people-2024> |
| Bromley | needs_assessment | 0.25 | Skip to content | <https://www.bromley.gov.uk/jsna> |
| Greenwich | needs_assessment | 0.25 | Skip to main content | <https://www.royalgreenwich.gov.uk/jsna> |
| Haringey | needs_assessment | 0.75 | Alcohol abuse statistics ( pdf , 44 page(s) , 1.86 MB ) | <https://www.haringey.gov.uk/sites/default/files/2024-04/jsna-alcohol.pdf> |
| Haringey | needs_assessment | 0.75 | Drug misuse statistics ( pdf , 51 page(s) , 2.22 MB ) | <https://www.haringey.gov.uk/sites/default/files/2024-04/jsna-drugs.pdf> |
| Haringey | needs_assessment | 0.75 | Family Hubs needs assessment ( pdf , 74 page(s) , 4.91 MB ) | <https://www.haringey.gov.uk/sites/default/files/2024-06/jsna_family_hubs.pdf> |
| Haringey | needs_assessment | 0.75 | Older Peoples Needs Assessment ( pdf , 32 page(s) , 1.57 MB ) | <https://www.haringey.gov.uk/sites/default/files/2026-01/jsna-older-peoples-needs-assessment.pdf> |
| Haringey | needs_assessment | 0.75 | Sexual and reproductive health strategy: 2021 to 2024 ( pdf , 14 page(s) , 838.9 KB ) | <https://www.haringey.gov.uk/sites/default/files/2024-04/jsna-sexual_and_reproductive_health.pdf> |
| Haringey | needs_assessment | 0.50 | Adult mental health data ( pdf , 42 page(s) , 2.03 MB ) | <https://www.haringey.gov.uk/sites/default/files/2024-04/jsna_-adult_mental_health.pdf> |
| Haringey | needs_assessment | 0.50 | Air pollution data ( pdf , 20 page(s) , 2.57 MB ) | <https://www.haringey.gov.uk/sites/default/files/2024-04/jsna-air_pollution.pdf> |
| Haringey | needs_assessment | 0.50 | Children and young people ( pdf , 60 page(s) , 5.7 MB ) | <https://www.haringey.gov.uk/sites/default/files/2025-07/jsna-chidren-young-people.pdf> |
| Haringey | needs_assessment | 0.50 | Children and young people’s mental health data ( pdf , 31 page(s) , 2.39 MB ) | <https://www.haringey.gov.uk/sites/default/files/2024-04/jsna-childrens_and_young_peoples_mental_health.pdf> |
| Haringey | needs_assessment | 0.50 | Disability inequalities ( pdf , 39 page(s) , 13.37 MB ) | <https://www.haringey.gov.uk/sites/default/files/2026-04/jsna-disability-inequalities.pdf> |
| Haringey | needs_assessment | 0.50 | Heatwaves data ( pdf , 31 page(s) , 4.11 MB ) | <https://www.haringey.gov.uk/sites/default/files/2024-06/jsna-heatwaves.pdf> |
| Haringey | needs_assessment | 0.50 | Modern slavery data ( pdf , 16 page(s) , 303.46 KB ) | <https://www.haringey.gov.uk/sites/default/files/2024-04/jsna-modern_slavery.pdf> |
| Haringey | needs_assessment | 0.50 | Sexual health data ( pdf , 14 page(s) , 266.63 KB ) | <https://www.haringey.gov.uk/sites/default/files/2024-04/jsna-sexual_health.pdf> |
| Haringey | needs_assessment | 0.50 | South Tottenham Jewish population needs analysis | <https://www.haringey.gov.uk/sites/default/files/2024-04/jsna-jewish_needs.pdf> |
| Haringey | needs_assessment | 0.50 | Special Educational Needs and Disabilities data | <https://www.haringey.gov.uk/sites/default/files/2024-04/jsna-send.pdf> |
| Haringey | needs_assessment | 0.50 | Violence Against Women and Girls data ( pdf , 13 page(s) , 759.6 KB ) | <https://www.haringey.gov.uk/sites/default/files/2024-04/jsna-vawg.pdf> |
| Haringey | needs_assessment | 0.25 | Skip to main content | <https://www.haringey.gov.uk/jsna> |
| Harrow | needs_assessment | 0.25 | Skip to content | <https://www.harrow.gov.uk/jsna> |
| Havering | needs_assessment | 0.25 | Skip to content | <https://www.havering.gov.uk/jsna> |
| Hillingdon | needs_assessment | 0.25 | Skip to content | <https://www.hillingdon.gov.uk/jsna> |
| Hounslow | needs_assessment | 0.75 | What is the Joint Strategic Needs Assessment (JSNA) | <https://www.hounslow.gov.uk/joint-strategic-needs-assessment/joint-strategic-needs-assessment-1> |
| Hounslow | needs_assessment | 0.25 | Skip to content | <https://www.hounslow.gov.uk/jsna> |
| Kensington and Chelsea | cdp_strategy | 0.50 | Combating Drugs and Alcohol Partnership | <https://www.rbkc.gov.uk/health-and-social-care/public-health/combating-drugs-and-alcohol-partnership> |
| Kensington and Chelsea | needs_assessment | 0.50 | JSNA hub | <https://www.rbkc.gov.uk/health-and-social-care/public-health/joint-strategic-needs-assessment> |
| Merton | needs_assessment | 0.50 | Joint Strategic Needs Assessment: Abbreviations and acronyms | <https://www.merton.gov.uk/healthy-living/publichealth/jsna/abbreviations-and-acronyms> |
| Merton | needs_assessment | 0.25 | Skip to main content | <https://www.merton.gov.uk/jsna> |
| Merton | needs_assessment | 0.25 | The Merton Story: latest snapshot of local needs | <https://www.merton.gov.uk/healthy-living/publichealth/jsna/the-merton-story/latest> |
| Merton | needs_assessment | 0.25 | Ward health profiles 2026 | <https://www.merton.gov.uk/healthy-living/publichealth/jsna/health-profiles> |
| Newham | needs_assessment | 0.25 | Skip to content | <https://www.newham.gov.uk/jsna> |
| Redbridge | needs_assessment | 0.25 | Skip to main content | <https://www.redbridge.gov.uk/jsna> |
| Richmond upon Thames | needs_assessment | 0.50 | guide to using the new JSNA | <https://www.richmond.gov.uk/services/public_health/public_health_publications/jsna/jsna_user_guide> |
| Richmond upon Thames | needs_assessment | 0.50 | JSNA at a glance dashboard | <https://www.richmond.gov.uk/services/public_health/public_health_publications/jsna/jsna_at_a_glance> |
| Richmond upon Thames | needs_assessment | 0.25 | Skip to main content | <https://www.richmond.gov.uk/jsna> |
| Richmond upon Thames | needs_assessment | 0.25 | People | <https://www.richmond.gov.uk/services/public_health/public_health_publications/jsna/jsna_people> |
| Richmond upon Thames | needs_assessment | 0.25 | Start Well | <https://www.richmond.gov.uk/services/public_health/public_health_publications/jsna/jsna_start_well_dev> |
| Richmond upon Thames | needs_assessment | 0.25 | Live Well - Healthy Lifestyle and Behaviours | <https://www.richmond.gov.uk/services/public_health/public_health_publications/jsna/jsna_live_well_healthy_lifestyle> |
| Richmond upon Thames | needs_assessment | 0.25 | Live Well - Long term conditions | <https://www.richmond.gov.uk/services/public_health/public_health_publications/jsna/jsna_live_well> |
| Richmond upon Thames | needs_assessment | 0.25 | Age Well | <https://www.richmond.gov.uk/services/public_health/public_health_publications/jsna/jsna_age_well> |
| Richmond upon Thames | needs_assessment | 0.25 | Place | <https://www.richmond.gov.uk/services/public_health/public_health_publications/jsna/jsna_place> |
| Richmond upon Thames | needs_assessment | 0.25 | Community Voice | <https://www.richmond.gov.uk/services/public_health/public_health_publications/jsna/jsna_community_voice> |
| Richmond upon Thames | needs_assessment | 0.25 | Vulnerable Groups | <https://www.richmond.gov.uk/services/public_health/public_health_publications/jsna/jsna_vulnerable_groups> |
| Richmond upon Thames | needs_assessment | 0.25 | Protect Well | <https://www.richmond.gov.uk/services/public_health/public_health_publications/jsna/jsna_protect_well> |
| Southwark | needs_assessment | 0.25 | Skip to main content | <https://www.southwark.gov.uk/jsna> |
| Tower Hamlets | needs_assessment | 1.00 | Substance misuse needs assessment 2023 | <https://www.towerhamlets.gov.uk/Documents/Public-Health/JSNA/Tower-Hamlets-Substance-Misuse-Needs-Assessment-2023.docx> |
| Tower Hamlets | needs_assessment | 0.75 | JSNA summary document | <https://www.towerhamlets.gov.uk/Documents/Public-Health/JSNA/JSNA_Summary.pdf> |
| Tower Hamlets | needs_assessment | 0.75 | Maternity JSNA | <https://www.towerhamlets.gov.uk/Documents/Public-Health/JSNA/Maternity-JSNA.pdf> |
| Tower Hamlets | needs_assessment | 0.75 | SEND JSNA | <https://www.towerhamlets.gov.uk/Documents/Public-Health/JSNA/SEND-JSNA-2025.docx> |
| Tower Hamlets | needs_assessment | 0.75 | Healthy early years JSNA | <https://www.towerhamlets.gov.uk/Documents/Public-Health/JSNA/Healthy-early-years-JSNA.pdf> |
| Tower Hamlets | needs_assessment | 0.75 | Children's oral health JSNA | <https://www.towerhamlets.gov.uk/Documents/Public-Health/JSNA/ChildrensOralHealthJSNA.docx> |
| Tower Hamlets | needs_assessment | 0.75 | Children and Young People Mental Health Needs Assessment 2025 | <https://www.towerhamlets.gov.uk/Documents/Public-Health/JSNA/Tower-Hamlets-CYP-MH-Needs-Assessment-2025.pdf> |
| Tower Hamlets | needs_assessment | 0.75 | Adult Autism - JSNA Factsheet (2016) | <https://www.towerhamlets.gov.uk/Documents/Public-Health/JSNA/Adult_Autism_JSNA_Factsheet.pdf> |
| Tower Hamlets | needs_assessment | 0.75 | Cancer - JSNA Factsheet (2016) | <https://www.towerhamlets.gov.uk/Documents/Public-Health/JSNA/CancerJSNA.pdf> |
| Tower Hamlets | needs_assessment | 0.75 | Physical activity - JSNA Factsheet (2017) | <https://www.towerhamlets.gov.uk/Documents/Public-Health/JSNA/JSNA_Physical_Activity_2017.pdf> |
| Tower Hamlets | needs_assessment | 0.75 | Eye health JSNA 2018 | <https://www.towerhamlets.gov.uk/Documents/Public-Health/JSNA/Eye_health_JSNA_2018.pdf> |
| Tower Hamlets | needs_assessment | 0.75 | Older people JSNA Summary - June 2017 | <https://www.towerhamlets.gov.uk/Documents/Public-Health/JSNA/OP_JSNA_Summary_Factsheet.pdf> |
| Tower Hamlets | needs_assessment | 0.75 | Needs Assessment about Violence Against Women and Girls in Tower Hamlets | <https://www.towerhamlets.gov.uk/Documents/Public-Health/JSNA/VAWG-Needs-Assessment-2023.docx> |
| Tower Hamlets | needs_assessment | 0.75 | Carer’s health - JSNA factsheet (2016) | <https://www.towerhamlets.gov.uk/Documents/Public-Health/JSNA/Carers_Health_JSNA_Factsheet_Oct_2016.pdf> |
| Tower Hamlets | needs_assessment | 0.75 | Mental Wellbeing JSNA Factsheet 2016 | <https://www.towerhamlets.gov.uk/Documents/Public-Health/JSNA/Mental_wellbeing_factsheet_2016.pdf> |
| Tower Hamlets | needs_assessment | 0.75 | Spatial Planning and Health Needs Assessment (November 2023) | <https://www.towerhamlets.gov.uk/Documents/Public-Health/JSNA/Spatial-Planning-and-Health-JSNA.docx> |
| Tower Hamlets | needs_assessment | 0.75 | Pharmaceutical Needs Assessment Report | <https://www.towerhamlets.gov.uk/Documents/Public-Health/JSNA/Pharmaceutical-needs-assessment-report.pdf> |
| Tower Hamlets | needs_assessment | 0.75 | Programme budgeting JSNA factsheet | <https://www.towerhamlets.gov.uk/Documents/Public-Health/JSNA/Programme-Budgeting-JSNA-Factsheet.pdf> |
| Tower Hamlets | needs_assessment | 0.50 | The people JSNA | <https://www.towerhamlets.gov.uk/lgnl/health__social_care/Health-and-adult-social-care/Health-and-wellbeing/joint_strategic_needs_assessme/The-people-JSNA.aspx> |
| Tower Hamlets | needs_assessment | 0.50 | Domestic violence | <https://www.towerhamlets.gov.uk/Documents/Public-Health/JSNA/Domestic-Violence-JSNA-Factsheet.pdf> |
| Tower Hamlets | needs_assessment | 0.50 | Gambling (February 2016) | <https://www.towerhamlets.gov.uk/Documents/Public-Health/JSNA/Gambling_fact_sheet_2016.pdf> |
| Tower Hamlets | needs_assessment | 0.50 | Health and wellbeing Tobacco Control (updated 2015) | <https://www.towerhamlets.gov.uk/Documents/Public-Health/JSNA/Health_and_Wellbeing_Tobacco_control.pdf> |
| Tower Hamlets | needs_assessment | 0.50 | Learning disabilities needs assessment | <https://www.towerhamlets.gov.uk/Documents/Public-Health/JSNA/Learning-Disabilities-JSNA-2024.pptx> |
| Tower Hamlets | needs_assessment | 0.50 | Chronic obstructive pulmonary disease | <https://www.towerhamlets.gov.uk/Documents/Public-Health/TH-JSNA-Factsheet-COPD-2015.pdf> |
| Tower Hamlets | needs_assessment | 0.50 | Health Equity in Primary Care | <https://www.towerhamlets.gov.uk/Documents/Public-Health/TH-JSNA-Health-Equity-in-Primary-Care-2014.pdf> |
| Tower Hamlets | needs_assessment | 0.50 | Oral health of adults | <https://www.towerhamlets.gov.uk/Documents/Public-Health/TH-JSNA-oral-health-of-adults-2015.pdf> |
| Tower Hamlets | needs_assessment | 0.50 | Type 2 diabetes | <https://www.towerhamlets.gov.uk/Documents/Public-Health/JSNA/Type_2_diabetes.pdf> |
| Tower Hamlets | needs_assessment | 0.50 | Falls | <https://www.towerhamlets.gov.uk/Documents/Public-Health/JSNA/Falls_JSNA_Factsheet_2015.pdf> |
| Tower Hamlets | needs_assessment | 0.50 | Last Years of Life | <https://www.towerhamlets.gov.uk/Documents/Public-Health/JSNA/Lastyearsoflife_JSNA_2015_allparts.pdf> |
| Tower Hamlets | needs_assessment | 0.50 | Loneliness and isolation in older people | <https://www.towerhamlets.gov.uk/Documents/Public-Health/JSNA/Lonelinesss_and_Isolation_in_older_people.pdf> |
| Tower Hamlets | needs_assessment | 0.50 | Oral health of older people | <https://www.towerhamlets.gov.uk/Documents/Public-Health/TH-JSNA-Factsheet-oral-health-older-people-2015.pdf> |
| Tower Hamlets | needs_assessment | 0.50 | Adult Social Care Needs Assessment | <https://www.towerhamlets.gov.uk/Documents/Public-Health/JSNA/Adult-Social-Care-JSNA.pptx> |
| Tower Hamlets | needs_assessment | 0.50 | Somali health profile | <https://www.towerhamlets.gov.uk/Documents/Public-Health/JSNA/Somali-health-profile.docx> |
| Tower Hamlets | needs_assessment | 0.50 | HFT Policy Review Report 5 year review | <https://www.towerhamlets.gov.uk/Documents/Public-Health/JSNA/HFT-Policy-Review-Report-5-year-review.pdf> |
| Tower Hamlets | needs_assessment | 0.50 | Climate change and health topic paper | <https://www.towerhamlets.gov.uk/Documents/Public-Health/JSNA/Climate-change-and-health-topic-paper.pdf> |
| Tower Hamlets | needs_assessment | 0.50 | Asthma | <https://www.towerhamlets.gov.uk/Documents/Public-Health/TH-JSNA-Factsheet-Asthma-2015.pdf> |
| Tower Hamlets | needs_assessment | 0.50 | Autism | <https://www.towerhamlets.gov.uk/Documents/Public-Health/JSNA/Autism-JSNA-Factsheet.pdf> |
| Tower Hamlets | needs_assessment | 0.50 | Physical Activity in Tower Hamlets | <https://www.towerhamlets.gov.uk/Documents/Public-Health/JSNA/Health-Needs-Assessment-for-Physical-Activity-in-Tower-Hamlets.docx> |
| Tower Hamlets | needs_assessment | 0.50 | Health and wellbeing tobacco control | <https://www.towerhamlets.gov.uk/Documents/Public-Health/JSNA/Tobacco-JSNA-July-2013-FInal.pdf> |
| Tower Hamlets | needs_assessment | 0.50 | Homelessness and health | <https://www.towerhamlets.gov.uk/Documents/Public-Health/JSNA/Homeless_Health_JSNA.pdf> |
| Tower Hamlets | needs_assessment | 0.50 | Mental Health JSNA February 2019 | <https://www.towerhamlets.gov.uk/Documents/Public-Health/JSNA/Mental-Health-JSNA-February-2019.pptx> |
| Tower Hamlets | needs_assessment | 0.50 | Offender health | <https://www.towerhamlets.gov.uk/Documents/Public-Health/JSNA/Offender_Health_JSNA_Fact_Sheet.pdf> |
| Tower Hamlets | needs_assessment | 0.50 | Environmental Health - Trading standards and public health 2022 | <https://www.towerhamlets.gov.uk/Documents/Public-Health/JSNA/Environmental-Health-Trading-Standards-and-Public-Health.docx> |
| Tower Hamlets | needs_assessment | 0.50 | Tuberculosis | <https://www.towerhamlets.gov.uk/Documents/Public-Health/TB-JSNA-Factsheet.pdf> |
| Tower Hamlets | needs_assessment | 0.50 | Hot food takeaway report | <https://www.towerhamlets.gov.uk/Documents/Public-Health/JSNA/Hot-food-takeaways-report.docx> |
| Tower Hamlets | needs_assessment | 0.50 | HIA Implementation programme report | <https://www.towerhamlets.gov.uk/Documents/Public-Health/JSNA/HIA-implementation-programme-report.docx> |
| Tower Hamlets | needs_assessment | 0.50 | Population needs | <https://www.towerhamlets.gov.uk/Documents/Borough_statistics/JSNA/Tower_Hamlets_Mental_Health_JSNA_Part_1_Population_Needs.pdf> |
| Tower Hamlets | needs_assessment | 0.50 | Facts and figures | <https://www.towerhamlets.gov.uk/Documents/Borough_statistics/JSNA/Tower_Hamlets_Mental_Health_JSNA_Part_2_Facts_and_Figures.pdf> |
| Tower Hamlets | needs_assessment | 0.50 | Recommendations | <https://www.towerhamlets.gov.uk/Documents/Borough_statistics/JSNA/Tower_Hamlets_Mental_Health_JSNA_Part_3_Recommendations.pdf> |
| Tower Hamlets | needs_assessment | 0.50 | Evidence reviews | <https://www.towerhamlets.gov.uk/Documents/Borough_statistics/JSNA/Evidence-Reviews-to-support-Tower-Hamlets-Mental-Health-Strategy.pdf> |
| Tower Hamlets | needs_assessment | 0.25 | Skip to content | <https://www.towerhamlets.gov.uk/jsna> |
| Tower Hamlets | needs_assessment | 0.25 | Sexual and Reproductive Health | <https://www.towerhamlets.gov.uk/Documents/Public-Health/JSNA/Sexual-and-Reproductive-Health-JSNA.pptx> |
| Tower Hamlets | needs_assessment | 0.25 | Food poverty [updated 2020] | <https://www.towerhamlets.gov.uk/Documents/Public-Health/JSNA/Food-Poverty-JSNA-accessible-07-09-20.pptx> |
| Wandsworth | needs_assessment | 0.50 | guide to using the new JSNA | <https://www.wandsworth.gov.uk/health-and-social-care/public-health/public-health-publications/jsna/jsna-user-guide/> |
| Wandsworth | needs_assessment | 0.50 | JSNA at a glance dashboard | <https://www.wandsworth.gov.uk/health-and-social-care/public-health/public-health-publications/jsna/jsna-at-a-glance/> |
| Wandsworth | needs_assessment | 0.25 | Skip to main content | <https://www.wandsworth.gov.uk/jsna> |
| Wandsworth | needs_assessment | 0.25 | People | <https://www.wandsworth.gov.uk/health-and-social-care/public-health/public-health-publications/jsna/jsna-people/> |
| Wandsworth | needs_assessment | 0.25 | Place | <https://www.wandsworth.gov.uk/health-and-social-care/public-health/public-health-publications/jsna/jsna-place/> |
| Wandsworth | needs_assessment | 0.25 | Start Well | <https://www.wandsworth.gov.uk/health-and-social-care/public-health/public-health-publications/jsna/jsna-start-well/> |
| Wandsworth | needs_assessment | 0.25 | Live Well - Healthy lifestyle and behaviours | <https://www.wandsworth.gov.uk/health-and-social-care/public-health/public-health-publications/jsna/jsna-live-well-healthy-lifestyle-and-behaviours/> |
| Wandsworth | needs_assessment | 0.25 | Live Well - Long term conditions | <https://www.wandsworth.gov.uk/health-and-social-care/public-health/public-health-publications/jsna/jsna-live-well-long-term-conditions/> |
| Wandsworth | needs_assessment | 0.25 | Age Well | <https://www.wandsworth.gov.uk/health-and-social-care/public-health/public-health-publications/jsna/jsna-age-well/> |
| Wandsworth | needs_assessment | 0.25 | Protect Well | <https://www.wandsworth.gov.uk/health-and-social-care/public-health/public-health-publications/jsna/jsna-protect-well/> |
| Wandsworth | needs_assessment | 0.25 | Vulnerable Groups | <https://www.wandsworth.gov.uk/health-and-social-care/public-health/public-health-publications/jsna/jsna-vulnerable-groups/> |
| Wandsworth | needs_assessment | 0.25 | Community Voice | <https://www.wandsworth.gov.uk/health-and-social-care/public-health/public-health-publications/jsna/jsna-community-voice/> |
| Westminster | cdp_strategy | 0.50 | Combating Drugs and Alcohol Partnership | <https://www.westminster.gov.uk/cdap> |

## North East

| Authority | Type (guess) | Conf. | Title | URL |
| --- | --- | ---: | --- | --- |
| County Durham | needs_assessment | 0.25 | Skip to content | <https://www.durham.gov.uk/jsna> |

## North West

| Authority | Type (guess) | Conf. | Title | URL |
| --- | --- | ---: | --- | --- |
| Bury | needs_assessment | 0.25 | Skip to main content | <https://www.bury.gov.uk/jsna> |
| Cheshire East | needs_assessment | 0.50 | About JSNA | <https://www.cheshireeast.gov.uk/council-and-democracy/council-information/jsna/about-jsna> |
| Cheshire East | needs_assessment | 0.50 | Cheshire East Joint Outcomes Framework | <https://www.cheshireeast.gov.uk/council-and-democracy/council-information/jsna/cheshire-east-joint-outcomes-framework> |
| Cheshire East | needs_assessment | 0.50 | JSNA products | <https://www.cheshireeast.gov.uk/council-and-democracy/council-information/jsna/jsna-products> |
| Cheshire East | needs_assessment | 0.25 | Skip to content | <https://www.cheshireeast.gov.uk/jsna> |
| Cheshire East | needs_assessment | 0.25 | Overviews of health and wellbeing | <https://www.cheshireeast.gov.uk/council-and-democracy/council-information/jsna/overviews-of-health-and-wellbeing> |
| Cheshire East | needs_assessment | 0.25 | Healthier places | <https://www.cheshireeast.gov.uk/council-and-democracy/council-information/jsna/healthier-places> |
| Cheshire East | needs_assessment | 0.25 | Starting well | <https://www.cheshireeast.gov.uk/council-and-democracy/council-information/jsna/starting-well> |
| Cheshire East | needs_assessment | 0.25 | Mental wellbeing | <https://www.cheshireeast.gov.uk/council-and-democracy/council-information/jsna/mental-wellbeing> |
| Cheshire East | needs_assessment | 0.25 | Ageing well | <https://www.cheshireeast.gov.uk/council-and-democracy/council-information/jsna/ageing-well> |
| Rochdale | needs_assessment | 0.50 | JSNA summary | <https://www.rochdale.gov.uk/joint-strategic-needs-assessment-jsna/joint-strategic-needs-assessment> |
| Rochdale | needs_assessment | 0.25 | Skip to content | <https://www.rochdale.gov.uk/jsna> |
| Rochdale | needs_assessment | 0.25 | Borough profile | <https://www.rochdale.gov.uk/joint-strategic-needs-assessment-jsna/borough-profile-joint-strategic-needs-assessment-jsna> |
| Rochdale | needs_assessment | 0.25 | Early Years | <https://www.rochdale.gov.uk/joint-strategic-needs-assessment-jsna/early-years-joint-strategic-needs-assessment-jsna> |
| Rochdale | needs_assessment | 0.25 | Developing Well | <https://www.rochdale.gov.uk/joint-strategic-needs-assessment-jsna/developing-well-joint-strategic-needs-assessment-jsna> |
| Rochdale | needs_assessment | 0.25 | Early Adulthood | <https://www.rochdale.gov.uk/joint-strategic-needs-assessment-jsna/early-adulthood-joint-strategic-needs-assessment-jsna> |
| Rochdale | needs_assessment | 0.25 | Working Well | <https://www.rochdale.gov.uk/joint-strategic-needs-assessment-jsna/working-well-joint-strategic-needs-assessment-jsna> |
| Rochdale | needs_assessment | 0.25 | Adult wellness | <https://www.rochdale.gov.uk/joint-strategic-needs-assessment-jsna/adult-wellness-jsna> |
| Rochdale | needs_assessment | 0.25 | Ageing well | <https://www.rochdale.gov.uk/joint-strategic-needs-assessment-jsna/ageing-well-jsna> |
| Rochdale | needs_assessment | 0.25 | Frailty in older age | <https://www.rochdale.gov.uk/joint-strategic-needs-assessment-jsna/frailty-older-age-jsna> |
| Rochdale | needs_assessment | 0.25 | Communities of interest | <https://www.rochdale.gov.uk/joint-strategic-needs-assessment-jsna/communities-interest-jsna> |
| Rochdale | needs_assessment | 0.25 | Mortality and illness | <https://www.rochdale.gov.uk/joint-strategic-needs-assessment-jsna/mortality-illness-jsna> |
| Rochdale | needs_assessment | 0.25 | Health and social care services | <https://www.rochdale.gov.uk/joint-strategic-needs-assessment-jsna/health-social-care-services-jsna> |
| Rochdale | needs_assessment | 0.25 | Wider determinants of health | <https://www.rochdale.gov.uk/joint-strategic-needs-assessment-jsna/wider-determinants-health-jsna> |
| Sefton | needs_assessment | 0.75 | Joint Strategic Needs Assessment (JSNA) | <https://www.sefton.gov.uk/your-council/plans-policies/business-intelligence-insight-performance/joint-strategic-needs-assessment-jsna/> |
| Sefton | needs_assessment | 0.75 | JSNA Highlight Report | <https://www.sefton.gov.uk/media/1884/jsna-highlight-report-2018.pdf> |
| Sefton | needs_assessment | 0.75 | JSNA 2018 Vulnerable Adults | <https://www.sefton.gov.uk/media/1888/jsna-2018-vulnerable-adults.pdf> |
| Sefton | needs_assessment | 0.75 | JSNA 2022 Wider Determinants | <https://www.sefton.gov.uk/media/6833/jsna-2022-wider-determinants.pdf> |
| Sefton | cdp_strategy | 0.50 | Combating Drugs Partnership | <https://www.sefton.gov.uk/public-health/combating-drugs-partnership/> |
| Sefton | needs_assessment | 0.50 | JSNA Overview | <https://www.sefton.gov.uk/your-council/plans-policies/business-intelligence-insight-performance/joint-strategic-needs-assessment-jsna/jsna-overview/> |
| Sefton | needs_assessment | 0.50 | JSNA 2014 | <https://www.sefton.gov.uk/your-council/plans-policies/business-intelligence-insight-performance/joint-strategic-needs-assessment-jsna/jsna-2014/> |
| Sefton | needs_assessment | 0.50 | Cancer JSNA for Cheshire and Merseyside | <https://www.sefton.gov.uk/your-council/plans-policies/business-intelligence-insight-performance/joint-strategic-needs-assessment-jsna/cancer-jsna-for-cheshire-and-merseyside/> |
| Sefton | needs_assessment | 0.50 | Adults At Risk | <https://www.sefton.gov.uk/media/6835/jsna-2023-adults-at-risk.pdf> |
| Sefton | needs_assessment | 0.50 | Children | <https://www.sefton.gov.uk/media/1885/jsna-2021-children.pdf> |
| Sefton | needs_assessment | 0.50 | Health | <https://www.sefton.gov.uk/media/6832/jsna-2023-health.pdf> |
| Sefton | needs_assessment | 0.50 | Special Educational Needs | <https://www.sefton.gov.uk/media/6934/send-jsna-2023-final.pdf> |
| Sefton | needs_assessment | 0.50 | Wider Determinants | <https://www.sefton.gov.uk/media/6834/jsna-2023-wider-determinants.pdf> |
| Sefton | needs_assessment | 0.25 | Skip to content | <https://www.sefton.gov.uk/jsna> |
| Sefton | needs_assessment | 0.25 | Additional Supporting Analysis 2017 | <https://www.sefton.gov.uk/your-council/plans-policies/business-intelligence-insight-performance/joint-strategic-needs-assessment-jsna/additional-supporting-analysis-2017/> |
| Tameside | needs_assessment | 0.75 | Joint Strategic Needs Assessment (JSNA) | <https://www.tameside.gov.uk/publichealth/healthandwellbeing> |
| Trafford | needs_assessment | 0.75 | Joint Strategic Needs Assessment (JSNA) Information on the current and future health and s | <https://www.trafford.gov.uk/health-and-wellbeing/joint-strategic-needs-assessment-jsna> |
| Warrington | needs_assessment | 1.00 | Rapid Desk Top Health Needs Assessment - Alcohol (1.16 MB) | <https://www.warrington.gov.uk/sites/default/files/2024-03/Rapid%20Desk%20Top%20Health%20Needs%20Assessment%20-%20Alcohol.pdf> |
| Warrington | needs_assessment | 0.75 | Warrington JSNA Core Document 2025 (2.85 MB) | <https://www.warrington.gov.uk/sites/default/files/2026-07/Warrington%20JSNA%20Core%20Document%202025.pdf> |
| Warrington | needs_assessment | 0.75 | JSNA Demographics 2021 (2.8 MB) | <https://www.warrington.gov.uk/sites/default/files/2022-04/JSNA%20Demographics%202021.pdf> |
| Warrington | needs_assessment | 0.75 | JSNA - SEND Review 2025 (6.03 MB) | <https://www.warrington.gov.uk/sites/default/files/2026-03/JSNA%20SEND%20Review%202025.pdf> |
| Warrington | needs_assessment | 0.75 | Adult Safeguarding JSNA 2019 (1.21 MB) | <https://www.warrington.gov.uk/sites/default/files/2019-11/adult_safeguarding_jsna_2019_final_0.pdf> |
| Warrington | needs_assessment | 0.75 | JSNA Warrington Deprivation profile report 2019 (3.98 MB) | <https://www.warrington.gov.uk/sites/default/files/2021-11/warrington_2019_deprivation_profile_report.pdf> |
| Warrington | needs_assessment | 0.50 | Cancer - 2019 (3.58 MB) | <https://www.warrington.gov.uk/sites/default/files/2020-01/warrington_cancer_jsna_2019_final.pdf> |
| Warrington | needs_assessment | 0.25 | Skip to main content | <https://www.warrington.gov.uk/jsna> |

## South East

| Authority | Type (guess) | Conf. | Title | URL |
| --- | --- | ---: | --- | --- |
| Brighton and Hove | needs_assessment | 0.75 | Joint Strategic Needs Assessment (JSNA) | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna> |
| Brighton and Hove | needs_assessment | 0.75 | Drugs and alcohol needs assessment 2022 | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/brighton-hove-drugs-and-alcohol-needs-assessment-2022> |
| Brighton and Hove | needs_assessment | 0.50 | JSNA Health and Wellbeing in Brighton & Hove Executive Summary | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/jsna-headline-summary-reports/jsna-health-and-wellbeing-brighton-hove-executive-summary> |
| Brighton and Hove | needs_assessment | 0.50 | JSNA Population in Brighton & Hove Executive Summary | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/jsna-headline-summary-reports/jsna-population-brighton-hove-executive-summary> |
| Brighton and Hove | needs_assessment | 0.50 | Pharmaceutical Needs Assessment in Brighton & Hove Executive Summary | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/jsna-headline-summary-reports/pharmaceutical-needs-assessment-brighton-hove-executive-summary> |
| Brighton and Hove | needs_assessment | 0.50 | Special Educational Needs and Disabilities in-depth needs assessment executive summary | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/healthy-people/special-educational-needs-and-disabilities-depth-needs-assessment-executive-summary> |
| Brighton and Hove | needs_assessment | 0.50 | In depth needs assessments | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/key-evidence-reports-and-briefings/depth-needs-assessments> |
| Brighton and Hove | needs_assessment | 0.50 | Local area profile for alcohol | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assement-jsna/area-profiles/local-area-profile-alcohol> |
| Brighton and Hove | needs_assessment | 0.50 | See the JSNA Annual report 2025 and programme HWB report | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/joint-strategic-needs-assessment-programme-updates> |
| Brighton and Hove | needs_assessment | 0.50 | Sensory loss JSNA summary | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/sensory-loss-jsna-summary> |
| Brighton and Hove | needs_assessment | 0.50 | Special Educational Needs and Disabilities, Learning Disabilities and Neurodiversity in-de | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/healthy-people/special-educational-needs-and-disabilities-learning-disabilities-and-neurodiversity-depth-needs> |
| Brighton and Hove | needs_assessment | 0.50 | Strategic Assessment of Crime and Community Safety 2024 | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/healthy-places/strategic-assessment-crime-and-community-safety-2025> |
| Brighton and Hove | needs_assessment | 0.50 | Pharmaceutical Needs Assessment in Brighton & Hove | <https://www.brighton-hove.gov.uk/health-and-wellbeing/joint-strategic-needs-assessment-jsna/pharmaceutical-needs-assessment-brighton-hove> |
| Brighton and Hove | needs_assessment | 0.50 | 2024 JSNA executive summary | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/jsna-headline-summary-reports/jsna-executive-summary> |
| Brighton and Hove | needs_assessment | 0.50 | 2024 JSNA population summary | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/jsna-headline-summary-reports/jsna-population-summary> |
| Brighton and Hove | needs_assessment | 0.50 | Executive summary of the JSNA PDF version | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assement-jsna/jsna-headline-summary-reports> |
| Brighton and Hove | needs_assessment | 0.50 | Mental health and wellbeing in Brighton & Hove JSNA report and summary | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/mental-health-and-wellbeing-brighton-hove-jsna-report-and-summary> |
| Brighton and Hove | needs_assessment | 0.50 | view the JSNA review stakeholder feedback | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna-review-2023> |
| Brighton and Hove | needs_assessment | 0.25 | Annual Reports of the Director of Public Health | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/key-evidence-reports-and-briefings/annual-reports-director-public-health> |
| Brighton and Hove | needs_assessment | 0.25 | Brighton & Hove 2021 Census briefing | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/population-and-population-groups/brighton-hove-2021-census-briefing> |
| Brighton and Hove | needs_assessment | 0.25 | Population groups summary statistics | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/population-and-population-groups/population-groups-summary-statistics> |
| Brighton and Hove | needs_assessment | 0.25 | Migration | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/population-and-population-groups/migration> |
| Brighton and Hove | needs_assessment | 0.25 | Physical disabilities and impairment | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/population-and-population-groups/physical-disabilities-and-impairments> |
| Brighton and Hove | needs_assessment | 0.25 | Carers | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/population-and-population-groups/carers> |
| Brighton and Hove | needs_assessment | 0.25 | Children in care | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/population-and-population-groups/children-care> |
| Brighton and Hove | needs_assessment | 0.25 | Ethnicity | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/population-and-population-groups/ethnicity> |
| Brighton and Hove | needs_assessment | 0.25 | Ex-service personnel | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/population-and-population-groups/ex-service-personnel> |
| Brighton and Hove | needs_assessment | 0.25 | Gender | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/population-and-population-groups/gender> |
| Brighton and Hove | needs_assessment | 0.25 | Gender Identity and Trans, Non-Binary and Intersex (TNBI) people | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/population-and-population-groups/gender-identity-and-trans-non-binary-and-intersex-tnbi-people> |
| Brighton and Hove | needs_assessment | 0.25 | Learning disabilities | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/population-and-population-groups/learning-disabilities> |
| Brighton and Hove | needs_assessment | 0.25 | Pregnancy and maternity | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/population-and-population-groups/pregnancy-and-maternity> |
| Brighton and Hove | needs_assessment | 0.25 | Religion, faith and belief | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/population-and-population-groups/religion-faith-and-belief> |
| Brighton and Hove | needs_assessment | 0.25 | Sexual orientation | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/population-and-population-groups/sexual-orientation> |
| Brighton and Hove | needs_assessment | 0.25 | Sex workers | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/population-and-population-groups/sex-workers> |
| Brighton and Hove | needs_assessment | 0.25 | Students | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/population-and-population-groups/students> |
| Brighton and Hove | needs_assessment | 0.25 | Archived documents for population and population groups | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/population-and-population-groups/population-and-population-groups-archive> |
| Brighton and Hove | needs_assessment | 0.25 | Healthy places summary | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/healthy-places/healthy-places-summary-report> |
| Brighton and Hove | needs_assessment | 0.25 | Healthy places data report | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/healthy-places/healthy-places-data-reports> |
| Brighton and Hove | needs_assessment | 0.25 | Healthy places: Related reports and briefings | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/healthy-places/healthy-places-related-reports-and-briefings> |
| Brighton and Hove | needs_assessment | 0.25 | Healthy places: External links | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/healthy-places/healthy-places-external-links> |
| Brighton and Hove | needs_assessment | 0.25 | Healthy places archive | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/healthy-places/healthy-places-archive> |
| Brighton and Hove | needs_assessment | 0.25 | Life expectancy | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/healthy-lives/life-expectancy> |
| Brighton and Hove | needs_assessment | 0.25 | Healthy lives: Starting well | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assement-jsna/healthy-lives/healthy-lives-starting-well> |
| Brighton and Hove | needs_assessment | 0.25 | Healthy lives: Living well | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/healthy-lives/healthy-lives-living-well> |
| Brighton and Hove | needs_assessment | 0.25 | Healthy lives: Ageing well | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/healthy-lives/healthy-lives-ageing-well> |
| Brighton and Hove | needs_assessment | 0.25 | Health protection | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/healthy-lives/health-protection> |
| Brighton and Hove | needs_assessment | 0.25 | Healthy lives: Related reports and briefings | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/healthy-lives/healthy-lives-related-reports-and-briefings> |
| Brighton and Hove | needs_assessment | 0.25 | Healthy lives: External links | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/healthy-lives/healthy-lives-external-links> |
| Brighton and Hove | needs_assessment | 0.25 | Healthy lives archive | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/healthy-lives-archive> |
| Brighton and Hove | needs_assessment | 0.25 | Healthy people: Starting well | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/healthy-people/healthy-people-starting-well> |
| Brighton and Hove | needs_assessment | 0.25 | Healthy people: Living well | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/healthy-people/healthy-people-living-well> |
| Brighton and Hove | needs_assessment | 0.25 | Healthy people: Ageing well | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/healthy-people/healthy-people-ageing-well> |
| Brighton and Hove | needs_assessment | 0.25 | Healthy people: Dying well | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/healthy-people/healthy-people-dying-well> |
| Brighton and Hove | needs_assessment | 0.25 | Healthy people: Related reports and briefings | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/healthy-people/healthy-people-related-reports-and-briefings> |
| Brighton and Hove | needs_assessment | 0.25 | Healthy people: External links | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/healthy-people/healthy-people-external-links> |
| Brighton and Hove | needs_assessment | 0.25 | Healthy people archive | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/healthy-people/healthy-people-archive> |
| Brighton and Hove | needs_assessment | 0.25 | Safe and Well at School Survey (SAWSS) | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/key-evidence-reports-and-briefings/safe-and-well-school-survey-sawss> |
| Brighton and Hove | needs_assessment | 0.25 | City tracker | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/key-evidence-reports-and-briefings/city-tracker> |
| Brighton and Hove | needs_assessment | 0.25 | Health Counts | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/key-evidence-reports-and-briefings/health-counts> |
| Brighton and Hove | needs_assessment | 0.25 | Census 2021 | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assement-jsna/reports-and-briefings/census-2021> |
| Brighton and Hove | needs_assessment | 0.25 | Briefings | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/reports-and-briefings/briefings> |
| Brighton and Hove | needs_assessment | 0.25 | Evidence reviews | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/key-evidence-reports-and-briefings/evidence-reviews> |
| Brighton and Hove | needs_assessment | 0.25 | Dashboards | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/reports-and-briefings/dashboards> |
| Brighton and Hove | needs_assessment | 0.25 | Reports and briefings - external links | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/key-evidence-reports-and-briefings/other-resources> |
| Brighton and Hove | needs_assessment | 0.25 | Reports and briefings groups archive | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/key-evidence-reports-and-briefings/reports-and-briefings-groups-archive> |
| Brighton and Hove | needs_assessment | 0.25 | Integrated community team profiles | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/area-profiles/integrated-community-team-profiles> |
| Brighton and Hove | needs_assessment | 0.25 | Primary Care Network profiles | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/area-profiles/primary-care-network-pcn-profiles> |
| Brighton and Hove | needs_assessment | 0.25 | Local area profile for gambling related harm | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/area-profiles/local-area-profile-gambling-related-harm> |
| Brighton and Hove | needs_assessment | 0.25 | Local Insight | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/area-profiles/local-insight-community-insight> |
| Brighton and Hove | needs_assessment | 0.25 | National tools with local data | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/area-profiles/national-tools-local-data> |
| Brighton and Hove | needs_assessment | 0.25 | Integrated community team profiles archive | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/area-profiles/integrated-community-team-profiles-archive> |
| Brighton and Hove | needs_assessment | 0.25 | Research governance | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/research-brighton-hove/research-governance> |
| Brighton and Hove | needs_assessment | 0.25 | Research in Brighton & Hove | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/research-brighton-hove/research-collaborations> |
| Brighton and Hove | needs_assessment | 0.25 | Research training and useful information | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/research-training-and-useful-information> |
| Brighton and Hove | needs_assessment | 0.25 | REN Report | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/research-brighton-hove/research-ready-communities-brighton-hove> |
| Brighton and Hove | needs_assessment | 0.25 | Evaluation of Multiple Compound Needs Programme - Executive Summary | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/evaluation-brighton-hove-multiple-compound-needs-programme-executive-summary> |
| Brighton and Hove | needs_assessment | 0.25 | Hypertension signposting 2024 | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/healthy-people/hypertension-signposting-2024> |
| Brighton and Hove | needs_assessment | 0.25 | Safe and Well at school survey 2023 summary | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/key-evidence-reports-and-briefings/safe-and-well-school> |
| Brighton and Hove | needs_assessment | 0.25 | Chronic Respiratory Disease - signposting | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/healthy-people/chronic-respiratory-disease-signposting> |
| Brighton and Hove | needs_assessment | 0.25 | Our population summary PDF version | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assement-jsna/jsna-headline-summary-reports/jsna-population-summary> |
| Brighton and Hove | needs_assessment | 0.25 | Cancer in Brighton & Hove | <https://www.brighton-hove.gov.uk/joint-strategic-needs-assessment-jsna/cancer-brighton-hove-2022-full-report> |
| Medway | needs_assessment | 0.50 | Strategies and plans | <https://www.medway.gov.uk/info/200591/medway_s_joint_strategic_needs_assessment_jsna/1930/medways_public_health_strategies_and_plans> |
| Medway | needs_assessment | 0.50 | Joint Local Health and Wellbeing Strategy | <https://www.medway.gov.uk/info/200591/medway_s_joint_strategic_needs_assessment_jsna/1571/joint_health_and_wellbeing_strategy> |
| Medway | needs_assessment | 0.25 | Skip to content | <https://www.medway.gov.uk/jsna> |
| Medway | needs_assessment | 0.25 | Chapters | <https://www.medway.gov.uk/downloads/download/643/joint_strategic_needs_assessment_jsna_chapters> |
| Medway | needs_assessment | 0.25 | Profiles | <https://www.medway.gov.uk/info/200591/medway_s_joint_strategic_needs_assessment_jsna/1590/area_profiles> |
| Medway | needs_assessment | 0.25 | Dashboard | <https://www.medway.gov.uk/info/200591/medway_s_joint_strategic_needs_assessment_jsna/1873/medways_joint_strategic_needs_assessment_jsna_data_dashboard> |
| Medway | needs_assessment | 0.25 | Medway Health and Wellbeing Survey | <https://www.medway.gov.uk/info/200591/medway_s_joint_strategic_needs_assessment_jsna/1650/medway_health_and_wellbeing_survey> |
| Medway | needs_assessment | 0.25 | People and place | <https://www.medway.gov.uk/info/200591/medway_s_joint_strategic_needs_assessment_jsna/1423/people_and_place> |
| Medway | needs_assessment | 0.25 | Best start in life | <https://www.medway.gov.uk/info/200591/medway_s_joint_strategic_needs_assessment_jsna/1566/giving_every_child_a_good_start_in_life> |
| Medway | needs_assessment | 0.25 | Improving health and wellbeing | <https://www.medway.gov.uk/info/200591/medway_s_joint_strategic_needs_assessment_jsna/1569/improving_mental_and_physical_health_and_wellbeing> |
| Medway | needs_assessment | 0.25 | Increasing years of healthy life | <https://www.medway.gov.uk/info/200591/medway_s_joint_strategic_needs_assessment_jsna/1568/preventing_early_death_and_increasing_years_of_healthy_life> |
| Medway | needs_assessment | 0.25 | Ageing well | <https://www.medway.gov.uk/info/200591/medway_s_joint_strategic_needs_assessment_jsna/1567/enabling_our_older_population_to_live_independently_and_well> |
| Medway | needs_assessment | 0.25 | Reducing health inequalities | <https://www.medway.gov.uk/info/200591/medway_s_joint_strategic_needs_assessment_jsna/1570/reducing_health_inequalities> |
| Medway | needs_assessment | 0.25 | Downloads | <https://www.medway.gov.uk/downloads/200591/medways_joint_strategic_needs_assessment_jsna> |
| Medway | needs_assessment | 0.25 | Infographics | <https://www.medway.gov.uk/info/200591/medway_s_joint_strategic_needs_assessment_jsna/1577/infographics> |
| Medway | needs_assessment | 0.25 | Annual Public Health Report | <https://www.medway.gov.uk/info/200591/medway_s_joint_strategic_needs_assessment_jsna/1573/annual_public_health_report> |
| Portsmouth | needs_assessment | 0.50 | JSNA overview | <https://www.portsmouth.gov.uk/services/health-and-wellbeing/joint-strategic-needs-assessment/jsna-overview/> |
| Portsmouth | needs_assessment | 0.50 | JSNA population health summary | <https://www.portsmouth.gov.uk/services/health-and-wellbeing/joint-strategic-needs-assessment/jsna-population-health-summary/> |
| Portsmouth | needs_assessment | 0.50 | Adults health and wellbeing – JSNA report | <https://www.portsmouth.gov.uk/services/health-and-wellbeing/joint-strategic-needs-assessment/adults-health-and-wellbeing-jsna-report/> |
| Portsmouth | needs_assessment | 0.50 | Children’s health, social care and education – JSNA report | <https://www.portsmouth.gov.uk/services/health-and-wellbeing/joint-strategic-needs-assessment/childrens-health-social-care-and-education-jsna-report/> |
| Portsmouth | needs_assessment | 0.50 | Portsmouth demography – JSNA report | <https://www.portsmouth.gov.uk/services/health-and-wellbeing/joint-strategic-needs-assessment/portsmouth-demography/> |
| Portsmouth | needs_assessment | 0.50 | Portsmouth births – JSNA report | <https://www.portsmouth.gov.uk/services/health-and-wellbeing/joint-strategic-needs-assessment/portsmouth-births-jsna-report/> |
| Portsmouth | needs_assessment | 0.50 | Portsmouth deaths – JSNA report | <https://www.portsmouth.gov.uk/services/health-and-wellbeing/joint-strategic-needs-assessment/portsmouth-deaths-jsna-report/> |
| Portsmouth | needs_assessment | 0.50 | Poverty and cost of living – JSNA report | <https://www.portsmouth.gov.uk/services/health-and-wellbeing/joint-strategic-needs-assessment/poverty-and-cost-of-living/> |
| Portsmouth | needs_assessment | 0.25 | Skip to content | <https://www.portsmouth.gov.uk/jsna> |
| Slough | needs_assessment | 0.75 | Joint Strategic Needs Assessment (JSNA) | <https://www.slough.gov.uk/joint-strategic-needs-assessment> |
| Wokingham | needs_assessment | 0.25 | Skip to main content | <https://www.wokingham.gov.uk/jsna> |

## South West

| Authority | Type (guess) | Conf. | Title | URL |
| --- | --- | ---: | --- | --- |
| Bath and North East Somerset | needs_assessment | 0.50 | JSNA | <https://www.bathnes.gov.uk/taxonomy/term/1963> |
| Bath and North East Somerset | needs_assessment | 0.25 | Skip to main content | <https://www.bathnes.gov.uk/jsna> |
| Bath and North East Somerset | needs_assessment | 0.25 | Strategic Evidence Base - Document Library and Datastore | <https://www.bathnes.gov.uk/jsna-document-library-and-data-store> |
| Bournemouth, Christchurch and Poole | needs_assessment | 0.75 | Joint Strategic Needs Assessment (JSNA) | <https://www.bcpcouncil.gov.uk/communities/public-health/joint-strategic-needs-assessment-jsna> |
| Bristol, City of | needs_assessment | 0.75 | About the Joint Strategic Needs Assessment (JSNA) | <https://www.bristol.gov.uk/council/policies-plans-and-strategies/social-care-and-health/joint-strategic-needs-assessment/about-the-joint-strategic-needs-assessment> |
| Bristol, City of | needs_assessment | 0.50 | JSNA data profiles | <https://www.bristol.gov.uk/council/policies-plans-and-strategies/social-care-and-health/joint-strategic-needs-assessment/jsna-data-profiles> |
| Bristol, City of | needs_assessment | 0.50 | JSNA Chapters and Spotlight reports | <https://www.bristol.gov.uk/council/policies-plans-and-strategies/social-care-and-health/joint-strategic-needs-assessment/jsna-chapters-and-spotlight-reports> |
| Bristol, City of | needs_assessment | 0.25 | Skip to content | <https://www.bristol.gov.uk/jsna> |
| Cornwall | needs_assessment | 0.25 | Skip to content | <https://www.cornwall.gov.uk/jsna> |
| Dorset | needs_assessment | 0.50 | Needs assessments and insights | <https://www.dorsetcouncil.gov.uk/jsna-needs-assessments-and-insights> |
| Dorset | needs_assessment | 0.25 | Explore health data | <https://www.dorsetcouncil.gov.uk/w/jsna-explore-health-data> |
| Plymouth | needs_assessment | 0.50 | Our JSNA topics | <https://www.plymouth.gov.uk/our-jsna-topics> |
| Plymouth | needs_assessment | 0.25 | Skip to main content | <https://www.plymouth.gov.uk/jsna> |
| South Gloucestershire | needs_assessment | 0.25 | Population Health Intelligence Portal | <https://www.southglos.gov.uk/health-and-social-care/health-services/jsna/> |

## West Midlands

| Authority | Type (guess) | Conf. | Title | URL |
| --- | --- | ---: | --- | --- |
| Birmingham | needs_assessment | 0.50 | Pharmacy needs assessment | <https://www.birmingham.gov.uk/info/50268/joint_strategic_needs_assessment_jsna/1301/pharmaceutical_needs_assessment_pna> |
| Birmingham | needs_assessment | 0.50 | Core JSNA 2019 | <https://www.birmingham.gov.uk/info/50268/joint_strategic_needs_assessment_jsna/1337/jsna_themes> |
| Birmingham | needs_assessment | 0.50 | Birmingham and Solihull Pharmaceutical Needs Assessment (PNA) 2025 to 2028 page | <https://www.birmingham.gov.uk/info/50268/joint_strategic_needs_assessment_jsna/1301/birmingham_and_solihull_pharmaceutical_needs_assessment_pna_2025_to_2028> |
| Birmingham | needs_assessment | 0.25 | Skip to content | <https://www.birmingham.gov.uk/jsna> |
| Birmingham | needs_assessment | 0.25 | Local area profiles | <https://www.birmingham.gov.uk/info/50268/joint_strategic_needs_assessment_jsna/1332/local_area_health_profiles> |
| Birmingham | needs_assessment | 0.25 | Deep dives | <https://www.birmingham.gov.uk/info/50268/joint_strategic_needs_assessment_jsna/2405/deep_dives> |
| Birmingham | needs_assessment | 0.25 | Downloads | <https://www.birmingham.gov.uk/downloads/50268/joint_strategic_needs_assessment_jsna> |
| Birmingham | needs_assessment | 0.25 | News | <https://www.birmingham.gov.uk/news/50268/joint_strategic_needs_assessment_jsna> |
| Shropshire | needs_assessment | 0.75 | Joint Strategic Needs Assessment (JSNA) | <https://www.shropshire.gov.uk/public-health/joint-strategic-needs-assessment-jsna/> |
| Shropshire | needs_assessment | 0.50 | JSNA for SEND | <https://www.shropshire.gov.uk/public-health/jsna-joint-strategic-needs-assessment/send-jsna/> |
| Shropshire | needs_assessment | 0.50 | Place-based Joint Strategic Needs Assessment | <https://www.shropshire.gov.uk/public-health/jsna-joint-strategic-needs-assessment/place-based-joint-strategic-needs-assessment/> |
| Shropshire | needs_assessment | 0.50 | Drugs and alcohol | <https://www.shropshire.gov.uk/public-health/jsna-joint-strategic-needs-assessment/drug-and-alcohol/> |
| Shropshire | needs_assessment | 0.50 | Children and Young People JSNA | <https://www.shropshire.gov.uk/public-health/jsna-joint-strategic-needs-assessment/children-and-young-people-jsna/> |
| Shropshire | needs_assessment | 0.25 | Skip to content | <https://www.shropshire.gov.uk/jsna> |
| Staffordshire | needs_assessment | 0.75 | Special Educational Needs in Staffordshire Joint Strategic Needs Assessment, April 2025 (P | <https://www.staffordshire.gov.uk/sites/default/files/2026-01/Staffordshire-SEND-JSNA-2025.pdf> |
| Staffordshire | needs_assessment | 0.50 | Previous Joint Strategic Needs Assessments | <https://www.staffordshire.gov.uk/staffordshire-observatory/insights/staffordshire-observatory/health-and-wellbeing/previous-jsna> |
| Stoke-on-Trent | needs_assessment | 0.25 | Skip to content | <https://www.stoke.gov.uk/jsna> |
| Warwickshire | needs_assessment | 0.75 | About the Joint Strategic Needs Assessment (JSNA) | <https://www.warwickshire.gov.uk/health-wellbeing/joint-strategic-needs-initiative-jsna/1> |
| Warwickshire | needs_assessment | 0.75 | Warwickshire Drugs Needs Assessment (2022) | <https://www.warwickshire.gov.uk/directory-record/7947/warwickshire-drugs-needs-assessment-2022-> |
| Warwickshire | needs_assessment | 0.75 | Warwickshire Alcohol Health Needs Assessment (2022) | <https://www.warwickshire.gov.uk/directory-record/7193/warwickshire-alcohol-health-needs-assessment-2022> |
| Warwickshire | needs_assessment | 0.75 | JSNA place based needs assessments 2017 to 2020 | <https://www.warwickshire.gov.uk/health-wellbeing/jsna-place-based-approach/1> |
| Warwickshire | needs_assessment | 0.50 | Sign up to JSNA updates | <https://www.warwickshire.gov.uk/joint-strategic-needs-assessments-1/joint-strategic-needs-initiative-jsna/3> |
| Warwickshire | needs_assessment | 0.50 | Thriving Adults JSNA (2026) | <https://www.warwickshire.gov.uk/thrivingadults> |
| Warwickshire | needs_assessment | 0.50 | LGBTQ+ JSNA (2026) | <https://www.warwickshire.gov.uk/directory-record/8904/lgbtq-jsna-2026-> |
| Warwickshire | needs_assessment | 0.50 | Adults with a Learning Disability JSNA (2025) | <https://www.warwickshire.gov.uk/directory-record/8076/adults-with-a-learning-disability-jsna-2025-> |
| Warwickshire | needs_assessment | 0.50 | Empowering Futures: Growing Up Well in Warwickshire JSNA (2024) | <https://www.warwickshire.gov.uk/empoweringfutures> |
| Warwickshire | needs_assessment | 0.50 | Healthy Ageing JSNA (2024) | <https://www.warwickshire.gov.uk/directory-record/7896/healthy-ageing-jsna-2024> |
| Warwickshire | needs_assessment | 0.50 | Mental Health and Wellbeing of Infants, Children, and Young People JSNA (2023) | <https://www.warwickshire.gov.uk/directory-record/7609/mental-health-and-wellbeing-of-infants-children-and-young-people-jsna-2023-> |
| Warwickshire | needs_assessment | 0.50 | Children’s 0 to 5 JSNA (2022) | <https://www.warwickshire.gov.uk/directory-record/7176/children-s-0-to-5-jsna-2022> |
| Warwickshire | needs_assessment | 0.50 | Warwickshire's Violence and Domestic Abuse JSNA (2021) | <https://www.warwickshire.gov.uk/directory-record/7177/warwickshire-s-domestic-violence-and-abuse-jsna-2021> |
| Warwickshire | needs_assessment | 0.25 | Skip to content | <https://www.warwickshire.gov.uk/jsna> |
| Wolverhampton | needs_assessment | 0.50 | JSNA | <https://www.wolverhampton.gov.uk/jsna/index.html> |
| Wolverhampton | needs_assessment | 0.50 | Thematic Needs Assessments and Impact Statements | <https://www.wolverhampton.gov.uk/jsna/thematic-needs-assessments/index.html> |
| Wolverhampton | needs_assessment | 0.25 | Skip to main content | <https://www.wolverhampton.gov.uk/jsna> |
| Wolverhampton | needs_assessment | 0.25 | Our City, Neighbourhoods and Ward Profiles | <https://www.wolverhampton.gov.uk/jsna/our-city/dashboard.html> |
| Wolverhampton | needs_assessment | 0.25 | Best Start to Life and Child Health | <https://www.wolverhampton.gov.uk/jsna/best-start/dashboard.html> |
| Wolverhampton | needs_assessment | 0.25 | Adult Wellbeing and Healthy Ageing | <https://www.wolverhampton.gov.uk/jsna/adult-wellbeing/dashboard.html> |
| Wolverhampton | needs_assessment | 0.25 | Screening and Vaccinations | <https://www.wolverhampton.gov.uk/jsna/screening-and-vaccinations/dashboard.html> |
| Wolverhampton | needs_assessment | 0.25 | Wider Determinants and Inclusion Health | <https://www.wolverhampton.gov.uk/jsna/health-behaviours/dashboard.html> |
| Wolverhampton | needs_assessment | 0.25 | Community Voice: what local people are telling us | <https://www.wolverhampton.gov.uk/jsna/community-voice/index.html> |
| Wolverhampton | needs_assessment | 0.25 | University of Wolverhampton Research | <https://www.wolverhampton.gov.uk/jsna/research/index.html> |
| Wolverhampton | needs_assessment | 0.25 | Public Health Annual Reports | <https://www.wolverhampton.gov.uk/jsna/public-health-annual-reports/index.html> |
| Worcestershire | needs_assessment | 0.75 | Local Health Information: Joint Strategic Needs Assessment (JSNA) | <https://www.worcestershire.gov.uk/council-services/council-and-democracy/research-reports-and-local-statistics/joint-strategic-needs-assessment-jsna> |
| Worcestershire | needs_assessment | 0.50 | JSNA Annual Summaries | <https://www.worcestershire.gov.uk/council-services/council-and-democracy/research-reports-and-local-statistics/joint-strategic-needs-assessment-jsna/jsna-annual-summaries> |
| Worcestershire | needs_assessment | 0.50 | Pharmaceutical Needs Assessment (PNA) | <https://www.worcestershire.gov.uk/council-services/council-and-democracy/research-reports-and-local-statistics/joint-strategic-needs-assessment-jsna/jsna-pharmaceutical-needs> |
| Worcestershire | needs_assessment | 0.50 | Drugs, Alcohol and Smoking | <https://www.worcestershire.gov.uk/council-services/council-and-democracy/research-reports-and-local-statistics/joint-strategic-needs-assessment-jsna/drugs-alcohol-and-smoking-jsna> |
| Worcestershire | needs_assessment | 0.50 | Local Health Needs Assessments and Profiles | <https://www.worcestershire.gov.uk/council-services/council-and-democracy/research-reports-and-local-statistics/joint-strategic-needs-assessment-jsna/local-health-profiles-jsna> |
| Worcestershire | needs_assessment | 0.25 | Skip to main content | <https://www.worcestershire.gov.uk/jsna> |
| Worcestershire | needs_assessment | 0.25 | Census data for Worcestershire | <https://www.worcestershire.gov.uk/council-services/council-and-democracy/research-reports-and-local-statistics/joint-strategic-needs-assessment-jsna/census-data-worcestershire> |
| Worcestershire | needs_assessment | 0.25 | Adults and Vulnerable Adults | <https://www.worcestershire.gov.uk/council-services/council-and-democracy/research-reports-and-local-statistics/joint-strategic-needs-assessment-jsna/adults-and-vulnerable-adults-jsna> |
| Worcestershire | needs_assessment | 0.25 | Child and Maternal Health | <https://www.worcestershire.gov.uk/council-services/council-and-democracy/research-reports-and-local-statistics/joint-strategic-needs-assessment-jsna/child-and-maternal-health-jsna> |
| Worcestershire | needs_assessment | 0.25 | Disease Specific Publications | <https://www.worcestershire.gov.uk/council-services/council-and-democracy/research-reports-and-local-statistics/joint-strategic-needs-assessment-jsna/disease-specific-jsna-publications> |
| Worcestershire | needs_assessment | 0.25 | Mental Health and Wellbeing | <https://www.worcestershire.gov.uk/council-services/council-and-democracy/research-reports-and-local-statistics/joint-strategic-needs-assessment-jsna/mental-health-and-wellbeing-jsna> |
| Worcestershire | needs_assessment | 0.25 | Obesity, Diet and Physical Activity | <https://www.worcestershire.gov.uk/council-services/council-and-democracy/research-reports-and-local-statistics/joint-strategic-needs-assessment-jsna/obesity-diet-and-physical-activity> |
| Worcestershire | needs_assessment | 0.25 | Sexual and Reproductive Health | <https://www.worcestershire.gov.uk/council-services/council-and-democracy/research-reports-and-local-statistics/joint-strategic-needs-assessment-jsna/sexual-and-reproductive-health> |
| Worcestershire | needs_assessment | 0.25 | Wider Determinants of Health | <https://www.worcestershire.gov.uk/council-services/council-and-democracy/research-reports-and-local-statistics/joint-strategic-needs-assessment-jsna/wider-determinants-health-jsna> |

## Yorkshire and The Humber

| Authority | Type (guess) | Conf. | Title | URL |
| --- | --- | ---: | --- | --- |
| Bradford | needs_assessment | 0.50 | Search JSNA | <https://www.bradford.gov.uk/search> |
| Bradford | needs_assessment | 0.25 | Skip to main content | <https://www.bradford.gov.uk/jsna> |
| Calderdale | needs_assessment | 0.75 | Joint Strategic Needs Assessment (JSNA) | <https://new.calderdale.gov.uk/health-and-social-care/jsna> |
| Kirklees | needs_assessment | 0.25 | I accept cookies | <https://www.kirklees.gov.uk/jsna> |
| North Yorkshire | needs_assessment | 0.25 | Skip to main content | <https://www.northyorks.gov.uk/jsna> |
| York | needs_assessment | 0.50 | Health Needs Assessments | <https://www.york.gov.uk/jsna-1?categoryId=1> |
| York | needs_assessment | 0.25 | Skip to content | <https://www.york.gov.uk/jsna> |
