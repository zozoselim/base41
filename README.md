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

NovaVision gerçek API bağlantısı için opsiyonel ortam değişkenleri:

```bash
set NOVAVISION_API_URL=http://127.0.0.1:9005/api
set NOVAVISION_ACCESS_TOKEN=your_optional_access_token
```

`NOVAVISION_API_URL` tanımlı değilse backend varsayılan olarak `http://127.0.0.1:9005/api` adresini dener. NovaVision response içinde OCR text bulunamazsa demo OCR metnini kullanır ve `debug.fallback_used=true` döndürür.

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

1. Frontend reçete fotoğrafını `multipart/form-data` ile `/prescription-scan` endpointine gönderir.
2. Backend görseli Base64 formatına çevirir.
3. Base64 görsel NovaVision OCR API'ye `module`, `executor`, `ws_channel`, `app.nodes`, `configs`, `access-token`, `app_id`, `service` ve `payload` alanlarını içeren request template'iyle POST edilir.
4. NovaVision response recursive olarak taranır; `outputContent`, `outputText`, `text`, `recognized_text`, `ocr_text`, detection text ve list içindeki `value/text/content` alanları aranır.
5. Response sadece `outputImage` döndürürse backend debug mesajı üretir: `NovaVision response içinde OCR text output bulunamadı. Flow output config sadece image döndürüyor olabilir.`
6. `data/medication_info.json` içindeki ilaç adları ve alias listeleri OCR metninde aranır.
7. Bulunan her ilaç için ayrı reçete özeti kartı döndürülür.
8. Frontend ilaç adı, etken madde, doz, kullanım sıklığı, kullanım zamanı, kullanım süresi, yan etki, uyarı ve doktor onay durumunu gösterir.

Önemli kurallar:

- NovaVision sadece OCR yapar.
- İlaç bilgisi backend'deki JSON dosyalarından gelir.
- Fotoğraftan tedavi kararı verilmez.
- Doz tahmini yapılmaz; doz OCR metninden veya doktor reçete verisinden alınır.
- Her sonuçta şu uyarı yer alır: `Bu bilgi doktor reçetesine dayalıdır. Tedavi kararı doktor onayı gerektirir.`

Demo ortamında kullanılan OCR metni:

```text
Parol 500 mg günde 2 kez 5 gün. Augmentin 1000 mg sabah akşam 7 gün.
```

NovaVision OCR Text Detection app reçete fotoğrafından metin okumak için dış servis olarak konumlandırılmıştır. OncoSafe backend bu OCR metnini işler, ilaçları eşleştirir ve hasta için anlaşılır reçete özeti üretir. Demo ortamında OCR çıktısı simüle edilir; `NOVAVISION_API_URL` tanımlandığında gerçek NovaVision API çağrısı yapılabilir.

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
