from __future__ import annotations

import base64
import json
import os
import re
from itertools import combinations
from pathlib import Path
from typing import Literal
from urllib import error, request

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
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


def extract_usage_instruction(ocr_text: str, matched_name: str) -> dict:
    pattern = rf"{re.escape(matched_name)}\s*([^.]*)"
    match = re.search(pattern, ocr_text, flags=re.IGNORECASE)
    instruction = match.group(0).strip() if match else matched_name

    dose_match = re.search(r"(\d+\s*mg)", instruction, flags=re.IGNORECASE)
    normalized_dose = dose_match.group(1).replace(" ", "") if dose_match else None
    if normalized_dose:
        normalized_dose = re.sub(r"(\d+)(mg)", r"\1 mg", normalized_dose, flags=re.IGNORECASE)

    normalized_frequency = re.search(
        r"(günde\s+\d+\s+kez|gÃ¼nde\s+\d+\s+kez|sabah\s+akşam|sabah\s+akÅŸam|günde\s+bir\s+kez|gÃ¼nde\s+bir\s+kez)",
        instruction,
        flags=re.IGNORECASE,
    )
    normalized_duration = re.search(r"(\d+\s+gün|\d+\s+gÃ¼n)", instruction, flags=re.IGNORECASE)

    folded_instruction = instruction.lower()
    for source_char, target_char in (
        ("\u00fc", "u"),
        ("\u015f", "s"),
        ("\u0131", "i"),
        ("\u0130", "i"),
        ("\u00e7", "c"),
        ("\u00f6", "o"),
        ("\u011f", "g"),
    ):
        folded_instruction = folded_instruction.replace(source_char, target_char)

    fallback_frequency = None
    frequency_count_match = re.search(r"g\S?nde\s+(\d+)\s+kez", folded_instruction)
    if frequency_count_match:
        fallback_frequency = f"günde {frequency_count_match.group(1)} kez"
    elif re.search(r"sabah\s+ak\S?am", folded_instruction):
        fallback_frequency = "sabah akşam"
    elif re.search(r"g\S?nde\s+bir\s+kez", folded_instruction):
        fallback_frequency = "günde bir kez"

    fallback_duration = None
    fallback_duration_match = re.search(r"(\d+)\s+g\S?n", folded_instruction)
    if fallback_duration_match:
        fallback_duration = f"{fallback_duration_match.group(1)} gün"

    return {
        "raw_instruction": instruction,
        "dose": normalized_dose if normalized_dose else "Reçete metninde belirtilmemiş",
        "frequency": normalized_frequency.group(1) if normalized_frequency else fallback_frequency or "Reçete metninde belirtilmemiş",
        "time": "Sabah ve akşam" if "sabah akşam" in instruction.lower() or "sabah akÅŸam" in instruction.lower() else "Reçete metnine göre",
        "duration": normalized_duration.group(1) if normalized_duration else fallback_duration or "Reçete metninde belirtilmemiş",
    }


OCR_TEXT_KEYS = {
    "outputContent",
    "outputText",
    "text",
    "recognized_text",
    "ocr_text",
    "content",
    "value",
}


OCR_REPLACEMENTS = {
    "Amoksisil": "Amoksisilin",
}


