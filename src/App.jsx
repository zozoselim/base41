import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  ClipboardCheck,
  FlaskConical,
  HeartPulse,
  LogIn,
  Search,
  ShieldAlert,
  Stethoscope,
  UserRound,
  XCircle
} from "lucide-react";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

const decisionLabels = {
  approve: "Approve",
  reject: "Reject",
  modify: "Modify",
  request_further_test: "Request Further Test"
};

const emptyMedicine = {
  medicine_name: "Aspirin",
  dosage: "100mg",
  frequency: "Once daily"
};

export default function App() {
  const [doctors, setDoctors] = useState([]);
  const [patients, setPatients] = useState([]);
  const [medicationCatalog, setMedicationCatalog] = useState([]);
  const [doctor, setDoctor] = useState(null);
  const [selectedPatientId, setSelectedPatientId] = useState(1);
  const [patient, setPatient] = useState(null);
  const [search, setSearch] = useState("");
  const [medicine, setMedicine] = useState(emptyMedicine);
  const [riskResult, setRiskResult] = useState(null);
  const [decisionMessage, setDecisionMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadInitialData() {
      try {
        const [doctorResponse, patientResponse] = await Promise.all([
          fetch(`${API_BASE}/doctors`),
          fetch(`${API_BASE}/patients`)
        ]);
        const catalogResponse = await fetch(`${API_BASE}/medication-catalog`);
        setDoctors(await doctorResponse.json());
        setPatients(await patientResponse.json());
        setMedicationCatalog(await catalogResponse.json());
      } catch {
        setError("Backend API is not reachable. Start FastAPI on port 8000.");
      }
    }
    loadInitialData();
  }, []);

  useEffect(() => {
    if (!doctor) return;
    async function loadPatient() {
      setRiskResult(null);
      setDecisionMessage("");
      const response = await fetch(`${API_BASE}/patients/${selectedPatientId}`);
      setPatient(await response.json());
    }
    loadPatient();
  }, [selectedPatientId, doctor]);

  const filteredPatients = useMemo(() => {
    const term = search.toLowerCase();
    return patients.filter((item) =>
      [item.name, item.cancer_status, item.diagnoses, item.risk_level]
        .join(" ")
        .toLowerCase()
        .includes(term)
    );
  }, [patients, search]);

  const stats = useMemo(() => {
    const highRisk = patients.filter((item) => estimatePatientRisk(item) === "High").length;
    const pending = patients.filter((item) => item.cancer_stage === "Stage III" || item.chronic_disease_count >= 4).length;
    return { total: patients.length, highRisk, pending };
  }, [patients]);

  async function analyzeRisk(event) {
    event.preventDefault();
    setLoading(true);
    setError("");
    setRiskResult(null);
    setDecisionMessage("");
    try {
      const response = await fetch(`${API_BASE}/analyze-new-medicine`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          patient_id: patient.id,
          new_medicine: medicine
        })
      });
      if (!response.ok) {
        const errorBody = await response.json().catch(() => ({}));
        throw new Error(errorBody.detail || "Risk analysis failed");
      }
      setRiskResult(await response.json());
    } catch (requestError) {
      setError(requestError.message || "Risk analysis could not be completed.");
    } finally {
      setLoading(false);
    }
  }

  async function saveDecision(decision) {
    if (!riskResult || !doctor || !patient) return;
    setLoading(true);
    setDecisionMessage("");
    try {
      const response = await fetch(`${API_BASE}/doctor-decision`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          doctor_id: doctor.id,
          patient_id: patient.id,
          new_medicine: riskResult.new_medicine,
          risk_score: riskResult.overall_risk_score,
          risk_level: riskResult.overall_risk_level,
          decision
        })
      });
      if (!response.ok) throw new Error("Decision save failed");
      setDecisionMessage(`${decisionLabels[decision]} saved for doctor-controlled review.`);
    } catch {
      setDecisionMessage("Decision could not be saved.");
    } finally {
      setLoading(false);
    }
  }

  if (!doctor) {
    return <LoginScreen doctors={doctors} onEnter={setDoctor} error={error} />;
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <HeartPulse size={24} />
          </div>
          <div>
            <h1>OncoSafe Vision AI</h1>
            <p>Clinical decision support only</p>
          </div>
        </div>
        <nav className="nav">
          <a href="#dashboard"><Activity size={18} /> Dashboard</a>
          <a href="#profile"><UserRound size={18} /> Patient Profile</a>
          <a href="#medicine"><FlaskConical size={18} /> New Medicine</a>
          <a href="#result"><ShieldAlert size={18} /> Puq.ai Result</a>
          <a href="#decision"><ClipboardCheck size={18} /> Doctor Decision</a>
        </nav>
        <div className="doctor-card">
          <span>Logged in doctor</span>
          <strong>{doctor.name}</strong>
          <small>{doctor.specialty}</small>
          <button onClick={() => setDoctor(null)}>Switch doctor</button>
        </div>
        <SafetyNotice compact />
      </aside>

      <main>
        <section className="hero" id="dashboard">
          <div>
            <p className="eyebrow">Puq.ai Medication Safety Agent + SQLite + FastAPI</p>
            <h2>Doctor dashboard for medicine risk review</h2>
            <p>
              Select a synthetic patient, enter a new medicine, and review structured medication risk support.
              Medium and High risk always require doctor review.
            </p>
          </div>
          <div className="integration-card">
            <CheckCircle2 size={22} />
            <div>
              <strong>Puq.ai integration ready</strong>
              <span>Real webhook if configured, safe fallback demo if unavailable.</span>
            </div>
          </div>
        </section>

        <section className="workspace">
          <div className="stat-grid">
            <Stat title="Total patients" value={stats.total} />
            <Stat title="High-risk patients" value={stats.highRisk} tone="danger" />
            <Stat title="Pending doctor decisions" value={stats.pending} tone="warning" />
            <Stat title="Puq.ai status" value="Webhook" tone="success" />
          </div>

          <div className="dashboard-grid">
            <section className="panel patient-list">
              <div className="panel-heading">
                <div>
                  <h3>Patient list</h3>
                  <p>Search/filter synthetic patients</p>
                </div>
              </div>
              <label className="search-box">
                <Search size={18} />
                <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search patients, cancer status, diagnosis" />
              </label>
              <div className="patient-scroll">
                {filteredPatients.map((item) => {
                  const level = estimatePatientRisk(item);
                  return (
                    <button
                      className={`patient-row ${selectedPatientId === item.id ? "active" : ""}`}
                      key={item.id}
                      onClick={() => setSelectedPatientId(item.id)}
                    >
                      <span>
                        <strong>{item.name}</strong>
                        <small>{item.age} yrs | {item.cancer_status}</small>
                      </span>
                      <RiskBadge level={level} />
                    </button>
                  );
                })}
              </div>
            </section>

            {patient && (
              <>
                <PatientProfile patient={patient} />
                <MedicineForm
                  medicine={medicine}
                  medicationCatalog={medicationCatalog}
                  setMedicine={setMedicine}
                  onSubmit={analyzeRisk}
                  loading={loading}
                  error={error}
                />
                <RiskResult result={riskResult} loading={loading} />
                <DecisionPanel result={riskResult} onDecision={saveDecision} message={decisionMessage} loading={loading} />
              </>
            )}
          </div>
        </section>
      </main>
    </div>
  );
}

