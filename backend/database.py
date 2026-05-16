from __future__ import annotations

import hashlib
import hmac
import re
import sqlite3
import secrets
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "oncosafe.sqlite3"
DEFAULT_PASSWORD = "demo123"
PRIVATE_FIELDS = {"tc_identity", "password_salt", "password_hash"}
DISEASE_CATALOG = [
    ("J00", "Nezle"),
    ("J11", "Grip"),
    ("J18", "Zatürre"),
    ("J20", "Akut Bronşit"),
    ("J44", "KOAH"),
    ("J45", "Astım"),
    ("J01", "Akut Sinüzit"),
    ("J02", "Akut Faranjit"),
    ("J03", "Akut Tonsillit (Bademcik İltihabı)"),
    ("E10", "Tip 1 Diyabet"),
    ("E11", "Tip 2 Diyabet"),
    ("E03", "Hipotiroidi"),
    ("E05", "Hipertiroidi"),
    ("E78", "Yüksek Kolesterol"),
    ("E66", "Obezite"),
    ("I10", "Yüksek Tansiyon"),
    ("I25", "Kronik Kalp Hastalığı"),
    ("I48", "Kalp Ritmi Bozukluğu"),
    ("I70", "Damar Sertliği"),
    ("I83", "Varis"),
    ("G43", "Migren"),
    ("G40", "Epilepsi"),
    ("G30", "Alzheimer"),
    ("G20", "Parkinson"),
    ("G35", "Multipl Skleroz (MS)"),
    ("G47", "Uykusuzluk (İnsomnia)"),
    ("A09", "Enfeksiyöz İshal"),
    ("B35", "Mantar Enfeksiyonu"),
    ("A41", "Sepsis (Kan Zehirlenmesi)"),
    ("B00", "Uçuk (Herpes Simplex)"),
    ("B01", "Suçiçeği"),
    ("M79.7", "Fibromiyalji"),
    ("M06", "Romatoid Artrit"),
    ("M81", "Kemik Erimesi"),
    ("M54.5", "Bel Ağrısı"),
    ("M17", "Diz Kireçlenmesi (Osteoartrit)"),
    ("K21", "Reflü"),
    ("K25", "Mide Ülseri"),
    ("K58", "Huzursuz Bağırsak Sendromu (IBS)"),
    ("K12", "Ağız Yarası (Aft)"),
    ("N39.0", "İdrar Yolu Enfeksiyonu"),
    ("N20", "Böbrek Taşı"),
    ("N40", "Prostat Büyümesi (BPH)"),
    ("N92", "Düzensiz Adet Kanaması"),
    ("H10", "Konjonktivit (Göz Nezlesi)"),
    ("H66", "Orta Kulak İltihabı"),
    ("L20", "Atopik Dermatit (Egzama)"),
    ("L70", "Akne (Sivilce)"),
    ("F32", "Depresyon"),
    ("F41", "Anksiyete (Kaygı Bozukluğu)"),
    ("C34", "Akciğer Kanseri"),
    ("C50", "Meme Kanseri"),
    ("C18", "Kolon Kanseri"),
    ("C61", "Prostat Kanseri"),
    ("C16", "Mide Kanseri"),
    ("C22", "Karaciğer Kanseri"),
    ("C91", "Lösemi (Kan Kanseri)"),
    ("C43", "Cilt Kanseri"),
    ("C73", "Tiroid Kanseri"),
    ("C25", "Pankreas Kanseri"),
    ("C56", "Yumurtalık (Over) Kanseri"),
    ("C64", "Böbrek Kanseri"),
    ("C67", "Mesane (İdrar Torbası) Kanseri"),
    ("C15", "Yemek Borusu (Özofagus) Kanseri"),
    ("C71", "Beyin Kanseri"),
]

DISEASE_POOLS_BY_DOCTOR = {
    1: ["C50", "C18", "C34", "C61", "C73", "C43", "C16", "C22", "C25", "C56", "I10", "E11"],
    2: ["E10", "E11", "E03", "E05", "E78", "E66", "J00", "J11", "J18", "J20", "K21", "K25", "K58"],
    3: ["I10", "I25", "I48", "I70", "I83", "E78", "G43", "G40", "G47", "N20"],
    4: ["J44", "J45", "J01", "J02", "J03", "M79.7", "M06", "M81", "M54.5", "M17", "L20", "L70"],
    5: ["C91", "A09", "B35", "A41", "B00", "B01", "N39.0", "N40", "N92", "H10", "H66", "F32", "F41", "G30", "G20", "G35"],
}


