# OncoSafe Vision AI

OncoSafe Vision AI, kanser hastaları ve çoklu ilaç kullanan bireyler için hazırlanmış hackathon MVP prototipidir. Sistem şunları birleştirir:

- NovaVision tarzı görsel ilaç tanıma
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
4. `Tahmin Et` butonuna basın.
5. Doktor onay panelini kullanın.

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
- `POST /analyze-drug-risk`
- `POST /predict-chemo-risk`
- `POST /doctor-decision`

## Veri

Sentetik veri dosyaları `data/` klasöründedir:

- `patients.json`
- `drug_interactions.json`
- `oncology_risk.json`

Gerçek e-Nabız verisi veya gerçek hasta verisi kullanılmaz.
