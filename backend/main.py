from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.database import (
    add_patient_medicine,
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
    get_patient_requested_tests,
    init_db,
    save_patient_requested_test,
    save_doctor_decision,
)
from backend.services.puq_ai_service import (
    MedicationCatalogError,
    PuqAIAsyncRunStarted,
    PuqAIResponseFormatError,
    PuqAIServiceError,
    call_puq_webhook,
    extract_structured_result,
    find_structured_result_candidates,
    get_puq_execution,
    get_fallback_puq_response,
    normalize_puq_response,
    prepare_puq_payload,
    supported_medications,
)


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

PUQ_RUN_PAYLOADS: dict[str, dict] = {}
PUQ_RUN_RESULTS: dict[str, dict] = {}
PUQ_CONTEXT_RESULTS: dict[str, dict] = {}


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
    dosage: str = ""
    frequency: str = ""
    risk_score: int
    risk_level: Literal["Low", "Medium", "High"]
    decision: Literal["approve", "reject", "modify", "request_further_test"]
    decision_note: str = ""
    test_name: str = ""
    test_date: str = ""
    test_note: str = ""


class PuqRunResultQuery(BaseModel):
    patient_id: int
    doctor_id: int | None = None
    new_medicine: NewMedicine


def puq_context_key(patient_id: int, new_medicine: dict) -> str:
    return "|".join(
        [
            str(patient_id),
            str(new_medicine.get("medicine_name", "")).strip().lower(),
            str(new_medicine.get("dosage", "")).strip().lower(),
            str(new_medicine.get("frequency", "")).strip().lower(),
        ]
    )


def puq_loose_context_key(patient_id: int, medicine_name: str) -> str:
    return f"{patient_id}|{medicine_name.strip().lower()}"


def store_puq_result(run_id: str | None, result: dict, puq_payload: dict) -> None:
    result["puq_async_pending"] = False
    result["puq_status"] = "CALLBACK_RECEIVED"
    result["clinical_decision_support_only"] = True
    result["puq_callback_received_at"] = datetime.now(timezone.utc).isoformat()
    if run_id:
        result["puq_run_id"] = run_id
        PUQ_RUN_RESULTS[run_id] = result
    patient_id = int(result.get("patient_id") or puq_payload["patient_data"]["id"])
    new_medicine = puq_payload["new_medicine"]
    PUQ_CONTEXT_RESULTS[puq_context_key(patient_id, new_medicine)] = result
    PUQ_CONTEXT_RESULTS[puq_loose_context_key(patient_id, result.get("new_medicine", new_medicine["medicine_name"]))] = result


def build_payload_for_callback(extracted: dict, raw_body: object) -> tuple[str | None, dict]:
    run_id = None
    if isinstance(raw_body, dict):
        run_id = raw_body.get("run_id") or raw_body.get("run_uid") or raw_body.get("execution_id")
    run_id = run_id or extracted.get("run_id") or extracted.get("run_uid")

    if run_id and run_id in PUQ_RUN_PAYLOADS:
        return str(run_id), PUQ_RUN_PAYLOADS[str(run_id)]

    patient_id = int(extracted.get("patient_id") or 0)
    if not patient_id:
        raise HTTPException(status_code=400, detail="Callback JSON icinde patient_id bulunamadi.")
    patient = get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Callback hasta kaydi bulunamadi.")
    medicine_name = extracted.get("new_medicine")
    if isinstance(medicine_name, dict):
        medicine_name = medicine_name.get("medicine_name")
    if not medicine_name:
        raise HTTPException(status_code=400, detail="Callback JSON icinde new_medicine bulunamadi.")
    puq_payload = prepare_puq_payload(
        patient,
        get_patient_medicines(patient_id),
        {
            "medicine_name": str(medicine_name),
            "dosage": "Not specified",
            "frequency": "Not specified",
        },
    )
    return str(run_id) if run_id else None, puq_payload


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
    patient["requested_tests"] = get_patient_requested_tests(patient_id)
    patient["synthetic_data"] = True
    return patient


