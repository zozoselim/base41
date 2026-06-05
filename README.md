# MediGuard

![MediGuard Cover](https://via.placeholder.com/1200x500?text=MediGuard+Project+Cover)

MediGuard is a clinical medication safety MVP for reviewing patient profiles, current treatments and newly added medicines in one workflow. We built it as a doctor-focused decision support interface with a patient portal, synthetic oncology-oriented patient data and Puq.ai-assisted medication risk analysis.

> This project is for clinical decision support only. It does not replace professional medical judgment and must not be used as a direct medication instruction.

## About the Project

MediGuard helps doctors evaluate medication risk before adding a new medicine to a patient's active treatment plan. The app combines patient demographics, diagnoses, allergies, lab values, current medications and medication catalog data, then sends a structured payload to a Puq.ai workflow for risk scoring.

We designed the project around a clear doctor workflow:

1. Log in as a doctor and review assigned patients.
2. Inspect patient diagnoses, lab values, allergies, risk factors and current medications.
3. Enter a new medication with dosage and frequency.
4. Review the structured Puq.ai risk result, detected interactions and safer alternatives.
5. Save the doctor decision or request additional tests.

Patients can also log in to view their treatment information, assigned doctor, active medications and risk-related factors.

## Preview

### Doctor Dashboard

![Doctor Dashboard](https://via.placeholder.com/1000x600?text=Doctor+Dashboard+Screenshot)

### Medication Risk Analysis

![Medication Risk Analysis](https://via.placeholder.com/1000x600?text=Medication+Risk+Analysis+Screenshot)

### Patient Portal

![Patient Portal](https://via.placeholder.com/1000x600?text=Patient+Portal+Screenshot)

## Features

- Doctor and patient login with seeded demo accounts
- Synthetic patient database with oncology, chronic disease, allergy, lab and medication data
- Doctor dashboard with patient search, risk summaries and assigned patient details
- Medication catalog validation before risk analysis
- Puq.ai webhook integration for structured medication risk analysis
- Low, medium and high risk scoring with interaction details
- Safer alternative suggestions for medium/high-risk cases when available
- Doctor decision workflow for approve, reject, modify or request further tests
- Requested test tracking on patient records
- Patient portal for treatment and medication safety visibility

## Technologies Used

- **Frontend:** React 18, Vite, CSS, lucide-react
- **Backend:** FastAPI, Pydantic, Uvicorn
- **Database:** SQLite
- **AI workflow:** Puq.ai webhook integration
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

Replace the placeholder image links below with real screenshots from the project.

| Page | Screenshot |
|---|---|
| Login Page | ![Login Page](https://via.placeholder.com/600x350?text=Login+Page) |
| Doctor Dashboard | ![Doctor Dashboard](https://via.placeholder.com/600x350?text=Doctor+Dashboard) |
| Patient Profile | ![Patient Profile](https://via.placeholder.com/600x350?text=Patient+Profile) |
| Risk Result | ![Risk Result](https://via.placeholder.com/600x350?text=Risk+Result) |
| Patient Portal | ![Patient Portal](https://via.placeholder.com/600x350?text=Patient+Portal) |

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

The backend sends medication risk payloads to the Puq.ai webhook configured in `.env`. The expected workflow behavior, response schema and routing details are documented in `PUQ_WORKFLOW.md`.

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
- Designing safer fallback behavior for external AI workflow failures
- Presenting medical risk information clearly without replacing doctor judgment

## Project Status

MediGuard is currently an MVP under active development. We may continue improving the UI, expanding the medication catalog, strengthening tests, refining the Puq.ai workflow and preparing deployment steps.
