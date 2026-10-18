import json, os, re
from collections import defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from decimal import Decimal, ROUND_HALF_UP
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import jwt

app = FastAPI()

IDP_ISSUER = "https://idp.exam.local"
IDP_AUDIENCE = "tds-8abkzvku.apps.exam.local"
IDP_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA2okOHspNjgA+2rTLbeuY
cxiP/hG8C6Sb9iwg3yiLAA4HCnpITcbWCSelbvbYGuc3EbNy4xFyf5Cbj5DHJMID
EkryOgyd2giIIIBOUBj8S63uGcnRpOBh9NFatfNwheKuzsPuVNldu6A9cNteNpXc
WyJjG2axVfmq7i6SuKr1JoWYG7xTTAvKPujSl4OtsQfO3h5NepzdfXpr28oNnzfW
ed+zclR6BcmNNo/WVfJ4xyCLSf0BCOgdTgW6PdaChd1l9VDetJZVEgC5tkyvXsfI
SI6iyrYbKR0NEBSqq4XkadEjsCs4F1RncsS4LlgniT7GlkL9Mce3b0wGLs9/7ZIX
dQIDAQAB
-----END PUBLIC KEY-----"""

class VerifyRequest(BaseModel):
    token: str

@app.post("/verify")
def verify(req: VerifyRequest):
    try:
        claims = jwt.decode(req.token, IDP_PUBLIC_KEY, algorithms=["RS256"], issuer=IDP_ISSUER, audience=IDP_AUDIENCE, options={"require": ["exp", "iss", "aud"]})
        return {"valid": True, "email": claims.get("email"), "sub": claims.get("sub"), "aud": claims.get("aud")}
    except Exception:
        return JSONResponse(status_code=401, content={"valid": False})
DATA = None

class Question(BaseModel):
    question: str

def load_data():
    global DATA
    if DATA is not None: return DATA
    with open(os.path.join(os.path.dirname(__file__), "ledger.json"), encoding="utf-8") as f:
        export = json.load(f)
    rates = {"USD": 1, "EUR": Decimal("1.05"), "INR": Decimal("0.01154")}
    latest = {}
    for x in export:
        old = latest.get(x["id"])
        if old is None or x["updated_at"] > old["updated_at"]: latest[x["id"]] = x
    DATA = (list(latest.values()), rates)
    return DATA

def usd(row, rates): return Decimal(str(row["amount"])) * rates[row["currency"]]
def money(v): return float(v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
def words(q): return q.lower().replace("-", " ")
def business_dt(row):
    value = row["created_at"].replace("Z", "+00:00")
    return datetime.fromisoformat(value).astimezone(ZoneInfo("Asia/Kolkata"))
def filtered(q, rows):
    q = words(q); out = rows
    for field, pat in (("region", r"\b(north|south|east|west|central)\b"), ("product", r"\b(blender|toaster|kettle|mixer|juicer|grinder|rice cooker|air fryer)\b")):
        m = re.search(pat, q)
        if m: out = [x for x in out if x[field].lower() == m.group(1)]
    cm = re.search(r"(?:customer|client)\s*(?:id\s*)?(c\d+)", q)
    if cm: out = [x for x in out if x["customer"].lower() == cm.group(1)]
    months = {"january":1,"february":2,"march":3,"april":4,"may":5,"june":6,"july":7,"august":8,"september":9,"october":10,"november":11,"december":12}
    mm = re.search(r"(january|february|march|april|may|june|july|august|september|october|november|december)\s+(20\d{2})", q)
    if mm: out = [x for x in out if business_dt(x).year == int(mm.group(2)) and business_dt(x).month == months[mm.group(1)]]
    elif (ym := re.search(r"\b(20\d{2})\b", q)) and ("year" in q or "during" in q):
        out = [x for x in out if business_dt(x).year == int(ym.group(1))]
    return out

@app.post("/")
def answer(req: Question):
    rows, rates = load_data(); q = words(req.question); selected = filtered(q, rows)
    if "refund" in q:
        selected = [x for x in selected if x["status"] == "refunded"]
    elif "void" in q:
        selected = [x for x in selected if x["status"] == "void"]
    else:
        selected = [x for x in selected if x["status"] == "paid"]
    if any(w in q for w in ("highest", "top", "most", "best")):
        key = "product" if "product" in q else "customer" if "customer" in q or "client" in q else "region"
        totals = defaultdict(Decimal)
        for x in selected: totals[x[key]] += usd(x, rates)
        return {"answer": max(totals, key=totals.get) if totals else None}
    if "unit" in q or "quantity" in q:
        return {"answer": sum(x["qty"] for x in selected)}
    if ("distinct customer" in q or "different customer" in q or
            "unique customer" in q or "different customers" in q or
            "distinct customers" in q or "unique customers" in q):
        return {"answer": len({x["customer"] for x in selected})}
    if "average" in q or "on average" in q or "avg" in q:
        total = sum((usd(x, rates) for x in selected), Decimal(0))
        return {"answer": money(total / len(selected)) if selected else 0.0}
    if ("count" in q or "number of" in q or "how many orders" in q or
            "how many refunded" in q or "how many paid" in q):
        return {"answer": len(selected)}
    return {"answer": money(sum((usd(x, rates) for x in selected), Decimal(0)))}
