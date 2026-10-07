import asyncio
import json
import logging
import os
from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException, Query, Security
from fastapi.security import APIKeyHeader
from fastapi.responses import JSONResponse, HTMLResponse
from playwright.async_api import async_playwright
from playwright_stealth import Stealth
from cekresi import CekresiClient, to_legacy
from config import settings
import sys

# FIX UNTUK WINDOWS (Wajib ditaruh paling atas sebelum Playwright berjalan)
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

app = FastAPI(
    title="Tiki Tracking Scraper API",
    description="API untuk melakukan tracking resi TIKI menggunakan Playwright",
    version="1.0.0"
)


api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def verify_api_key(api_key: str = Security(api_key_header)):
    if not settings.API_KEY:
        # Jika API_KEY tidak diset di .env, skip validasi
        return
    if not api_key or api_key != settings.API_KEY:
        raise HTTPException(
            status_code=401,
            detail={"status": "401", "response": {"message": "API Key tidak valid atau tidak diberikan."}}
        )

async def klik_checkbox_recaptcha(page, resi: str, timeout_detik: int = 25) -> str:
    """Klik checkbox reCAPTCHA v2 dan tunggu token muncul. Return token atau '' jika gagal."""
    try:
        # Pastikan widget sudah dirender oleh grecaptcha.render()
        await page.wait_for_selector(".recaptcha-box", timeout=15000)
        await page.eval_on_selector(".recaptcha-widget", "e => e.scrollIntoView({block: 'center'})")
        await page.wait_for_timeout(1500)

        anchor_iframe = "iframe[src*='recaptcha/api2/anchor']"
        await page.wait_for_selector(anchor_iframe, timeout=15000)

        checkbox = page.frame_locator(anchor_iframe).locator("#recaptcha-anchor")
        await checkbox.wait_for(state="visible", timeout=10000)
        logging.info(f"[{resi}] Mengklik checkbox reCAPTCHA...")
        await checkbox.click(timeout=10000)
    except Exception as e:
        logging.warning(f"[{resi}] Gagal klik checkbox: {e}")
        return ""

    # Polling token via helper JS bawaan TIKI (getRecaptchaToken)
    for _ in range(timeout_detik * 2):
        try:
            token = await page.evaluate(
                "() => { try { return getRecaptchaToken(document.querySelector('.tracking-form-input')); }"
                " catch(e) { return ''; } }"
            )
            if token:
                logging.info(f"[{resi}] Token reCAPTCHA didapat ({len(token)} char).")
                return token
        except Exception:
            pass
        await asyncio.sleep(0.5)

    logging.warning(f"[{resi}] Token reCAPTCHA tidak muncul (kemungkinan image-challenge).")
    return ""


def buat_network_listener(status_container):
    async def handle_response(response):
        # Endpoint baru: POST /api/tracking (frontend getTracking)
        if "/api/tracking" in response.url or "track" in response.url:
            try:
                content_type = response.headers.get("content-type", "")
                if "application/json" in content_type:
                    data = await response.json()
                    if "status" in data and "response" in data:
                        status_container["hasil"] = data
            except Exception:
                pass

    return handle_response


@app.get("/health")
async def health():
    return {"status": "200", "response": {"message": "OK"}}


@app.get("/cekresi", response_class=HTMLResponse)
async def halaman_cekresi():
    with open(os.path.join(os.path.dirname(__file__), "static", "cekresi.html"), encoding="utf-8") as f:
        return f.read()


