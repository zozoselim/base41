from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path
from typing import Literal
from urllib import error, request

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.database import (
    authenticate_doctor,
    authenticate_patient,
    create_doctor,
    create_patient,
    get_all_doctors,
    get_all_patients,
    get_disease_catalog,
    get_patient,
    get_patient_diagnosis_codes,
    get_patient_medicines,
    init_db,
    save_doctor_decision,
)
from backend.services.puq_ai_service import (
    MedicationCatalogError,
    call_puq_webhook,
    get_fallback_puq_response,
    prepare_puq_payload,
    supported_medications,
)


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"


app = FastAPI(
    title="OncoSafe Vision AI API",
    description="Sentetik veri, SQLite ve Puq.ai webhook entegrasyonu kullanan klinik karar destek MVP API'si.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class NewMedicine(BaseModel):
    medicine_name: str = Field(..., min_length=1)
    dosage: str = Field(..., min_length=1)
    frequency: str = Field(..., min_length=1)


class LoginRequest(BaseModel):
    role: Literal["doctor", "patient"]
    tc_identity: str = Field(..., min_length=11, max_length=11)
    password: str = Field(..., min_length=1)


class RegisterDoctorRequest(BaseModel):
    tc_identity: str = Field(..., min_length=11, max_length=11)
    password: str = Field(..., min_length=4)
    name: str = Field(..., min_length=2)
    specialty: str = Field("Tıbbi Onkoloji", min_length=2)
    hospital: str = Field("Base41 Üniversitesi Hastanesi", min_length=2)
    experience_years: int = Field(1, ge=0, le=70)
    email: str = Field(..., min_length=5)


class RegisterPatientRequest(BaseModel):
    tc_identity: str = Field(..., min_length=11, max_length=11)
    password: str = Field(..., min_length=4)
    doctor_id: int
    name: str = Field(..., min_length=2)
    age: int = Field(45, ge=0, le=120)
    gender: str = Field("Kadın", min_length=2)
    height_cm: int = Field(165, ge=80, le=230)
    weight_kg: int = Field(70, ge=20, le=250)
    smoking_status: str = "Hiç sigara içmemiş"
    alcohol_use: str = "Yok"
    diagnoses: str = "Genel takip"
    allergies: str = "Yok"
    creatinine: float = Field(0.9, ge=0)
    alt: int = Field(24, ge=0)
    ast: int = Field(22, ge=0)
    hemoglobin: float = Field(13.2, ge=0)
    cancer_status: str = ""
    cancer_stage: str = ""
    kidney_function_status: str = "Normal"
    liver_function_status: str = "Normal"
    chronic_disease_count: int = Field(1, ge=0)


class AnalyzeNewMedicineRequest(BaseModel):
    patient_id: int
    doctor_id: int | None = None
    new_medicine: NewMedicine


class DoctorDecisionRequest(BaseModel):
    doctor_id: int
    patient_id: int
    new_medicine: str
    risk_score: int
    risk_level: Literal["Low", "Medium", "High"]
    decision: Literal["approve", "reject", "modify", "request_further_test"]


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "app": "OncoSafe Vision AI",
        "safety_note": "Yalnızca klinik karar desteğidir. Doktor değerlendirmesi gereklidir.",
    }


@app.post("/auth/login")
def login(payload: LoginRequest) -> dict:
    if payload.role == "doctor":
        user = authenticate_doctor(payload.tc_identity, payload.password)
    else:
        user = authenticate_patient(payload.tc_identity, payload.password)

    if not user:
        raise HTTPException(status_code=401, detail="TC kimlik numarası veya şifre hatalı")
    return {"role": payload.role, "user": user}


OCR_TEXT_KEYS = {"outputContent", "outputText", "text", "recognized_text", "ocr_text", "content", "value"}
OCR_REPLACEMENTS = {
    "Amoksisil": "Amoksisilin",
    "REGETE": "REÇETE",
}


def load_json(name: str):
    with (DATA_DIR / name).open(encoding="utf-8") as file:
        return json.load(file)


def medication_info() -> dict:
    return load_json("medication_info.json")


def demo_prescriptions() -> list[dict]:
    path = DATA_DIR / "prescriptions.json"
    if not path.exists():
        return []
    return load_json("prescriptions.json")


def normalize_patient_id(value: str | int) -> int:
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if text.upper().startswith("P") and text[1:].isdigit():
        return int(text[1:])
    if text.isdigit():
        return int(text)
    raise HTTPException(status_code=400, detail="Geçersiz hasta ID")


