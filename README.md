# 📦 Tiki Tracking Scraper API

API untuk melakukan tracking resi **TIKI** menggunakan **Playwright** dengan **FastAPI**.  
Menggunakan browser automation (Firefox headless) untuk mengambil data tracking langsung dari website TIKI.

---

## 🚀 Fitur

- **Scraping otomatis** dari website TIKI (`tiki.id/id/track`)
- **Stealth mode** — menyamarkan fingerprint bot agar tidak terdeteksi reCAPTCHA
- **Multi-selector fallback** — mendeteksi input field secara otomatis
- **Debug mode** — simpan screenshot & HTML untuk troubleshooting
- **API Key security** — endpoint dilindungi dengan X-API-Key header
- **Konfigurasi via `.env`** — mudah diaktifkan/dinonaktifkan tanpa edit kode
- **Docker support** — jalankan di container dengan mudah

---

## 📁 Struktur Project

```
tiki-scrap/
├── app.py              # Main application (FastAPI + Playwright)
├── config.py           # Base settings (baca dari .env)
├── .env                # Environment variables
├── .env.example        # Contoh file .env
├── requirements.txt    # Python dependencies
├── Dockerfile          # Docker image definition
├── docker-compose.yml  # Docker compose config
├── .dockerignore       # Docker ignore rules
├── .gitignore          # Git ignore rules
└── debug/              # Folder debug output (screenshot & HTML)
```

---

## ⚙️ Konfigurasi

Edit file `.env` untuk mengatur aplikasi:

```env
# Debug Mode: simpan screenshot & HTML ke folder debug/
# true = aktif, false = nonaktif
DEBUG=false

# Browser Headless Mode
# true = tanpa tampilan browser, false = tampilkan browser
HEADLESS=true

# API Key untuk mengamankan endpoint
# Kosongkan untuk open access (tidak disarankan)
API_KEY=your-secret-key-here
```

### Semua konfigurasi (via `config.py`)

| Variable   | Default   | Keterangan                      |
| ---------- | --------- | ------------------------------- |
| `DEBUG`    | `false`   | Aktifkan screenshot & HTML dump |
| `HEADLESS` | `true`    | Mode headless browser           |
| `API_KEY`  | `""`      | API Key untuk autentikasi       |
| `HOST`     | `0.0.0.0` | Server host                     |
| `PORT`     | `8000`    | Server port                     |

---

## 🛠️ Instalasi (Manual)

### 1. Clone & masuk ke project

```bash
git clone <repo-url>
cd tiki-scrap
```

### 2. Buat virtual environment

```bash
python -m venv .venv
```

### 3. Aktifkan virtual environment

**Windows (PowerShell):**

```powershell
.venv\Scripts\Activate.ps1
```

**Linux/Mac:**

```bash
source .venv/bin/activate
```

### 4. Install dependencies

```bash
pip install -r requirements.txt
```

### 5. Install Playwright browsers

```bash
playwright install firefox
```

### 6. Jalankan server

```bash
python app.py
```

Server berjalan di `http://localhost:8000`

---

## 🐳 Instalasi (Docker)

### Build & run

```bash
docker-compose up -d --build
```

### Lihat logs

```bash
docker-compose logs -f
```

### Stop

```bash
docker-compose down
```

---

## 📡 API Endpoint

### Track Resi

```
GET /api/track?resi={nomor_resi}
```

**Headers:**

| Header      | Required | Description         |
| ----------- | -------- | ------------------- |
| `X-API-Key` | ✅       | API Key dari `.env` |

**Parameter:**

| Param  | Type     | Required | Description                                    |
| ------ | -------- | -------- | ---------------------------------------------- |
| `resi` | `string` | ✅       | Nomor resi TIKI (bisa multiple, pisahkan koma) |

**Contoh request:**

```bash
curl -H "X-API-Key: your-secret-key-here" \
  "http://localhost:8000/api/track?resi=660108012346,660108011392"
```

**Response sukses (200):**

```json
{
  "status": "200",
  "response": {
    ...
  }
}
```

**Response error (404):**

```json
{
  "status": "404",
  "response": {
    "message": "Data tracking tidak ditemukan atau reCAPTCHA memblokir bot."
  }
}
```

**Response error (401):**

```json
{
  "status": "401",
  "response": {
    "message": "API Key tidak valid atau tidak diberikan."
  }
}
```

**Response error (500):**

```json
{
  "status": "500",
  "response": {
    "message": "Internal Server Error: ..."
  }
}
```

### Swagger UI

Buka di browser: `http://localhost:8000/docs`

---

## 🐛 Debug Mode

Aktifkan debug untuk troubleshooting:

1. Set `DEBUG=true` di `.env`
2. Jalankan server
3. Cek folder `debug/` — berisi screenshot PNG dan HTML dari halaman yang di-scrape

```
debug/
├── 660108012346_20260713_082015.png
└── 660108012346_20260713_082015.html
```

---

## 🏗️ Tech Stack

- **Python 3.13**
- **FastAPI** — web framework
- **Playwright** — browser automation
- **playwright-stealth** — anti-bot detection
- **uvicorn** — ASGI server
- **Docker** — containerization

---

## 📝 Catatan

- Menggunakan **Firefox** karena lebih sulit dideteksi sebagai bot dibanding Chromium
- `playwright-stealth` memodifikasi fingerprint browser agar terlihat seperti user biasa
- reCAPTCHA mungkin masih memblokir jika terdeteksi behavioral analysis
- Jika `API_KEY` kosong di `.env`, endpoint bisa diakses tanpa autentikasi
- Untuk penggunaan production, pertimbangkan rate limiting dan caching

---

## 📄 License

MIT
