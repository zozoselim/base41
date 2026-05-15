from __future__ import annotations

import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "oncosafe.sqlite3"


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row else None


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict]:
    return [dict(row) for row in rows]


def init_db() -> None:
    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS doctors (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                specialty TEXT NOT NULL,
                hospital TEXT NOT NULL,
                experience_years INTEGER NOT NULL,
                email TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS patients (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                age INTEGER NOT NULL,
                gender TEXT NOT NULL,
                height_cm INTEGER NOT NULL,
                weight_kg INTEGER NOT NULL,
                bmi REAL NOT NULL,
                smoking_status TEXT NOT NULL,
                alcohol_use TEXT NOT NULL,
                diagnoses TEXT NOT NULL,
                allergies TEXT NOT NULL,
                creatinine REAL NOT NULL,
                alt INTEGER NOT NULL,
                ast INTEGER NOT NULL,
                hemoglobin REAL NOT NULL,
                cancer_status TEXT NOT NULL,
                cancer_stage TEXT NOT NULL,
                kidney_function_status TEXT NOT NULL,
                liver_function_status TEXT NOT NULL,
                chronic_disease_count INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS patient_medicines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id INTEGER NOT NULL,
                medicine_name TEXT NOT NULL,
                dosage TEXT NOT NULL,
                frequency TEXT NOT NULL,
                FOREIGN KEY (patient_id) REFERENCES patients (id)
            );

            CREATE TABLE IF NOT EXISTS doctor_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doctor_id INTEGER NOT NULL,
                patient_id INTEGER NOT NULL,
                new_medicine TEXT NOT NULL,
                risk_score INTEGER NOT NULL,
                risk_level TEXT NOT NULL,
                decision TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (doctor_id) REFERENCES doctors (id),
                FOREIGN KEY (patient_id) REFERENCES patients (id)
            );
            """
        )
        seed_database(connection)


def seed_database(connection: sqlite3.Connection) -> None:
    doctor_count = connection.execute("SELECT COUNT(*) FROM doctors").fetchone()[0]
    patient_count = connection.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
    if doctor_count and patient_count:
        return

    connection.execute("DELETE FROM doctor_decisions")
    connection.execute("DELETE FROM patient_medicines")
    connection.execute("DELETE FROM patients")
    connection.execute("DELETE FROM doctors")

    doctors = [
        (1, "Dr. Elif Arslan", "Medical Oncology", "Base41 University Hospital", 14, "elif.arslan@base41.health"),
        (2, "Dr. Mert Kaya", "Internal Medicine", "Istanbul Clinical Center", 11, "mert.kaya@base41.health"),
        (3, "Dr. Deniz Yilmaz", "Cardiology", "Anatolia Heart Institute", 18, "deniz.yilmaz@base41.health"),
        (4, "Dr. Selin Aksoy", "Clinical Pharmacology", "Base41 Research Hospital", 9, "selin.aksoy@base41.health"),
        (5, "Dr. Can Demir", "Hematology", "Marmara Oncology Campus", 16, "can.demir@base41.health"),
    ]
    connection.executemany(
        """
        INSERT INTO doctors (id, name, specialty, hospital, experience_years, email)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        doctors,
    )

    patients = build_patients()
    connection.executemany(
        """
        INSERT INTO patients (
            id, name, age, gender, height_cm, weight_kg, bmi, smoking_status,
            alcohol_use, diagnoses, allergies, creatinine, alt, ast, hemoglobin,
            cancer_status, cancer_stage, kidney_function_status, liver_function_status,
            chronic_disease_count
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        patients,
    )

    medicine_rows = []
    for patient in patients:
        patient_id = patient[0]
        medicine_rows.extend((patient_id, *medicine) for medicine in medicines_for_patient(patient_id))

    connection.executemany(
        """
        INSERT INTO patient_medicines (patient_id, medicine_name, dosage, frequency)
        VALUES (?, ?, ?, ?)
        """,
        medicine_rows,
    )


def build_patients() -> list[tuple]:
    patients = [
        (
            1,
            "Ayşe Demir",
            67,
            "Female",
            162,
            74,
            28.2,
            "Former smoker",
            "No",
            "Breast Cancer, Hypertension",
            "None",
            1.4,
            40,
            35,
            10.8,
            "Breast Cancer",
            "Stage III",
            "Mild impairment",
            "Normal",
            2,
        )
    ]

    names = [
        "Mehmet Kaya",
        "Zeynep Arslan",
        "Fatma Yilmaz",
        "Ali Celik",
        "Emine Sahin",
        "Mustafa Ozturk",
        "Elif Aydin",
        "Hasan Koc",
        "Derya Aksoy",
        "Murat Polat",
        "Aylin Gunes",
        "Kemal Yildiz",
        "Seda Kaplan",
        "Burak Eren",
        "Nermin Tas",
        "Orhan Kurt",
        "Buse Kara",
        "Serkan Aslan",
        "Gulsen Er",
        "Ozan Duman",
        "Cemre Ucar",
        "Hakan Bilgin",
        "Yasemin Toprak",
        "Levent Ersoy",
        "Pelin Yavuz",
        "Tuncay Acar",
        "Melis Bozkurt",
        "Engin Sari",
        "Gizem Korkmaz",
        "Fikret Tekin",
        "Nazli Can",
        "Erdem Baran",
        "Sevgi Keskin",
        "Tolga Guler",
        "Aslihan Sen",
        "Ece Dogan",
        "Cihan Ates",
        "Mine Ozcan",
        "Kadir Demirci",
        "Irem Bulut",
        "Volkan Cakir",
        "Sibel Karaca",
        "Arda Tunc",
        "Nuray Ekin",
        "Sinan Basar",
        "Gokce Tan",
        "Yusuf Ercan",
        "Esra Kiraz",
        "Berkay Solak",
    ]
    cancer_profiles = [
        ("No active cancer", "N/A"),
        ("Breast Cancer", "Stage I"),
        ("Breast Cancer", "Stage II"),
        ("Breast Cancer", "Stage III"),
        ("Colon Cancer", "Stage II"),
        ("Lung Cancer", "Stage III"),
        ("Lymphoma", "Stage II"),
        ("Prostate Cancer", "Stage I"),
    ]
    chronic_conditions = [
        "Hypertension",
        "Type 2 Diabetes",
        "Chronic Kidney Disease",
        "Coronary Artery Disease",
        "COPD",
        "Atrial Fibrillation",
        "Hyperlipidemia",
        "Hypothyroidism",
    ]
    allergies = ["None", "Penicillin", "Sulfa", "NSAID sensitivity", "Iodine contrast", "Cephalosporin"]
    smoking = ["Never smoker", "Former smoker", "Current smoker"]
    alcohol = ["No", "Occasional", "Regular"]

    for index, name in enumerate(names, start=2):
        age = 34 + ((index * 7) % 48)
        gender = "Female" if index % 3 != 0 else "Male"
        height = 154 + ((index * 5) % 35)
        weight = 55 + ((index * 9) % 48)
        bmi = round(weight / ((height / 100) ** 2), 1)
        cancer_status, cancer_stage = cancer_profiles[index % len(cancer_profiles)]
        diagnosis_count = 1 + (index % 4)
        diagnoses = chronic_conditions[index % len(chronic_conditions) : index % len(chronic_conditions) + diagnosis_count]
        if len(diagnoses) < diagnosis_count:
            diagnoses += chronic_conditions[: diagnosis_count - len(diagnoses)]
        if cancer_status != "No active cancer":
            diagnoses = [cancer_status] + diagnoses

        creatinine = round(0.7 + ((index * 0.13) % 1.5), 1)
        alt = 18 + ((index * 7) % 70)
        ast = 17 + ((index * 6) % 68)
        hemoglobin = round(9.4 + ((index * 0.37) % 5.2), 1)
        kidney_status = "Moderate impairment" if creatinine >= 1.7 else "Mild impairment" if creatinine >= 1.3 else "Normal"
        liver_status = "Elevated enzymes" if alt > 55 or ast > 55 else "Normal"

        patients.append(
            (
                index,
                name,
                age,
                gender,
                height,
                weight,
                bmi,
                smoking[index % len(smoking)],
                alcohol[index % len(alcohol)],
                ", ".join(diagnoses),
                allergies[index % len(allergies)],
                creatinine,
                alt,
                ast,
                hemoglobin,
                cancer_status,
                cancer_stage,
                kidney_status,
                liver_status,
                len(diagnoses),
            )
        )

    return patients[:50]


def medicines_for_patient(patient_id: int) -> list[tuple[str, str, str]]:
    if patient_id == 1:
        return [
            ("Warfarin", "5mg", "Once daily"),
            ("Ibuprofen", "400mg", "Twice daily"),
            ("Lisinopril", "10mg", "Once daily"),
        ]

    medicine_pool = [
        ("Metformin", "500mg", "Twice daily"),
        ("Aspirin", "100mg", "Once daily"),
        ("Atorvastatin", "20mg", "Once nightly"),
        ("Lisinopril", "10mg", "Once daily"),
        ("Warfarin", "5mg", "Once daily"),
        ("Ibuprofen", "400mg", "As needed"),
        ("Spironolactone", "25mg", "Once daily"),
        ("Omeprazole", "20mg", "Once daily"),
        ("Clopidogrel", "75mg", "Once daily"),
        ("Amlodipine", "5mg", "Once daily"),
        ("Prednisone", "10mg", "Once daily"),
        ("Levothyroxine", "50mcg", "Once daily"),
        ("Furosemide", "40mg", "Once daily"),
        ("Insulin Glargine", "12 units", "Once nightly"),
        ("Tamoxifen", "20mg", "Once daily"),
        ("Capecitabine", "500mg", "Twice daily"),
    ]
    count = 2 + (patient_id % 5)
    start = (patient_id * 3) % len(medicine_pool)
    medicines = [medicine_pool[(start + offset) % len(medicine_pool)] for offset in range(count)]

    if patient_id % 9 == 0:
        medicines = [("Warfarin", "5mg", "Once daily"), ("Aspirin", "100mg", "Once daily"), *medicines[:2]]
    if patient_id % 13 == 0:
        medicines = [("Lisinopril", "10mg", "Once daily"), ("Spironolactone", "25mg", "Once daily"), *medicines[:3]]

    deduped = []
    seen = set()
    for medicine in medicines:
        if medicine[0] not in seen:
            deduped.append(medicine)
            seen.add(medicine[0])
    return deduped[:6]


def get_all_doctors() -> list[dict]:
    with get_connection() as connection:
        rows = connection.execute("SELECT * FROM doctors ORDER BY id").fetchall()
        return rows_to_dicts(rows)


def get_all_patients() -> list[dict]:
    with get_connection() as connection:
        rows = connection.execute("SELECT * FROM patients ORDER BY id").fetchall()
        return rows_to_dicts(rows)


def get_patient(patient_id: int) -> dict | None:
    with get_connection() as connection:
        row = connection.execute("SELECT * FROM patients WHERE id = ?", (patient_id,)).fetchone()
        return row_to_dict(row)


def get_patient_medicines(patient_id: int) -> list[dict]:
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT id, patient_id, medicine_name, dosage, frequency FROM patient_medicines WHERE patient_id = ? ORDER BY id",
            (patient_id,),
        ).fetchall()
        return rows_to_dicts(rows)


def save_doctor_decision(
    doctor_id: int,
    patient_id: int,
    new_medicine: str,
    risk_score: int,
    risk_level: str,
    decision: str,
) -> dict:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO doctor_decisions (doctor_id, patient_id, new_medicine, risk_score, risk_level, decision)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (doctor_id, patient_id, new_medicine, risk_score, risk_level, decision),
        )
        row = connection.execute(
            "SELECT * FROM doctor_decisions WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
        return dict(row)