@app.get("/patients/{patient_id}/medicines")
def patient_medicines(patient_id: int) -> list[dict]:
    if not get_patient(patient_id):
        raise HTTPException(status_code=404, detail="Hasta bulunamadı")
    return get_patient_medicines(patient_id)


@app.get("/patients/{patient_id}/requested-tests")
def patient_requested_tests(patient_id: int, doctor_id: int | None = None) -> list[dict]:
    if not get_patient(patient_id, doctor_id=doctor_id):
        raise HTTPException(status_code=404, detail="Hasta bulunamadÄ±")
    return get_patient_requested_tests(patient_id)


@app.get("/medication-catalog")
def medication_catalog() -> list[dict]:
    return supported_medications()


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
    except PuqAIAsyncRunStarted as exc:
        PUQ_RUN_PAYLOADS[exc.run_id] = puq_payload
        return {
            "puq_async_pending": True,
            "puq_run_id": exc.run_id,
            "puq_workflow_id": exc.workflow_id,
            "puq_raw_response_preview": exc.raw_preview,
            "message": "Puq.ai analizi devam ediyor. Sonuc bekleniyor.",
            "clinical_decision_support_only": True,
        }
    except PuqAIResponseFormatError as exc:
        result = get_fallback_puq_response(
            payload.patient_id,
            new_medicine,
            patient_data=patient,
            current_medications=current_medications,
        )
        result["puq_error_type"] = "response_format"
        result["puq_error_detail"] = str(exc)
        result["puq_raw_response_preview"] = exc.raw_preview
        result["warning"] = (
            "Puq.ai workflow istegi aldi ancak beklenen yapilandirilmis JSON'u dondurmedi. "
            "Guvenli yedek sonuc gosteriliyor."
        )
    except PuqAIServiceError as exc:
        result = get_fallback_puq_response(
            payload.patient_id,
            new_medicine,
            patient_data=patient,
            current_medications=current_medications,
        )
        result["puq_error_type"] = "request_failed"
        result["puq_error_detail"] = str(exc)
    except Exception as exc:
        result = get_fallback_puq_response(
            payload.patient_id,
            new_medicine,
            patient_data=patient,
            current_medications=current_medications,
        )
        result["puq_error_type"] = "unexpected"
        result["puq_error_detail"] = str(exc)

    result["doctor_review_required"] = result.get("overall_risk_level") in {"Medium", "High"} or any(
        item.get("doctor_review_required") for item in result.get("detected_interactions", [])
    )
    result["clinical_decision_support_only"] = True
    return result


