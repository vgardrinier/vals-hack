# BIC-Bench V2 dataset distribution

This is the review checkpoint before the evaluation harness is finalized. Counts are produced and validated by `python bic-bench-v2/validate_dataset.py`.

## Size and difficulty

| Slice | Cases | Hard | Medium | Multi-constraint |
| --- | ---: | ---: | ---: | ---: |
| Approved seed set | 8 | 8 | 0 | 5 |
| New expansion set | 62 | 24 | 38 | 22 |
| **Total** | **70** | **32** | **38** | **27** |

The expansion exceeds the requested minima of 18 hard and 8 multi-constraint cases. Hard cases require evidence conjunction, a scope distinction, temporal reconciliation, a meaningful missing approval, or light inference rather than retrieval of one isolated sentence.

## Constraint families

| Canonical family | Cases | Typical hidden decision |
| --- | ---: | --- |
| Safety and quality release | 13 | Whether evidence and signoffs support release, dispatch, shipment, or operation |
| Consent, privacy, and identity | 11 | Who may receive data, which purpose or channel is authorized, and whose identity controls |
| Authority and governance | 10 | Whether the requester or evidence source has authority to approve, publish, assign, or accept |
| Evidence and claims accuracy | 8 | Whether provenance supports a payment, claim, classification, certificate, or public statement |
| Contractual and preference scope | 7 | Whether rights, entitlements, exclusivity, terminology, or a narrow request permit adaptation |
| Operational and permit scope | 6 | Whether work remains inside an approved site, access, consultation, airspace, or emergency exception |
| Temporal, version, and certification validity | 6 | Which timestamp, registration, certificate, coverage period, or document revision controls |
| Financial and risk controls | 5 | Whether funds, payout state, protected servicing, or a temporary bridge can change |
| Data and security governance | 4 | Which region, environment, enclave, or export path permits the data action |

## Industry coverage

The set contains **70 synthetic companies in 70 distinct industries**, with one case per industry. This prevents one high-frequency vertical from dominating aggregate scores.

`advertising_technology`, `aerospace_manufacturing`, `agricultural_biotechnology`, `architecture_and_engineering`, `automotive_retail`, `b2b_saas`, `book_publishing`, `carbon_accounting`, `clinical_research`, `cloud_infrastructure`, `commercial_aviation`, `commercial_construction`, `commercial_waste_services`, `consumer_electronics_repair`, `corporate_facilities`, `corporate_travel`, `cosmetics`, `creative_agency`, `credit_union_lending`, `customer_support_outsourcing`, `defense_supply_chain`, `drone_delivery`, `ecommerce_marketplace`, `education_technology`, `energy_field_services`, `enterprise_accounting`, `executive_recruiting`, `fashion_supply_chain`, `financial_news`, `fintech_payments`, `food_manufacturing`, `forestry`, `freight_brokerage`, `funeral_services`, `healthcare_diagnostics`, `home_healthcare`, `hospitality_technology`, `laboratory_instruments`, `legal_services`, `live_events`, `luxury_retail`, `managed_cybersecurity`, `maritime_shipping`, `medical_translation`, `mineral_exploration`, `mortgage_servicing`, `museum_operations`, `music_publishing`, `nonprofit_fundraising`, `omnichannel_retail`, `online_gaming`, `payment_processing`, `payroll_services`, `pharmaceutical_logistics`, `pharmaceutical_medical_affairs`, `podcast_production`, `professional_sports`, `property_insurance`, `public_sector_grants`, `rail_infrastructure`, `renewable_energy_trading`, `residential_property_management`, `restaurant_franchising`, `satellite_operations`, `semiconductor_design`, `specialty_chemicals`, `telecommunications`, `veterinary_services`, `warehouse_robotics`, and `water_utility`.

## Action and context coverage

- **70 unique primary action types:** no primary action label is reused.
- **233 context documents:** between 3 and 6 per task, mean 3.33.
- Every case defines at least one machine-readable `forbidden` predicate and one `required` predicate.
- Every correct behavior advances a safe workflow; refusal alone is explicitly insufficient.
- The future runner will remain offline and use the same prompt structure, tools, and step limit for every model.

## Next stage

After this distribution is approved, implement the fixed agent loop, tool simulator, trajectory logging, hybrid scorer, configurable `--trials` defaulting to 5, leaderboard mode with 8 trials, and mean plus standard-deviation reporting.

