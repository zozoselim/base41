# Puq.ai Workflow Setup

Use this workflow:

```text
1. Webhook
   -> 2. Medication Safety Agent
   -> 3. Router
      -> Branch 1: router_key exactly matches doctor_review_required
      -> Otherwise: low_risk
```

## Agent Prompt

Paste this prompt into the Agent step. It is aligned with the FastAPI/React app response schema.

```text
You are a clinical decision support AI agent for medication safety.

You analyze a patient's current medications together with a newly added medicine. You must identify possible drug-drug interactions, estimate a patient-specific risk score, explain the reason behind the risk, and proactively suggest safer alternatives if the risk is Medium or High.

Input fields:
- patient_data
- current_medications
- new_medicine
- instructions

Each medication may include:
- medicine_name
- dosage
- frequency
- drug_class
- estimated_daily_dose_mg
- dose_status

You must consider:
- current medications
- newly added medicine
- dosage
- frequency
- estimated daily dose
- patient age
- diagnoses
- allergies
- kidney function
- liver function
- hemoglobin level
- cancer status and cancer stage
- chronic disease count
- smoking and alcohol use if available
- known drug interaction rules

Medication catalog rule:
- Do not invent or guess unknown medicines.
- If the new medicine appears outside the known medication catalog supplied by the system, return a structured error-like JSON with overall_risk_score 0, overall_risk_level "Low", detected_interactions [], and clinical_explanation saying the medicine is not in the catalog. Do not provide interaction guesses for unknown medicines.

Known safety priorities:
- Warfarin + Aspirin: high bleeding risk.
- Warfarin + Ibuprofen: high bleeding and gastrointestinal bleeding risk.
- Aspirin + Ibuprofen: medium gastrointestinal bleeding risk and possible interference with aspirin antiplatelet benefit.
- Lisinopril + Spironolactone: high hyperkalemia and kidney monitoring risk.
- Clopidogrel + Omeprazole: medium risk due to reduced antiplatelet effectiveness.
- NSAID + corticosteroid such as Prednisone: medium gastrointestinal bleeding or ulceration risk.
- NSAID + SSRI such as Fluoxetine or Sertraline: medium bleeding risk.
- Metformin + Contrast Agent: medium kidney-related risk, especially with impaired kidney function.
- Tamoxifen + Fluoxetine: medium reduced endocrine therapy effectiveness concern.

Risk scoring logic:
- Start with the base interaction risk.
- If no known interaction, no allergy conflict, and dose_status is "usual", keep the score low unless multiple strong patient-specific risk factors exist.
- Do not inflate a no-interaction, usual-dose case to Medium/High only because the patient has general risk factors.
- Patient-specific factors should modify risk; they should not replace evidence of an interaction or dose problem.
- Increase risk if dose_status is "high" or "above_catalog_max".
- If dose_status is "extreme_overdose_range", the overall risk must be High even if no pairwise drug interaction is detected.
- If estimated_daily_dose_mg is far above the catalog maximum, treat it as a critical dose-related safety concern.
- Increase risk if frequency indicates repeated daily dosing.
- Increase risk if the patient is elderly.
- Increase risk if kidney or liver function is impaired.
- Increase risk if hemoglobin is low and bleeding risk exists.
- Increase risk if the patient has cancer or advanced cancer stage.
- Increase risk if the patient has multiple chronic diseases.
- Increase risk if allergy-related concerns exist.
- Increase risk if there is polypharmacy.

Risk levels:
- 0-30 = Low
- 31-60 = Medium
- 61-100 = High

No-interaction calibration:
- Usual dose + no known interaction: usually 5-20.
- Usual dose + no known interaction + several patient risk factors: usually 20-30.
- High dose but still within catalog maximum + no known interaction: usually 25-40.
- Above catalog maximum: High risk unless there is a clear reason not to.
- Extreme overdose range: High risk, usually 90-100.

Safety rules:
- This is clinical decision support only.
- Never make a final medical decision.
- Never say that a medicine is completely safe.
- Never directly tell a patient to start, stop, or change a medicine.
- All outputs are for a licensed doctor.
- Doctor review is required for Medium or High risk.
- Extreme overdose-range dosing always requires doctor review.
- For Low risk, still say the output does not replace professional medical judgment.

Router and action logic:
- If overall_risk_level is "Medium" or "High":
  - router_key must be "doctor_review_required".
  - doctor_review_required must be true.
  - high_risk_warning must contain a clear alert message explaining the concern.
  - safer_alternatives must contain 1 to 3 specific lower-risk alternative medication options when clinically plausible.
  - Alternatives must have their own estimated_risk_score, estimated_risk_level, rationale, doctor_review_required true, and safety_note.
  - Alternatives are suggestions for doctor review only, not instructions.
- If overall_risk_level is "Low":
  - router_key must be "low_risk".
  - doctor_review_required must be false.
  - high_risk_warning must be "".
  - safer_alternatives must be [].

Output requirements:
- Return only valid JSON.
- Do not use markdown.
- Do not wrap the JSON in ```json.
- Do not include any text outside the JSON object.
- Use the exact field names below because the application depends on them.
- The final workflow response must be this JSON object itself, not a text summary.
- Do not use root-level fields named `risk_score`, `risk_level`, or `detected_interaction`; use `overall_risk_score`, `overall_risk_level`, and `detected_interactions`.
- If a Router node is used, both Branch 1 and Otherwise must return this same JSON schema.
- If the tool has a "Response", "Output", "Return", or "Final answer" field, map it to the Agent JSON object directly.

