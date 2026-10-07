"""Sumber alternatif: cekresi.com (tanpa reCAPTCHA, pure HTTP).

Alur yang ditiru dari JS homepage cekresi.com:
  1. GET https://cekresi.com/ -> ambil viewstate, secret_key + cookie session
  2. GET content.cekresi.com/resi/initialize_exp.php (auto-detect ekspedisi, opsional)
  3. POST apa2.cekresi.com/cekresi/resi/initialize.php dengan form +
     timers = Base64(AES-128-CBC(Pkcs7(RESI), key, iv)) (sama persis dengan
     ManualJS.MDX.goinstring di merge.js) + header X-Requested-With.
"""

import base64
import html as htmlmod
import json
import logging
import random
import re
import string
import urllib.parse
import urllib.request
from datetime import datetime

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

KEY = bytes.fromhex("79540e250fdb16afac03e19c46dbdeb3")
IV = bytes.fromhex("eb2bb9425e81ffa942522e4414e95bd0")
UI = "a5d42c5d817e1e107d1160c167fd9c9e"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) "
    "Gecko/20100101 Firefox/128.0"
)
TIMEOUT = 30


def _rand_w(n: int = 6) -> str:
    return "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(n))


def make_timers(resi: str) -> str:
    raw = pad(resi.strip().upper().replace(" ", "").encode(), 16)
    ct = AES.new(KEY, AES.MODE_CBC, IV).encrypt(raw)
    return base64.b64encode(ct).decode()


class CekresiClient:
    def __init__(self):
        self.opener = urllib.request.build_opener()
        self.opener.addheaders = [("User-Agent", UA)]

    def _get(self, url: str) -> str:
        req = urllib.request.Request(
            url,
            headers={
                "X-Requested-With": "XMLHttpRequest",
                "Referer": "https://cekresi.com/",
                "Origin": "https://cekresi.com",
                "Accept": "*/*",
                "Accept-Language": "id,en-US;q=0.7,en;q=0.3",
            },
        )
        with self.opener.open(req, timeout=TIMEOUT) as r:
            return r.read().decode("utf-8", errors="replace")

    def _post(self, url: str, form: dict) -> str:
        data = urllib.parse.urlencode(form).encode()
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "X-Requested-With": "XMLHttpRequest",
                "Referer": "https://cekresi.com/",
                "Accept": "*/*",
                "Origin": "https://cekresi.com",
            },
        )
        with self.opener.open(req, timeout=TIMEOUT) as r:
            return r.read().decode("utf-8", errors="replace")

    def detect(self, resi: str) -> dict:
        """Langkah 1 alur cekresi: auto-detect daftar ekspedisi utk satu resi.
        Return {"ok": True, "resi": ..., "ekspedisi": [{"kode":..., "nama":...}]}."""
        resi = resi.strip().upper().replace(" ", "")
        self._get("https://cekresi.com/")  # cookie session
        raw = self._get(
            f"https://content.cekresi.com/resi/initialize_exp.php"
            f"?r={urllib.parse.quote(resi)}&p=1&w={_rand_w()}"
        )
        try:
            data = json.loads(raw)
            content = data.get("content", "")
        except (ValueError, AttributeError):
            return {"ok": False, "error": "Resi tidak dikenali (tidak ada ekspedisi)."}
        lihat = []
        for kode, nama in re.findall(r"setExp\('([^']+)'\)[^>]*>([^<]+)<", content):
            if kode not in [e["kode"] for e in lihat]:
                lihat.append({"kode": kode, "nama": htmlmod.unescape(nama).strip()})
        if not lihat:
            return {"ok": False, "error": "Resi tidak dikenali (tidak ada ekspedisi)."}
        return {"ok": True, "resi": resi, "ekspedisi": lihat}

    def track(self, resi: str, kurir: str = "TIKI") -> dict:
        resi = resi.strip().upper().replace(" ", "")
        kurir = kurir.strip().upper()

        home = self._get("https://cekresi.com/")
        vs = re.search(r'id="viewstate" value="([^"]+)"', home)
        sk = re.search(r'id="secret_key" value="([^"]+)"', home)
        if not vs or not sk:
            return {"ok": False, "error": "Gagal ambil viewstate/secret_key dari homepage."}

        html = self._post(
            f"https://apa2.cekresi.com/cekresi/resi/initialize.php?ui={UI}&p=1&w={_rand_w()}",
            {
                "viewstate": vs.group(1),
                "secret_key": sk.group(1),
                "e": kurir,
                "noresi": resi,
                "timers": make_timers(resi),
            },
        )

        if "Ada kesalahan" in html or "contact us" in html:
            return {"ok": False, "error": "Resi tidak ditemukan / ditolak server cekresi."}

        m_status = re.search(r"status <strong>(.*?)</strong>", html)
        m_dari = re.search(r"dari (.*?)<br\s*/>(.*?)status", html, re.S)
        m_penerima = re.search(
            r'id="last_position">\s*(.*?)\s*</div>', html, re.S
        )
        status = m_status.group(1).strip() if m_status else "-"
        pengirim = re.sub(r"<.*?>", "", m_dari.group(1)).strip() if m_dari else ""
        pengirim_kota = re.sub(r"<.*?>", "", m_dari.group(2)).strip() if m_dari else ""
        penerima = (
            re.sub(r"\s+", " ", m_penerima.group(1)).strip() if m_penerima else "-"
        )

        history = []
        m_hist = re.search(r"<h4>History</h4>(.*)", html, re.S)
        if m_hist:
            for tgl, lok, st in re.findall(
                r"<tr>\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*</tr>",
                m_hist.group(1),
                re.S,
            ):
                tgl = re.sub(r"\s+", " ", tgl).strip()
                if tgl.lower() == "tanggal":
                    continue
                history.append(
                    {
                        "tanggal": tgl,
                        "lokasi": re.sub(r"\s+", " ", lok).strip(),
                        "status": re.sub(r"\s+", " ", st).strip(),
                    }
                )

        if not history:
            return {"ok": False, "error": "Resi tidak ditemukan (tidak ada history)."}

        return {
            "ok": True,
            "resi": resi,
            "kurir": kurir,
            "status": status,
            "pengirim": pengirim,
            "pengirim_kota": pengirim_kota,
            "penerima": penerima,
            "history": history,
        }