@app.get("/api/track-cekresi", dependencies=[Depends(verify_api_key)])
async def track_cekresi(
    resi: str = Query(..., description="Nomor resi (bisa multiple, pisahkan koma)"),
    kurir: str = Query("TIKI", description="Kode ekspedisi (mis. TIKI, JNE, JET)"),
):
    """Versi alternatif via cekresi.com — tanpa browser & tanpa reCAPTCHA (pure HTTP),
    response disamakan dengan format tiki.id: {status, msg, response[...]}."""
    daftar = [r.strip().upper().replace(" ", "") for r in resi.split(",") if r.strip()]
    daftar = list(dict.fromkeys(daftar))  # buang duplikat, pertahankan urutan
    if not daftar:
        return JSONResponse(
            status_code=404,
            content={"status": "404", "response": {"message": "Nomor resi kosong."}},
        )
    if len(daftar) > 20:
        return JSONResponse(
            status_code=400,
            content={"status": "400", "response": {"message": "Maksimal 20 resi per request."}},
        )
    logging.info(f"[cekresi:{kurir}] Request tracking untuk {len(daftar)} resi.")
    try:
        # Satu session/client per resi (urllib opener tidak thread-safe),
        # dijalankan konkuren agar multiresi tetap cepat.
        mentah = await asyncio.gather(
            *[asyncio.to_thread(CekresiClient().track, r, kurir) for r in daftar]
        )
    except Exception as e:
        logging.error(f"[cekresi:{kurir}] Error: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "500", "response": {"message": f"Internal Server Error: {e}"}},
        )
    data = [to_legacy(item) for item in mentah if item.get("ok")]
    if not data:
        return JSONResponse(
            status_code=404,
            content={"status": "404", "response": {"message": "Semua resi tidak ditemukan."}},
        )
    return JSONResponse(
        status_code=200,
        content={
            "status": 200,
            "msg": "single" if len(data) == 1 else "multiple",
            "response": data,
        },
    )


@app.get("/api/track-cekresi/expedisi", dependencies=[Depends(verify_api_key)])
async def daftar_ekspedisi(
    resi: str = Query(..., description="Nomor resi (bisa multiple, pisahkan koma)"),
):
    """Langkah 1 alur cekresi: auto-detect daftar ekspedisi yang tersedia."""
    daftar = [r.strip().upper().replace(" ", "") for r in resi.split(",") if r.strip()]
    daftar = list(dict.fromkeys(daftar))
    if not daftar:
        return JSONResponse(
            status_code=404,
            content={"status": "404", "response": {"message": "Nomor resi kosong."}},
        )
    try:
        mentah = await asyncio.gather(
            *[asyncio.to_thread(CekresiClient().detect, r) for r in daftar]
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "500", "response": {"message": f"Internal Server Error: {e}"}},
        )
    gabung, per_resi = [], {}
    for r, item in zip(daftar, mentah):
        if not item.get("ok"):
            per_resi[r] = {"error": item.get("error", "Tidak dikenali.")}
            continue
        per_resi[r] = {"ekspedisi": [e["kode"] for e in item["ekspedisi"]]}
        for e in item["ekspedisi"]:
            if e["kode"] not in [g["kode"] for g in gabung]:
                gabung.append(e)
    if not gabung:
        return JSONResponse(
            status_code=404,
            content={"status": "404", "response": {"message": "Resi tidak dikenali."}},
        )
    return JSONResponse(
        status_code=200,
        content={"status": 200, "msg": "single" if len(daftar) == 1 else "multiple", "response": gabung},
    )


