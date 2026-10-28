# Regulatory requirements matrix

Research snapshot: 28 October 2026. This is an engineering intake matrix, not a
legal opinion, operational authorization or certification. No flight test is
permitted. Requirements must be rechecked for the exact operator, aircraft, cargo,
location and concept of operations with the competent authority before physical work.

| Scope | Requirement to investigate | Software accommodation | Evidence still required |
| --- | --- | --- | --- |
| EU operation category | Delivery/BVLOS is generally outside open-category limitations; specific or certified classification depends on the operation | Simulation-only mission mode, explicit independent authorization boundary | Authority determination of category and authorization route |
| EU specific category | Applicable authorization, STS/PDRA applicability or operational risk assessment | Versioned constraints, mission/audit histories | Approved ConOps, relevant SORA/PDRA evidence and operator manual |
| EU airspace | Current national geographic zones and any designated U-space requirements | Restricted-zone abstraction; synthetic data labelled | Licensed authoritative source, freshness, USSP integration where applicable |
| EU identity | Operator registration and applicable remote identification | Unique simulated aircraft identifiers; no claim of remote-ID implementation | Qualified hardware/remote ID and operator registration |
| EU people | Pilot/operator competency and maintenance responsibilities | Roles and inspection history | Authority-approved competency and actual maintenance procedures |
| EU incident/insurance | Applicable occurrence reporting, insurance and cargo-specific obligations | Internal incident records | Reporting deadlines/authority route, insurance cover and medical/dangerous-goods assessment |
| GDPR | Purpose, lawful basis, minimisation, retention, access/erasure, processor/transfer safeguards | Tenant fences, private sessions, expiring tracking without location/address | Privacy approval, records of processing, DPIA assessment, DPAs and actual retention/backup policy |

Sources: [EASA specific category](https://www.easa.europa.eu/en/domains/drones-air-mobility/operating-drone/specific-category-civil-drones),
[EASA SORA](https://www.easa.europa.eu/en/domains/drones-air-mobility/operating-drone/specific-category-civil-drones/specific-operations-risk-assessment-sora),
[EASA U-space](https://www.easa.europa.eu/en/domains/air-traffic-management/u-space),
[GDPR Article 5](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32016R0679).

U-space service obligations apply in designated U-space airspace; they do not replace
underlying UAS operating requirements. No U-space authorization service is implemented.

## Southern Africa: separate national reviews

These are distinct jurisdictions; EU approval or another country's permission must
never populate a national approval field. No national rule pack is active.

| Country | Verified intake source / finding | Outstanding work |
| --- | --- | --- |
| South Africa | [SACAA UAS](https://www.caa.co.za/industry-information/uas/) and [government Part 101 amendment](https://www.gov.za/sites/default/files/gcis_document/202303/48228rg11556gon3170.pdf) describe operator, airworthiness and maintenance processes. The cited Part 101 applicability excludes autonomous unmanned aircraft | Obtain current consolidated rules and authority interpretation of the proposed autonomy/remote-pilot ConOps, UASOC, BVLOS and cargo permissions; do not assume an RPAS path authorizes autonomous delivery |
| Namibia | [NCAA](https://ncaa.com.na/) identifies Part 101 registration and written authorization requirements | Obtain current Part 101/technical standards and operation-specific permissions, BVLOS, import, insurance and privacy assessment |
| Zambia | [ZCAA RPAS](https://caa.co.zm/index.php/rpas) identifies registration and remote-pilot licensing; [official forms](https://www.caa.co.zm/documents/Airworthiness%20-%20RPAS%20Forms) include flight authorization | Validate current regulations and delivery/BVLOS/cargo authorization with ZCAA |
| Botswana | No sufficiently current authoritative rule text verified in this research pass | Separate CAAB review required; no inferred permission |
| Zimbabwe | No current authoritative operating rule text verified | Separate CAAZ review required |
| Angola | Not assessed | Separate national authority, airspace, import and data-protection review |
| Mozambique | Not assessed | Separate national authority, airspace, import and data-protection review |
| Malawi | Not assessed | Separate national authority, airspace, import and data-protection review |
| Lesotho | Not assessed | Separate national authority and cross-border review |
| Eswatini | Not assessed | Separate national authority and cross-border review |
| Mauritius | Not assessed | Separate national authority and data-protection review |
| Madagascar | Not assessed | Separate national authority and data-protection review |
| Seychelles | Not assessed | Separate national authority and protected-area review |
| Other expansion markets | No framework imported automatically | Country-specific assessment before a regional configuration is enabled |

Physical milestones additionally require aircraft/propulsion selection, flight-controller
and command-link qualification, fail-safe evidence, independent hazard review, hardware
and software integration tests, emergency procedures, training and explicit test authority.