def _to_legacy_date(tgl: str) -> str:
    """'06 Oct 2026 07:56:31' -> '2026-10-06 07:56:31' (format tiki.id)."""
    try:
        return datetime.strptime(tgl, "%d %b %Y %H:%M:%S").strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return tgl


def _infer_status_code(noted: str) -> str:
    """Kode status tiki (POD/DEL/DEX/...) tidak disediakan cekresi,
    jadi ditebak dari teks noted agar konsumen lama (progress bar) tetap jalan."""
    t = noted.upper()
    if "RECEIVED BY" in t or "DELIVERED" in t or t.startswith("SUCCESS"):
        return "POD 01"
    if "WITH DELIVERY COURIER" in t:
        return "DEL 01"
    if "DEX" in t or "FAILED" in t or "GAGAL" in t or "DITAHAN" in t:
        return "DEX"
    if "ARRIVED" in t:
        return "INC 01"
    if "DEPARTED" in t:
        return "ROS"
    if "PICKED" in t or "PICK UP" in t or "PICKUP" in t:
        return "PUP 05"
    if "DATA ENTRY" in t:
        return "MDE 01"
    return ""


def _split_place(lokasi: str) -> str:
    m = re.search(r"\[(.*?)\]", lokasi)
    return m.group(1).strip() if m else lokasi


def to_legacy(item: dict) -> dict:
    """Ubah hasil track() menjadi struktur response tiki.id
    {cnno, seq_no, ..., history[{seq_no, entry_date, status, entry_name, entry_place, noted}], image_pod}.
    Field yang tidak disediakan cekresi diisi default kosong/nol."""
    history = [
        {
            "seq_no": 0,
            "entry_date": _to_legacy_date(h["tanggal"]),
            "status": _infer_status_code(h["status"]),
            "entry_name": h["lokasi"],
            "entry_place": _split_place(h["lokasi"]),
            "noted": h["status"],
        }
        for h in item.get("history", [])
    ]
    consignee = ""
    for h in history:
        m = re.search(r"RECEIVED BY\s*:?\s*(.*?)(?:\s+-|$)", h["noted"], re.I)
        if m:
            consignee = m.group(1).strip()
            break
    return {
        "cnno": item.get("resi", ""),
        "seq_no": 0,
        "sender_reference": "",
        "origin_tariff": "",
        "destination_tariff_code": "",
        "destination_city_name": "",
        "product": "",
        "sys_created_on": history[-1]["entry_date"] if history else "",
        "consignor_name": item.get("pengirim", ""),
        "consignor_address": item.get("pengirim_kota", ""),
        "consignee_name": consignee,
        "consignee_address": "",
        "weight": 0,
        "insurance_fee": 0,
        "shipment_fee": 0,
        "pieces_no": 0,
        "est_day": "",
        "est_date": "",
        "history": history,
        "image_pod": None,
    }
