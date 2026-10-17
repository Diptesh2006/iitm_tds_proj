import json, os, re
from collections import defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from decimal import Decimal, ROUND_HALF_UP
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()
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
    # Currency words describe the requested output currency; ledger amounts
    # are always converted to USD and must not be filtered by source currency.
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
    if "distinct customer" in q or "unique customer" in q:
        return {"answer": len({x["customer"] for x in selected})}
    if "average" in q or "on average" in q or "avg" in q:
        total = sum((usd(x, rates) for x in selected), Decimal(0))
        return {"answer": money(total / len(selected)) if selected else 0.0}
    if "count" in q or "number of" in q: return {"answer": len(selected)}
    return {"answer": money(sum((usd(x, rates) for x in selected), Decimal(0)))}
