from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv


WARNING = "Puq.ai servisine şu anda ulaşılamıyor. Güvenli demo sonucu gösteriliyor."
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
            "risk_scoring": "0-30 Düşük, 31-60 Orta, 61-100 Yüksek",
            "output_language": "Turkish",
        },
    }


async def call_puq_webhook(payload: dict[str, Any]) -> dict[str, Any]:
    webhook_url = os.getenv("PUQ_WEBHOOK_URL", "").strip()
    api_key = os.getenv("PUQ_API_KEY", "").strip()

    if not webhook_url or webhook_url == "your_puq_ai_webhook_url":
        raise RuntimeError("PUQ_WEBHOOK_URL yapılandırılmamış")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Token {api_key}",
    }
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(webhook_url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()

    if not isinstance(data, dict):
        raise RuntimeError("Puq.ai yanıtı bir JSON nesnesi olmalıdır")

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
    response.setdefault("highest_risk_pair", "Etkileşim bulunmadı")
    response.setdefault(
        "clinical_explanation",
        "Puq.ai ajanı kritik bir etkileşim döndürmedi. Klinik kullanım için doktor değerlendirmesi gereklidir.",
    )
    response.setdefault("recommended_doctor_action", "Herhangi bir klinik işlem öncesinde sonucu değerlendirin.")
    response.setdefault(
        "safety_note",
        "Bu sonuç yalnızca klinik karar desteği içindir ve profesyonel tıbbi değerlendirmenin yerine geçmez.",
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
                "current_medicine": "Bilinen alerji",
                "new_medicine": new_name,
                "interaction_found": True,
                "risk_score": 75,
                "risk_level": "High",
                "possible_side_effects": ["Olası alerji uyumsuzluğu"],
                "reason": "Yeni ilaç kayıtlı alerji veya duyarlılıkla uyumsuz olabilir.",
                "patient_specific_factors": factors + ["Kayıtlı alerji"],
                "doctor_review_required": True,
            }
        )

    if not interactions:
        score = min(60, 18 + factor_score(factors))
        interactions.append(
            {
                "current_medicine": "Mevcut ilaç listesi",
                "new_medicine": new_name,
                "interaction_found": False,
                "risk_score": score,
                "risk_level": risk_level_from_score(score),
                "possible_side_effects": ["Yüksek güvenli demo etkileşimi saptanmadı"],
                "reason": "Demo yedek mantığı bilinen ciddi bir etkileşim bulmadı; yine de klinik değerlendirme gereklidir.",
                "patient_specific_factors": factors or ["Belirgin yedek risk faktörü saptanmadı"],
                "doctor_review_required": score > 30,
            }
        )

    highest = max(interactions, key=lambda item: item["risk_score"])
    overall_score = highest["risk_score"]
    overall_level = risk_level_from_score(overall_score)
    highest_pair = f"{highest['current_medicine']} + {new_name}" if highest["interaction_found"] else "Yüksek riskli eşleşme saptanmadı"

    return {
        "patient_id": patient_id,
        "new_medicine": new_name,
        "overall_risk_score": overall_score,
        "overall_risk_level": overall_level,
        "detected_interactions": interactions,
        "highest_risk_pair": highest_pair,
        "clinical_explanation": clinical_explanation(new_name, highest, factors),
        "recommended_doctor_action": recommended_action(overall_level),
        "safety_note": "Bu sonuç yalnızca klinik karar desteği içindir ve profesyonel tıbbi değerlendirmenin yerine geçmez.",
        "is_fallback": True,
        "warning": WARNING,
    }


