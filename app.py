import asyncio
import json
import logging
import os
from datetime import datetime
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from playwright.async_api import async_playwright
from playwright_stealth import Stealth
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


def buat_network_listener(status_container):
    async def handle_response(response):
        # Memastikan mendengarkan endpoint tracking yang tepat
        if "track" in response.url:
            try:
                content_type = response.headers.get("content-type", "")
                if "application/json" in content_type:
                    data = await response.json()
                    if "status" in data and "response" in data:
                        status_container["hasil"] = data
            except Exception:
                pass

    return handle_response


@app.get("/api/track")
async def track_resi(resi: str = Query(..., description="Nomor resi TIKI yang ingin dicari")):
    logging.info(f"Menerima request tracking untuk resi: {resi}")
    status_container = {"hasil": None}

    async with async_playwright() as p:
        # Gunakan Firefox — lebih sulit dideteksi bot daripada Chromium
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
            await page.goto(settings.TIKI_TRACK_URL, timeout=settings.PAGE_TIMEOUT, wait_until="domcontentloaded")

            # Tunggu halaman benar-benar selesai render (tunggu JS framework)
            await page.wait_for_timeout(settings.RENDER_WAIT)

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

            logging.info(f"[{resi}] Mengklik tombol lacak...")
            await page.click('.tracking-btn-lacak')

            # Polling network untuk menunggu reCAPTCHA beres & data dikirim kembali
            timeout_detik = settings.POLLING_TIMEOUT
            for _ in range(timeout_detik):
                if status_container["hasil"] is not None:
                    break
                await asyncio.sleep(1)

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
            # Beri jeda 2 detik agar Anda sempat melihat apa yang terjadi di browser sebelum menutup otomatis
            await page.wait_for_timeout(2000)
            await browser.close()


if __name__ == "__main__":
    import uvicorn

    logging.info(f"DEBUG mode: {'AKTIF' if settings.DEBUG else 'NONAKTIF'}")
    logging.info(f"HEADLESS mode: {'AKTIF' if settings.HEADLESS else 'NONAKTIF'}")

    # reload dimatikan untuk mencegah bentrokan ProactorEventLoop di Windows child-process
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)