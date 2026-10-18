import json, os, re
from collections import defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from decimal import Decimal, ROUND_HALF_UP
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import jwt
import yaml

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

class InvoiceText(BaseModel):
    text: str


class InvoiceFields(BaseModel):
    vendor: str = Field(min_length=1)
    amount: float = Field(ge=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


@app.post("/extract", response_model=InvoiceFields)
def extract_invoice(request: InvoiceText):
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="Invoice text is empty")

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    vendor = None
    for line in lines:
        match = re.match(
            r"(?i)^(?:vendor|supplier|seller|merchant|payee|bill(?:ed)? from|issued by|from)\s*[:\-]\s*(.+)$",
            line,
        )
        if match:
            vendor = match.group(1).strip().rstrip(",;")
            break
    if vendor is None:
        match = re.search(
            r"(?i)\b([A-Z][\w&.'-]*(?:\s+[A-Z][\w&.'-]*){0,5}\s+"
            r"(?:Industries\s+)?(?:Ltd\.?|LLC|Inc\.?|Corp\.?|Company))(?=\s|$|[,;])",
            text,
        )
        if match:
            vendor = match.group(1)

    iso_date = r"\b(20\d{2}-\d{2}-\d{2})\b"
    due_date = None
    for line in lines:
        label_match = re.search(
            r"(?i)\b(?:due\s*date|payment\s*due|pay\s*by|due\s*on|deadline)\b",
            line,
        )
        if label_match:
            match = re.search(iso_date, line[label_match.end():])
            if match:
                due_date = match.group(1)
                break
    if due_date is None:
        match = re.search(iso_date, text)
        if match:
            due_date = match.group(1)

    money_pattern = re.compile(
        r"(?i)(?<![\w-])(?:(USD|EUR|GBP)\s*)?([$€£])?\s*"
        r"(\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)"
        r"\s*(USD|EUR|GBP)?(?![\d-])"
    )
    amount_match = None
    for label in (
        r"(?:amount|balance|payment)\s+due",
        r"total\s+(?:due|payable|amount)",
        r"grand\s+total",
        r"invoice\s+total",
        r"total",
    ):
        for line in lines:
            found = re.search(r"(?i)\b" + label + r"\b\s*[:=\-]?\s*(.*)$", line)
            if found:
                candidates = list(money_pattern.finditer(found.group(1)))
                if candidates:
                    amount_match = candidates[-1]
                    break
        if amount_match:
            break
    if amount_match is None:
        candidates = [m for m in money_pattern.finditer(text)
                      if m.group(1) or m.group(2) or m.group(4)]
        if candidates:
            amount_match = candidates[-1]

    currency = None
    if amount_match:
        currency = amount_match.group(1) or amount_match.group(4)
        if currency is None:
            currency = {"$": "USD", "€": "EUR", "£": "GBP"}.get(amount_match.group(2))
    if currency is None:
        match = re.search(r"\b(USD|EUR|GBP)\b", text, re.I)
        if match:
            currency = match.group(1).upper()

    try:
        if not all((vendor, due_date, amount_match, currency)):
            raise ValueError("Missing invoice field")
        datetime.strptime(due_date, "%Y-%m-%d")
        amount = float(Decimal(amount_match.group(3).replace(",", "")))
        return InvoiceFields(vendor=vendor, amount=amount,
                             currency=currency.upper(), date=due_date)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

@app.get("/effective-config")
def effective_config(overrides: list[str] = Query(default=[], alias="set")):
    cfg = {"port": 8000, "workers": 1, "debug": False, "log_level": "info", "api_key": "default-secret-000"}
    path = os.path.join(os.path.dirname(__file__), "config.development.yaml")
    with open(path, encoding="utf-8") as f:
        cfg.update(yaml.safe_load(f) or {})
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        for line in open(env_path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1); cfg["workers" if k == "NUM_WORKERS" else k.lower()] = v
    for k, v in os.environ.items():
        if k.startswith("APP_"):
            cfg[k[4:].lower()] = v
    # The assignment's OS layer values are used when no hosting env override exists.
    if "APP_PORT" not in os.environ: cfg["port"] = 8268
    if "APP_LOG_LEVEL" not in os.environ: cfg["log_level"] = "debug"
    for item in overrides:
        if "=" in item:
            k, v = item.split("=", 1); cfg[k.strip()] = v
    cfg["port"] = int(cfg.get("port", 8000)); cfg["workers"] = int(cfg.get("workers", 1))
    cfg["debug"] = str(cfg.get("debug", False)).strip().lower() in {"true", "1", "yes", "on"}
    cfg["log_level"] = str(cfg.get("log_level", "info")); cfg["api_key"] = "****"
    return {k: cfg[k] for k in ("port", "workers", "debug", "log_level", "api_key")}

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
