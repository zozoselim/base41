from __future__ import annotations

import json
import re
from itertools import combinations
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"


app = FastAPI(
    title="OncoSafe Vision AI API",
    description="Hackathon MVP için sentetik veri kullanan klinik karar destek API'si.",
    version="0.1.0",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ScanMedicationRequest(BaseModel):
    patient_id: str = "P001"
    image: str | None = None


class ScanMedicineGuideRequest(BaseModel):
    patient_id: str = "P001"
    image: str | None = None
    detected_name: str | None = None


class PrescriptionScanRequest(BaseModel):
    patient_id: str = "P001"
    image: str | None = None
    ocr_text: str | None = None


class AnalyzeDrugRiskRequest(BaseModel):
    patient_id: str
    medications: list[str]


class PredictChemoRiskRequest(BaseModel):
    patient_id: str
    age: int | None = None
    tumor_size: float | None = None
    grade: int | None = None
    node_status: int | None = None
    er: int | None = None
    pr: int | None = None
    her2: int | None = None
    ki67: int | None = None
    synthetic_gene_score: int | None = None


class DoctorDecisionRequest(BaseModel):
    patient_id: str
    decision: Literal["approve", "reject", "modify_alternative", "request_further_test"]
    note: str | None = None


def load_json(name: str):
    with (DATA_DIR / name).open(encoding="utf-8") as file:
        return json.load(file)


def patients():
    return load_json("patients.json")


def interactions():
    return load_json("drug_interactions.json")


def medicine_guides():
    return load_json("medicine_guides.json")


def medication_info():
    return load_json("medication_info.json")


def demo_prescriptions():
    return load_json("prescriptions.json")


def find_patient(patient_id: str):
    patient = next((item for item in patients() if item["patient_id"] == patient_id), None)
    if not patient:
        raise HTTPException(status_code=404, detail="Hasta bulunamadı")
    return patient


def patient_factor_score(patient: dict) -> tuple[int, list[str]]:
    score = 0
    factors: list[str] = []

    if patient["age"] > 65:
        score += 10
        factors.append("Yaş > 65")
    if patient["creatinine"] >= 1.4:
        score += 8
        factors.append("Böbrek fonksiyonunda risk göstergesi")
    if patient["alt"] > 50 or patient["ast"] > 50:
        score += 7
        factors.append("Karaciğer enzimlerinde yükselme")
    if patient["hemoglobin"] < 11:
        score += 10
        factors.append("Düşük hemoglobin")
    if "Breast Cancer" in patient["diagnoses"] or "Meme Kanseri" in patient["diagnoses"]:
        score += 5
        factors.append("Kanser hastası faktörü")
    if patient["allergies"] != ["None"] and patient["allergies"] != ["Yok"]:
        score += 5
        factors.append("Bilinen alerji öyküsü")

    return score, factors


def match_interaction(drug_a: str, drug_b: str):
    for rule in interactions():
        if {rule["drug_a"], rule["drug_b"]} == {drug_a, drug_b}:
            return rule
    return None


def extract_usage_instruction(ocr_text: str, medication_name: str) -> dict:
    pattern = rf"{re.escape(medication_name)}\s*([^.]*)"
    match = re.search(pattern, ocr_text, flags=re.IGNORECASE)
    instruction = match.group(0).strip() if match else medication_name

    dose_match = re.search(r"(\d+\s*mg)", instruction, flags=re.IGNORECASE)
    frequency_match = re.search(
        r"(günde\s+\d+\s+kez|sabah\s+akşam|günde\s+bir\s+kez)",
        instruction,
        flags=re.IGNORECASE,
    )
    duration_match = re.search(r"(\d+\s+gün)", instruction, flags=re.IGNORECASE)

    return {
        "raw_instruction": instruction,
        "dose": dose_match.group(1) if dose_match else "Reçete metninde belirtilmemiş",
        "frequency": frequency_match.group(1) if frequency_match else "Reçete metninde belirtilmemiş",
        "time": "Sabah ve akşam" if "sabah akşam" in instruction.lower() else "Reçete metnine göre",
        "duration": duration_match.group(1) if duration_match else "Reçete metninde belirtilmemiş",
    }


@app.get("/patients")
def list_patients():
    return patients()


@app.get("/patients/{patient_id}")
def get_patient(patient_id: str):
    return find_patient(patient_id)


@app.post("/scan-medications")
def scan_medications(payload: ScanMedicationRequest):
    mock_outputs = {
        "P001": [
            {"name": "Warfarin", "confidence": 0.94},
            {"name": "Ibuprofen", "confidence": 0.91},
            {"name": "Lisinopril", "confidence": 0.88},
        ],
        "P002": [
            {"name": "Metformin", "confidence": 0.93},
            {"name": "Aspirin", "confidence": 0.90},
        ],
        "P003": [
            {"name": "Warfarin", "confidence": 0.95},
            {"name": "Aspirin", "confidence": 0.92},
            {"name": "Spironolactone", "confidence": 0.89},
            {"name": "Lisinopril", "confidence": 0.86},
        ],
    }

    return {
        "source": "NovaVision simülasyon çıktısı",
        "image": payload.image,
        "detected_medications": mock_outputs.get(payload.patient_id, []),
    }


@app.post("/scan-medicine-guide")
def scan_medicine_guide(payload: ScanMedicineGuideRequest):
    patient = find_patient(payload.patient_id)
    detected_name = payload.detected_name or patient["current_drugs"][0]
    guide = medicine_guides().get(detected_name)

    if not guide:
        raise HTTPException(status_code=404, detail="İlaç rehberi bulunamadı")

    return {
        "source": "NovaVision object detection simülasyon çıktısı",
        "image": payload.image,
        "detected_medication": {
            "name": detected_name,
            "confidence": 0.96,
            "bbox": {"x": 128, "y": 84, "width": 420, "height": 260},
        },
        "prescription_summary": guide,
        "safety_note": "Bu bilgi reçete veya doktor/eczacı danışmanlığının yerine geçmez.",
    }


@app.post("/prescription-scan")
def prescription_scan(payload: PrescriptionScanRequest):
    find_patient(payload.patient_id)
    prescriptions = demo_prescriptions()
    demo = next(
        (item for item in prescriptions if item["patient_id"] == payload.patient_id),
        prescriptions[0],
    )
    ocr_text = payload.ocr_text or demo["ocr_text"]
    found_medications = []

    for medication_name, info in medication_info().items():
        if re.search(rf"\b{re.escape(medication_name)}\b", ocr_text, flags=re.IGNORECASE):
            usage = extract_usage_instruction(ocr_text, medication_name)
            found_medications.append(
                {
                    "name": medication_name,
                    "display_name": info["display_name"],
                    "active_ingredient": info["active_ingredient"],
                    "purpose": info["purpose"],
                    "dose": usage["dose"],
                    "frequency": usage["frequency"],
                    "time": usage["time"],
                    "duration": usage["duration"],
                    "raw_instruction": usage["raw_instruction"],
                    "side_effects": info["side_effects"],
                    "warnings": info["warnings"],
                    "alternative": info["alternative"],
                    "doctor_approval": info["doctor_approval"],
                    "safety_note": "Bu bilgi doktor reçetesine dayalıdır. Tedavi kararı doktor onayı gerektirir.",
                }
            )

    return {
        "patient_id": payload.patient_id,
        "source": "NovaVision OCR Text Detection simülasyon çıktısı",
        "image": payload.image,
        "ocr_text": ocr_text,
        "medication_count": len(found_medications),
        "medications": found_medications,
    }


@app.post("/analyze-drug-risk")
def analyze_drug_risk(payload: AnalyzeDrugRiskRequest):
    patient = find_patient(payload.patient_id)
    extra_score, factors = patient_factor_score(patient)
    found = []

    for drug_a, drug_b in combinations(payload.medications, 2):
        rule = match_interaction(drug_a, drug_b)
        if not rule:
            continue

        score = min(100, rule["base_score"] + extra_score)
        level = "Yüksek" if score >= 70 else "Orta" if score >= 40 else "Düşük"
        found.append(
            {
                "drug_pair": f"{drug_a} + {drug_b}",
                "risk_score": score,
                "risk_level": level,
                "possible_side_effect": rule["side_effect"],
                "reason": f"{rule['reason']} Hastaya özel faktörler: {', '.join(factors) or 'Belirgin ek faktör yok'}.",
                "alternative": rule["alternative"],
                "doctor_review_required": True,
            }
        )

    overall_score = max([item["risk_score"] for item in found], default=18)
    overall_risk = "Yüksek" if overall_score >= 70 else "Orta" if overall_score >= 40 else "Düşük"

    return {
        "patient_id": payload.patient_id,
        "overall_risk": overall_risk,
        "risk_score": overall_score,
        "interactions": found,
    }


@app.post("/predict-chemo-risk")
def predict_chemo_risk(payload: PredictChemoRiskRequest):
    patient = find_patient(payload.patient_id)
    features = patient | payload.model_dump(exclude_none=True)

    score = 0
    reasons: list[str] = []
    score += min(25, features["tumor_size"] * 7)
    score += features["grade"] * 10
    score += 18 if features["node_status"] else 0
    score += 16 if features["ki67"] >= 30 else 9 if features["ki67"] >= 15 else 2
    score += round(features["synthetic_gene_score"] * 0.32)
    score += 5 if features["pr"] == 0 else 0
    score -= 3 if features["age"] > 70 else 0
    final_score = max(5, min(96, round(score)))

    if features["grade"] >= 3:
        reasons.append("Yüksek tümör derecesi")
    if features["ki67"] >= 30:
        reasons.append("Yüksek Ki-67 değeri")
    if features["node_status"]:
        reasons.append("Pozitif lenf nodu tutulumu")
    if features["synthetic_gene_score"] >= 60:
        reasons.append("Yüksek sentetik genomik risk skoru")
    if features["tumor_size"] >= 2.5:
        reasons.append("Daha büyük tümör boyutu")
    if not reasons:
        reasons.append("Daha düşük derece, küçük tümör boyutu ve düşük sentetik genomik risk skoru")

    beneficial = final_score >= 55
    confidence = min(0.92, 0.68 + final_score / 400) if beneficial else max(0.66, 0.9 - final_score / 300)

    return {
        "patient_id": payload.patient_id,
        "cancer_therapy_risk_score": final_score,
        "prediction": "Kemoterapi faydalı olabilir" if beneficial else "Kemoterapi gerekli olmayabilir",
        "confidence": round(confidence, 2),
        "explanation": reasons,
        "doctor_review_required": True,
        "safety_note": "Bu çıktı Oncotype DX, genetik test veya klinik karar verme sürecinin yerine geçmez.",
    }


@app.post("/doctor-decision")
def doctor_decision(payload: DoctorDecisionRequest):
    find_patient(payload.patient_id)
    return {
        "patient_id": payload.patient_id,
        "decision": payload.decision,
        "note": payload.note,
        "status": "Doktor kontrollü iş akışı için kaydedildi",
    }