@app.get("/api/track", dependencies=[Depends(verify_api_key)])
async def track_resi(resi: str = Query(..., description="Nomor resi TIKI yang ingin dicari")):
    logging.info(f"Menerima request tracking untuk resi: {resi}")
    status_container = {"hasil": None}

    async with async_playwright() as p:
        # Gunakan Firefox — TIKI mendeteksi Chromium sebagai bot
        browser = await p.firefox.launch(headless=settings.HEADLESS)

        # Buat browser context baru untuk isolasi session/cookies
        browser_context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
            viewport={"width": 1920, "height": 1080},
            locale="id-ID",
            timezone_id="Asia/Jakarta",
        )
        page = await browser_context.new_page()

        # Pasang stealth agar fingerprint tidak terdeteksi sebagai bot
        stealth = Stealth()
        await stealth.apply_stealth_async(page)

        # Pasang listener pada browser_context agar menangkap seluruh network di session tersebut
        browser_context.on("response", buat_network_listener(status_container))

        try:
            logging.info(f"[{resi}] Membuka website TIKI...")
            # 'domcontentloaded' lebih cepat karena tidak tunggu semua gambar/iframe selesai
            await page.goto(settings.TIKI_TRACK_URL, timeout=settings.PAGE_TIMEOUT, wait_until="domcontentloaded")

            # Tunggu render framework (2000ms — kompromi cepat tapi cukup untuk JS framework)
            await page.wait_for_timeout(2000)

            # Debug: simpan screenshot & HTML hanya jika DEBUG aktif
            screenshot_path = None
            if settings.DEBUG:
                os.makedirs(settings.DEBUG_DIR, exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                resi_clean = resi.replace(",", "_")
                screenshot_path = os.path.join(settings.DEBUG_DIR, f"{resi_clean}_{timestamp}.png")
                html_path = os.path.join(settings.DEBUG_DIR, f"{resi_clean}_{timestamp}.html")
                await page.screenshot(path=screenshot_path, full_page=True)
                html_content = await page.content()
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(html_content)
                logging.info(f"[{resi}] Debug screenshot: {screenshot_path}")
                logging.info(f"[{resi}] Debug HTML: {html_path}")

            # Coba berbagai selector
            selector_ditemukan = None
            for selector in ['#track-no', 'input[name="track_no"]', 'input[placeholder*="resi"]', 'input[type="text"]']:
                try:
                    elem = await page.wait_for_selector(selector, timeout=5000)
                    if elem:
                        is_visible = await elem.is_visible()
                        if is_visible:
                            selector_ditemukan = selector
                            logging.info(f"[{resi}] Ditemukan elemen dengan selector: {selector}")
                            break
                except Exception:
                    continue

            if not selector_ditemukan:
                logging.error(f"[{resi}] Tidak ada input yang ditemukan.")
                detail_msg = "Elemen input tidak ditemukan."
                if settings.DEBUG and screenshot_path:
                    detail_msg += f" Debug: {screenshot_path}"
                return JSONResponse(
                    status_code=500,
                    content={"status": "500", "response": {"message": detail_msg}}
                )

            logging.info(f"[{resi}] Mengisi nomor resi ke selector: {selector_ditemukan}...")
            await page.fill(selector_ditemukan, resi)
            await page.wait_for_timeout(500)

            # ALUR BARU: wajib centang reCAPTCHA dulu sebelum klik Lacak
            token = await klik_checkbox_recaptcha(page, resi)
            if not token:
                # Cek apakah muncul image-challenge (bframe) untuk pesan error yang jelas
                challenge = False
                try:
                    bframe = await page.query_selector("iframe[src*='recaptcha/api2/bframe']")
                    challenge = bframe is not None and await bframe.is_visible()
                except Exception:
                    pass
                msg = ("reCAPTCHA image-challenge muncul, auto-klik gagal. "
                       "Coba HEADLESS=false / IP residential, atau pakai solver berbayar (2Captcha/CapSolver).")
                if not challenge:
                    msg = "Gagal mendapatkan token reCAPTCHA (checkbox tidak bisa diklik)."
                logging.warning(f"[{resi}] {msg}")
                return JSONResponse(
                    status_code=428,
                    content={"status": "428", "response": {"message": msg}}
                )

            logging.info(f"[{resi}] Mengklik tombol lacak...")
            await page.click('.tracking-btn-lacak')

            # Polling network untuk menunggu reCAPTCHA beres & data dikirim kembali
            # Lebih responsif dengan interval 100ms dibanding 1 detik
            timeout_detik = settings.POLLING_TIMEOUT
            for _ in range(timeout_detik * 10):
                if status_container["hasil"] is not None:
                    break
                await asyncio.sleep(0.1)

            if status_container["hasil"]:
                logging.info(f"[{resi}] Sukses mendapatkan data tracking.")
                return JSONResponse(
                    status_code=200,
                    content=status_container["hasil"]
                )
            else:
                logging.warning(f"[{resi}] Timeout data network tidak ditemukan.")
                return JSONResponse(
                    status_code=404,
                    content={"status": "404", "response": {"message": "Data tracking tidak ditemukan atau reCAPTCHA memblokir bot."}}
                )

        except Exception as e:
            logging.error(f"[{resi}] Terjadi error: {str(e)}")
            return JSONResponse(
                status_code=500,
                content={"status": "500", "response": {"message": f"Internal Server Error: {str(e)}"}}
            )

        finally:
            await browser.close()


if __name__ == "__main__":
    import uvicorn

    logging.info(f"DEBUG mode: {'AKTIF' if settings.DEBUG else 'NONAKTIF'}")
    logging.info(f"HEADLESS mode: {'AKTIF' if settings.HEADLESS else 'NONAKTIF'}")

    # reload dimatikan untuk mencegah bentrokan ProactorEventLoop di Windows child-process
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)