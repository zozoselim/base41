# OncoSafe Vision AI

OncoSafe Vision AI, kanser hastaları ve çoklu ilaç kullanan bireyler için hazırlanmış hackathon MVP prototipidir.

Sistem şunları birleştirir:

- NovaVision OCR ile reçete fotoğrafından metin okuma
- OCR metninden ilaç adlarını bulma
- Hastaya anlaşılır reçete özeti kartları oluşturma
- Açıklanabilir ilaç etkileşim risk skoru
- Onkoloji tedavisi için ön risk tahmini
- Doktor onay akışı
- Yalnızca sentetik veri kullanımı

Bu prototip tanı koymaz, reçetenin veya doktor kararının yerine geçmez ve tıbbi karar vermez. Her öneri doktor değerlendirmesi gerektirir.

## Hızlı Demo

`index.html` dosyasını tarayıcıda açın.

Önerilen demo akışı:

1. `Ayse Demir - P001` hastasını seçin.
2. `NovaVision Reçeteyi Tara` butonuna basın.
3. OCR metninin ekrana geldiğini gösterin.
4. Parol ve Augmentin için reçete özeti kartlarını gösterin.
5. `NovaVision ile Tara` ve `İlaç Riskini Analiz Et` ile ilaç etkileşim riskini gösterin.
6. `Tahmin Et` butonuyla onkoloji ön risk skorunu gösterin.
7. Doktor onay panelini kullanın.

Demo OCR metni:

```text
Parol 500 mg günde 2 kez 5 gün. Augmentin 1000 mg sabah akşam 7 gün.
```

## Backend İskeleti

FastAPI backend dosyası `backend/main.py` içindedir.

Bağımlılıkları kurmak için:

```bash
pip install -r requirements.txt
```

Backend'i çalıştırmak için:

```bash
uvicorn backend.main:app --reload
```

Endpointler:

- `GET /patients`
- `GET /patients/{patient_id}`
- `POST /prescription-scan`
- `POST /scan-medications`
- `POST /analyze-drug-risk`
- `POST /predict-chemo-risk`
- `POST /doctor-decision`

## NovaVision Entegrasyon Fikri

NovaVision app local klasöre eklenmez. NovaVision dış sistem olarak kullanılır.

NovaVision tarafında:

1. Reçete fotoğrafı yüklenir.
2. OCR Text Detection paketi reçetedeki yazıyı okur.
3. OCR metni OncoSafe backend'e aktarılır.

Local proje tarafında:

1. `/prescription-scan` endpointi OCR metnini alır.
2. `data/medication_info.json` içindeki ilaç adları OCR metninde aranır.
3. Bulunan her ilaç için ayrı reçete özeti kartı döndürülür.
4. Frontend ilaç adı, etken madde, doz, kullanım sıklığı, kullanım zamanı, kullanım süresi, yan etki, uyarı ve doktor onay durumunu gösterir.

Sunum cümlesi:

> NovaVision OCR Text Detection paketi, reçete fotoğrafındaki metni okumak için kullanıldı. Okunan metin OncoSafe backend'e aktarılıyor; sistem bu metindeki ilaçları tanıyıp hastaya anlaşılır reçete özeti, yan etki uyarısı ve doktor onay bilgisi gösteriyor.

## Veri

Sentetik veri dosyaları `data/` klasöründedir:

- `patients.json`
- `drug_interactions.json`
- `oncology_risk.json`
- `medication_info.json`
- `prescriptions.json`

Gerçek e-Nabız verisi veya gerçek hasta verisi kullanılmaz.
