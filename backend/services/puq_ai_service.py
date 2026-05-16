from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv


WARNING = "Puq.ai service is currently unavailable. Showing fallback demo result."
ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


class MedicationCatalogError(ValueError):
    pass


MEDICATION_CATALOG = {
    "amlodipine": {"name": "Amlodipine", "class": "calcium_channel_blocker", "high_daily_mg": 10, "max_daily_mg": 10},
    "aspirin": {"name": "Aspirin", "class": "antiplatelet_nsaid", "high_daily_mg": 325, "max_daily_mg": 4000},
    "atorvastatin": {"name": "Atorvastatin", "class": "statin", "high_daily_mg": 80, "max_daily_mg": 80},
    "capecitabine": {"name": "Capecitabine", "class": "oncology_antimetabolite", "high_daily_mg": 2500, "max_daily_mg": 5000},
    "clopidogrel": {"name": "Clopidogrel", "class": "antiplatelet", "high_daily_mg": 75, "max_daily_mg": 300},
    "contrast agent": {"name": "Contrast Agent", "class": "contrast_agent", "high_daily_mg": None, "max_daily_mg": None},
    "fluoxetine": {"name": "Fluoxetine", "class": "ssri", "high_daily_mg": 40, "max_daily_mg": 80},
    "furosemide": {"name": "Furosemide", "class": "loop_diuretic", "high_daily_mg": 80, "max_daily_mg": 600},
    "ibuprofen": {"name": "Ibuprofen", "class": "nsaid", "high_daily_mg": 1200, "max_daily_mg": 3200},
    "insulin glargine": {"name": "Insulin Glargine", "class": "insulin", "high_daily_mg": None, "max_daily_mg": None},
    "levothyroxine": {"name": "Levothyroxine", "class": "thyroid_hormone", "high_daily_mg": 0.2, "max_daily_mg": 0.3},
    "lisinopril": {"name": "Lisinopril", "class": "ace_inhibitor", "high_daily_mg": 40, "max_daily_mg": 80},
    "metformin": {"name": "Metformin", "class": "biguanide", "high_daily_mg": 2000, "max_daily_mg": 2550},
    "omeprazole": {"name": "Omeprazole", "class": "ppi", "high_daily_mg": 40, "max_daily_mg": 120},
    "pantoprazole": {"name": "Pantoprazole", "class": "ppi", "high_daily_mg": 40, "max_daily_mg": 80},
    "paracetamol": {"name": "Paracetamol", "class": "analgesic", "high_daily_mg": 3000, "max_daily_mg": 4000},
    "prednisone": {"name": "Prednisone", "class": "corticosteroid", "high_daily_mg": 20, "max_daily_mg": 80},
    "sertraline": {"name": "Sertraline", "class": "ssri", "high_daily_mg": 100, "max_daily_mg": 200},
    "spironolactone": {"name": "Spironolactone", "class": "potassium_sparing_diuretic", "high_daily_mg": 50, "max_daily_mg": 200},
    "tamoxifen": {"name": "Tamoxifen", "class": "serm", "high_daily_mg": 20, "max_daily_mg": 40},
    "topical nsaid": {"name": "Topical NSAID", "class": "topical_nsaid", "high_daily_mg": None, "max_daily_mg": None},
    "warfarin": {"name": "Warfarin", "class": "anticoagulant", "high_daily_mg": 7.5, "max_daily_mg": 15},
}

FREQUENCY_MULTIPLIERS = {
    "once daily": 1,
    "once nightly": 1,
    "twice daily": 2,
    "three times daily": 3,
    "four times daily": 4,
    "as needed": 1,
    "once weekly": 1 / 7,
}