def normalize_ocr_text(text: str) -> str:
    normalized = text
    for wrong, right in OCR_REPLACEMENTS.items():
        normalized = re.sub(rf"(?<!\w){re.escape(wrong)}(?!\w)", right, normalized, flags=re.IGNORECASE)

    def fix_mg(match: re.Match) -> str:
        amount = match.group(1).upper().replace("O", "0")
        return f"{amount} mg"

    normalized = re.sub(r"\b(\d+[O0]*|[O0]?\d+[O0]*)\s*mg\b", fix_mg, normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def detection_position(detection: dict) -> tuple[float, float]:
    box = detection.get("boundingBox") or detection.get("bounding_box") or detection.get("bbox") or {}
    if not isinstance(box, dict):
        return (0, 0)
    top = box.get("top", box.get("y", box.get("minY", 0)))
    left = box.get("left", box.get("x", box.get("minX", 0)))
    return (float(top or 0), float(left or 0))


def collect_detection_text(detections: list) -> str | None:
    items = [item for item in detections if isinstance(item, dict) and isinstance(item.get("data"), str) and item["data"].strip()]
    if not items:
        return None
    items.sort(key=detection_position)
    return normalize_ocr_text(" ".join(item["data"].strip() for item in items))


def recursive_find_output_detections(payload) -> str | None:
    if isinstance(payload, dict):
        if payload.get("name") in {"outputDetections", "detections"} and isinstance(payload.get("value"), list):
            text = collect_detection_text(payload["value"])
            if text:
                return text

        for key, value in payload.items():
            if str(key) in {"outputDetections", "detections"} and isinstance(value, list):
                text = collect_detection_text(value)
                if text:
                    return text

        for value in payload.values():
            found = recursive_find_output_detections(value)
            if found:
                return found

    if isinstance(payload, list):
        for item in payload:
            found = recursive_find_output_detections(item)
            if found:
                return found

    return None


def build_novavision_request_payload(image_base64: str, filename: str | None, content_type: str | None) -> dict:
    app_id = os.getenv("NOVAVISION_APP_ID", "ocr-text-detection")
    image_node_id = os.getenv("NOVAVISION_IMAGE_NODE_ID", "ImageLoad")
    ocr_node_id = os.getenv("NOVAVISION_OCR_NODE_ID", "OCRTextDetection")
    access_token = os.getenv("NOVAVISION_ACCESS_TOKEN")

    return {
        "module": "app",
        "executor": "run",
        "ws_channel": os.getenv("NOVAVISION_WS_CHANNEL", "onsafe-prescription-ocr"),
        "access-token": access_token,
        "app_id": app_id,
        "service": "ocr_text_detection",
        "app": {
            "id": app_id,
            "nodes": [
                {
                    "id": image_node_id,
                    "name": "Image Load",
                    "module": "ImageLoad",
                    "configs": {
                        "imageFieldType": "base64",
                        "basedata": image_base64,
                        "Image Source": {
                            "type": "base64",
                            "value": image_base64,
                            "mimeType": content_type or "image/jpeg",
                            "filename": filename,
                        },
                    },
                },
                {
                    "id": ocr_node_id,
                    "name": "OCR Text Detection",
                    "module": "OCRTextDetection",
                    "configs": {
                        "input": image_node_id,
                        "output": "text",
                    },
                },
            ],
        },
        "configs": {
            image_node_id: {
                "imageFieldType": "base64",
                "basedata": image_base64,
                "Image Source": {
                    "type": "base64",
                    "value": image_base64,
                    "mimeType": content_type or "image/jpeg",
                    "filename": filename,
                },
            },
            ocr_node_id: {
                "output": "text",
            },
        },
        "payload": {
            "imageFieldType": "base64",
            "basedata": image_base64,
            "Image Source": {
                "type": "base64",
                "value": image_base64,
                "mimeType": content_type or "image/jpeg",
                "filename": filename,
            },
        },
    }


def recursive_find_ocr_text(payload, parent_key: str = "") -> str | None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            key_text = str(key)
            if key_text in OCR_TEXT_KEYS and isinstance(value, str) and value.strip():
                sibling_keys = {str(item).lower() for item in payload.keys()}
                image_context = (
                    "image" in parent_key.lower()
                    or "outputimage" in sibling_keys
                    or "mimetype" in sibling_keys
                    or "mimeType" in payload
                )
                if key_text == "value" and (image_context or value.strip().lower().startswith("data:image")):
                    continue
                return value.strip()
            if "text" in key_text.lower() and isinstance(value, str) and value.strip():
                return value.strip()
            if "detection" in key_text.lower() and isinstance(value, str) and value.strip():
                return value.strip()

        for key, value in payload.items():
            found = recursive_find_ocr_text(value, parent_key=str(key))
            if found:
                return found

    if isinstance(payload, list):
        texts = []
        for item in payload:
            if isinstance(item, str) and item.strip():
                texts.append(item.strip())
            else:
                found = recursive_find_ocr_text(item, parent_key=parent_key)
                if found:
                    texts.append(found)
        if texts:
            return " ".join(texts)

    return None


def response_has_output_image_only(payload) -> bool:
    found_text = False
    found_image = False

    def walk(value, parent_key: str = ""):
        nonlocal found_text, found_image
        if isinstance(value, dict):
            for key, inner in value.items():
                key_lower = str(key).lower()
                if key_lower in {"outputimage", "output_image"} or "mime" in key_lower:
                    found_image = True
                if "text" in key_lower or str(key) in OCR_TEXT_KEYS:
                    if isinstance(inner, str) and inner.strip() and "image" not in parent_key.lower():
                        found_text = True
                walk(inner, parent_key=str(key))
        elif isinstance(value, list):
            for item in value:
                walk(item, parent_key=parent_key)

    walk(payload)
    return found_image and not found_text


def call_novavision_ocr(image_base64: str, filename: str | None, content_type: str | None) -> tuple[str | None, dict]:
    api_url = os.getenv("NOVAVISION_API_URL", "http://127.0.0.1:9005/api")

    payload = build_novavision_request_payload(image_base64, filename, content_type)
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}

    api_key = os.getenv("NOVAVISION_ACCESS_TOKEN") or os.getenv("NOVAVISION_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    debug = {
        "novavision_called": True,
        "novavision_api_url": api_url,
        "raw_response_keys": [],
        "ocr_output_found": False,
        "fallback_used": False,
    }

    api_request = request.Request(api_url, data=body, headers=headers, method="POST")
    try:
        with request.urlopen(api_request, timeout=20) as response:
            response_body = response.read().decode("utf-8")
    except (error.URLError, TimeoutError, ValueError) as exc:
        debug["error"] = str(exc)
        return None, debug

    try:
        response_payload = json.loads(response_body)
    except json.JSONDecodeError:
        text = response_body.strip() or None
        debug["raw_response_keys"] = ["<non-json-response>"]
        debug["ocr_output_found"] = bool(text)
        return text, debug

    debug["raw_response_keys"] = list(response_payload.keys()) if isinstance(response_payload, dict) else [type(response_payload).__name__]
    text = recursive_find_output_detections(response_payload)
    debug["ocr_output_type"] = "outputDetections" if text else None
    if not text:
        text = recursive_find_ocr_text(response_payload)
        if text:
            text = normalize_ocr_text(text)
            debug["ocr_output_type"] = "text"
    debug["ocr_output_found"] = bool(text)
    if not text and response_has_output_image_only(response_payload):
        debug["message"] = "NovaVision response içinde OCR text output bulunamadı. Flow output config sadece image döndürüyor olabilir."
    return text, debug