def normalize_ocr_text(text: str) -> str:
    normalized = text
    for wrong, right in OCR_REPLACEMENTS.items():
        normalized = re.sub(rf"(?<!\w){re.escape(wrong)}(?!\w)", right, normalized, flags=re.IGNORECASE)

    def fix_mg(match: re.Match) -> str:
        amount = match.group(1).upper().replace("O", "0")
        return f"{amount} mg"

    normalized = re.sub(r"\b([0-9O]+)\s*mg\b", fix_mg, normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def detection_position(detection: dict) -> tuple[float, float]:
    box = detection.get("boundingBox") or detection.get("bounding_box") or detection.get("bbox") or {}
    if not isinstance(box, dict):
        return (0, 0)
    top = box.get("top", box.get("y", box.get("minY", 0)))
    left = box.get("left", box.get("x", box.get("minX", 0)))
    return (float(top or 0), float(left or 0))


def is_text_detection_item(value) -> bool:
    return (
        isinstance(value, dict)
        and isinstance(value.get("data"), str)
        and value["data"].strip()
        and (
            isinstance(value.get("boundingBox"), dict)
            or isinstance(value.get("bounding_box"), dict)
            or isinstance(value.get("bbox"), dict)
            or "confidence" in value
            or str(value.get("classLabel", "")).casefold() == "text"
        )
    )


def collect_detection_text(detections: list) -> str | None:
    items = [item for item in detections if is_text_detection_item(item)]
    if not items:
        return None
    items.sort(key=detection_position)
    return normalize_ocr_text(" ".join(item["data"].strip() for item in items))


def recursive_collect_detection_items(payload) -> list[dict]:
    if is_text_detection_item(payload):
        return [payload]

    found = []
    if isinstance(payload, dict):
        for value in payload.values():
            found.extend(recursive_collect_detection_items(value))
    elif isinstance(payload, list):
        for item in payload:
            found.extend(recursive_collect_detection_items(item))
    return found


def detection_value_to_text(value) -> str | None:
    if isinstance(value, list):
        text = collect_detection_text(value)
        if text:
            return text
        return collect_detection_text(recursive_collect_detection_items(value))

    if isinstance(value, dict):
        for list_key in ("value", "data", "items", "detections", "outputDetections"):
            if isinstance(value.get(list_key), list):
                text = detection_value_to_text(value[list_key])
                if text:
                    return text
        return collect_detection_text(recursive_collect_detection_items(value))

    return None


def recursive_find_output_detections(payload) -> str | None:
    if isinstance(payload, dict):
        if payload.get("name") in {"outputDetections", "detections"}:
            text = detection_value_to_text(payload.get("value"))
            if text:
                return text

        for key, value in payload.items():
            if str(key) in {"outputDetections", "detections"}:
                text = detection_value_to_text(value)
                if text:
                    return text

        for value in payload.values():
            found = recursive_find_output_detections(value)
            if found:
                return found

    if isinstance(payload, list):
        text = detection_value_to_text(payload)
        if text:
            return text
        for item in payload:
            found = recursive_find_output_detections(item)
            if found:
                return found

    broad_items = recursive_collect_detection_items(payload)
    return collect_detection_text(broad_items) if broad_items else None


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
                return normalize_ocr_text(value.strip())
            if "text" in key_text.lower() and isinstance(value, str) and value.strip():
                return normalize_ocr_text(value.strip())

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
            return normalize_ocr_text(" ".join(texts))

    return None


def build_novavision_request_payload(image_base64: str, filename: str | None, content_type: str | None) -> dict:
    app_id = os.getenv("NOVAVISION_APP_ID", "ocr-text-detection")
    image_node_id = os.getenv("NOVAVISION_IMAGE_NODE_ID", "ImageLoad")
    ocr_node_id = os.getenv("NOVAVISION_OCR_NODE_ID", "OCRTextDetection")
    image_source = {
        "type": "base64",
        "value": image_base64,
        "mimeType": content_type or "image/jpeg",
        "filename": filename,
    }
    return {
        "module": "app",
        "executor": "run",
        "ws_channel": os.getenv("NOVAVISION_WS_CHANNEL", "onsafe-prescription-ocr"),
        "access-token": os.getenv("NOVAVISION_ACCESS_TOKEN"),
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
                        "Image Source": image_source,
                    },
                },
                {
                    "id": ocr_node_id,
                    "name": "OCR Text Detection",
                    "module": "OCRTextDetection",
                    "configs": {"input": image_node_id, "output": "text"},
                },
            ],
        },
        "configs": {
            image_node_id: {"imageFieldType": "base64", "basedata": image_base64, "Image Source": image_source},
            ocr_node_id: {"output": "text"},
        },
        "payload": {"imageFieldType": "base64", "basedata": image_base64, "Image Source": image_source},
    }