def prepare_puq_payload(
    patient_data: dict[str, Any],
    current_medications: list[dict[str, Any]],
    new_medicine: dict[str, Any],
) -> dict[str, Any]:
    validate_medication(new_medicine["medicine_name"])
    enriched_current = [enrich_medication(item) for item in current_medications]
    enriched_new = enrich_medication(new_medicine)
    return {
        "task": "medication_risk_analysis",
        "patient_data": patient_data,
        "current_medications": enriched_current,
        "new_medicine": enriched_new,
        "instructions": {
            "compare_new_medicine_with_current_medications": True,
            "calculate_risk_score": True,
            "use_dosage_and_frequency_in_risk_score": True,
            "recommend_lower_risk_alternatives_for_medium_or_high_risk": True,
            "return_structured_json": True,
            "doctor_review_required": True,
            "do_not_make_final_medical_decisions": True,
            "risk_scoring": "0-30 Low, 31-60 Medium, 61-100 High",
            "alternative_rules": (
                "When overall_risk_level is Medium or High, return safer_alternatives. "
                "Alternatives must be framed as options for doctor review only, not medication instructions."
            ),
            "medication_catalog_rule": "If the medicine is outside the supplied known catalog, say it is not in the catalog instead of guessing.",
            "output_language": "English with Turkish-friendly clinical labels when useful",
        },
    }


async def call_puq_webhook(payload: dict[str, Any]) -> dict[str, Any]:
    webhook_url = os.getenv("PUQ_WEBHOOK_URL", "").strip()
    api_key = os.getenv("PUQ_API_KEY", "").strip()

    if not webhook_url or webhook_url == "your_puq_ai_webhook_url":
        raise RuntimeError("PUQ_WEBHOOK_URL is not configured")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Token {api_key}",
    }
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(webhook_url, json=payload, headers=headers)
        response.raise_for_status()
        try:
            data = response.json()
        except json.JSONDecodeError:
            data = response.text

    return normalize_puq_response(data, payload)


def normalize_puq_response(response: Any, payload: dict[str, Any]) -> dict[str, Any]:
    response = extract_structured_result(response)
    if not isinstance(response, dict):
        raise RuntimeError("Puq.ai response did not contain structured medication risk JSON")

    patient_id = payload["patient_data"]["id"]
    medicine_name = payload["new_medicine"]["medicine_name"]

    if "overall_risk_score" not in response and response.get("detected_interactions"):
        response["overall_risk_score"] = max(
            int(item.get("risk_score", 0)) for item in response["detected_interactions"]
        )
    if "overall_risk_score" not in response and "overall_risk_level" not in response:
        raise RuntimeError("Puq.ai response is missing overall_risk_score and overall_risk_level")

    response.setdefault("patient_id", patient_id)
    response.setdefault("new_medicine", medicine_name)
    response.setdefault("detected_interactions", [])
    response["overall_risk_score"] = int(response.get("overall_risk_score", 0))
    response.setdefault("overall_risk_level", risk_level_from_score(response["overall_risk_score"]))
    response.setdefault("highest_risk_pair", "No interaction found")
    response.setdefault(
        "clinical_explanation",
        "No critical interaction was returned by the Puq.ai agent. Doctor review remains required for clinical use.",
    )
    response.setdefault("recommended_doctor_action", "Review the result before taking any clinical action.")
    response.setdefault("safer_alternatives", [])
    response.setdefault("high_risk_warning", warning_for_level(response["overall_risk_level"]))
    response.setdefault(
        "safety_note",
        "This result is for clinical decision support only and does not replace professional medical judgment.",
    )
    response = apply_local_safety_floor(response, payload)
    response["is_fallback"] = False
    return response


