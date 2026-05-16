import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ClipboardCheck,
  FlaskConical,
  HeartPulse,
  LogIn,
  LogOut,
  Search,
  ShieldAlert,
  Stethoscope,
  UserRound,
  XCircle
} from "lucide-react";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

const decisionLabels = {
  approve: "Onay",
  reject: "Ret",
  modify: "Düzenleme",
  request_further_test: "Ek tetkik isteği"
};

const emptyMedicine = {
  medicine_name: "Aspirin",
  dosage: "100 mg",
  frequency: "Günde bir kez"
};

export default function App() {
  const [doctors, setDoctors] = useState([]);
  const [patients, setPatients] = useState([]);
  const [medicationCatalog, setMedicationCatalog] = useState([]);
  const [session, setSession] = useState(null);
  const [selectedPatientId, setSelectedPatientId] = useState(null);
  const [patient, setPatient] = useState(null);
  const [search, setSearch] = useState("");
  const [medicine, setMedicine] = useState(emptyMedicine);
  const [riskResult, setRiskResult] = useState(null);
  const [pendingRun, setPendingRun] = useState(null);
  const [decisionMessage, setDecisionMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const doctor = session?.role === "doctor" ? session.user : null;
  const loggedPatient = session?.role === "patient" ? session.user : null;

  useEffect(() => {
    async function loadInitialData() {
      try {
        const [doctorResponse, catalogResponse] = await Promise.all([
          fetch(`${API_BASE}/doctors`),
          fetch(`${API_BASE}/medication-catalog`)
        ]);
        if (!doctorResponse.ok) throw new Error("Doktorlar yüklenemedi");
        setDoctors(await doctorResponse.json());
        if (catalogResponse.ok) {
          setMedicationCatalog(await catalogResponse.json());
        }
      } catch {
        setError("Backend API'ye ulasilamiyor. Once FastAPI'yi baslatin.");
      }
    }
    loadInitialData();
  }, []);

  useEffect(() => {
    if (!doctor) {
      setPatients([]);
      setSelectedPatientId(null);
      setPatient(null);
      return;
    }
    async function loadDoctorPatients() {
      setLoading(true);
      setError("");
      try {
        const response = await fetch(`${API_BASE}/patients?doctor_id=${doctor.id}`);
        if (!response.ok) throw new Error("Hastalar yüklenemedi");
        const data = await response.json();
        setPatients(data);
        setSelectedPatientId(data[0]?.id ?? null);
        setPatient(null);
      } catch {
        setError("Doktora bağlı hastalar yüklenemedi.");
      } finally {
        setLoading(false);
      }
    }
    loadDoctorPatients();
  }, [doctor?.id]);

  useEffect(() => {
    if (!doctor || !selectedPatientId) return;
    async function loadPatient() {
      setRiskResult(null);
      setPendingRun(null);
      setDecisionMessage("");
      const response = await fetch(`${API_BASE}/patients/${selectedPatientId}?doctor_id=${doctor.id}`);
      if (response.ok) {
        setPatient(await response.json());
      }
    }
    loadPatient();
  }, [selectedPatientId, doctor]);

  const filteredPatients = useMemo(() => {
    const term = search.toLowerCase();
    return patients.filter((item) =>
      [item.name, item.cancer_status, item.diagnoses]
        .join(" ")
        .toLowerCase()
        .includes(term)
    );
  }, [patients, search]);

  const stats = useMemo(() => {
    const cancerDiagnosed = patients.filter((item) => hasCancerDiagnosis(item)).length;
    const pending = patients.filter((item) => item.cancer_stage === "Stage III" || item.chronic_disease_count >= 4).length;
    return { total: patients.length, cancerDiagnosed, pending };
  }, [patients]);

  async function refreshSelectedPatient() {
    if (!doctor || !selectedPatientId) return null;
    const response = await fetch(`${API_BASE}/patients/${selectedPatientId}?doctor_id=${doctor.id}`);
    if (!response.ok) return null;
    const data = await response.json();
    setPatient(data);
    return data;
  }

  async function loginUser(credentials) {
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(credentials)
      });
      if (!response.ok) throw new Error("Giriş başarısız");
      setSession(await response.json());
    } catch {
      setError("TC kimlik numarası veya şifre hatalı.");
    } finally {
      setLoading(false);
    }
  }

  function logout() {
    setSession(null);
    setPatients([]);
    setPatient(null);
    setSelectedPatientId(null);
    setRiskResult(null);
    setPendingRun(null);
    setDecisionMessage("");
    setError("");
  }

  async function analyzeRisk(event) {
    event.preventDefault();
    if (!doctor || !patient) return;
    setLoading(true);
    setError("");
      setRiskResult(null);
      setPendingRun(null);
    setDecisionMessage("");
    try {
      const response = await fetch(`${API_BASE}/analyze-new-medicine`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          patient_id: patient.id,
          doctor_id: doctor.id,
          new_medicine: medicine
        })
      });
      if (!response.ok) {
        const errorBody = await response.json().catch(() => ({}));
        throw new Error(errorBody.detail || "Risk analizi başarısız");
      }
      const data = await response.json();
      if (data.puq_async_pending && data.puq_run_id) {
        setPendingRun(data);
      } else {
        setRiskResult(data);
      }
    } catch (requestError) {
      setError(translateValue(requestError.message) || "Risk analizi tamamlanamadı.");
    } finally {
      setLoading(false);
    }
  }

  async function pollPuqRun(runInfo = pendingRun) {
    if (!runInfo?.puq_run_id || !doctor || !patient) return;
    try {
      const response = await fetch(`${API_BASE}/puq-runs/${runInfo.puq_run_id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          patient_id: patient.id,
          doctor_id: doctor.id,
          new_medicine: medicine
        })
      });
      if (!response.ok) {
        const errorBody = await response.json().catch(() => ({}));
        throw new Error(errorBody.detail || "Puq.ai sonucu kontrol edilemedi");
      }
      const data = await response.json();
      if (data.overall_risk_score !== undefined) {
        setPendingRun(null);
        setRiskResult(data);
      } else if (data.puq_async_pending === false) {
        setPendingRun(null);
        const candidate = data.puq_output_candidates?.[0];
        const candidateHint = candidate ? ` JSON adayi: ${candidate.path}` : "";
        setError(`${translateValue(data.message || "Puq.ai sonucu yapilandirilmis risk JSON'u icermiyor.")}${candidateHint}`);
      } else {
        setPendingRun({ ...runInfo, ...data });
      }
    } catch (requestError) {
      setError(translateValue(requestError.message) || "Puq.ai sonucu kontrol edilemedi.");
    }
  }

  useEffect(() => {
    if (!pendingRun?.puq_run_id || riskResult) return;
    const intervalId = window.setInterval(() => {
      pollPuqRun(pendingRun);
    }, 2500);
    return () => window.clearInterval(intervalId);
  }, [pendingRun?.puq_run_id, pendingRun?.puq_status, riskResult, doctor?.id, patient?.id, medicine.medicine_name, medicine.dosage, medicine.frequency]);

  async function saveDecision(decision, details = {}) {
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
          dosage: medicine.dosage,
          frequency: medicine.frequency,
          risk_score: riskResult.overall_risk_score,
          risk_level: riskResult.overall_risk_level,
          decision,
          ...details
        })
      });
      if (!response.ok) throw new Error("Karar kaydedilemedi");
      await response.json();
      await refreshSelectedPatient();
      setDecisionMessage(`${decisionLabels[decision]} doktor kontrollü inceleme için kaydedildi.`);
    } catch {
      setDecisionMessage("Karar kaydedilemedi.");
    } finally {
      setLoading(false);
    }
  }

  if (!session) {
    return <LoginScreen onLogin={loginUser} loading={loading} error={error} />;
  }

  if (loggedPatient) {
    return <PatientPortal patient={loggedPatient} onLogout={logout} />;
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
            <p>Yalnızca klinik karar desteği</p>
          </div>
        </div>
        <nav className="nav">
          <a href="#dashboard"><Activity size={18} /> Panel</a>
          <a href="#profile"><UserRound size={18} /> Hasta Profili</a>
          <a href="#medicine"><FlaskConical size={18} /> Yeni İlaç</a>
          <a href="#result"><ShieldAlert size={18} /> Puq.ai Sonucu</a>
          <a href="#decision"><ClipboardCheck size={18} /> Doktor Kararı</a>
        </nav>
        <div className="doctor-card">
          <span>Giriş yapan doktor</span>
          <strong>{doctor.name}</strong>
          <small>{translateValue(doctor.specialty)}</small>
          <button onClick={logout}><LogOut size={16} /> Çıkış yap</button>
        </div>
        <SafetyNotice compact />
      </aside>

      <main>
        <section className="hero" id="dashboard">
          <div>
            <p className="eyebrow">Puq.ai İlaç Güvenliği Ajanı + SQLite + FastAPI</p>
            <h2>İlaç riski incelemesi için doktor paneli</h2>
            <p>
              Sentetik bir hasta seçin, yeni ilacı girin ve yapılandırılmış ilaç riski desteğini inceleyin.
              Orta ve yüksek risk her zaman doktor değerlendirmesi gerektirir.
            </p>
          </div>
          <div className="top-panel">
            <div className="doctor-top-card">
              <Stethoscope size={18} />
              <div>
                <strong>{doctor.name}</strong>
                <span>{translateValue(doctor.specialty)}</span>
              </div>
              <button onClick={logout}><LogOut size={15} /> Cikis</button>
            </div>
            <div className="compact-stats">
              <Stat title="Toplam hasta" value={stats.total} />
              <Stat title="Kanser tanili" value={stats.cancerDiagnosed} tone="warning" />
              <Stat title="Oncelikli" value={stats.pending} tone="danger" />
            </div>
          </div>
        </section>

        <section className="workspace">
          <div className="stat-grid">
            <Stat title="Toplam hasta" value={stats.total} />
            <Stat title="Kanser tanılı hasta" value={stats.cancerDiagnosed} tone="warning" />
            <Stat title="Öncelikli takip" value={stats.pending} tone="danger" />
          </div>

          <div className="dashboard-grid">
            <section className="panel patient-list">
              <div className="panel-heading">
                <div>
                  <h3>Hasta listesi</h3>
                  <p>Sentetik hastalarda arama ve filtreleme</p>
                </div>
              </div>
              <label className="search-box">
                <Search size={18} />
                <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Hasta, hastalık veya tanı ara" />
              </label>
              <div className="patient-scroll">
                {filteredPatients.length === 0 && (
                  <div className="empty-list">Bu doktora atanmış hasta bulunmuyor.</div>
                )}
                {filteredPatients.map((item) => (
                  <button
                    className={`patient-row ${selectedPatientId === item.id ? "active" : ""}`}
                    key={item.id}
                    onClick={() => setSelectedPatientId(item.id)}
                  >
                    <span>
                      <strong>{item.name}</strong>
                      <small className="patient-age">{item.age} yaş{hasCancerDiagnosis(item) && ` | ${translateValue(item.cancer_status)}`}</small>
                      <small className="patient-diagnoses">{patientDiseaseSummary(item)}</small>
                    </span>
                  </button>
                ))}
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
                <RiskResult result={riskResult} loading={loading || Boolean(pendingRun)} pendingRun={pendingRun} />
                <DecisionPanel result={riskResult} onDecision={saveDecision} message={decisionMessage} loading={loading} />
              </>
            )}
          </div>
        </section>
      </main>
    </div>
  );
}

function LoginScreen({ onLogin, loading, error }) {
  const [role, setRole] = useState("doctor");
  const [credentials, setCredentials] = useState({ tc_identity: "10000000001", password: "demo123" });

  function switchRole(nextRole) {
    setRole(nextRole);
    setCredentials({
      tc_identity: nextRole === "doctor" ? "10000000001" : "20000000001",
      password: "demo123"
    });
  }

  function submitLogin(event) {
    event.preventDefault();
    onLogin({ role, ...credentials });
  }

  return (
    <div className="login-page">
      <div className="login-hero">
        <p className="eyebrow">Klinik ilaç güvenliği platformu</p>
        <h1>OncoSafe Vision</h1>
        <p>
          Hasta tanıları, mevcut tedaviler ve ilaç etkileşimlerini tek bir güvenli çalışma alanında birleştirir.
          Doktorlara daha hızlı, tutarlı ve izlenebilir karar desteği sunar.
        </p>
        <div className="login-feature-grid">
          <div>
            <Stethoscope size={20} />
            <strong>Hekime özel çalışma alanı</strong>
            <span>Atanmış hastalar, tanı kodları ve ilaç geçmişi düzenli bir klinik akış içinde yönetilir.</span>
          </div>
          <div>
            <UserRound size={20} />
            <strong>Risk odaklı hasta güvenliği</strong>
            <span>Yeni ilaç girişleri hasta profiliyle birlikte değerlendirilir; kritik durumlar doktor incelemesi için öne çıkarılır.</span>
          </div>
        </div>
        <SafetyNotice />
      </div>
      <section className="login-panel">
        <div className="auth-header">
          <div>
            <h2>Hesap Girişi</h2>
            <p>TC kimlik numaranız ve şifrenizle güvenli oturum açın.</p>
          </div>
          <span className="auth-status">Güvenli giriş</span>
        </div>
        <div className="role-toggle">
          <button className={role === "doctor" ? "active" : ""} onClick={() => switchRole("doctor")}>
            <Stethoscope size={18} /> Doktor
          </button>
          <button className={role === "patient" ? "active" : ""} onClick={() => switchRole("patient")}>
            <UserRound size={18} /> Hasta
          </button>
        </div>
        {error && <div className="alert danger">{error}</div>}
        <form className="auth-form" onSubmit={submitLogin}>
          <label>
            TC Kimlik Numarası
            <input
              value={credentials.tc_identity}
              onChange={(event) => setCredentials({ ...credentials, tc_identity: event.target.value })}
              inputMode="numeric"
              maxLength={11}
              required
            />
          </label>
          <label>
            Şifre
            <input
              type="password"
              value={credentials.password}
              onChange={(event) => setCredentials({ ...credentials, password: event.target.value })}
              required
            />
          </label>
          <button className="primary-action auth-submit" disabled={loading}>
            <LogIn size={18} /> {loading ? "Giriş yapılıyor..." : `${roleLabel(role)} alanına gir`}
          </button>
        </form>
      </section>
    </div>
  );
}

function PatientPortal({ patient, onLogout }) {
  const safePatient = { ...patient, current_medications: patient.current_medications || [], requested_tests: patient.requested_tests || [] };
  const factors = riskFactors(safePatient, safePatient.current_medications);
  return (
    <div className="app-shell patient-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <HeartPulse size={24} />
          </div>
          <div>
            <h1>OncoSafe Vision AI</h1>
            <p>Hasta profili erişimi</p>
          </div>
        </div>
        <nav className="nav">
          <a href="#profile"><UserRound size={18} /> Profilim</a>
          <a href="#medicines"><FlaskConical size={18} /> İlaçlar</a>
        </nav>
        <div className="doctor-card">
          <span>Giriş yapan hasta</span>
          <strong>{safePatient.name}</strong>
          <small>Atanan doktor #{safePatient.doctor_id}</small>
          <button onClick={onLogout}><LogOut size={16} /> Çıkış yap</button>
        </div>
        <SafetyNotice compact />
      </aside>
      <main>
        <section className="hero patient-hero">
          <div>
            <p className="eyebrow">Hasta görünümü</p>
            <h2>Salt okunur hasta profili</h2>
            <p>
              Hastalar sentetik profillerini ve ilaç listelerini görüntüleyebilir. Klinik işlemler doktor kontrolünde kalır.
            </p>
          </div>
        </section>
        <section className="workspace">
          <div className="dashboard-grid patient-dashboard">
            <PatientProfile patient={safePatient} />
            <section className="panel" id="medicines">
              <div className="panel-heading">
                <div>
                  <h3>Riskle ilişkili faktörler</h3>
                  <p>Klinik yorum için doktor değerlendirmesi gereklidir.</p>
                </div>
              </div>
              <div className="pill-list warning-list">
                {factors.length ? factors.map((factor) => <span key={factor}>{factor}</span>) : <span>Belirgin risk faktörü saptanmadı</span>}
              </div>
              <SafetyNotice compact />
            </section>
          </div>
        </section>
      </main>
    </div>
  );
}

function PatientProfile({ patient }) {
  const currentMedicines = (patient.current_medications || []).map((item) => ({
    ...item,
    frequency: translateValue(item.frequency)
  }));
  const diagnosisCodes = patient.diagnosis_codes || [];
  const requestedTests = patient.requested_tests || [];
  const factors = riskFactors(patient, currentMedicines);
  return (
    <section className="panel span-2" id="profile">
      <div className="panel-heading">
        <div>
          <h3>{patient.name}</h3>
          <p>Seçili sentetik hasta profili</p>
        </div>
        <span className="synthetic">Sentetik</span>
      </div>
      <div className="profile-grid">
        <Fact label="Hasta ID" value={`#${patient.id}`} />
        {patient.doctor_id && <Fact label="Atanan doktor ID" value={`#${patient.doctor_id}`} />}
        <Fact label="Yaş / Cinsiyet" value={`${patient.age} / ${translateValue(patient.gender)}`} />
        <Fact label="Boy / Kilo / VKİ" value={`${patient.height_cm} cm / ${patient.weight_kg} kg / ${patient.bmi}`} />
        <Fact label="Sigara / Alkol" value={`${translateValue(patient.smoking_status)} / ${translateValue(patient.alcohol_use)}`} />
        {hasCancerDiagnosis(patient) && (
          <Fact label="Kanser profili" value={`${translateValue(patient.cancer_status)} | ${translateValue(patient.cancer_stage)}`} />
        )}
        <Fact label="Tanılar" value={translateValue(patient.diagnoses)} />
        <Fact label="Alerjiler" value={translateValue(patient.allergies)} />
        <Fact label="Böbrek / Karaciğer" value={`${translateValue(patient.kidney_function_status)} / ${translateValue(patient.liver_function_status)}`} />
        <Fact label="Laboratuvar" value={`Cr ${patient.creatinine}, ALT ${patient.alt}, AST ${patient.ast}, Hb ${patient.hemoglobin}`} />
        <Fact label="Kronik hastalık sayısı" value={patient.chronic_disease_count} />
      </div>
      {diagnosisCodes.length > 0 && (
        <div className="diagnosis-code-block">
          <h4>Tanı kodları</h4>
          <div className="pill-list diagnosis-list">
            {diagnosisCodes.map((item) => (
              <span key={item.code}>{item.code} - {item.name}</span>
            ))}
          </div>
        </div>
      )}
      <div className="split-row">
        <div>
          <h4>Mevcut ilaçlar</h4>
          <div className="pill-list">
            {currentMedicines.length === 0 && <span>Mevcut ilaç kaydı yok</span>}
            {currentMedicines.map((item) => (
              <span key={item.id}>{item.medicine_name} - {item.dosage} - {item.frequency}</span>
            ))}
          </div>
        </div>
        <div>
          <h4>Riskle ilişkili hasta faktörleri</h4>
          <div className="pill-list warning-list">
            {factors.length ? factors.map((factor) => <span key={factor}>{factor}</span>) : <span>Belirgin risk faktörü saptanmadı</span>}
          </div>
        </div>
      </div>
      {requestedTests.length > 0 && (
        <div className="requested-tests">
          <h4>Istenecek tetkikler</h4>
          <div className="test-list">
            {requestedTests.map((item) => (
              <article key={item.id} className="test-item">
                <strong>{item.test_name}</strong>
                <span>{item.test_date} | {item.doctor_name}</span>
                <p>{item.note || "Ek aciklama yok"}</p>
              </article>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

function MedicineForm({ medicine, medicationCatalog, setMedicine, onSubmit, loading, error }) {
  return (
    <section className="panel" id="medicine">
      <div className="panel-heading">
        <div>
          <h3>Yeni ilaç girişi</h3>
          <p>Puq.ai risk analizi için ilaç bilgilerini girin</p>
        </div>
      </div>
      <form className="medicine-form" onSubmit={onSubmit}>
        <div className="medicine-select-wrapper">
          İlaç adı
          <MedicineSelect
            medicineName={medicine.medicine_name}
            medicationCatalog={medicationCatalog}
            onSelect={(medicineName) => setMedicine({ ...medicine, medicine_name: medicineName })}
          />
        </div>
        <label>
          Doz
          <input value={medicine.dosage} onChange={(event) => setMedicine({ ...medicine, dosage: event.target.value })} required />
        </label>
        <label>
          Kullanım sıklığı
          <input value={medicine.frequency} onChange={(event) => setMedicine({ ...medicine, frequency: event.target.value })} required />
        </label>
        {error && <div className="alert danger">{error}</div>}
        <button className="primary-action" disabled={loading}>
          <ShieldAlert size={18} /> {loading ? "Analiz ediliyor..." : "Riski analiz et"}
        </button>
      </form>
    </section>
  );
}

function MedicineSelect({ medicineName, medicationCatalog, onSelect }) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);

  const filteredMedicines = useMemo(() => {
    const term = query.trim().toLowerCase();
    const medicines = medicationCatalog.map((item) => item.medicine_name).filter(Boolean);
    if (!term) return medicines;
    return medicines.filter((name) => name.toLowerCase().includes(term));
  }, [medicationCatalog, query]);

  function chooseMedicine(name) {
    onSelect(name);
    setQuery("");
    setOpen(false);
  }

  return (
    <div className="medicine-select">
      <div className="field-label">Ilac adi</div>
      <button type="button" className="select-trigger" onClick={() => setOpen((value) => !value)}>
        <span>{medicineName || "Katalogdan ilac sec"}</span>
        <ChevronDown size={17} />
      </button>
      {open && (
        <div className="select-popover">
          <label className="select-search">
            <Search size={16} />
            <input
              autoFocus
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Ilac ara"
            />
          </label>
          <div className="select-options" role="listbox">
            {filteredMedicines.length === 0 && <div className="select-empty">Eslesen ilac bulunamadi</div>}
            {filteredMedicines.map((name) => (
              <button
                type="button"
                role="option"
                aria-selected={name === medicineName}
                className={name === medicineName ? "selected" : ""}
                key={name}
                onClick={() => chooseMedicine(name)}
              >
                <span>{name}</span>
                {name === medicineName && <CheckCircle2 size={16} />}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function RiskResult({ result, loading, pendingRun }) {
  if (!result) {
    return (
      <section className="panel" id="result">
        <div className="empty-state">
          {pendingRun || loading ? (
            <>
              <div className="loading-ring" />
              <strong>Puq.ai analizi bekleniyor</strong>
              <span>Workflow sonucu hazir olana kadar bekleniyor. Yerel guvenlik sonucu gosterilmiyor.</span>
              {pendingRun?.puq_run_id && <small>Run ID: {pendingRun.puq_run_id}</small>}
            </>
          ) : (
            <>
              <ShieldAlert size={28} />
              <strong>Puq.ai Risk Sonucu</strong>
              <span>Yapılandırılmış JSON risk desteğini görmek için yeni bir ilacı analiz edin.</span>
            </>
          )}
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
          <h3>Puq.ai İlaç Güvenliği Ajanı tarafından üretildi</h3>
          <p>Yapılandırılmış ilaç risk analizi | Yalnızca klinik karar desteği</p>
        </div>
        <RiskBadge level={result.overall_risk_level} />
      </div>
      {result.is_fallback && (
        <div className="alert warning fallback-warning">
          <AlertTriangle size={18} />
          <div>
            <strong>{translateValue(result.warning)}</strong>
            {result.puq_error_detail && (
              <small>
                Puq.ai durum: {translateValue(result.puq_error_type || "bilinmiyor")} - {translateValue(result.puq_error_detail)}
              </small>
            )}
            {result.puq_raw_response_preview && (
              <small>Ham cevap onizleme: {result.puq_raw_response_preview}</small>
            )}
          </div>
        </div>
      )}
      {requiresReview && (
        <div className={`critical-warning ${String(result.overall_risk_level).toLowerCase()}`}>
          <AlertTriangle size={24} />
          <div>
            <strong>{riskLevelLabel(result.overall_risk_level)} risk saptandı - doktor değerlendirmesi gerekli</strong>
            <span>
              {translateValue(result.high_risk_warning) ||
                "Bu sonuç herhangi bir klinik işlemden önce doktor tarafından değerlendirilmelidir. Daha düşük riskli alternatifler yalnızca karar desteği amacıyla gösterilir."}
            </span>
          </div>
        </div>
      )}
      <div className="result-grid">
        <div className={`score-card ${String(result.overall_risk_level).toLowerCase()}`}>
          <div className="score-ring" style={{ "--score": `${result.overall_risk_score * 3.6}deg` }}>
            <strong>{result.overall_risk_score}</strong>
          </div>
          <span>Genel risk skoru</span>
          <RiskBadge level={result.overall_risk_level} />
        </div>
        <div className="clinical-copy">
          <Fact label="Yeni ilaç" value={translateValue(result.new_medicine)} />
          <Fact label="En yüksek riskli eşleşme" value={translateValue(result.highest_risk_pair)} />
          <Fact label="Klinik açıklama" value={translateValue(result.clinical_explanation)} />
          <Fact label="Önerilen doktor aksiyonu" value={translateValue(result.recommended_doctor_action)} />
          <Fact label="Güvenlik notu" value={translateValue(result.safety_note)} />
        </div>
      </div>
      {requiresReview && (
        <div className="alternatives-section">
          <div className="panel-heading compact-heading">
            <div>
              <h3>Daha düşük riskli alternatif seçenekler</h3>
              <p>Yalnızca doktor değerlendirmesi için klinik niyet alternatifi olarak gösterilir. Sistem reçete yazmaz.</p>
            </div>
          </div>
          {alternatives.length ? (
            <div className="alternatives-grid">
              {alternatives.map((item, index) => (
                <article className="alternative-card" key={`${item.medicine_name}-${index}`}>
                  <div className="alternative-topline">
                    <strong>{translateValue(item.medicine_name)}</strong>
                    <RiskBadge level={item.estimated_risk_level || "Low"} />
                  </div>
                  <span className="alternative-score">Tahmini risk: {item.estimated_risk_score ?? "--"} / 100</span>
                  <p>{translateValue(item.rationale)}</p>
                  <Fact label="Benzer klinik kullanım amacı" value={translateValue(item.suggested_use_case || "Doktor tarafından seçilecek eşdeğer klinik amaç")} />
                  <small>{translateValue(item.safety_note || "Yalnızca doktor değerlendirmesi içindir. İlaç talimatı değildir.")}</small>
                </article>
              ))}
            </div>
          ) : (
            <div className="alert warning">
              <AlertTriangle size={18} />
              Daha düşük riskli alternatif döndürülmedi. Karar öncesinde farmakoloji veya uzman değerlendirmesi isteyin.
            </div>
          )}
        </div>
      )}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Mevcut ilaç</th>
              <th>Yeni ilaç</th>
              <th>Etkileşim</th>
              <th>Skor</th>
              <th>Seviye</th>
              <th>Olası yan etkiler</th>
              <th>Gerekçe</th>
              <th>Doz / sıklık notu</th>
              <th>Hastaya özel faktörler</th>
            </tr>
          </thead>
          <tbody>
            {result.detected_interactions.map((item, index) => (
              <tr key={`${item.current_medicine}-${index}`}>
                <td>{translateValue(item.current_medicine)}</td>
                <td>{translateValue(item.new_medicine)}</td>
                <td>{item.interaction_found ? "Bulundu" : "Saptanmadı"}</td>
                <td>{item.risk_score}</td>
                <td><RiskBadge level={item.risk_level} /></td>
                <td>{(item.possible_side_effects || []).map(translateValue).join(", ")}</td>
                <td>{translateValue(item.reason)}</td>
                <td>{translateValue(item.dose_frequency_note || "Doz/sıklık güvenlik motoru tarafından değerlendirildi.")}</td>
                <td>{(item.patient_specific_factors || []).map(translateValue).join(", ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {loading && <div className="alert">Kaydediliyor...</div>}
    </section>
  );
}

function DecisionPanel({ result, onDecision, message, loading }) {
  const [decisionNote, setDecisionNote] = useState("");
  const [testDraft, setTestDraft] = useState({
    test_name: "CBC, kreatinin, ALT/AST",
    test_date: new Date().toISOString().slice(0, 10),
    test_note: ""
  });

  function requestTest() {
    onDecision("request_further_test", {
      decision_note: decisionNote,
      test_name: testDraft.test_name,
      test_date: testDraft.test_date,
      test_note: testDraft.test_note
    });
  }

  return (
    <section className="panel" id="decision">
      <div className="panel-heading">
        <div>
          <h3>Doktor karar paneli</h3>
          <p>Klinik karar ve ek tetkik bilgisi kaydedilir.</p>
        </div>
      </div>
      <div className="decision-actions">
        <button disabled={!result || loading} onClick={() => onDecision("approve", { decision_note: decisionNote })}><CheckCircle2 size={18} /> Onayla</button>
        <button disabled={!result || loading} onClick={() => onDecision("reject", { decision_note: decisionNote })}><XCircle size={18} /> Reddet</button>
        <button disabled={!result || loading} onClick={() => onDecision("modify", { decision_note: decisionNote })}><ClipboardCheck size={18} /> Duzenle</button>
        <button disabled={!result || loading} onClick={requestTest}><FlaskConical size={18} /> Tetkik iste</button>
      </div>
      <div className="decision-note-grid">
        <label>
          Karar notu
          <textarea value={decisionNote} onChange={(event) => setDecisionNote(event.target.value)} placeholder="Doktor notu" />
        </label>
        <label>
          Tetkik adi
          <input value={testDraft.test_name} onChange={(event) => setTestDraft({ ...testDraft, test_name: event.target.value })} />
        </label>
        <label>
          Tetkik tarihi
          <input type="date" value={testDraft.test_date} onChange={(event) => setTestDraft({ ...testDraft, test_date: event.target.value })} />
        </label>
        <label>
          Tetkik aciklamasi
          <textarea value={testDraft.test_note} onChange={(event) => setTestDraft({ ...testDraft, test_note: event.target.value })} placeholder="Hastaya ve doktora gorunecek not" />
        </label>
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
        Bu sistem yalnızca klinik karar desteği sağlar. Hastaya ilaç başlatma, durdurma veya değiştirme talimatı vermez.
        Orta veya yüksek risk her zaman doktor değerlendirmesi gerektirir.
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
  return <span className={`risk-badge ${String(level).toLowerCase()}`}>{riskLevelLabel(level)}</span>;
}

function hasCancerDiagnosis(patient) {
  const status = String(patient?.cancer_status || "").trim();
  return Boolean(status && !["No active cancer", "Aktif kanser yok", "Yok", "N/A"].includes(status));
}

function patientDiseaseSummary(patient) {
  const diagnoses = translateValue(patient?.diagnoses || "").trim();
  return diagnoses || "Tanı kaydı yok";
}

function riskFactors(patient, medicines = []) {
  const factors = [];
  if (patient.age > 65) factors.push("65 yaş üzeri");
  if (patient.hemoglobin < 11) factors.push("Düşük hemoglobin");
  if (patient.kidney_function_status !== "Normal") factors.push("Böbrek fonksiyon bozukluğu");
  if (patient.liver_function_status !== "Normal") factors.push("Karaciğer fonksiyon riski");
  if (hasCancerDiagnosis(patient)) factors.push("Kanser tanısı");
  if (hasCancerDiagnosis(patient) && patient.cancer_stage === "Stage III") factors.push("İleri kanser evresi");
  if (patient.smoking_status === "Current smoker") factors.push("Aktif sigara kullanımı");
  if (patient.alcohol_use !== "No") factors.push("Alkol kullanımı");
  if (patient.chronic_disease_count >= 3) factors.push("Çoklu kronik hastalık");
  if (medicines.length >= 5) factors.push("Çoklu ilaç kullanımı");
  if (patient.allergies !== "None" && patient.allergies !== "Yok") factors.push(`Kayıtlı alerji: ${translateValue(patient.allergies)}`);
  return factors;
}

function roleLabel(role) {
  return role === "doctor" ? "doktor" : "hasta";
}

function riskLevelLabel(level) {
  const labels = {
    Low: "Düşük",
    Medium: "Orta",
    High: "Yüksek"
  };
  return labels[level] || level;
}

function translateValue(value) {
  if (value === null || value === undefined) return "";
  if (Array.isArray(value)) return value.map(translateValue).join(", ");
  const text = String(value);
  if (text.includes(", ")) {
    return text.split(", ").map(translateValue).join(", ");
  }
  const dictionary = {
    "Medical Oncology": "Tıbbi Onkoloji",
    "Internal Medicine": "Dahiliye",
    Cardiology: "Kardiyoloji",
    "Clinical Pharmacology": "Klinik Farmakoloji",
    Hematology: "Hematoloji",
    Female: "Kadın",
    Male: "Erkek",
    Other: "Diğer",
    "No active cancer": "",
    "Aktif kanser yok": "",
    "Breast Cancer": "Meme kanseri",
    "Colon Cancer": "Kolon kanseri",
    "Lung Cancer": "Akciğer kanseri",
    Lymphoma: "Lenfoma",
    "Prostate Cancer": "Prostat kanseri",
    "Stage I": "Evre I",
    "Stage II": "Evre II",
    "Stage III": "Evre III",
    "Stage IV": "Evre IV",
    "N/A": "Yok",
    Hypertension: "Hipertansiyon",
    "Type 2 Diabetes": "Tip 2 diyabet",
    "Chronic Kidney Disease": "Kronik böbrek hastalığı",
    "Coronary Artery Disease": "Koroner arter hastalığı",
    COPD: "KOAH",
    "Atrial Fibrillation": "Atriyal fibrilasyon",
    Hyperlipidemia: "Hiperlipidemi",
    Hypothyroidism: "Hipotiroidi",
    None: "Yok",
    Penicillin: "Penisilin",
    Sulfa: "Sülfa",
    "NSAID sensitivity": "NSAİİ duyarlılığı",
    "Iodine contrast": "İyotlu kontrast",
    Cephalosporin: "Sefalosporin",
    "Never smoker": "Hiç sigara içmemiş",
    "Former smoker": "Eski sigara kullanıcısı",
    "Current smoker": "Aktif sigara kullanıcısı",
    No: "Yok",
    Occasional: "Ara sıra",
    Regular: "Düzenli",
    Normal: "Normal",
    "Mild impairment": "Hafif bozulma",
    "Moderate impairment": "Orta düzey bozulma",
    "Elevated enzymes": "Enzim yüksekliği",
    "Once daily": "Günde bir kez",
    "Twice daily": "Günde iki kez",
    "Once nightly": "Her gece bir kez",
    "As needed": "Gerektiğinde",
    "Current medication list": "Mevcut ilaç listesi",
    "Known allergy": "Bilinen alerji",
    "No high-risk pair detected": "Yüksek riskli eşleşme saptanmadı",
    "No interaction found": "Etkileşim bulunmadı",
    "Increased bleeding risk": "Kanama riskinde artış",
    "Gastrointestinal bleeding": "Gastrointestinal kanama",
    Hyperkalemia: "Hiperkalemi",
    "Kidney function deterioration": "Böbrek fonksiyonunda kötüleşme",
    "Kidney-related adverse effect": "Böbrekle ilişkili advers etki",
    "Lactic acidosis risk in susceptible patients": "Duyarlı hastalarda laktik asidoz riski",
    "Reduced antiplatelet effectiveness": "Antiplatelet etkinlikte azalma",
    "Reduced antiplatelet effect": "Antiplatelet etkide azalma",
    "Reduced endocrine therapy effectiveness": "Endokrin tedavi etkinliğinde azalma",
    "Potential allergy conflict": "Olası alerji uyumsuzluğu",
    "No high-confidence demo interaction detected": "Yüksek güvenli etkileşim saptanmadı",
    "No high-confidence serious interaction detected": "Yüksek güvenli ciddi etkileşim saptanmadı",
    "Recorded allergy": "Kayıtlı alerji",
    "Age over 65": "65 yaş üzeri",
    "Low hemoglobin": "Düşük hemoglobin",
    "Kidney function impairment": "Böbrek fonksiyon bozukluğu",
    "Liver enzyme elevation": "Karaciğer enzim yüksekliği",
    "Liver function concern": "Karaciğer fonksiyon riski",
    "Cancer diagnosis": "Kanser tanısı",
    "Advanced cancer stage": "İleri kanser evresi",
    "Alcohol use": "Alkol kullanımı",
    "Multiple chronic diseases": "Çoklu kronik hastalık",
    Polypharmacy: "Çoklu ilaç kullanımı",
    "Puq.ai service is currently unavailable. Showing fallback demo result.": "Puq.ai servisine su anda ulasilamiyor. Guvenli yedek sonuc gosteriliyor.",
    "Puq.ai workflow istegi aldi ancak beklenen yapilandirilmis JSON'u dondurmedi. Guvenli yedek sonuc gosteriliyor.": "Puq.ai workflow istegi aldi ancak beklenen yapilandirilmis JSON'u dondurmedi. Guvenli yedek sonuc gosteriliyor.",
    "Puq.ai analizi arka planda basladi. Sonuc hazir olana kadar yerel guvenlik analizi gosteriliyor.": "Puq.ai analizi arka planda basladi. Sonuc hazir olana kadar yerel guvenlik analizi gosteriliyor.",
    "Puq.ai analizi henuz tamamlanmadi.": "Puq.ai analizi henuz tamamlanmadi.",
    "Puq.ai calisti ancak execution detayinda yapilandirilmis risk JSON'u bulunamadi.": "Puq.ai calisti ancak execution detayinda yapilandirilmis risk JSON'u bulunamadi.",
    "Puq.ai run basladi ancak execution sonucu backend tarafindan okunamadi. PUQ_API_KEY gercek API key olmali ve execution endpoint erisimi acik olmali.": "Puq.ai run basladi ancak execution sonucu backend tarafindan okunamadi. PUQ_API_KEY gercek API key olmali ve execution endpoint erisimi acik olmali.",
    "PUQ_API_KEY is not configured": "PUQ_API_KEY ayarlanmamis. .env dosyasina gercek Puq.ai API key yazilmali.",
    response_format: "Cevap formati hatasi",
    request_failed: "Istek basarisiz",
    unexpected: "Beklenmeyen hata",
    "Puq.ai yaniti beklenen yapilandirilmis ilac risk JSON'unu icermiyor.": "Puq.ai yaniti beklenen yapilandirilmis ilac risk JSON'unu icermiyor.",
    "Puq.ai yanitinda overall_risk_score veya overall_risk_level alani eksik.": "Puq.ai yanitinda overall_risk_score veya overall_risk_level alani eksik.",
    "Puq.ai response did not contain structured medication risk JSON": "Puq.ai yaniti beklenen yapilandirilmis ilac risk JSON'unu icermiyor.",
    "Puq.ai response is missing overall_risk_score and overall_risk_level": "Puq.ai yanitinda overall_risk_score veya overall_risk_level alani eksik.",
    "This result must be reviewed by a doctor before any clinical action. Lower-risk alternatives are shown only as decision support options.": "Bu sonuç herhangi bir klinik işlemden önce doktor tarafından değerlendirilmelidir. Daha düşük riskli alternatifler yalnızca karar desteği amacıyla gösterilir.",
    "Doctor review is required before any clinical action.": "Herhangi bir klinik işlemden önce doktor değerlendirmesi gereklidir.",
    "Monitor clinically and verify patient-specific contraindications.": "Klinik olarak izleyin ve hastaya özel kontrendikasyonları doğrulayın.",
    "For doctor review only. Not a medication instruction.": "Yalnızca doktor değerlendirmesi içindir. İlaç talimatı değildir.",
    "Dose/frequency assessed by the safety engine.": "Doz/sıklık güvenlik motoru tarafından değerlendirildi."
  };
  return dictionary[text] || text;
}