def parse_novavision_response(response_payload) -> tuple[str | None, str | None]:
    detections_text = recursive_find_output_detections(response_payload)
    if detections_text:
        return detections_text, "outputDetections"

    text = recursive_find_ocr_text(response_payload)
    if text:
        return text, "text"

    return None, None


def call_novavision_ocr(image_base64: str, filename: str | None, content_type: str | None) -> tuple[str | None, dict]:
    api_url = os.getenv("NOVAVISION_API_URL")
    debug = {
        "novavision_called": bool(api_url),
        "raw_response_keys": [],
        "ocr_output_found": False,
        "fallback_used": False,
    }
    if not api_url:
        debug["message"] = "NOVAVISION_API_URL tanımlı değil."
        return None, debug

    payload = build_novavision_request_payload(image_base64, filename, content_type)
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    access_token = os.getenv("NOVAVISION_ACCESS_TOKEN")
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"

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
        text = normalize_ocr_text(response_body.strip()) if response_body.strip() else None
        debug["raw_response_keys"] = ["<non-json-response>"]
        debug["ocr_output_found"] = bool(text)
        debug["ocr_output_type"] = "raw-text" if text else None
        return text, debug

    debug["raw_response_keys"] = list(response_payload.keys()) if isinstance(response_payload, dict) else [type(response_payload).__name__]
    text, output_type = parse_novavision_response(response_payload)
    debug["ocr_output_found"] = bool(text)
    debug["ocr_output_type"] = output_type
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
    seen = set()
    for candidate in candidates:
        if not candidate or candidate.casefold() in seen:
            continue
        seen.add(candidate.casefold())
        if re.search(rf"(?<!\w){re.escape(candidate)}(?!\w)", ocr_text, flags=re.IGNORECASE):
            return candidate
        folded_candidate = fold_for_match(candidate)
        if re.search(rf"(?<!\w){re.escape(folded_candidate)}(?!\w)", folded_ocr_text, flags=re.IGNORECASE):
            return candidate
    return None


def extract_usage_instruction(ocr_text: str, matched_name: str) -> dict:
    pattern = rf"{re.escape(matched_name)}\s*([^.]*)"
    match = re.search(pattern, ocr_text, flags=re.IGNORECASE)
    instruction = match.group(0).strip() if match else matched_name
    dose_match = re.search(r"(\d+\s*mg)", instruction, flags=re.IGNORECASE)
    dose = re.sub(r"(\d+)\s*mg", r"\1 mg", dose_match.group(1), flags=re.IGNORECASE) if dose_match else "Reçete metninde belirtilmemiş"
    return {
        "raw_instruction": instruction,
        "dose": dose,
        "frequency": "Reçete metnine göre",
        "time": "Reçete metnine göre",
        "duration": "Reçete metninde belirtilmemiş",
    }


def make_display_name(matched_name: str, usage: dict) -> str:
    dose = usage.get("dose")
    if not dose or dose == "Reçete metninde belirtilmemiş":
        return matched_name
    if re.search(re.escape(dose), matched_name, flags=re.IGNORECASE):
        return matched_name
    return f"{matched_name} {dose}"


def build_prescription_summary(patient_id: int, ocr_text: str, source: str, image_meta: dict | None = None, debug: dict | None = None) -> dict:
    found_medications = []
    for medication_name, info in medication_info().items():
        matched_name = find_medication_alias(ocr_text, medication_name, info)
        if not matched_name:
            continue
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
        "debug": debug or {"novavision_called": False, "ocr_output_found": False, "fallback_used": False, "raw_response_keys": []},
        "medication_count": len(found_medications),
        "medications": found_medications,
        "safety_note": "Bu bilgi doktor reçetesine dayalıdır. Tedavi kararı doktor onayı gerektirir.",
    }


@app.get("/doctors")
def doctors() -> list[dict]:
    return get_all_doctors()


@app.get("/disease-codes")
def disease_codes() -> list[dict]:
    return get_disease_catalog()