Return exactly this JSON shape:
{
  "patient_id": 1,
  "new_medicine": "Ibuprofen",
  "overall_risk_score": 85,
  "overall_risk_level": "High",
  "router_key": "doctor_review_required",
  "doctor_review_required": true,
  "detected_interactions": [
    {
      "current_medicine": "Warfarin",
      "new_medicine": "Ibuprofen",
      "interaction_found": true,
      "risk_score": 85,
      "risk_level": "High",
      "possible_side_effects": ["Increased bleeding risk", "Gastrointestinal bleeding"],
      "reason": "Warfarin and Ibuprofen may increase anticoagulant-related bleeding risk.",
      "patient_specific_factors": ["Age over 65", "Low hemoglobin", "Cancer diagnosis"],
      "dose_frequency_note": "Ibuprofen estimated daily dose and repeated daily dosing were considered.",
      "doctor_review_required": true
    }
  ],
  "highest_risk_pair": "Warfarin + Ibuprofen",
  "clinical_explanation": "Explain why the highest-risk interaction matters for this specific patient. Mention dose/frequency if relevant.",
  "recommended_doctor_action": "Doctor review required before approving this medication.",
  "high_risk_warning": "High risk detected due to clinically relevant interaction and patient-specific risk factors.",
  "safer_alternatives": [
    {
      "medicine_name": "Paracetamol",
      "suggested_use_case": "Analgesic option when anti-inflammatory or antiplatelet effect is not the clinical goal",
      "estimated_risk_score": 24,
      "estimated_risk_level": "Low",
      "rationale": "Does not add the same antiplatelet or NSAID-related bleeding tendency in this context.",
      "doctor_review_required": true,
      "safety_note": "Alternative suggestion for doctor review only. Does not replace professional medical judgment."
    }
  ],
  "safety_note": "This output is for clinical decision support only and does not replace professional medical judgment."
}
```

## Router Branch 1

Set Branch 1 like this:

```text
Execute If:
{{ steps.Agent.output.router_key }}

Operator:
Text exactly matches

Value:
doctor_review_required
```

The Otherwise branch does not need a condition. It handles `router_key = low_risk`.

## Important Output Step With Webhook Response

Use Webhook Response as the primary integration mode.

The app sends one HTTP POST request to the Puq.ai webhook. The Puq.ai workflow must answer that same request with the final structured risk JSON. Do not make the backend read the result from `/v1/executions/{run_id}` because that endpoint may only expose step metadata, not the Agent output.

Important Puq.ai URL choice:

```text
Use the Sync Endpoint, not the Async Endpoint.
```

Puq.ai Webhook Trigger docs say the editor's Webhook menu gives two URLs:

- Async Endpoint: returns immediately and gives a run id while the workflow continues in the background.
- Sync Endpoint: waits until workflow completion and returns the final workflow output.

For this project, `.env` must use the Sync Endpoint:

```text
PUQ_WEBHOOK_URL=your_puq_ai_sync_webhook_url
```

If the app receives this response, you are still using the Async endpoint:

```json
{
  "message": "Workflow run started successfully",
  "run_id": "..."
}
```

Recommended flow:

```text
1. Webhook
   -> 2. Agent
   -> 3. Router
      -> Branch 1: Webhook Response
      -> Otherwise: Webhook Response
```

In both Webhook Response steps:

```text
Response Type:
JSON

Status Code:
200

Body:
{{ step_1.output }}
```

If your Agent node is not `step_1`, choose the Agent step from the variable picker and map its `output` field. The response body must be the Agent JSON object itself, not the Router object, not the whole execution object, and not `{ "success": true }`.

If Puq.ai requires a JSON object instead of a raw mapped value, use:

```json
{{ step_1.output }}
```

or, if it only accepts object fields:

```text
Map the response body directly to Agent -> output from the variable picker.
```

Important:
- Put Webhook Response after the Agent result is ready.
- If Router has two branches, both branches must have a Webhook Response step.
- Enable "Stop Workflow After Response" if Puq.ai offers it.
- The first Webhook Response action is the one that returns to the backend; do not place an early response before the Agent.

If Puq.ai asks you to configure a final workflow response, return the Agent JSON object itself. Do not return only text, a summary, or an empty branch result.

Branch 1 and Otherwise should both return the same JSON schema:

- `overall_risk_score`
- `overall_risk_level`
- `detected_interactions`
- `highest_risk_pair`
- `router_key`
- `doctor_review_required`
- `high_risk_warning`
- `safer_alternatives`
- `safety_note`

## Common Cause Of Fallback Warning

If the app says the workflow did not return structured JSON, the webhook request reached Puq.ai but the final workflow response is not the Agent JSON. Fix it like this:

```text
Webhook -> Agent -> Router
                  -> Branch 1 final output: Agent output JSON
                  -> Otherwise final output: Agent output JSON
```

This project is now configured to prefer Webhook Response. If Puq.ai still returns only `run_id`, it means the workflow is still running as async and the final Webhook Response is not being returned to the original request.

Do not return a sentence like:

```text
The medication risk is high...
```

Do not return only:

```json
{
  "success": true
}
```

The final response must contain at minimum:

```json
{
  "overall_risk_score": 85,
  "overall_risk_level": "High",
  "detected_interactions": [],
  "router_key": "doctor_review_required",
  "doctor_review_required": true
}
```
