"""Sumber alternatif: cekresi.com (tanpa reCAPTCHA, pure HTTP).

Alur yang ditiru dari JS homepage cekresi.com:
  1. GET https://cekresi.com/ -> ambil viewstate, secret_key + cookie session
  2. GET content.cekresi.com/resi/initialize_exp.php (auto-detect ekspedisi, opsional)
  3. POST apa2.cekresi.com/cekresi/resi/initialize.php dengan form +
     timers = Base64(AES-128-CBC(Pkcs7(RESI), key, iv)) (sama persis dengan
     ManualJS.MDX.goinstring di merge.js) + header X-Requested-With.
"""

import base64
import logging
import random
import re
import string
import urllib.parse
import urllib.request

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
                "Accept": "*/*",
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
        m_dari = re.search(r"no resi <strong>.*?</strong>\s*dari (.*?)<br", html, re.S)
        m_penerima = re.search(
            r'id="last_position">\s*(.*?)\s*</div>', html, re.S
        )
        status = m_status.group(1).strip() if m_status else "-"
        pengirim = re.sub(r"<.*?>", "", m_dari.group(1)).strip() if m_dari else "-"
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

        if not history and status == "-":
            logging.warning("Parse cekresi kosong untuk %s", resi)
            return {"ok": False, "error": "Gagal parse response cekresi."}

        return {
            "ok": True,
            "resi": resi,
            "kurir": kurir,
            "status": status,
            "pengirim": pengirim,
            "penerima": penerima,
            "history": history,
        }
