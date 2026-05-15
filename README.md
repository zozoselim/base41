# OncoSafe Vision AI

OncoSafe Vision AI is a healthcare hackathon MVP for doctors. It is a clinical decision support prototype that helps review the risk of adding a new medicine for a synthetic patient already using multiple medicines.

Important safety rules:

- The system never makes final medical decisions.
- The system never tells a patient to start, stop, or change medicine.
- All results are shown as clinical decision support only.
- Medium and High risk require doctor review.
- All seeded data is synthetic.

## Stack

- Frontend: React + Vite
- Backend: FastAPI
- Database: SQLite
- AI integration: Puq.ai webhook/API with safe fallback response

## Run Locally

Backend:

```bash
py -3 -m pip install -r requirements.txt
py -3 -m uvicorn backend.main:app --reload
```

Frontend:

```bash
corepack pnpm install
corepack pnpm dev
```

Open:

```text
http://127.0.0.1:5173
```

API docs:

```text
http://127.0.0.1:8000/docs
```

## Puq.ai Configuration

Create or edit `.env`:

```env
PUQ_WEBHOOK_URL=your_puq_ai_webhook_url
PUQ_API_KEY=your_puq_ai_api_key
```

The backend sends this header to Puq.ai:

```json
{
  "Content-Type": "application/json",
  "Authorization": "Token YOUR_PUQ_API_KEY"
}
```

If Puq.ai is unavailable or not configured, `/analyze-new-medicine` returns a fallback JSON response with:

```json
{
  "is_fallback": true,
  "warning": "Puq.ai service is currently unavailable. Showing fallback demo result."
}
```

## Main Flow

Doctor login
-> Select patient
-> View patient profile and current medicines
-> Enter new medicine
-> FastAPI `/analyze-new-medicine`
-> SQLite lookup
-> Puq.ai webhook or fallback
-> Frontend risk result display
-> Doctor decision saved through `/doctor-decision`

## API Endpoints

- `GET /doctors`
- `GET /patients`
- `GET /patients/{patient_id}`
- `GET /patients/{patient_id}/medicines`
- `POST /analyze-new-medicine`
- `POST /doctor-decision`

The SQLite database is created automatically as `oncosafe.sqlite3` on backend startup and seeded with 5 doctors, 50 synthetic patients, and 2 to 6 medicines per patient.