function LoginScreen({ doctors, onEnter, error }) {
  const [selected, setSelected] = useState(null);
  return (
    <div className="login-page">
      <div className="login-hero">
        <p className="eyebrow">Healthcare hackathon MVP</p>
        <h1>OncoSafe Vision AI</h1>
        <p>
          Clinical decision support prototype for doctors evaluating new medicine risk in patients with polypharmacy.
        </p>
        <SafetyNotice />
      </div>
      <section className="login-panel">
        <h2>Doctor role entry</h2>
        <p>Select a synthetic doctor profile to enter the dashboard.</p>
        {error && <div className="alert danger">{error}</div>}
        <div className="doctor-grid">
          {doctors.map((doctor) => (
            <button
              className={`doctor-option ${selected?.id === doctor.id ? "active" : ""}`}
              key={doctor.id}
              onClick={() => setSelected(doctor)}
            >
              <Stethoscope size={20} />
              <strong>{doctor.name}</strong>
              <span>{doctor.specialty}</span>
              <small>{doctor.hospital} | {doctor.experience_years} years</small>
            </button>
          ))}
        </div>
        <button className="primary-action" disabled={!selected} onClick={() => onEnter(selected)}>
          <LogIn size={18} /> Enter doctor dashboard
        </button>
      </section>
    </div>
  );
}