def fold_for_match(value: str) -> str:
    folded = value.casefold()
    for source_char, target_char in (
        ("\u0131", "i"),
        ("\u0130", "i"),
        ("\u00fc", "u"),
        ("\u00f6", "o"),
        ("\u00e7", "c"),
        ("\u015f", "s"),
        ("\u011f", "g"),
    ):
        folded = folded.replace(source_char, target_char)
    return folded


def find_medication_alias(ocr_text: str, medication_name: str, info: dict) -> str | None:
    candidates = [medication_name, *info.get("aliases", [])]
    folded_ocr_text = fold_for_match(ocr_text)
    unique_candidates = []
    seen = set()
    for candidate in candidates:
        if not candidate or candidate.lower() in seen:
            continue
        seen.add(candidate.lower())
        unique_candidates.append(candidate)

    for candidate in unique_candidates:
        if re.search(rf"(?<!\w){re.escape(candidate)}(?!\w)", ocr_text, flags=re.IGNORECASE):
            return candidate

    for candidate in unique_candidates:
        folded_candidate = fold_for_match(candidate)
        if re.search(rf"(?<!\w){re.escape(folded_candidate)}(?!\w)", folded_ocr_text, flags=re.IGNORECASE):
            return candidate
    return None


def make_display_name(matched_name: str, usage: dict) -> str:
    dose = usage.get("dose")
    if not dose or dose == "Reçete metninde belirtilmemiş":
        return matched_name
    if re.search(re.escape(dose), matched_name, flags=re.IGNORECASE):
        return matched_name
    return f"{matched_name} {dose}"


def build_prescription_summary(
    patient_id: str,
    ocr_text: str,
    source: str,
    image_meta: dict | None = None,
    debug: dict | None = None,
) -> dict:
    find_patient(patient_id)
    found_medications = []

    for medication_name, info in medication_info().items():
        matched_name = find_medication_alias(ocr_text, medication_name, info)
        if matched_name:
            usage = extract_usage_instruction(ocr_text, matched_name)
            found_medications.append(
                {
                    "name": medication_name,
                    "matched_name": matched_name,
                    "display_name": make_display_name(matched_name, usage),
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
        "patient_id": patient_id,
        "source": source,
        "image": image_meta,
        "ocr_text": ocr_text,
        "debug": debug or {
            "novavision_called": False,
            "novavision_api_url": os.getenv("NOVAVISION_API_URL", "http://127.0.0.1:9005/api"),
            "raw_response_keys": [],
            "ocr_output_found": False,
            "fallback_used": False,
        },
        "medication_count": len(found_medications),
        "medications": found_medications,
        "safety_note": "Bu bilgi doktor reçetesine dayalıdır. Tedavi kararı doktor onayı gerektirir.",
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
async def prescription_scan(
    patient_id: str = Form("P001"),
    image: UploadFile | None = File(None),
    ocr_text: str | None = Form(None),
):
    find_patient(patient_id)
    prescriptions = demo_prescriptions()
    demo = next(
        (item for item in prescriptions if item["patient_id"] == patient_id),
        prescriptions[0],
    )
    image_meta = None
    image_base64 = None

    if image:
        image_bytes = await image.read()
        image_base64 = base64.b64encode(image_bytes).decode("ascii")
        image_meta = {
            "filename": image.filename,
            "content_type": image.content_type,
            "size_bytes": len(image_bytes),
            "base64_size": len(image_base64),
        }

    source = "NovaVision OCR Text Detection simülasyon çıktısı"
    final_ocr_text = ocr_text
    debug = {
        "novavision_called": False,
        "novavision_api_url": os.getenv("NOVAVISION_API_URL", "http://127.0.0.1:9005/api"),
        "raw_response_keys": [],
        "ocr_output_found": bool(ocr_text),
        "fallback_used": False,
    }

    if not final_ocr_text and image_base64:
        novavision_text, debug = call_novavision_ocr(
            image_base64=image_base64,
            filename=image.filename if image else None,
            content_type=image.content_type if image else None,
        )
        if novavision_text:
            final_ocr_text = novavision_text
            source = "NovaVision OCR Text Detection"

    if not final_ocr_text and image_base64:
        source = "NovaVision OCR metni alınamadı, demo fallback kullanıldı"
        debug["fallback_used"] = True

    if not final_ocr_text:
        final_ocr_text = demo["ocr_text"]
        debug["fallback_used"] = True

    return build_prescription_summary(
        patient_id=patient_id,
        ocr_text=final_ocr_text,
        source=source,
        image_meta=image_meta,
        debug=debug,
    )


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