@app.post("/puq-runs/{run_id}")
async def puq_run_status(run_id: str, payload: PuqRunResultQuery) -> dict:
    patient = get_patient(payload.patient_id, doctor_id=payload.doctor_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Hasta bulunamadi")

    current_medications = get_patient_medicines(payload.patient_id)
    new_medicine = payload.new_medicine.model_dump()

    if run_id in PUQ_RUN_RESULTS:
        return PUQ_RUN_RESULTS[run_id]
    context_result = PUQ_CONTEXT_RESULTS.get(puq_context_key(payload.patient_id, new_medicine))
    context_result = context_result or PUQ_CONTEXT_RESULTS.get(
        puq_loose_context_key(payload.patient_id, new_medicine["medicine_name"])
    )
    if context_result:
        return context_result

    try:
        puq_payload = prepare_puq_payload(patient, current_medications, new_medicine)
    except MedicationCatalogError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    try:
        execution = await get_puq_execution(run_id)
    except PuqAIServiceError as exc:
        return {
            "puq_async_pending": True,
            "puq_status": "EXECUTION_LOOKUP_FAILED",
            "puq_run_id": run_id,
            "message": (
                "Puq.ai run basladi ancak execution sonucu backend tarafindan okunamadi. "
                "PUQ_API_KEY gercek API key olmali ve execution endpoint erisimi acik olmali."
            ),
            "puq_error_detail": str(exc),
        }

    status = str(execution.get("status", "UNKNOWN")).upper()
    extracted = extract_structured_result(execution)

    if extracted:
        result = normalize_puq_response(extracted, puq_payload)
        result["puq_async_pending"] = False
        result["puq_status"] = status
        result["puq_run_id"] = run_id
        result["clinical_decision_support_only"] = True
        return result

    if status not in {"SUCCEEDED", "SUCCESS", "COMPLETED", "FINISHED"}:
        return {
            "puq_async_pending": status in {"PENDING", "RUNNING", "PAUSED"},
            "puq_status": status,
            "puq_run_id": run_id,
            "message": "Puq.ai analizi henuz tamamlanmadi.",
            "puq_output_candidates": find_structured_result_candidates(execution),
        }

    return {
        "puq_async_pending": False,
        "puq_status": status,
        "puq_run_id": run_id,
        "message": (
            "Puq.ai async run_id dondurdu. .env icindeki PUQ_WEBHOOK_URL muhtemelen Async webhook endpoint. "
            "Puq.ai Webhook menüsünden Sync endpoint'i kopyalayip PUQ_WEBHOOK_URL olarak kullanmalisin; "
            "Webhook Response adimi da Agent/Router sonrasinda Agent output JSON'unu dondurmeli."
        ),
        "puq_raw_response_preview": str(execution)[:800],
        "puq_output_candidates": find_structured_result_candidates(execution),
    }


@app.post("/puq-callback")
async def puq_callback(request: Request) -> dict:
    try:
        raw_body: object = await request.json()
    except Exception:
        raw_body = (await request.body()).decode("utf-8", errors="replace")

    extracted = extract_structured_result(raw_body)
    if not extracted:
        raise HTTPException(
            status_code=400,
            detail="Callback beklenen yapilandirilmis risk JSON'unu icermiyor.",
        )

    run_id, puq_payload = build_payload_for_callback(extracted, raw_body)
    result = normalize_puq_response(extracted, puq_payload)
    store_puq_result(run_id, result, puq_payload)
    return {
        "status": "saved",
        "puq_run_id": run_id,
        "overall_risk_score": result["overall_risk_score"],
        "overall_risk_level": result["overall_risk_level"],
    }


@app.post("/doctor-decision")
def doctor_decision(payload: DoctorDecisionRequest) -> dict:
    if not get_patient(payload.patient_id, doctor_id=payload.doctor_id):
        raise HTTPException(status_code=404, detail="Hasta bulunamadı")
    if payload.doctor_id not in {doctor["id"] for doctor in get_all_doctors()}:
        raise HTTPException(status_code=404, detail="Doktor bulunamadı")

    added_medicine = None
    requested_test = None
    decision_note = payload.decision_note

    if payload.decision == "approve":
        added_medicine = add_patient_medicine(
            payload.patient_id,
            payload.new_medicine,
            payload.dosage or "Not specified",
            payload.frequency or "Not specified",
        )
        decision_note = decision_note or "Ilac doktor onayi ile hasta mevcut ilac listesine eklendi."

    if payload.decision == "request_further_test":
        if not payload.test_name.strip() or not payload.test_date.strip():
            raise HTTPException(status_code=400, detail="Tetkik adi ve tarihi zorunludur")
        requested_test = save_patient_requested_test(
            payload.doctor_id,
            payload.patient_id,
            payload.test_name,
            payload.test_date,
            payload.test_note or payload.decision_note,
        )
        decision_note = decision_note or f"Tetkik istendi: {payload.test_name}"

    saved = save_doctor_decision(
        doctor_id=payload.doctor_id,
        patient_id=payload.patient_id,
        new_medicine=payload.new_medicine,
        risk_score=payload.risk_score,
        risk_level=payload.risk_level,
        decision=payload.decision,
        decision_note=decision_note,
    )
    return {
        "status": "saved",
        "decision": saved,
        "added_medicine": added_medicine,
        "requested_test": requested_test,
        "safety_note": "Karar doktor kontrollü iş akışı için kaydedildi. Sistem nihai tıbbi karar vermez.",
    }