function PatientProfile({ patient }) {
  const factors = riskFactors(patient, patient.current_medications);
  return (
    <section className="panel span-2" id="profile">
      <div className="panel-heading">
        <div>
          <h3>{patient.name}</h3>
          <p>Selected synthetic patient profile</p>
        </div>
        <span className="synthetic">Synthetic</span>
      </div>
      <div className="profile-grid">
        <Fact label="Patient ID" value={`#${patient.id}`} />
        <Fact label="Age / Gender" value={`${patient.age} / ${patient.gender}`} />
        <Fact label="Height / Weight / BMI" value={`${patient.height_cm} cm / ${patient.weight_kg} kg / ${patient.bmi}`} />
        <Fact label="Smoking / Alcohol" value={`${patient.smoking_status} / ${patient.alcohol_use}`} />
        <Fact label="Cancer profile" value={`${patient.cancer_status} | ${patient.cancer_stage}`} />
        <Fact label="Diagnoses" value={patient.diagnoses} />
        <Fact label="Allergies" value={patient.allergies} />
        <Fact label="Kidney / Liver" value={`${patient.kidney_function_status} / ${patient.liver_function_status}`} />
        <Fact label="Labs" value={`Cr ${patient.creatinine}, ALT ${patient.alt}, AST ${patient.ast}, Hb ${patient.hemoglobin}`} />
        <Fact label="Chronic disease count" value={patient.chronic_disease_count} />
      </div>
      <div className="split-row">
        <div>
          <h4>Current medicines</h4>
          <div className="pill-list">
            {patient.current_medications.map((item) => (
              <span key={item.id}>{item.medicine_name} - {item.dosage} - {item.frequency}</span>
            ))}
          </div>
        </div>
        <div>
          <h4>Risk-related patient factors</h4>
          <div className="pill-list warning-list">
            {factors.length ? factors.map((factor) => <span key={factor}>{factor}</span>) : <span>No major demo risk factor detected</span>}
          </div>
        </div>
      </div>
    </section>
  );
}

function MedicineForm({ medicine, medicationCatalog, setMedicine, onSubmit, loading, error }) {
  return (
    <section className="panel" id="medicine">
      <div className="panel-heading">
        <div>
          <h3>New medicine input</h3>
          <p>Enter medicine details for Puq.ai risk analysis</p>
        </div>
      </div>
      <form className="medicine-form" onSubmit={onSubmit}>
        <label>
          Medicine name
          <input
            list="medication-catalog"
            value={medicine.medicine_name}
            onChange={(event) => setMedicine({ ...medicine, medicine_name: event.target.value })}
            required
          />
          <datalist id="medication-catalog">
            {medicationCatalog.map((item) => (
              <option value={item.medicine_name} key={item.medicine_name} />
            ))}
          </datalist>
        </label>
        <label>
          Dosage
          <input value={medicine.dosage} onChange={(event) => setMedicine({ ...medicine, dosage: event.target.value })} required />
        </label>
        <label>
          Frequency
          <input value={medicine.frequency} onChange={(event) => setMedicine({ ...medicine, frequency: event.target.value })} required />
        </label>
        {error && <div className="alert danger">{error}</div>}
        <button className="primary-action" disabled={loading}>
          <ShieldAlert size={18} /> {loading ? "Analyzing..." : "Analyze Risk"}
        </button>
      </form>
    </section>
  );
}

