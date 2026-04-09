# Healthcare Encounters Fixtures

Multi-table healthcare data for testing join and aggregation operations across encounters, diagnoses, and treatments.

## Files

| File | Rows | Description |
|------|------|-------------|
| `encounters.csv` | 100 | Patient encounters with department and dates |
| `diagnoses.csv` | 80 | Diagnoses linked to encounters via encounter_id |
| `treatments.csv` | 60 | Treatments/procedures linked to encounters via encounter_id |

## Schema: encounters.csv

| Column | Type | Description |
|--------|------|-------------|
| encounter_id | string | Unique ID (ENC00001-ENC00100) |
| patient_id | string | Patient ID (PAT0001-PAT0060, ~49 unique) |
| department | string | Emergency, Cardiology, Orthopedics, General, Pediatrics |
| admit_date | date | YYYY-MM-DD (2025) |
| discharge_date | date | YYYY-MM-DD (admit + 0-7 days) |
| provider_id | string | Provider ID (PROV001-PROV010) |

## Schema: diagnoses.csv

| Column | Type | Description |
|--------|------|-------------|
| diagnosis_id | string | Unique ID (DX00001-DX00080) |
| encounter_id | string | FK to encounters.encounter_id |
| icd_code | string | ICD-10 code (J06.9, I10, M54.5, etc.) |
| description | string | Diagnosis description |
| primary_flag | boolean | True if primary diagnosis for the encounter |

## Schema: treatments.csv

| Column | Type | Description |
|--------|------|-------------|
| treatment_id | string | Unique ID (TX00001-TX00060) |
| encounter_id | string | FK to encounters.encounter_id |
| procedure_code | string | CPT procedure code |
| description | string | Procedure description |
| cost | float | Treatment cost in USD ($50-$50,000) |

## Join Keys

- `encounters.encounter_id` = `diagnoses.encounter_id` (1:many -- some encounters have multiple diagnoses)
- `encounters.encounter_id` = `treatments.encounter_id` (1:many -- some encounters have multiple treatments)

## Data Characteristics

- ~49 unique patients across 100 encounters (some patients have multiple visits)
- 70 encounters have at least one diagnosis; 10 encounters have multiple diagnoses
- 48 encounters have at least one treatment; some have multiple treatments
- Not every encounter has a diagnosis or treatment (realistic -- some are admin/follow-up)
- Length of stay ranges from 0 (same-day) to 7 days

## ICD-10 Codes Used

| Code | Description |
|------|-------------|
| J06.9 | Acute upper respiratory infection |
| I10 | Essential hypertension |
| M54.5 | Low back pain |
| E11.9 | Type 2 diabetes mellitus |
| J18.9 | Pneumonia, unspecified |
| K21.0 | Gastro-esophageal reflux disease |
| N39.0 | Urinary tract infection |
| S62.5 | Fracture of thumb |
| R10.9 | Abdominal pain, unspecified |
| J45.9 | Asthma, unspecified |
| I25.10 | Atherosclerotic heart disease |
| M79.3 | Panniculitis, unspecified |
| R50.9 | Fever, unspecified |
| S82.0 | Fracture of patella |
| G43.9 | Migraine, unspecified |

## Intended Use

Tests the agent's ability to:
1. **Join** encounters with diagnoses and treatments (two separate joins or a three-way join)
2. **Aggregate** treatment costs by department (Group recipe)
3. **Count** diagnoses per department or per ICD code
4. **Calculate** average length of stay (discharge - admit date) by department
5. **Identify** high-cost encounters (filter or sort)
6. Handle the 1:many cardinality correctly (avoid row duplication in aggregation)