SQL_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SQL_TYPE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(?:\(\d+(?:,\d+)?\))?$")


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row else None


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict]:
    return [dict(row) for row in rows]


def public_record(row: sqlite3.Row | dict | None) -> dict | None:
    if row is None:
        return None
    data = dict(row)
    for field in PRIVATE_FIELDS:
        data.pop(field, None)
    return data


def public_records(rows: list[sqlite3.Row]) -> list[dict]:
    return [public_record(row) for row in rows if row is not None]


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    password_salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        password_salt.encode("utf-8"),
        120_000,
    ).hex()
    return password_salt, digest


def verify_password(password: str, salt: str | None, password_hash: str | None) -> bool:
    if not salt or not password_hash:
        return False
    _, candidate = hash_password(password, salt)
    return hmac.compare_digest(candidate, password_hash)


def doctor_tc_identity(doctor_id: int) -> str:
    return _tc_identity("10000000", doctor_id)


def patient_tc_identity(patient_id: int) -> str:
    return _tc_identity("20000000", patient_id)


def _tc_identity(prefix: str, person_id: int) -> str:
    if not re.fullmatch(r"\d{8}", prefix):
        raise ValueError("prefix 8 haneli sayısal bir değer olmalıdır")
    if not 0 <= person_id <= 999:
        raise ValueError("person_id 0 ile 999 arasında olmalıdır")
    return f"{prefix}{person_id:03d}"


def doctor_for_patient(patient_id: int) -> int:
    return ((patient_id - 1) % 5) + 1


def disease_category(code: str) -> str:
    prefix = code[0]
    categories = {
        "A": "Enfeksiyon",
        "B": "Enfeksiyon",
        "C": "Kanser",
        "E": "Endokrin ve metabolik",
        "F": "Ruh sağlığı",
        "G": "Nöroloji",
        "H": "Göz/Kulak",
        "I": "Kardiyovasküler",
        "J": "Solunum",
        "K": "Sindirim",
        "L": "Deri",
        "M": "Kas-iskelet",
        "N": "Ürogenital",
    }
    return categories.get(prefix, "Diğer")


def disease_display(code: str, name: str) -> str:
    return f"{code} - {name}"