function RiskResult({ result, loading }) {
  if (!result) {
    return (
      <section className="panel" id="result">
        <div className="empty-state">
          <ShieldAlert size={28} />
          <strong>Puq.ai Risk Result Page</strong>
          <span>Analyze a new medicine to display structured JSON risk support.</span>
        </div>
      </section>
    );
  }

  const requiresReview = ["Medium", "High"].includes(result.overall_risk_level);
  const alternatives = result.safer_alternatives || [];

  return (
    <section className="panel span-2" id="result">
      <div className="panel-heading">
        <div>
          <h3>Generated by Puq.ai Medication Safety Agent</h3>
          <p>Structured medication risk analysis | Clinical decision support only</p>
        </div>
        <RiskBadge level={result.overall_risk_level} />
      </div>
      {result.is_fallback && <div className="alert warning"><AlertTriangle size={18} /> {result.warning}</div>}
      {requiresReview && (
        <div className={`critical-warning ${result.overall_risk_level.toLowerCase()}`}>
          <AlertTriangle size={24} />
          <div>
            <strong>{result.overall_risk_level} risk detected - doctor review required</strong>
            <span>
              {result.high_risk_warning ||
                "This result must be reviewed by a doctor before any clinical action. Lower-risk alternatives are shown only as decision support options."}
            </span>
          </div>
        </div>
      )}
      <div className="result-grid">
        <div className={`score-card ${result.overall_risk_level.toLowerCase()}`}>
          <div className="score-ring" style={{ "--score": `${result.overall_risk_score * 3.6}deg` }}>
            <strong>{result.overall_risk_score}</strong>
          </div>
          <span>Overall risk score</span>
          <RiskBadge level={result.overall_risk_level} />
        </div>
        <div className="clinical-copy">
          <Fact label="New medicine" value={result.new_medicine} />
          <Fact label="Highest risk pair" value={result.highest_risk_pair} />
          <Fact label="Clinical explanation" value={result.clinical_explanation} />
          <Fact label="Recommended doctor action" value={result.recommended_doctor_action} />
          <Fact label="Safety note" value={result.safety_note} />
        </div>
      </div>
      {requiresReview && (
        <div className="alternatives-section">
          <div className="panel-heading compact-heading">
            <div>
              <h3>Lower-risk alternative options</h3>
              <p>Clinical intent alternatives suggested for doctor review only. The system does not prescribe.</p>
            </div>
          </div>
          {alternatives.length ? (
            <div className="alternatives-grid">
              {alternatives.map((item, index) => (
                <article className="alternative-card" key={`${item.medicine_name}-${index}`}>
                  <div className="alternative-topline">
                    <strong>{item.medicine_name}</strong>
                    <RiskBadge level={item.estimated_risk_level || "Low"} />
                  </div>
                  <span className="alternative-score">Estimated risk: {item.estimated_risk_score ?? "--"} / 100</span>
                  <p>{item.rationale}</p>
                  <Fact label="Possible same-function use case" value={item.suggested_use_case || "Doctor-selected equivalent clinical intent"} />
                  <small>{item.safety_note || "For doctor review only. Not a medication instruction."}</small>
                </article>
              ))}
            </div>
          ) : (
            <div className="alert warning">
              <AlertTriangle size={18} />
              No lower-risk alternative was returned. Request pharmacology/specialist review before deciding.
            </div>
          )}
        </div>
      )}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Current medicine</th>
              <th>New medicine</th>
              <th>Interaction</th>
              <th>Score</th>
              <th>Level</th>
              <th>Possible side effects</th>
              <th>Reason</th>
              <th>Dose / frequency note</th>
              <th>Patient-specific factors</th>
            </tr>
          </thead>
          <tbody>
            {result.detected_interactions.map((item, index) => (
              <tr key={`${item.current_medicine}-${index}`}>
                <td>{item.current_medicine}</td>
                <td>{item.new_medicine}</td>
                <td>{item.interaction_found ? "Found" : "Not detected"}</td>
                <td>{item.risk_score}</td>
                <td><RiskBadge level={item.risk_level} /></td>
                <td>{item.possible_side_effects.join(", ")}</td>
                <td>{item.reason}</td>
                <td>{item.dose_frequency_note || "Dose/frequency assessed by the safety engine."}</td>
                <td>{item.patient_specific_factors.join(", ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {loading && <div className="alert">Saving...</div>}
    </section>
  );
}

function DecisionPanel({ result, onDecision, message, loading }) {
  return (
    <section className="panel" id="decision">
      <div className="panel-heading">
        <div>
          <h3>Doctor decision panel</h3>
          <p>Human review remains required before clinical action.</p>
        </div>
      </div>
      <div className="decision-actions">
        <button disabled={!result || loading} onClick={() => onDecision("approve")}><CheckCircle2 size={18} /> Approve</button>
        <button disabled={!result || loading} onClick={() => onDecision("reject")}><XCircle size={18} /> Reject</button>
        <button disabled={!result || loading} onClick={() => onDecision("modify")}><ClipboardCheck size={18} /> Modify</button>
        <button disabled={!result || loading} onClick={() => onDecision("request_further_test")}><FlaskConical size={18} /> Request Further Test</button>
      </div>
      {message && <div className="alert success">{message}</div>}
      <SafetyNotice compact />
    </section>
  );
}

function SafetyNotice({ compact = false }) {
  return (
    <div className={`safety-notice ${compact ? "compact" : ""}`}>
      <AlertTriangle size={compact ? 16 : 20} />
      <span>
        This system is clinical decision support only. It never tells a patient to start, stop, or change medicine.
        Medium or High risk always requires doctor review.
      </span>
    </div>
  );
}

function Stat({ title, value, tone = "info" }) {
  return (
    <div className={`stat ${tone}`}>
      <span>{title}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Fact({ label, value }) {
  return (
    <div className="fact">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function RiskBadge({ level }) {
  return <span className={`risk-badge ${String(level).toLowerCase()}`}>{level}</span>;
}

function estimatePatientRisk(patient) {
  let score = 0;
  if (patient.age > 65) score += 20;
  if (patient.hemoglobin < 11) score += 18;
  if (patient.kidney_function_status !== "Normal") score += 15;
  if (patient.liver_function_status !== "Normal") score += 12;
  if (patient.cancer_status !== "No active cancer") score += 16;
  if (patient.cancer_stage === "Stage III") score += 10;
  if (patient.chronic_disease_count >= 3) score += 12;
  if (score >= 61) return "High";
  if (score >= 31) return "Medium";
  return "Low";
}

function riskFactors(patient, medicines = []) {
  const factors = [];
  if (patient.age > 65) factors.push("Age over 65");
  if (patient.hemoglobin < 11) factors.push("Low hemoglobin");
  if (patient.kidney_function_status !== "Normal") factors.push("Kidney function impairment");
  if (patient.liver_function_status !== "Normal") factors.push("Liver function concern");
  if (patient.cancer_status !== "No active cancer") factors.push("Cancer diagnosis");
  if (patient.cancer_stage === "Stage III") factors.push("Advanced cancer stage");
  if (patient.smoking_status === "Current smoker") factors.push("Current smoker");
  if (patient.alcohol_use !== "No") factors.push("Alcohol use");
  if (patient.chronic_disease_count >= 3) factors.push("Multiple chronic diseases");
  if (medicines.length >= 5) factors.push("Polypharmacy");
  if (patient.allergies !== "None") factors.push(`Recorded allergy: ${patient.allergies}`);
  return factors;
}
