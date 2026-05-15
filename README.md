# OncoSafe Vision AI

OncoSafe Vision AI, kanser hastaları ve çoklu ilaç kullanan bireyler için hazırlanmış hackathon MVP prototipidir. Sistem şunları birleştirir:

- NovaVision tarzı görsel ilaç tanıma
- Hasta için fotoğraftan ilaç rehberi ve reçete özeti
- Açıklanabilir ilaç etkileşim risk skoru
- Onkoloji tedavisi için ön risk tahmini
- Doktor onay akışı
- Yalnızca sentetik veri kullanımı

Bu prototip tanı koymaz, Oncotype DX yerine geçmez ve tıbbi karar vermez. Her öneri doktor değerlendirmesi gerektirir.

## Hızlı Demo

`index.html` dosyasını tarayıcıda açın.

Önerilen demo akışı:

1. `Ayse Demir - P001` hastasını seçin.
2. `NovaVision ile Tara` butonuna basın.
3. `İlaç Riskini Analiz Et` butonuna basın.
4. `Hasta İlaç Rehberi` bölümünde `İlacı Tanı` butonuna basarak ilaç kullanım özetini gösterin.
5. `Tahmin Et` butonuna basın.
6. Doktor onay panelini kullanın.

Tek tıklamalı `Tüm MVP Akışını Çalıştır` butonu jüri demosunu otomatik çalıştırır.

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
- `POST /scan-medications`
- `POST /scan-medicine-guide`
- `POST /analyze-drug-risk`
- `POST /predict-chemo-risk`
- `POST /doctor-decision`

## NovaVision Entegrasyon Fikri

NovaVision projede iki amaçla kullanılır:

1. Reçete veya birden fazla ilaç kutusu görselinden ilaç listesini çıkarmak.
2. Tek ilaç kutusu fotoğrafından ilacı tanıyıp hastaya anlaşılır ilaç kullanım özeti göstermek.

Gerçek entegrasyon planı:

1. NovaVision Suite içinde Object Detection veya Classification akışı oluşturulur.
2. İlaç kutusu, reçete alanı veya ilaç etiketi sınıfları tanımlanır.
3. NovaVision çıktısı `name`, `confidence` ve gerekiyorsa `bbox` alanlarıyla JSON olarak backend'e gönderilir.
4. Backend bu çıktıyı `/scan-medications` veya `/scan-medicine-guide` endpointinde işler.
5. Demo sırasında gerçek API erişimi hazır değilse aynı formatta simülasyon JSON'u kullanılır.

## Veri

Sentetik veri dosyaları `data/` klasöründedir:

- `patients.json`
- `drug_interactions.json`
- `oncology_risk.json`
- `medicine_guides.json`

Gerçek e-Nabız verisi veya gerçek hasta verisi kullanılmaz.