def disease_codes_for_patient(patient_id: int) -> list[str]:
    if patient_id == 1:
        return ["C50", "I10", "E11"]

    doctor_id = doctor_for_patient(patient_id)
    codes = DISEASE_POOLS_BY_DOCTOR[doctor_id]
    count = 2 + (patient_id % 3)
    start = ((patient_id // 5) + patient_id * 2) % len(codes)
    assigned = [codes[(start + offset * 3) % len(codes)] for offset in range(count)]
    return list(dict.fromkeys(assigned))


def cancer_profile_for_codes(patient_id: int, codes: list[str], disease_lookup: dict[str, str]) -> tuple[str, str]:
    cancer_code = next((code for code in codes if code.startswith("C")), None)
    if not cancer_code:
        return "", ""
    stages = ["Stage I", "Stage II", "Stage III"]
    return disease_lookup[cancer_code], stages[patient_id % len(stages)]


def table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    _validate_sql_identifier(table_name)
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row["name"] for row in rows}


def add_column_if_missing(connection: sqlite3.Connection, table_name: str, column_definition: str) -> None:
    _validate_sql_identifier(table_name)
    parts = column_definition.split()
    if len(parts) != 2:
        raise ValueError("column_definition '<column_name> <column_type>' formatında olmalıdır")
    column_name, column_type = parts
    _validate_sql_identifier(column_name)
    _validate_sql_type(column_type)
    if column_name not in table_columns(connection, table_name):
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")


def _validate_sql_identifier(value: str) -> None:
    if not SQL_IDENTIFIER_RE.fullmatch(value):
        raise ValueError("Geçersiz SQL tanımlayıcı: yalnızca harf, rakam ve alt çizgi kullanılabilir")


def _validate_sql_type(value: str) -> None:
    if not SQL_TYPE_RE.fullmatch(value):
        raise ValueError("Geçersiz SQL türü: örnek geçerli formatlar TEXT, INTEGER, VARCHAR(255)")


def init_db() -> None:
    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS doctors (
                id INTEGER PRIMARY KEY,
                tc_identity TEXT UNIQUE,
                password_salt TEXT,
                password_hash TEXT,
                name TEXT NOT NULL,
                specialty TEXT NOT NULL,
                hospital TEXT NOT NULL,
                experience_years INTEGER NOT NULL,
                email TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS patients (
                id INTEGER PRIMARY KEY,
                doctor_id INTEGER,
                tc_identity TEXT UNIQUE,
                password_salt TEXT,
                password_hash TEXT,
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
                chronic_disease_count INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (doctor_id) REFERENCES doctors (id)
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

            CREATE TABLE IF NOT EXISTS disease_catalog (
                code TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                category TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS patient_diagnosis_codes (
                patient_id INTEGER NOT NULL,
                disease_code TEXT NOT NULL,
                PRIMARY KEY (patient_id, disease_code),
                FOREIGN KEY (patient_id) REFERENCES patients (id),
                FOREIGN KEY (disease_code) REFERENCES disease_catalog (code)
            );
            """
        )
        migrate_schema(connection)
        seed_database(connection)
        ensure_seed_auth_data(connection)
        ensure_disease_data(connection)


def migrate_schema(connection: sqlite3.Connection) -> None:
    add_column_if_missing(connection, "doctors", "tc_identity TEXT")
    add_column_if_missing(connection, "doctors", "password_salt TEXT")
    add_column_if_missing(connection, "doctors", "password_hash TEXT")
    add_column_if_missing(connection, "doctors", "created_at TEXT")
    add_column_if_missing(connection, "patients", "doctor_id INTEGER")
    add_column_if_missing(connection, "patients", "tc_identity TEXT")
    add_column_if_missing(connection, "patients", "password_salt TEXT")
    add_column_if_missing(connection, "patients", "password_hash TEXT")
    add_column_if_missing(connection, "patients", "created_at TEXT")
    connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_doctors_tc_identity ON doctors(tc_identity)")
    connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_patients_tc_identity ON patients(tc_identity)")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS disease_catalog (
            code TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS patient_diagnosis_codes (
            patient_id INTEGER NOT NULL,
            disease_code TEXT NOT NULL,
            PRIMARY KEY (patient_id, disease_code),
            FOREIGN KEY (patient_id) REFERENCES patients (id),
            FOREIGN KEY (disease_code) REFERENCES disease_catalog (code)
        )
        """
    )


def ensure_seed_auth_data(connection: sqlite3.Connection) -> None:
    doctor_rows = connection.execute(
        "SELECT id, tc_identity, password_salt, password_hash FROM doctors ORDER BY id"
    ).fetchall()
    for row in doctor_rows:
        salt = row["password_salt"]
        password_hash = row["password_hash"]
        if not salt or not password_hash:
            salt, password_hash = hash_password(DEFAULT_PASSWORD)
        connection.execute(
            """
            UPDATE doctors
            SET tc_identity = COALESCE(tc_identity, ?),
                password_salt = ?,
                password_hash = ?,
                created_at = COALESCE(created_at, CURRENT_TIMESTAMP)
            WHERE id = ?
            """,
            (doctor_tc_identity(row["id"]), salt, password_hash, row["id"]),
        )

    patient_rows = connection.execute(
        "SELECT id, doctor_id, tc_identity, password_salt, password_hash FROM patients ORDER BY id"
    ).fetchall()
    for row in patient_rows:
        salt = row["password_salt"]
        password_hash = row["password_hash"]
        if not salt or not password_hash:
            salt, password_hash = hash_password(DEFAULT_PASSWORD)
        connection.execute(
            """
            UPDATE patients
            SET doctor_id = COALESCE(doctor_id, ?),
                tc_identity = COALESCE(tc_identity, ?),
                password_salt = ?,
                password_hash = ?,
                created_at = COALESCE(created_at, CURRENT_TIMESTAMP)
            WHERE id = ?
            """,
            (doctor_for_patient(row["id"]), patient_tc_identity(row["id"]), salt, password_hash, row["id"]),
        )
    connection.execute("UPDATE patients SET name = 'Ayse Demir' WHERE id = 1")


def ensure_disease_data(connection: sqlite3.Connection) -> None:
    connection.execute("DELETE FROM patient_diagnosis_codes")
    connection.execute("DELETE FROM disease_catalog")
    connection.executemany(
        """
        INSERT INTO disease_catalog (code, name, category)
        VALUES (?, ?, ?)
        """,
        [(code, name, disease_category(code)) for code, name in DISEASE_CATALOG],
    )

    disease_lookup = {code: name for code, name in DISEASE_CATALOG}
    patient_rows = connection.execute("SELECT id FROM patients ORDER BY id").fetchall()

    for row in patient_rows:
        patient_id = row["id"]
        assigned_codes = disease_codes_for_patient(patient_id)
        diagnosis_text = ", ".join(disease_display(code, disease_lookup[code]) for code in assigned_codes)
        cancer_status, cancer_stage = cancer_profile_for_codes(patient_id, assigned_codes, disease_lookup)
        connection.executemany(
            """
            INSERT INTO patient_diagnosis_codes (patient_id, disease_code)
            VALUES (?, ?)
            """,
            [(patient_id, code) for code in assigned_codes],
        )
        connection.execute(
            """
            UPDATE patients
            SET diagnoses = ?,
                chronic_disease_count = ?,
                cancer_status = ?,
                cancer_stage = ?
            WHERE id = ?
            """,
            (diagnosis_text, len(assigned_codes), cancer_status, cancer_stage, patient_id),
        )


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
        (1, doctor_tc_identity(1), *hash_password(DEFAULT_PASSWORD), "Dr. Elif Arslan", "Medical Oncology", "Base41 University Hospital", 14, "elif.arslan@base41.health"),
        (2, doctor_tc_identity(2), *hash_password(DEFAULT_PASSWORD), "Dr. Mert Kaya", "Internal Medicine", "Istanbul Clinical Center", 11, "mert.kaya@base41.health"),
        (3, doctor_tc_identity(3), *hash_password(DEFAULT_PASSWORD), "Dr. Deniz Yilmaz", "Cardiology", "Anatolia Heart Institute", 18, "deniz.yilmaz@base41.health"),
        (4, doctor_tc_identity(4), *hash_password(DEFAULT_PASSWORD), "Dr. Selin Aksoy", "Clinical Pharmacology", "Base41 Research Hospital", 9, "selin.aksoy@base41.health"),
        (5, doctor_tc_identity(5), *hash_password(DEFAULT_PASSWORD), "Dr. Can Demir", "Hematology", "Marmara Oncology Campus", 16, "can.demir@base41.health"),
    ]
    connection.executemany(
        """
        INSERT INTO doctors (id, tc_identity, password_salt, password_hash, name, specialty, hospital, experience_years, email)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        doctors,
    )

    patients = build_patients()
    patient_rows = []
    for patient in patients:
        patient_id = patient[0]
        patient_rows.append(
            (
                patient_id,
                doctor_for_patient(patient_id),
                patient_tc_identity(patient_id),
                *hash_password(DEFAULT_PASSWORD),
                *patient[1:],
            )
        )
    connection.executemany(
        """
        INSERT INTO patients (
            id, doctor_id, tc_identity, password_salt, password_hash,
            name, age, gender, height_cm, weight_kg, bmi, smoking_status,
            alcohol_use, diagnoses, allergies, creatinine, alt, ast, hemoglobin,
            cancer_status, cancer_stage, kidney_function_status, liver_function_status,
            chronic_disease_count
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        patient_rows,
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
        ("", ""),
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
        if cancer_status:
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
        return public_records(rows)


def get_all_patients(doctor_id: int | None = None) -> list[dict]:
    with get_connection() as connection:
        if doctor_id is None:
            rows = connection.execute("SELECT * FROM patients ORDER BY id").fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM patients WHERE doctor_id = ? ORDER BY id",
                (doctor_id,),
            ).fetchall()
        return public_records(rows)


def get_patient(patient_id: int, doctor_id: int | None = None) -> dict | None:
    with get_connection() as connection:
        if doctor_id is None:
            row = connection.execute("SELECT * FROM patients WHERE id = ?", (patient_id,)).fetchone()
        else:
            row = connection.execute(
                "SELECT * FROM patients WHERE id = ? AND doctor_id = ?",
                (patient_id, doctor_id),
            ).fetchone()
        return public_record(row)


def authenticate_doctor(tc_identity: str, password: str) -> dict | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM doctors WHERE tc_identity = ?",
            (tc_identity.strip(),),
        ).fetchone()
        if not row or not verify_password(password, row["password_salt"], row["password_hash"]):
            return None
        return public_record(row)


def authenticate_patient(tc_identity: str, password: str) -> dict | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM patients WHERE tc_identity = ?",
            (tc_identity.strip(),),
        ).fetchone()
        if not row or not verify_password(password, row["password_salt"], row["password_hash"]):
            return None
        patient = public_record(row)
    if patient:
        patient["current_medications"] = get_patient_medicines(patient["id"])
        patient["diagnosis_codes"] = get_patient_diagnosis_codes(patient["id"])
        patient["synthetic_data"] = True
    return patient


def get_disease_catalog() -> list[dict]:
    with get_connection() as connection:
        rows = connection.execute("SELECT code, name, category FROM disease_catalog ORDER BY code").fetchall()
        return rows_to_dicts(rows)


def get_patient_diagnosis_codes(patient_id: int) -> list[dict]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT dc.code, dc.name, dc.category
            FROM patient_diagnosis_codes pdc
            JOIN disease_catalog dc ON dc.code = pdc.disease_code
            WHERE pdc.patient_id = ?
            ORDER BY dc.code
            """,
            (patient_id,),
        ).fetchall()
        return rows_to_dicts(rows)


def get_patient_medicines(patient_id: int) -> list[dict]:
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT id, patient_id, medicine_name, dosage, frequency FROM patient_medicines WHERE patient_id = ? ORDER BY id",
            (patient_id,),
        ).fetchall()
        return rows_to_dicts(rows)


def create_doctor(
    tc_identity: str,
    password: str,
    name: str,
    specialty: str,
    hospital: str,
    experience_years: int,
    email: str,
) -> dict:
    salt, password_hash = hash_password(password)
    try:
        with get_connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO doctors (
                    tc_identity, password_salt, password_hash, name, specialty,
                    hospital, experience_years, email
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tc_identity.strip(),
                    salt,
                    password_hash,
                    name.strip(),
                    specialty.strip(),
                    hospital.strip(),
                    experience_years,
                    email.strip(),
                ),
            )
            row = connection.execute("SELECT * FROM doctors WHERE id = ?", (cursor.lastrowid,)).fetchone()
            return public_record(row)
    except sqlite3.IntegrityError as exc:
        raise ValueError("TC kimlik numarası zaten kayıtlı") from exc


def create_patient(
    tc_identity: str,
    password: str,
    doctor_id: int,
    name: str,
    age: int,
    gender: str,
    height_cm: int,
    weight_kg: int,
    smoking_status: str,
    alcohol_use: str,
    diagnoses: str,
    allergies: str,
    creatinine: float,
    alt: int,
    ast: int,
    hemoglobin: float,
    cancer_status: str,
    cancer_stage: str,
    kidney_function_status: str,
    liver_function_status: str,
    chronic_disease_count: int,
) -> dict:
    salt, password_hash = hash_password(password)
    bmi = round(weight_kg / ((height_cm / 100) ** 2), 1)
    try:
        with get_connection() as connection:
            doctor = connection.execute("SELECT id FROM doctors WHERE id = ?", (doctor_id,)).fetchone()
            if not doctor:
                raise ValueError("Doktor bulunamadı")
            cursor = connection.execute(
                """
                INSERT INTO patients (
                    doctor_id, tc_identity, password_salt, password_hash, name, age,
                    gender, height_cm, weight_kg, bmi, smoking_status, alcohol_use,
                    diagnoses, allergies, creatinine, alt, ast, hemoglobin,
                    cancer_status, cancer_stage, kidney_function_status,
                    liver_function_status, chronic_disease_count
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    doctor_id,
                    tc_identity.strip(),
                    salt,
                    password_hash,
                    name.strip(),
                    age,
                    gender.strip(),
                    height_cm,
                    weight_kg,
                    bmi,
                    smoking_status.strip(),
                    alcohol_use.strip(),
                    diagnoses.strip(),
                    allergies.strip(),
                    creatinine,
                    alt,
                    ast,
                    hemoglobin,
                    cancer_status.strip(),
                    cancer_stage.strip(),
                    kidney_function_status.strip(),
                    liver_function_status.strip(),
                    chronic_disease_count,
                ),
            )
            row = connection.execute("SELECT * FROM patients WHERE id = ?", (cursor.lastrowid,)).fetchone()
            patient = public_record(row)
            patient["current_medications"] = []
            patient["diagnosis_codes"] = []
            patient["synthetic_data"] = True
            return patient
    except sqlite3.IntegrityError as exc:
        raise ValueError("TC kimlik numarası zaten kayıtlı") from exc


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
