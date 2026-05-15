from __future__ import annotations

from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.database import (
    get_all_doctors,
    get_all_patients,
    get_patient,
    get_patient_medicines,
    init_db,
    save_doctor_decision,
)
from backend.services.puq_ai_service import (
    call_puq_webhook,
    get_fallback_puq_response,
    prepare_puq_payload,
)


app = FastAPI(
    title="OncoSafe Vision AI API",
    description="Clinical decision support hackathon MVP using synthetic data, SQLite, and Puq.ai webhook integration.",
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


class AnalyzeNewMedicineRequest(BaseModel):
    patient_id: int
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
        "safety_note": "Clinical decision support only. Doctor review is required.",
    }


@app.get("/doctors")
def doctors() -> list[dict]:
    return get_all_doctors()


@app.get("/patients")
def patients() -> list[dict]:
    return get_all_patients()


@app.get("/patients/{patient_id}")
def patient_detail(patient_id: int) -> dict:
    patient = get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    patient["current_medications"] = get_patient_medicines(patient_id)
    patient["synthetic_data"] = True
    return patient


@app.get("/patients/{patient_id}/medicines")
def patient_medicines(patient_id: int) -> list[dict]:
    if not get_patient(patient_id):
        raise HTTPException(status_code=404, detail="Patient not found")
    return get_patient_medicines(patient_id)


@app.post("/analyze-new-medicine")
async def analyze_new_medicine(payload: AnalyzeNewMedicineRequest) -> dict:
    patient = get_patient(payload.patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    current_medications = get_patient_medicines(payload.patient_id)
    new_medicine = payload.new_medicine.model_dump()
    puq_payload = prepare_puq_payload(patient, current_medications, new_medicine)

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
    if not get_patient(payload.patient_id):
        raise HTTPException(status_code=404, detail="Patient not found")
    if payload.doctor_id not in {doctor["id"] for doctor in get_all_doctors()}:
        raise HTTPException(status_code=404, detail="Doctor not found")

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
        "safety_note": "Decision recorded for doctor-controlled workflow. The system did not make a final medical decision.",
    }