@app.post("/doctors")
def register_doctor(payload: RegisterDoctorRequest) -> dict:
    try:
        doctor = create_doctor(**payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return doctor


@app.get("/patients")
def patients(doctor_id: int | None = None) -> list[dict]:
    return get_all_patients(doctor_id=doctor_id)


@app.post("/patients")
def register_patient(payload: RegisterPatientRequest) -> dict:
    try:
        patient = create_patient(**payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return patient


@app.get("/patients/{patient_id}")
def patient_detail(patient_id: int, doctor_id: int | None = None) -> dict:
    patient = get_patient(patient_id, doctor_id=doctor_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Hasta bulunamadı")
    patient["current_medications"] = get_patient_medicines(patient_id)
    patient["diagnosis_codes"] = get_patient_diagnosis_codes(patient_id)
    patient["synthetic_data"] = True
    return patient


@app.get("/patients/{patient_id}/medicines")
def patient_medicines(patient_id: int) -> list[dict]:
    if not get_patient(patient_id):
        raise HTTPException(status_code=404, detail="Hasta bulunamadı")
    return get_patient_medicines(patient_id)


@app.get("/medication-catalog")
def medication_catalog() -> list[dict]:
    return supported_medications()


@app.post("/prescription-scan")
async def prescription_scan(
    patient_id: str = Form("1"),
    image: UploadFile | None = File(None),
    ocr_text: str | None = Form(None),
) -> dict:
    normalized_patient_id = normalize_patient_id(patient_id)
    if not get_patient(normalized_patient_id):
        raise HTTPException(status_code=404, detail="Hasta bulunamadı")

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

    source = "Manuel OCR metni"
    final_ocr_text = normalize_ocr_text(ocr_text) if ocr_text else None
    debug = {
        "novavision_called": False,
        "raw_response_keys": [],
        "ocr_output_found": bool(final_ocr_text),
        "fallback_used": False,
    }

    if not final_ocr_text and image_base64:
        novavision_text, debug = call_novavision_ocr(image_base64, image.filename if image else None, image.content_type if image else None)
        if novavision_text:
            final_ocr_text = novavision_text
            source = "NovaVision OCR Text Detection"

    if not final_ocr_text:
        demo = next((item for item in demo_prescriptions() if item.get("patient_id") in {str(normalized_patient_id), f"P{normalized_patient_id:03d}"}), None)
        final_ocr_text = normalize_ocr_text(demo["ocr_text"]) if demo else ""
        source = "NovaVision OCR metni alınamadı, demo fallback kullanıldı"
        debug["fallback_used"] = True

    return build_prescription_summary(
        patient_id=normalized_patient_id,
        ocr_text=final_ocr_text,
        source=source,
        image_meta=image_meta,
        debug=debug,
    )


@app.post("/analyze-new-medicine")
async def analyze_new_medicine(payload: AnalyzeNewMedicineRequest) -> dict:
    patient = get_patient(payload.patient_id, doctor_id=payload.doctor_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Hasta bulunamadı")

    current_medications = get_patient_medicines(payload.patient_id)
    new_medicine = payload.new_medicine.model_dump()
    try:
        puq_payload = prepare_puq_payload(patient, current_medications, new_medicine)
    except MedicationCatalogError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    try:
        result = await call_puq_webhook(puq_payload)
    except Exception:
        result = get_fallback_puq_response(
            payload.patient_id,
            new_medicine,
            patient_data=patient,
            current_medications=current_medications,
        )

    result["doctor_review_required"] = result.get("overall_risk_level") in {"Medium", "High"} or any(
        item.get("doctor_review_required") for item in result.get("detected_interactions", [])
    )
    result["clinical_decision_support_only"] = True
    return result


@app.post("/doctor-decision")
def doctor_decision(payload: DoctorDecisionRequest) -> dict:
    if not get_patient(payload.patient_id, doctor_id=payload.doctor_id):
        raise HTTPException(status_code=404, detail="Hasta bulunamadı")
    if payload.doctor_id not in {doctor["id"] for doctor in get_all_doctors()}:
        raise HTTPException(status_code=404, detail="Doktor bulunamadı")

    saved = save_doctor_decision(
        doctor_id=payload.doctor_id,
        patient_id=payload.patient_id,
        new_medicine=payload.new_medicine,
        risk_score=payload.risk_score,
        risk_level=payload.risk_level,
        decision=payload.decision,
    )
    return {
        "status": "saved",
        "decision": saved,
        "safety_note": "Karar doktor kontrollü iş akışı için kaydedildi. Sistem nihai tıbbi karar vermez.",
    }
