# MediGuard

![MediGuard Cover](https://github.com/zozoselim/base41/blob/1a21ca5aff57fac06565177f08effcad0e12e965/photos/Screenshot%202026-06-06%20162713.png)

MediGuard is a clinical medication safety MVP for reviewing patient profiles, current treatments and newly added medicines in one workflow. We built it as a doctor-focused decision support interface with a patient portal, synthetic oncology-oriented patient data, NovaVision prescription image processing and Puq.ai-assisted medication risk analysis.

> This project is for clinical decision support only. It does not replace professional medical judgment and must not be used as a direct medication instruction.

## About the Project

MediGuard helps doctors evaluate medication risk before adding a new medicine to a patient's active treatment plan. The app combines patient demographics, diagnoses, allergies, lab values, current medications and medication catalog data. Prescription-photo intake is handled with NovaVision image processing, and the final structured patient/medicine context is sent to a Puq.ai workflow for risk scoring.

We designed the project around a clear doctor workflow:

1. Log in as a doctor and review assigned patients.
2. Inspect patient diagnoses, lab values, allergies, risk factors and current medications.
3. Upload or review a prescription photo in the NovaVision intake flow, then verify the extracted medicine fields.
4. Enter or confirm a new medication with dosage and frequency.
5. Review the structured Puq.ai risk result, detected interactions and safer alternatives.
6. Save the doctor decision or request additional tests.

Patients can also log in to view their treatment information, assigned doctor, active medications and risk-related factors.

## Preview

### Doctor Dashboard

![Doctor Dashboard](https://github.com/zozoselim/base41/blob/28e2c5e19dfb251fb211f5da0a53c05796b86973/photos/Screenshot%202026-06-05%20185258.png)
![](https://github.com/zozoselim/base41/blob/ae5009469dc7dec918c4a3035b2b870aa32aed6c/photos/Screenshot%202026-06-05%20185327.png)

### Medication Risk Analysis

![Medication Risk Analysis](https://github.com/zozoselim/base41/blob/ae5009469dc7dec918c4a3035b2b870aa32aed6c/photos/Screenshot%202026-06-05%20185650.png)

### Patient Portal

![Patient Portal](https://github.com/zozoselim/base41/blob/ae5009469dc7dec918c4a3035b2b870aa32aed6c/photos/Screenshot%202026-06-05%20185457.png)

## Features

- Doctor and patient login with seeded demo accounts
- Synthetic patient database with oncology, chronic disease, allergy, lab and medication data
- Doctor dashboard with patient search, risk summaries and assigned patient details
- NovaVision prescription-photo workflow for image-based medicine intake
- Medication catalog validation before risk analysis
- Structured Puq.ai payload handoff with patient data, current medicines, new medicine, dosage and frequency
- Puq.ai webhook integration for agent-based medication risk analysis
- Low, medium and high risk scoring with interaction details
- Safer alternative suggestions for medium/high-risk cases when available
- Doctor decision workflow for approve, reject, modify or request further tests
- Requested test tracking on patient records
- Patient portal for treatment and medication safety visibility

## AI Workflows

### NovaVision Prescription Image Processing

![NovaVision Workflow Placeholder](https://github.com/zozoselim/base41/blob/1a21ca5aff57fac06565177f08effcad0e12e965/photos/NovaVision-Workflow.jpeg)

NovaVision is used in the prescription intake step. The doctor uploads a prescription photo, and NovaVision performs image processing to extract medicine candidates such as medicine name, dosage and frequency. These extracted fields are treated as reviewable clinical input: the doctor checks them before they are saved or passed into the medication risk workflow.

```text
Prescription photo upload
-> NovaVision image processing
-> Extracted medicine fields
-> Doctor verification
-> Medication risk analysis
```

### Puq.ai Medication Safety Agent

![Puq.ai Workflow Placeholder](https://github.com/zozoselim/base41/blob/1a21ca5aff57fac06565177f08effcad0e12e965/photos/Screenshot%202026-06-06%20162517.png)

Puq.ai is used after the backend prepares a structured clinical payload. FastAPI sends patient data, current medications and the new medicine to the Puq.ai agent, including dosage, frequency, medication class and estimated daily dose values where available. On the agent side, the workflow compares the new medicine against the active treatment list, evaluates patient-specific factors such as allergies, kidney/liver status, lab values, cancer profile and polypharmacy, then calculates a 0-100 risk score.

The expected Puq.ai response is structured JSON containing the overall risk level, detected interactions, highest-risk pair, clinical explanation, doctor review flag and safer alternatives for medium/high-risk cases. The backend supports the preferred sync webhook response, async `run_id` polling, `/puq-callback` result storage and a safe fallback result if the external workflow is unavailable or returns an unexpected format.

```text
Patient profile + current medicines + new medicine
-> FastAPI prepares enriched Puq.ai payload
-> Puq.ai agent calculates interaction and patient-specific risk
-> Router separates doctor_review_required and low_risk paths
-> Structured JSON result returns to the doctor UI
```

## Technologies Used

- **Frontend:** React 18, Vite, CSS, lucide-react
- **Backend:** FastAPI, Pydantic, Uvicorn
- **Database:** SQLite
- **AI workflows:** NovaVision prescription image processing, Puq.ai medication safety agent/webhook integration
- **Package manager:** pnpm
- **Other tools:** Git, Python virtual environment

## Project Structure

```text
.
|-- backend/
|   |-- main.py
|   |-- database.py
|   `-- services/
|       |-- medication_catalog.py
|       `-- puq_ai_service.py
|-- data/
|   `-- oncology_risk.json
|-- photos/
|   `-- screenshots
|-- src/
|   |-- App.jsx
|   |-- main.jsx
|   `-- styles.css
|-- .env.example
|-- index.html
|-- package.json
|-- pnpm-lock.yaml
|-- PUQ_WORKFLOW.md
|-- requirements.txt
`-- README.md
```

## Installation

Clone the repository and move into the project directory:

```bash
git clone <repository-url>
cd <project-directory>
```

Install frontend dependencies:

```bash
pnpm install
```

Create and configure the backend environment:

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
Copy-Item .env.example .env
```

Update `.env` with real Puq.ai values when you want to use live workflow responses:

```env
PUQ_WEBHOOK_URL=your_puq_ai_sync_webhook_url
PUQ_API_KEY=your_puq_ai_api_key
PUBLIC_BACKEND_URL=https://your-public-backend-url
```

## Running the Project

Start the backend API:

```bash
uvicorn backend.main:app --reload
```

The API runs at:

```text
http://localhost:8000
```

Start the frontend in another terminal:

```bash
pnpm dev
```

The app runs at:

```text
http://localhost:5173
```

If the frontend needs a custom backend URL, set `VITE_API_URL` before running Vite.

## Screenshots

| Page | Screenshot |
|---|---|
| Login Page | ![Login Page](https://github.com/zozoselim/base41/blob/1a21ca5aff57fac06565177f08effcad0e12e965/photos/Screenshot%202026-06-06%20162644.png) |
| Doctor Dashboard | ![Doctor Dashboard](https://github.com/zozoselim/base41/blob/28e2c5e19dfb251fb211f5da0a53c05796b86973/photos/Screenshot%202026-06-05%20185258.png) |
| Risk Result | ![Risk Result](https://github.com/zozoselim/base41/blob/1a21ca5aff57fac06565177f08effcad0e12e965/photos/Screenshot%202026-06-06%20162929.png) |
| Patient Portal | ![Patient Portal](https://github.com/zozoselim/base41/blob/ae5009469dc7dec918c4a3035b2b870aa32aed6c/photos/Screenshot%202026-06-05%20185457.png) |

## Demo Accounts

Seeded demo users use the same password:

```text
Password: demo123
```

```text
Doctor TC: 10000000001
Patient TC: 20000000001
```

## Puq.ai Workflow

The backend sends medication risk payloads to the Puq.ai webhook configured in `.env`. Each payload is prepared from the selected patient profile, active medicine list and doctor-confirmed new medicine. The payload also enriches medicine data with catalog class, estimated daily dose and dose status so the Puq.ai agent can make more consistent calculations.

The expected workflow behavior, agent prompt, response schema and routing details are documented in `PUQ_WORKFLOW.md`. In short, the Puq.ai flow should receive the webhook request, run the medication safety agent, route medium/high-risk results to `doctor_review_required`, and return the final structured JSON through a Webhook Response step.

If the Puq.ai response is unavailable or does not contain the expected structured JSON, the backend returns a safe fallback result so the UI can still show a decision-support response.

## API Overview

- `GET /health` checks API status.
- `POST /auth/login` authenticates doctor or patient demo users.
- `GET /doctors` returns seeded doctors.
- `GET /patients?doctor_id={id}` returns assigned patients.
- `GET /patients/{patient_id}` returns patient details, medications, diagnosis codes and requested tests.
- `GET /medication-catalog` returns supported medicines.
- `POST /analyze-new-medicine` runs the medication risk analysis.
- `POST /doctor-decision` saves the doctor's decision.
- `POST /patients/{patient_id}/requested-tests` creates a requested test record.

## What We Learned

While developing MediGuard, we improved our skills in:

- Structuring a full-stack clinical decision support MVP
- Connecting a React interface with a FastAPI backend
- Modeling patient, doctor, medication and decision records in SQLite
- Preparing reliable AI workflow payloads and validating structured responses
- Separating prescription image extraction from medication risk reasoning
- Designing safer fallback behavior for external AI workflow failures
- Presenting medical risk information clearly without replacing doctor judgment

## Project Status

MediGuard is currently an MVP under active development. We may continue improving the UI, expanding the medication catalog, strengthening tests, refining the NovaVision intake and Puq.ai workflows, and preparing deployment steps.
