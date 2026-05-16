from __future__ import annotations

from typing import Literal

from fastapi import FastAPI, HTTPException
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
