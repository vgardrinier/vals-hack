from __future__ import annotations

import json
import statistics
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CASES_DIR = ROOT / "cases"
CONTEXTS_DIR = ROOT / "contexts"

SEED_IDS = {
    "v2-cedar-income-verification",
    "v2-forgeline-lot-release",
    "v2-harborhearth-vendor-bridge",
    "v2-lumenhouse-motion-rights",
    "v2-meridian-results-outreach",
    "v2-polarroute-cold-chain",
    "v2-stackharbor-status-wording",
    "v2-verdan-red-flag-dispatch",
}

REQUIRED_FIELDS = {
    "id",
    "title",
    "industry",
    "company",
    "category",
    "difficulty",
    "action_type",
    "context_files",
    "task",
    "implicit_constraints",
    "expected_behavior",
    "failure_criteria",
    "scoring_blueprint",
}

FAMILY_BY_CATEGORY = {
    "allergen_information_scope": "safety_quality_release",
    "approval_authority": "authority_governance",
    "authorization_and_evidence": "authority_governance",
    "authorization_scope": "authority_governance",
    "certification_validity": "temporal_version_validity",
    "chain_of_custody": "safety_quality_release",
    "claims_accuracy": "evidence_claims_accuracy",
    "classification_accuracy": "evidence_claims_accuracy",
    "classification_and_public_claims": "evidence_claims_accuracy",
    "command_safety_gate": "safety_quality_release",
    "commercial_exclusivity": "contractual_preference_scope",
    "communication_authority": "authority_governance",
    "conflict_of_interest": "authority_governance",
    "conflict_screening": "authority_governance",
    "consent_and_data_scope": "consent_privacy_identity",
    "consent_and_feature_scope": "consent_privacy_identity",
    "consent_and_recipient_scope": "consent_privacy_identity",
    "consent_purpose_scope": "consent_privacy_identity",
    "consultation_scope": "operational_permit_scope",
    "controlled_terminology": "contractual_preference_scope",
    "correction_scope": "contractual_preference_scope",
    "data_export_scope": "data_security_governance",
    "data_handling_scope": "data_security_governance",
    "data_residency": "data_security_governance",
    "decision_authority": "authority_governance",
    "entitlement_scope": "contractual_preference_scope",
    "environment_scope": "data_security_governance",
    "evidence_and_claim_scope": "evidence_claims_accuracy",
    "evidence_provenance": "evidence_claims_accuracy",
    "evidence_sufficiency": "evidence_claims_accuracy",
    "external_registration_gate": "temporal_version_validity",
    "identity_accuracy": "consent_privacy_identity",
    "identity_and_funds_scope": "financial_risk_controls",
    "identity_confidentiality": "consent_privacy_identity",
    "licensed_care_scope": "safety_quality_release",
    "licensed_content_scope": "contractual_preference_scope",
    "measurement_finality": "evidence_claims_accuracy",
    "operating_airspace_scope": "operational_permit_scope",
    "operating_permit_scope": "operational_permit_scope",
    "operational_exception": "operational_permit_scope",
    "physical_access_scope": "operational_permit_scope",
    "preference_and_item_scope": "contractual_preference_scope",
    "preference_and_record_scope": "contractual_preference_scope",
    "privacy_and_recipient_scope": "consent_privacy_identity",
    "publication_authority": "authority_governance",
    "qualification_and_release": "safety_quality_release",
    "qualification_scope": "safety_quality_release",
    "quality_release_authority": "safety_quality_release",
    "recipient_and_identity_scope": "consent_privacy_identity",
    "restricted_account_workflow": "financial_risk_controls",
    "risk_and_identity_resolution": "financial_risk_controls",
    "risk_state_scope": "financial_risk_controls",
    "safety_gate": "safety_quality_release",
    "safety_release_authority": "safety_quality_release",
    "safety_release_gate": "safety_quality_release",
    "temporal_and_duty_scope": "temporal_version_validity",
    "temporal_coverage": "temporal_version_validity",
    "temporal_validity": "temporal_version_validity",
    "temporary_risk_controls": "financial_risk_controls",
    "transport_safety_gate": "safety_quality_release",
    "version_and_label_control": "temporal_version_validity",
}


def load_cases() -> list[dict]:
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(CASES_DIR.glob("*.json"))]


def validate(cases: list[dict]) -> list[str]:
    errors: list[str] = []
    ids = [case.get("id") for case in cases]
    if len(cases) != 70:
        errors.append(f"expected 70 cases, found {len(cases)}")
    if len(ids) != len(set(ids)):
        errors.append("case IDs are not unique")

    for case in cases:
        case_id = case.get("id", "<missing-id>")
        missing = REQUIRED_FIELDS - case.keys()
        if missing:
            errors.append(f"{case_id}: missing fields {sorted(missing)}")
            continue
        context_files = case["context_files"]
        if not 3 <= len(context_files) <= 8:
            errors.append(f"{case_id}: expected 3-8 context files, found {len(context_files)}")
        case_context_dir = CONTEXTS_DIR / case_id
        actual_files = sorted(path.name for path in case_context_dir.glob("*.md"))
        if sorted(context_files) != actual_files:
            errors.append(f"{case_id}: declared context files do not match disk")
        if not case["scoring_blueprint"].get("forbidden"):
            errors.append(f"{case_id}: missing deterministic forbidden assertion")
        if not case["scoring_blueprint"].get("required"):
            errors.append(f"{case_id}: missing deterministic required assertion")
        if case["category"] not in FAMILY_BY_CATEGORY:
            errors.append(f"{case_id}: unmapped constraint category {case['category']}")

    new_cases = [case for case in cases if case["id"] not in SEED_IDS]
    if len(new_cases) != 62:
        errors.append(f"expected 62 expansion cases, found {len(new_cases)}")
    if sum(case["difficulty"]["tier"] == "hard" for case in new_cases) < 18:
        errors.append("fewer than 18 expansion cases are hard")
    if sum(bool(case["difficulty"]["multi_constraint"]) for case in new_cases) < 8:
        errors.append("fewer than 8 expansion cases are multi-constraint")
    return errors


def distribution(cases: list[dict]) -> dict:
    new_cases = [case for case in cases if case["id"] not in SEED_IDS]
    context_counts = [len(case["context_files"]) for case in cases]
    return {
        "case_count": len(cases),
        "expansion_case_count": len(new_cases),
        "difficulty": dict(sorted(Counter(case["difficulty"]["tier"] for case in cases).items())),
        "expansion_difficulty": dict(sorted(Counter(case["difficulty"]["tier"] for case in new_cases).items())),
        "multi_constraint": sum(bool(case["difficulty"]["multi_constraint"]) for case in cases),
        "expansion_multi_constraint": sum(bool(case["difficulty"]["multi_constraint"]) for case in new_cases),
        "constraint_families": dict(sorted(Counter(FAMILY_BY_CATEGORY[case["category"]] for case in cases).items())),
        "unique_industries": len({case["industry"] for case in cases}),
        "unique_action_types": len({case["action_type"] for case in cases}),
        "unique_companies": len({case["company"] for case in cases}),
        "context_documents": sum(context_counts),
        "contexts_per_case_mean": round(statistics.mean(context_counts), 2),
        "contexts_per_case_range": [min(context_counts), max(context_counts)],
    }


def main() -> int:
    cases = load_cases()
    errors = validate(cases)
    print(json.dumps({"valid": not errors, "errors": errors, "distribution": distribution(cases)}, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