def extract_structured_result(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        if is_risk_result(value):
            return value

        for key in (
            "result",
            "data",
            "output",
            "response",
            "message",
            "content",
            "text",
            "body",
            "json",
        ):
            if key in value:
                found = extract_structured_result(value[key])
                if found:
                    return found

        for nested_value in value.values():
            found = extract_structured_result(nested_value)
            if found:
                return found

    if isinstance(value, list):
        for item in value:
            found = extract_structured_result(item)
            if found:
                return found

    if isinstance(value, str):
        parsed = parse_json_text(value)
        if parsed is not None:
            return extract_structured_result(parsed)

    return None


def is_risk_result(value: dict[str, Any]) -> bool:
    return any(
        key in value
        for key in (
            "overall_risk_score",
            "overall_risk_level",
            "detected_interactions",
            "highest_risk_pair",
        )
    )


def parse_json_text(text: str) -> Any:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()

    for candidate in (cleaned, extract_first_json_object(cleaned)):
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


def extract_first_json_object(text: str) -> str | None:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return text[start : end + 1]


def normalize_name(name: str) -> str:
    return " ".join(name.strip().lower().split())


def validate_medication(name: str) -> dict[str, Any]:
    key = normalize_name(name)
    if key not in MEDICATION_CATALOG:
        known = ", ".join(sorted(item["name"] for item in MEDICATION_CATALOG.values()))
        raise MedicationCatalogError(
            f"'{name}' is not in the medication catalog. Please choose one of the supported demo medicines: {known}."
        )
    return MEDICATION_CATALOG[key]


def supported_medications() -> list[dict[str, Any]]:
    return [
        {
            "medicine_name": item["name"],
            "drug_class": item["class"],
            "high_daily_mg": item["high_daily_mg"],
            "max_daily_mg": item["max_daily_mg"],
        }
        for item in sorted(MEDICATION_CATALOG.values(), key=lambda entry: entry["name"])
    ]


def enrich_medication(medicine: dict[str, Any]) -> dict[str, Any]:
    catalog = validate_medication(medicine["medicine_name"])
    daily_dose_mg = estimate_daily_dose_mg(medicine.get("dosage", ""), medicine.get("frequency", ""))
    dose_status = dose_status_for(catalog, daily_dose_mg)
    return {
        "medicine_name": catalog["name"],
        "dosage": medicine.get("dosage", ""),
        "frequency": medicine.get("frequency", ""),
        "drug_class": catalog["class"],
        "estimated_daily_dose_mg": daily_dose_mg,
        "dose_status": dose_status,
    }


def estimate_daily_dose_mg(dosage: str, frequency: str) -> float | None:
    strength = parse_strength_mg(dosage)
    if strength is None:
        return None
    frequency_key = normalize_name(frequency)
    multiplier = FREQUENCY_MULTIPLIERS.get(frequency_key, 1)
    return round(strength * multiplier, 2)


def parse_strength_mg(dosage: str) -> float | None:
    normalized = dosage.lower().replace(",", "")
    word_multiplier = 1
    if re.search(r"\b(milyon|million)\b", normalized):
        word_multiplier = 1_000_000
        normalized = re.sub(r"\b(milyon|million)\b", "", normalized)
    elif re.search(r"\b(bin|thousand)\b", normalized):
        word_multiplier = 1_000
        normalized = re.sub(r"\b(bin|thousand)\b", "", normalized)

    match = re.search(r"(\d+(?:\.\d+)?)\s*(mcg|mg|g|units?)", normalized)
    if not match:
        return None
    value = float(match.group(1)) * word_multiplier
    unit = match.group(2)
    if unit == "g":
        return value * 1000
    if unit == "mcg":
        return value / 1000
    if unit.startswith("unit"):
        return None
    return value


def dose_status_for(catalog: dict[str, Any], daily_dose_mg: float | None) -> str:
    if daily_dose_mg is None:
        return "unknown"
    max_daily = catalog.get("max_daily_mg")
    high_daily = catalog.get("high_daily_mg")
    if max_daily is not None and daily_dose_mg > max_daily * 10:
        return "extreme_overdose_range"
    if high_daily is not None and max_daily is None and daily_dose_mg > high_daily * 10:
        return "extreme_overdose_range"
    if max_daily is not None and daily_dose_mg > max_daily:
        return "above_catalog_max"
    if high_daily is not None and daily_dose_mg >= high_daily:
        return "high"
    return "usual"


def apply_local_safety_floor(response: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    local = local_risk_assessment(
        payload["patient_data"],
        payload.get("current_medications", []),
        payload["new_medicine"],
    )
    local_score = int(local["overall_risk_score"])
    remote_score = int(response.get("overall_risk_score", 0))

    if local_score > remote_score:
        response["overall_risk_score"] = local_score
        response["overall_risk_level"] = local["overall_risk_level"]
        response["highest_risk_pair"] = local["highest_risk_pair"]
        response["detected_interactions"] = merge_interactions(
            response.get("detected_interactions", []),
            local["detected_interactions"],
        )
        response["clinical_explanation"] = local["clinical_explanation"]
        response["recommended_doctor_action"] = local["recommended_doctor_action"]
        response["high_risk_warning"] = local["high_risk_warning"]
        response["safer_alternatives"] = local["safer_alternatives"]
        response["local_safety_floor_applied"] = True

    return response


def merge_interactions(remote: list[dict[str, Any]], local: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged = list(remote)
    seen = {(item.get("current_medicine"), item.get("new_medicine")) for item in merged}
    for item in local:
        key = (item.get("current_medicine"), item.get("new_medicine"))
        if key not in seen:
            merged.append(item)
            seen.add(key)
    return merged


def get_fallback_puq_response(patient_id: int, new_medicine: dict[str, Any], patient_data: dict[str, Any] | None = None, current_medications: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    patient_data = patient_data or {}
    current_medications = current_medications or []
    return {
        **local_risk_assessment(patient_data, current_medications, new_medicine),
        "patient_id": patient_id,
        "is_fallback": True,
        "warning": WARNING,
    }


def local_risk_assessment(patient_data: dict[str, Any], current_medications: list[dict[str, Any]], new_medicine: dict[str, Any]) -> dict[str, Any]:
    enriched_current = [enrich_medication(item) for item in current_medications]
    enriched_new = enrich_medication(new_medicine)
    new_name = enriched_new["medicine_name"]
    factors = patient_specific_factors(patient_data, enriched_current, new_name)
    dose_factors = dose_frequency_factors(enriched_new)
    interactions = []

    for current in enriched_current:
        interaction = known_interaction(current["medicine_name"], new_name)
        score = interaction["base_score"] if interaction else 18
        if interaction:
            current_dose_factors = dose_frequency_factors(current)
            all_factors = factors + dose_factors + current_dose_factors
            score += factor_score(factors)
            score += dose_frequency_score(enriched_new, current)
            score = min(100, score)
            interactions.append(
                {
                    "current_medicine": current["medicine_name"],
                    "new_medicine": new_name,
                    "interaction_found": True,
                    "risk_score": score,
                    "risk_level": risk_level_from_score(score),
                    "possible_side_effects": interaction["possible_side_effects"],
                    "reason": interaction["reason"],
                    "patient_specific_factors": all_factors or ["No major patient-specific factor detected"],
                    "dose_frequency_note": dose_frequency_note(enriched_new, current),
                    "doctor_review_required": score > 30,
                }
            )

    allergy_hit = allergy_conflict(patient_data.get("allergies", ""), new_name)
    if allergy_hit:
        interactions.append(
            {
                "current_medicine": "Known allergy",
                "new_medicine": new_name,
                "interaction_found": True,
                "risk_score": 75,
                "risk_level": "High",
                "possible_side_effects": ["Potential allergy conflict"],
                "reason": "The new medicine may conflict with a recorded allergy or sensitivity.",
                "patient_specific_factors": factors + dose_factors + ["Recorded allergy"],
                "dose_frequency_note": dose_frequency_note(enriched_new, None),
                "doctor_review_required": True,
            }
        )

    if not interactions:
        score = no_interaction_score(factors, enriched_new)
        if enriched_new.get("dose_status") == "above_catalog_max":
            score = max(score, 72)
        if enriched_new.get("dose_status") == "extreme_overdose_range":
            score = max(score, 95)
        score = min(100, score)
        interactions.append(
            {
                "current_medicine": "Current medication list",
                "new_medicine": new_name,
                "interaction_found": False,
                "risk_score": score,
                "risk_level": risk_level_from_score(score),
                "possible_side_effects": ["No high-confidence demo interaction detected"],
                "reason": no_interaction_reason(enriched_new),
                "patient_specific_factors": factors + dose_factors or ["No major local risk factor detected"],
                "dose_frequency_note": dose_frequency_note(enriched_new, None),
                "doctor_review_required": score > 30,
            }
        )

    highest = max(interactions, key=lambda item: item["risk_score"])
    overall_score = highest["risk_score"]
    overall_level = risk_level_from_score(overall_score)
    highest_pair = f"{highest['current_medicine']} + {new_name}" if highest["interaction_found"] else "No high-risk pair detected"
    alternatives = safer_alternatives_for(new_name, highest, patient_data, current_medications, factors)

    return {
        "patient_id": patient_data.get("id"),
        "new_medicine": new_name,
        "overall_risk_score": overall_score,
        "overall_risk_level": overall_level,
        "detected_interactions": interactions,
        "highest_risk_pair": highest_pair,
        "clinical_explanation": clinical_explanation(new_name, highest, factors),
        "recommended_doctor_action": recommended_action(overall_level),
        "high_risk_warning": warning_for_level(overall_level),
        "safer_alternatives": alternatives if overall_level in {"Medium", "High"} else [],
        "safety_note": "This result is for clinical decision support only and does not replace professional medical judgment.",
        "dose_frequency_assessed": True,
    }


def known_interaction(current: str, new: str) -> dict[str, Any] | None:
    pair = {current.lower(), new.lower()}
    rules = [
        {
            "drugs": {"warfarin", "aspirin"},
            "base_score": 82,
            "possible_side_effects": ["Increased bleeding risk"],
            "reason": "Warfarin and Aspirin may both increase bleeding tendency.",
        },
        {
            "drugs": {"warfarin", "ibuprofen"},
            "base_score": 78,
            "possible_side_effects": ["Increased bleeding risk", "Gastrointestinal bleeding"],
            "reason": "Warfarin and Ibuprofen may increase anticoagulant-related bleeding risk.",
        },
        {
            "drugs": {"aspirin", "ibuprofen"},
            "base_score": 54,
            "possible_side_effects": ["Gastrointestinal bleeding", "Reduced antiplatelet effect"],
            "reason": "Both medicines can irritate the gastric mucosa and affect platelet-related bleeding risk.",
        },
        {
            "drugs": {"lisinopril", "spironolactone"},
            "base_score": 76,
            "possible_side_effects": ["Hyperkalemia", "Kidney function deterioration"],
            "reason": "Both medicines can raise potassium and require kidney function monitoring.",
        },
        {
            "drugs": {"metformin", "contrast agent"},
            "base_score": 58,
            "possible_side_effects": ["Kidney-related adverse effect", "Lactic acidosis risk in susceptible patients"],
            "reason": "Metformin risk may rise when kidney function is impaired around contrast exposure.",
        },
        {
            "drugs": {"clopidogrel", "omeprazole"},
            "base_score": 50,
            "possible_side_effects": ["Reduced antiplatelet effectiveness"],
            "reason": "Omeprazole may reduce activation of Clopidogrel in some patients.",
        },
        {
            "drugs": {"tamoxifen", "fluoxetine"},
            "base_score": 48,
            "possible_side_effects": ["Reduced endocrine therapy effectiveness"],
            "reason": "Fluoxetine may affect Tamoxifen metabolism.",
        },
        {
            "drugs": {"ibuprofen", "prednisone"},
            "base_score": 58,
            "possible_side_effects": ["Gastrointestinal bleeding", "Ulceration risk"],
            "reason": "NSAID and corticosteroid overlap may increase gastrointestinal adverse event risk.",
        },
        {
            "drugs": {"aspirin", "prednisone"},
            "base_score": 56,
            "possible_side_effects": ["Gastrointestinal bleeding", "Ulceration risk"],
            "reason": "Aspirin and corticosteroid overlap may increase gastrointestinal bleeding concern.",
        },
        {
            "drugs": {"sertraline", "ibuprofen"},
            "base_score": 48,
            "possible_side_effects": ["Increased bleeding risk"],
            "reason": "SSRI and NSAID overlap may increase bleeding risk in susceptible patients.",
        },
        {
            "drugs": {"fluoxetine", "ibuprofen"},
            "base_score": 50,
            "possible_side_effects": ["Increased bleeding risk"],
            "reason": "SSRI and NSAID overlap may increase bleeding risk in susceptible patients.",
        },
    ]

    for rule in rules:
        if rule["drugs"] == pair:
            return rule
    return None


def patient_specific_factors(patient: dict[str, Any], current_medications: list[dict[str, Any]], new_name: str) -> list[str]:
    factors = []
    if patient.get("age", 0) > 65:
        factors.append("Age over 65")
    if patient.get("hemoglobin", 99) < 11:
        factors.append("Low hemoglobin")
    if "impairment" in str(patient.get("kidney_function_status", "")).lower():
        factors.append("Kidney function impairment")
    if "elevated" in str(patient.get("liver_function_status", "")).lower():
        factors.append("Liver enzyme elevation")
    if patient.get("cancer_status") and patient.get("cancer_status") != "No active cancer":
        factors.append("Cancer diagnosis")
    if "Stage III" in str(patient.get("cancer_stage", "")) or "Stage IV" in str(patient.get("cancer_stage", "")):
        factors.append("Advanced cancer stage")
    if str(patient.get("smoking_status", "")).lower() == "current smoker":
        factors.append("Current smoker")
    if str(patient.get("alcohol_use", "")).lower() in {"regular", "occasional"}:
        factors.append("Alcohol use")
    if patient.get("chronic_disease_count", 0) >= 3:
        factors.append("Multiple chronic diseases")
    if len(current_medications) >= 5:
        factors.append("Polypharmacy")
    if allergy_conflict(patient.get("allergies", ""), new_name):
        factors.append("Recorded allergy")
    return factors


def dose_frequency_factors(medicine: dict[str, Any]) -> list[str]:
    factors = []
    daily_dose = medicine.get("estimated_daily_dose_mg")
    if daily_dose is not None:
        factors.append(f"{medicine['medicine_name']} estimated daily dose {daily_dose:g} mg")
    if medicine.get("dose_status") == "extreme_overdose_range":
        factors.append(f"{medicine['medicine_name']} extreme overdose-range daily dose")
    if medicine.get("dose_status") == "high":
        factors.append(f"{medicine['medicine_name']} high daily dose range")
    if medicine.get("dose_status") == "above_catalog_max":
        factors.append(f"{medicine['medicine_name']} above catalog maximum daily dose")
    frequency = normalize_name(medicine.get("frequency", ""))
    if "twice" in frequency or "three" in frequency or "four" in frequency:
        factors.append(f"{medicine['medicine_name']} repeated daily dosing")
    return factors


def dose_frequency_score(new_medicine: dict[str, Any], current_medicine: dict[str, Any] | None) -> int:
    score = single_dose_score(new_medicine)
    if current_medicine:
        score += single_dose_score(current_medicine)
        pair_classes = {new_medicine.get("drug_class"), current_medicine.get("drug_class")}
        if pair_classes & {"nsaid", "antiplatelet_nsaid"} and pair_classes & {"anticoagulant", "antiplatelet"}:
            score += 8
        if pair_classes == {"ace_inhibitor", "potassium_sparing_diuretic"}:
            score += 7
    return min(80, score)


def single_dose_score(medicine: dict[str, Any]) -> int:
    status = medicine.get("dose_status")
    if status == "extreme_overdose_range":
        return 70
    if status == "above_catalog_max":
        return 45
    if status == "high":
        return 12
    if "repeated daily dosing" in " ".join(dose_frequency_factors(medicine)).lower():
        return 3
    return 0


def dose_frequency_note(new_medicine: dict[str, Any], current_medicine: dict[str, Any] | None) -> str:
    notes = dose_frequency_factors(new_medicine)
    if current_medicine:
        notes += dose_frequency_factors(current_medicine)
    return "; ".join(notes) if notes else "Dose and frequency did not add a specific local risk modifier."


def no_interaction_score(factors: list[str], new_medicine: dict[str, Any]) -> int:
    dose_status = new_medicine.get("dose_status")
    if dose_status == "extreme_overdose_range":
        return 95
    if dose_status == "above_catalog_max":
        return 72

    score = 8
    cautious_factor_weights = {
        "Age over 65": 3,
        "Low hemoglobin": 2,
        "Kidney function impairment": 4,
        "Liver enzyme elevation": 4,
        "Cancer diagnosis": 3,
        "Advanced cancer stage": 4,
        "Current smoker": 1,
        "Alcohol use": 2,
        "Multiple chronic diseases": 3,
        "Polypharmacy": 3,
        "Recorded allergy": 12,
    }
    score += sum(cautious_factor_weights.get(factor, 0) for factor in factors)
    if dose_status == "high":
        score += 8
    if "repeated daily dosing" in " ".join(dose_frequency_factors(new_medicine)).lower():
        score += 2
    return min(40, score)


def no_interaction_reason(new_medicine: dict[str, Any]) -> str:
    if new_medicine.get("dose_status") == "extreme_overdose_range":
        return (
            "No known pairwise interaction was detected, but the entered dose is far above the catalog maximum. "
            "This creates a critical dose-related medication safety concern that requires urgent doctor review."
        )
    if new_medicine.get("dose_status") == "above_catalog_max":
        return (
            "No known pairwise interaction was detected, but the entered dose is above the catalog maximum. "
            "This raises a high dose-related medication safety concern requiring doctor review."
        )
    return "Local safety logic did not find a known serious interaction, but clinical review is still required."


def allergy_conflict(allergies: str, medicine_name: str) -> bool:
    lowered_allergies = allergies.lower()
    lowered_medicine = medicine_name.lower()
    if lowered_allergies in {"none", "yok", ""}:
        return False
    if "nsaid" in lowered_allergies and lowered_medicine in {"aspirin", "ibuprofen", "naproxen"}:
        return True
    if "sulfa" in lowered_allergies and lowered_medicine in {"sulfamethoxazole", "furosemide"}:
        return True
    if "penicillin" in lowered_allergies and lowered_medicine in {"penicillin", "amoxicillin"}:
        return True
    return lowered_medicine in lowered_allergies


def factor_score(factors: list[str]) -> int:
    weights = {
        "Age over 65": 8,
        "Low hemoglobin": 9,
        "Kidney function impairment": 8,
        "Liver enzyme elevation": 6,
        "Cancer diagnosis": 7,
        "Advanced cancer stage": 8,
        "Current smoker": 4,
        "Alcohol use": 4,
        "Multiple chronic diseases": 6,
        "Polypharmacy": 6,
        "Recorded allergy": 15,
    }
    return sum(weights.get(factor, 0) for factor in factors)


def risk_level_from_score(score: int) -> str:
    if score <= 30:
        return "Low"
    if score <= 60:
        return "Medium"
    return "High"


def recommended_action(level: str) -> str:
    if level == "High":
        return "Doctor review required before approving this medicine. Consider alternatives, additional labs, or specialist/pharmacology review."
    if level == "Medium":
        return "Doctor review required. Confirm indication, dose, monitoring plan, and patient-specific risk factors."
    return "Low-risk support result. Doctor review is still required before any clinical action."


def warning_for_level(level: str) -> str:
    if level == "High":
        return (
            "High risk detected. Do not treat this as an automatic approval. "
            "A doctor must review the interaction, patient factors, and any lower-risk alternatives."
        )
    if level == "Medium":
        return (
            "Medium risk detected. Doctor review is required before any clinical action. "
            "Consider whether a lower-risk alternative can meet the same clinical intent."
        )
    return "Low risk support result. Doctor review is still required before clinical use."


def safer_alternatives_for(
    new_name: str,
    highest: dict[str, Any],
    patient: dict[str, Any],
    current_medications: list[dict[str, Any]],
    factors: list[str],
) -> list[dict[str, Any]]:
    current_names = {item["medicine_name"].lower() for item in current_medications}
    new_lower = new_name.lower()
    alternatives_by_trigger = {
        "aspirin": [
            {
                "medicine_name": "Paracetamol",
                "suggested_use_case": "Analgesic option when antiplatelet effect is not the clinical goal",
                "estimated_risk_score": 24,
                "estimated_risk_level": "Low",
                "rationale": "It does not add the same antiplatelet bleeding tendency in this demo rule set.",
                "doctor_review_required": True,
            },
            {
                "medicine_name": "Topical NSAID",
                "suggested_use_case": "Localized musculoskeletal pain option",
                "estimated_risk_score": 28,
                "estimated_risk_level": "Low",
                "rationale": "Lower systemic exposure may reduce interaction burden, depending on indication and patient context.",
                "doctor_review_required": True,
            },
        ],
        "ibuprofen": [
            {
                "medicine_name": "Paracetamol",
                "suggested_use_case": "Pain or fever option",
                "estimated_risk_score": 22,
                "estimated_risk_level": "Low",
                "rationale": "Fallback logic does not flag a serious Warfarin bleeding interaction for Paracetamol.",
                "doctor_review_required": True,
            }
        ],
        "spironolactone": [
            {
                "medicine_name": "Amlodipine",
                "suggested_use_case": "Blood pressure control option when clinically appropriate",
                "estimated_risk_score": 26,
                "estimated_risk_level": "Low",
                "rationale": "It does not share the same potassium-raising mechanism as Lisinopril in this demo rule set.",
                "doctor_review_required": True,
            }
        ],
        "omeprazole": [
            {
                "medicine_name": "Pantoprazole",
                "suggested_use_case": "Gastric acid suppression option",
                "estimated_risk_score": 30,
                "estimated_risk_level": "Low",
                "rationale": "Often considered when Clopidogrel interaction concern exists, but doctor confirmation is required.",
                "doctor_review_required": True,
            }
        ],
        "fluoxetine": [
            {
                "medicine_name": "Sertraline",
                "suggested_use_case": "Alternative SSRI option when clinically appropriate",
                "estimated_risk_score": 34,
                "estimated_risk_level": "Medium",
                "rationale": "May have less concern with Tamoxifen metabolism than Fluoxetine in this demo rule set.",
                "doctor_review_required": True,
            }
        ],
    }
    alternatives = alternatives_by_trigger.get(new_lower, [])

    if not alternatives and highest.get("current_medicine", "").lower() in {"warfarin", "aspirin", "ibuprofen"}:
        alternatives = alternatives_by_trigger["ibuprofen"]

    filtered = [item for item in alternatives if item["medicine_name"].lower() not in current_names]
    if not filtered:
        filtered = [
            {
                "medicine_name": "Specialist-selected alternative",
                "suggested_use_case": "Same clinical intent after doctor/pharmacology review",
                "estimated_risk_score": max(18, min(45, highest["risk_score"] - 35)),
                "estimated_risk_level": "Medium" if highest["risk_score"] > 80 else "Low",
                "rationale": (
                    "No specific fallback alternative was available without duplicating the current medicine list. "
                    f"Patient factors considered: {', '.join(factors) if factors else 'none flagged'}."
                ),
                "doctor_review_required": True,
            }
        ]

    for item in filtered:
        item["safety_note"] = "Alternative suggestion for doctor review only. The system does not prescribe or change medication."
    return filtered


def clinical_explanation(new_name: str, highest: dict[str, Any], factors: list[str]) -> str:
    factor_text = ", ".join(factors) if factors else "no major fallback risk modifiers"
    if highest["interaction_found"]:
        return (
            f"The new medicine {new_name} was compared with the current medication list. "
            f"The highest fallback risk was found for {highest['current_medicine']} due to: {highest['reason']} "
            f"Patient-specific factors considered: {factor_text}."
        )
    return (
        f"No high-confidence serious interaction was detected by fallback demo logic for {new_name}. "
        f"Patient-specific factors considered: {factor_text}. This is not a final medical decision."
    )