def known_interaction(current: str, new: str) -> dict[str, Any] | None:
    pair = {current.lower(), new.lower()}
    rules = [
        {
            "drugs": {"warfarin", "aspirin"},
            "base_score": 70,
            "possible_side_effects": ["Kanama riskinde artış"],
            "reason": "Warfarin ve Aspirin birlikte kanama eğilimini artırabilir.",
        },
        {
            "drugs": {"warfarin", "ibuprofen"},
            "base_score": 72,
            "possible_side_effects": ["Kanama riskinde artış", "Gastrointestinal kanama"],
            "reason": "Warfarin ve Ibuprofen antikoagülan ilişkili kanama riskini artırabilir.",
        },
        {
            "drugs": {"aspirin", "ibuprofen"},
            "base_score": 54,
            "possible_side_effects": ["Gastrointestinal kanama", "Antiplatelet etkide azalma"],
            "reason": "İki ilaç da mide mukozasını irrite edebilir ve platelet ilişkili kanama riskini etkileyebilir.",
        },
        {
            "drugs": {"lisinopril", "spironolactone"},
            "base_score": 68,
            "possible_side_effects": ["Hiperkalemi", "Böbrek fonksiyonunda kötüleşme"],
            "reason": "İki ilaç da potasyumu yükseltebilir ve böbrek fonksiyonu izlemi gerektirir.",
        },
        {
            "drugs": {"metformin", "contrast agent"},
            "base_score": 58,
            "possible_side_effects": ["Böbrekle ilişkili advers etki", "Duyarlı hastalarda laktik asidoz riski"],
            "reason": "Kontrast maruziyeti çevresinde böbrek fonksiyonu bozulmuşsa Metformin riski artabilir.",
        },
        {
            "drugs": {"clopidogrel", "omeprazole"},
            "base_score": 42,
            "possible_side_effects": ["Antiplatelet etkinlikte azalma"],
            "reason": "Omeprazole bazı hastalarda Clopidogrel aktivasyonunu azaltabilir.",
        },
        {
            "drugs": {"tamoxifen", "fluoxetine"},
            "base_score": 48,
            "possible_side_effects": ["Endokrin tedavi etkinliğinde azalma"],
            "reason": "Fluoxetine Tamoxifen metabolizmasını etkileyebilir.",
        },
    ]

    for rule in rules:
        if rule["drugs"] == pair:
            return rule
    return None


def patient_specific_factors(patient: dict[str, Any], current_medications: list[dict[str, Any]], new_name: str) -> list[str]:
    factors = []
    cancer_status = str(patient.get("cancer_status", "")).strip()
    has_cancer = bool(cancer_status and cancer_status not in {"No active cancer", "Aktif kanser yok", "Yok", "N/A"})
    if patient.get("age", 0) > 65:
        factors.append("65 yaş üzeri")
    if patient.get("hemoglobin", 99) < 11:
        factors.append("Düşük hemoglobin")
    if "impairment" in str(patient.get("kidney_function_status", "")).lower():
        factors.append("Böbrek fonksiyon bozukluğu")
    if "elevated" in str(patient.get("liver_function_status", "")).lower():
        factors.append("Karaciğer enzim yüksekliği")
    if has_cancer:
        factors.append("Kanser tanısı")
    if has_cancer and ("Stage III" in str(patient.get("cancer_stage", "")) or "Stage IV" in str(patient.get("cancer_stage", ""))):
        factors.append("İleri kanser evresi")
    if str(patient.get("smoking_status", "")).lower() == "current smoker":
        factors.append("Aktif sigara kullanımı")
    if str(patient.get("alcohol_use", "")).lower() in {"regular", "occasional"}:
        factors.append("Alkol kullanımı")
    if patient.get("chronic_disease_count", 0) >= 3:
        factors.append("Çoklu kronik hastalık")
    if len(current_medications) >= 5:
        factors.append("Çoklu ilaç kullanımı")
    if allergy_conflict(patient.get("allergies", ""), new_name):
        factors.append("Kayıtlı alerji")
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
        "65 yaş üzeri": 8,
        "Düşük hemoglobin": 9,
        "Böbrek fonksiyon bozukluğu": 8,
        "Karaciğer enzim yüksekliği": 6,
        "Kanser tanısı": 7,
        "İleri kanser evresi": 8,
        "Aktif sigara kullanımı": 4,
        "Alkol kullanımı": 4,
        "Çoklu kronik hastalık": 6,
        "Çoklu ilaç kullanımı": 6,
        "Kayıtlı alerji": 15,
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
        return "Bu ilacı onaylamadan önce doktor değerlendirmesi gereklidir. Alternatifleri, ek laboratuvarları veya uzman/klinik farmakoloji değerlendirmesini düşünün."
    if level == "Medium":
        return "Doktor değerlendirmesi gereklidir. Endikasyonu, dozu, izlem planını ve hastaya özel risk faktörlerini doğrulayın."
    return "Düşük riskli destek sonucu. Herhangi bir klinik işlem öncesinde yine de doktor değerlendirmesi gereklidir."


def clinical_explanation(new_name: str, highest: dict[str, Any], factors: list[str]) -> str:
    factor_text = ", ".join(factors) if factors else "belirgin yedek risk değiştiricisi yok"
    if highest["interaction_found"]:
        return (
            f"Yeni ilaç {new_name}, mevcut ilaç listesiyle karşılaştırıldı. "
            f"En yüksek yedek risk {highest['current_medicine']} için bulundu. Gerekçe: {highest['reason']} "
            f"Dikkate alınan hastaya özel faktörler: {factor_text}."
        )
    return (
        f"{new_name} için yedek demo mantığı yüksek güvenli ciddi bir etkileşim saptamadı. "
        f"Dikkate alınan hastaya özel faktörler: {factor_text}. Bu nihai bir tıbbi karar değildir."
    )
