import asyncio
import json
import logging
from fastapi import FastAPI, HTTPException, Query
from playwright.async_api import async_playwright
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
        # headless=False diubah agar jendela browser Chromium muncul di layar Anda
        browser = await p.chromium.launch(headless=False)

        # Buat browser context baru untuk isolasi session/cookies
        browser_context = await browser.new_context()
        page = await browser_context.new_page()

        # Pasang listener pada browser_context agar menangkap seluruh network di session tersebut
        browser_context.on("response", buat_network_listener(status_container))

        try:
            logging.info(f"[{resi}] Membuka website TIKI...")
            # Menggunakan wait_until="networkidle" agar memastikan script menunggu halaman stabil
            await page.goto("https://www.tiki.id/id/track", timeout=45000, wait_until="networkidle")

            # Proteksi Tambahan: Tunggu elemen #track-no benar-benar ada di DOM secara fisik sebelum diisi
            logging.info(f"[{resi}] Menunggu elemen #track-no tersedia di layar...")
            await page.wait_for_selector('#track-no', timeout=15000)

            logging.info(f"[{resi}] Mengisi nomor resi...")
            await page.fill('#track-no', resi)

            logging.info(f"[{resi}] Mengklik tombol lacak...")
            await page.click('.tracking-btn-lacak')

            # Polling network selama 15 detik untuk menunggu reCAPTCHA beres & data dikirim kembali
            timeout_detik = 15
            for _ in range(timeout_detik):
                if status_container["hasil"] is not None:
                    break
                await asyncio.sleep(1)

            if status_container["hasil"]:
                logging.info(f"[{resi}] Sukses mendapatkan data tracking.")
                return status_container["hasil"]
            else:
                logging.warning(f"[{resi}] Timeout data network tidak ditemukan.")
                raise HTTPException(status_code=404,
                                    detail="Data tracking tidak ditemukan atau reCAPTCHA memblokir bot.")

        except Exception as e:
            logging.error(f"[{resi}] Terjadi error: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

        finally:
            # Beri jeda 2 detik agar Anda sempat melihat apa yang terjadi di browser sebelum menutup otomatis
            await page.wait_for_timeout(2000)
            await browser.close()


if __name__ == "__main__":
    import uvicorn

    # reload dimatikan untuk mencegah bentrokan ProactorEventLoop di Windows child-process
    uvicorn.run(app, host="0.0.0.0", port=8001)