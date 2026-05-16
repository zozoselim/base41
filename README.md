# OncoSafe Vision AI

OncoSafe Vision AI, doktorlar için hazırlanmış bir sağlık hackathon MVP'sidir. Sistem, çoklu ilaç kullanan sentetik bir hastaya yeni ilaç eklenirken oluşabilecek riski incelemeye yardımcı olan bir klinik karar destek prototipidir.

Önemli güvenlik kuralları:

- Sistem hiçbir zaman nihai tıbbi karar vermez.
- Sistem hastaya ilaç başlatma, durdurma veya değiştirme talimatı vermez.
- Tüm sonuçlar yalnızca klinik karar desteği olarak gösterilir.
- Orta ve yüksek risk doktor değerlendirmesi gerektirir.
- Otomatik oluşturulan tüm veriler sentetiktir.

## Teknoloji

- Frontend: React + Vite
- Backend: FastAPI
- Veritabanı: SQLite
- Yapay zeka entegrasyonu: Güvenli yedek yanıtlı Puq.ai webhook/API

## Yerelde Çalıştırma

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

Açılacak adres:

```text
http://127.0.0.1:5173
```

API dokümantasyonu:

```text
http://127.0.0.1:8000/docs
```

## Puq.ai Yapılandırması

`.env` dosyasını oluşturun veya düzenleyin:

```env
PUQ_WEBHOOK_URL=your_puq_ai_webhook_url
PUQ_API_KEY=your_puq_ai_api_key
```

Backend Puq.ai servisine şu başlıkla istek gönderir:

```json
{
  "Content-Type": "application/json",
  "Authorization": "Token YOUR_PUQ_API_KEY"
}
```

Puq.ai kullanılamazsa veya yapılandırılmamışsa `/analyze-new-medicine` güvenli bir yedek JSON yanıtı döndürür:

```json
{
  "is_fallback": true,
  "warning": "Puq.ai servisine şu anda ulaşılamıyor. Güvenli demo sonucu gösteriliyor."
}
```

## NovaVision OCR Yapılandırması

NovaVision OCR Text Detection flow'u dış servis olarak kullanılır. Reçete görseli backend'e yüklenir, backend görseli Base64'e çevirir ve `NOVAVISION_API_URL` tanımlıysa NovaVision'a gönderir.

```env
NOVAVISION_API_URL=http://127.0.0.1:9005/api
NOVAVISION_ACCESS_TOKEN=your_optional_access_token
```

`NOVAVISION_ACCESS_TOKEN` boşsa Authorization header gönderilmez. NovaVision response içinde `outputDetections.value[].data` alanları okunur, bounding box konumuna göre sıralanır ve ilaç bilgileri `data/medication_info.json` içindeki alias listeleriyle eşleştirilir. Demo fallback yalnızca NovaVision response alınamazsa kullanılır.

## Ana Akış

Doktor girişi
-> Hasta seçimi
-> Hasta profili ve mevcut ilaçların görüntülenmesi
-> Yeni ilacın girilmesi
-> FastAPI `/analyze-new-medicine`
-> SQLite sorgusu
-> Puq.ai webhook veya güvenli yedek yanıt
-> Frontend risk sonucu gösterimi
-> Doktor kararının `/doctor-decision` üzerinden kaydedilmesi

## API Endpointleri

- `POST /auth/login`
- `GET /doctors`
- `GET /patients`
- `GET /patients/{patient_id}`
- `GET /patients/{patient_id}/medicines`
- `POST /prescription-scan`
- `POST /analyze-new-medicine`
- `POST /doctor-decision`

SQLite veritabanı backend başlangıcında otomatik olarak `oncosafe.sqlite3` adıyla oluşturulur. Veritabanına 5 doktor, 50 sentetik hasta ve hasta başına 2 ile 6 arasında ilaç otomatik eklenir.
