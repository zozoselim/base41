from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv


WARNING = "Puq.ai service is currently unavailable. Showing fallback demo result."
ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


def prepare_puq_payload(
    patient_data: dict[str, Any],
    current_medications: list[dict[str, Any]],
    new_medicine: dict[str, Any],
) -> dict[str, Any]:
    return {
        "task": "medication_risk_analysis",
        "patient_data": patient_data,
        "current_medications": [
            {
                "medicine_name": item["medicine_name"],
                "dosage": item["dosage"],
                "frequency": item["frequency"],
            }
            for item in current_medications
        ],
        "new_medicine": new_medicine,
        "instructions": {
            "compare_new_medicine_with_current_medications": True,
            "calculate_risk_score": True,
            "return_structured_json": True,
            "doctor_review_required": True,
            "do_not_make_final_medical_decisions": True,
            "risk_scoring": "0-30 Low, 31-60 Medium, 61-100 High",
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
        data = response.json()

    if not isinstance(data, dict):
        raise RuntimeError("Puq.ai response must be a JSON object")

    return normalize_puq_response(data, payload)


def normalize_puq_response(response: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    if "result" in response and isinstance(response["result"], dict):
        response = response["result"]
    if "data" in response and isinstance(response["data"], dict):
        response = response["data"]

    patient_id = payload["patient_data"]["id"]
    medicine_name = payload["new_medicine"]["medicine_name"]
    response.setdefault("patient_id", patient_id)
    response.setdefault("new_medicine", medicine_name)
    response.setdefault("detected_interactions", [])
    response.setdefault("overall_risk_score", 0)
    response.setdefault("overall_risk_level", risk_level_from_score(int(response["overall_risk_score"])))
    response.setdefault("highest_risk_pair", "No interaction found")
    response.setdefault(
        "clinical_explanation",
        "No critical interaction was returned by the Puq.ai agent. Doctor review remains required for clinical use.",
    )
    response.setdefault("recommended_doctor_action", "Review the result before taking any clinical action.")
    response.setdefault(
        "safety_note",
        "This result is for clinical decision support only and does not replace professional medical judgment.",
    )
    response["is_fallback"] = False
    return response


def get_fallback_puq_response(patient_id: int, new_medicine: dict[str, Any], patient_data: dict[str, Any] | None = None, current_medications: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    patient_data = patient_data or {}
    current_medications = current_medications or []
    new_name = new_medicine["medicine_name"]
    factors = patient_specific_factors(patient_data, current_medications, new_name)
    interactions = []

    for current in current_medications:
        interaction = known_interaction(current["medicine_name"], new_name)
        score = interaction["base_score"] if interaction else 18
        if interaction:
            score += factor_score(factors)
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
                    "patient_specific_factors": factors,
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
                "patient_specific_factors": factors + ["Recorded allergy"],
                "doctor_review_required": True,
            }
        )

    if not interactions:
        score = min(60, 18 + factor_score(factors))
        interactions.append(
            {
                "current_medicine": "Current medication list",
                "new_medicine": new_name,
                "interaction_found": False,
                "risk_score": score,
                "risk_level": risk_level_from_score(score),
                "possible_side_effects": ["No high-confidence demo interaction detected"],
                "reason": "Fallback demo logic did not find a known serious interaction, but clinical review is still required.",
                "patient_specific_factors": factors or ["No major fallback risk factor detected"],
                "doctor_review_required": score > 30,
            }
        )

    highest = max(interactions, key=lambda item: item["risk_score"])
    overall_score = highest["risk_score"]
    overall_level = risk_level_from_score(overall_score)
    highest_pair = f"{highest['current_medicine']} + {new_name}" if highest["interaction_found"] else "No high-risk pair detected"

    return {
        "patient_id": patient_id,
        "new_medicine": new_name,
        "overall_risk_score": overall_score,
        "overall_risk_level": overall_level,
        "detected_interactions": interactions,
        "highest_risk_pair": highest_pair,
        "clinical_explanation": clinical_explanation(new_name, highest, factors),
        "recommended_doctor_action": recommended_action(overall_level),
        "safety_note": "This result is for clinical decision support only and does not replace professional medical judgment.",
        "is_fallback": True,
        "warning": WARNING,
    }


def known_interaction(current: str, new: str) -> dict[str, Any] | None:
    pair = {current.lower(), new.lower()}
    rules = [
        {
            "drugs": {"warfarin", "aspirin"},
            "base_score": 70,
            "possible_side_effects": ["Increased bleeding risk"],
            "reason": "Warfarin and Aspirin may both increase bleeding tendency.",
        },
        {
            "drugs": {"warfarin", "ibuprofen"},
            "base_score": 72,
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
            "base_score": 68,
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
            "base_score": 42,
            "possible_side_effects": ["Reduced antiplatelet effectiveness"],
            "reason": "Omeprazole may reduce activation of Clopidogrel in some patients.",
        },
        {
            "drugs": {"tamoxifen", "fluoxetine"},
            "base_score": 48,
            "possible_side_effects": ["Reduced endocrine therapy effectiveness"],
            "reason": "Fluoxetine may affect Tamoxifen metabolism.",
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
