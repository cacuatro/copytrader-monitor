from fastapi import FastAPI, HTTPException, BackgroundTasks, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import httpx
import os
from pathlib import Path
from dotenv import load_dotenv
import json
import asyncio
import base64
import hashlib
import hmac
from datetime import datetime, timedelta
from typing import Optional
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

app = FastAPI(title="CopyTrader Monitor API")
BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

MYFXBOOK_EMAIL = os.getenv("MYFXBOOK_EMAIL", "")
MYFXBOOK_PASSWORD = os.getenv("MYFXBOOK_PASSWORD", "")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
AUTH_SECRET = os.getenv("AUTH_SECRET", "troque-este-segredo-em-producao")
TOKEN_TTL_HOURS = int(os.getenv("TOKEN_TTL_HOURS", "12"))
USD_BRL_RATE = os.getenv("USD_BRL_RATE", "")

ACCOUNTS_MAP = {
    "gold-dragon": {"id": 11709872, "name": "Gold Dragon", "description": "Estrategia em XAUUSD", "pair": "XAUUSD", "cents": True},
    "gold-long-ictrading": {"id": 11823718, "name": "Gold Long IC Trading", "description": "Estrategia em XAUUSD", "pair": "XAUUSD", "cents": True},
    "gold-long": {"id": 11709870, "name": "Gold Long", "description": "Estrategia em XAUUSD", "pair": "XAUUSD", "cents": True},
    "rayla-conta-02": {"id": 12038663, "name": "Portfolio Estrategias MT5", "description": "Estrategia em XAUUSD", "pair": "XAUUSD", "cents": True},
    "rayla-estrategias-mt4": {"id": 12038682, "name": "Portfolio Estrategias MT4", "description": "Estrategia em XAUUSD", "pair": "XAUUSD", "cents": True},
}

CLIENTS_MAP = {
    "cliente-teste": {
        "name": "Cliente Teste",
        "username": "cliente-teste",
        "password": "teste123",
        "notify_emails": [],
        "accounts": ["gold-dragon", "gold-long-ictrading", "gold-long"],
    },
    "rayla": {
        "name": "Rayla",
        "username": "rayla",
        "password": "Rayla@2026",
        "notify_emails": [],
        "accounts": ["rayla-conta-02", "rayla-estrategias-mt4"],
    },
}

_session_cache = {"session": None, "expires": None}
_data_cache = {}
CACHE_TTL_MINUTES = 15


def make_token(client_slug: str) -> str:
    expires = int((datetime.utcnow() + timedelta(hours=TOKEN_TTL_HOURS)).timestamp())
    payload = f"{client_slug}:{expires}"
    signature = hmac.new(AUTH_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}:{signature}".encode()).decode()


def verify_token(token: str) -> str:
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        client_slug, expires, signature = raw.rsplit(":", 2)
    except Exception:
        raise HTTPException(401, "Token invalido")
    payload = f"{client_slug}:{expires}"
    expected = hmac.new(AUTH_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(401, "Token invalido")
    if int(expires) < int(datetime.utcnow().timestamp()):
        raise HTTPException(401, "Sessao expirada")
    if client_slug not in CLIENTS_MAP:
        raise HTTPException(401, "Cliente invalido")
    return client_slug


def require_client_auth(slug: str, authorization: Optional[str]) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Login necessario")
    token_slug = verify_token(authorization.replace("Bearer ", "", 1))
    if token_slug != slug:
        raise HTTPException(403, "Acesso negado")


def myfxbook_datetime_to_local(value: Optional[str]) -> Optional[str]:
    if not value:
        return value
    try:
        dt = datetime.strptime(value, "%m/%d/%Y %H:%M") - timedelta(hours=3)
        return dt.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return value


def month_ranges_from_year_start():
    now = datetime.utcnow()
    current = datetime(now.year, 1, 1)
    ranges = []
    while current <= now:
        next_month = datetime(current.year + 1, 1, 1) if current.month == 12 else datetime(current.year, current.month + 1, 1)
        end = min(next_month - timedelta(days=1), now)
        ranges.append((current, end))
        current = next_month
    return ranges


async def get_monthly_gain_series(session: str, account_id: int, flat_gains: list, div: float) -> list:
    ranges = month_ranges_from_year_start()
    tasks = [
        cached_get(
            "https://www.myfxbook.com/api/get-gain.json",
            {"session": session, "id": account_id, "start": start.strftime("%Y-%m-%d"), "end": end.strftime("%Y-%m-%d")},
        )
        for start, end in ranges
    ]
    gain_results = await asyncio.gather(*tasks, return_exceptions=True)
    rows = []
    for (start, end), result in zip(ranges, gain_results):
        profit = 0.0
        for g in flat_gains:
            try:
                d = datetime.strptime(g["date"], "%m/%d/%Y")
                if start.date() <= d.date() <= end.date():
                    profit += float(g.get("profit", 0))
            except Exception:
                pass
        gain_value = None
        if not isinstance(result, Exception):
            try:
                gain_value = round(float(result.get("value", 0)), 2)
            except Exception:
                gain_value = None
        rows.append({"month": start.strftime("%Y-%m"), "label": start.strftime("%m/%Y"), "gain": gain_value, "profit": round(profit / div, 2)})
    return rows


async def get_myfxbook_session() -> str:
    now = datetime.utcnow()
    if _session_cache["session"] and _session_cache["expires"] > now:
        return _session_cache["session"]
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            "https://www.myfxbook.com/api/login.json",
            params={"email": MYFXBOOK_EMAIL, "password": MYFXBOOK_PASSWORD},
        )
    data = r.json()
    if data.get("error"):
        raise HTTPException(502, f"MyFXBook login falhou: {data.get('message')}")
    _session_cache["session"] = data["session"]
    _session_cache["expires"] = now + timedelta(hours=23)
    return data["session"]


async def cached_get(url: str, params: dict) -> dict:
    key = url + json.dumps(params, sort_keys=True)
    now = datetime.utcnow()
    if key in _data_cache and _data_cache[key]["expires"] > now:
        return _data_cache[key]["data"]
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(url, params=params)
    data = r.json()
    _data_cache[key] = {"data": data, "expires": now + timedelta(minutes=CACHE_TTL_MINUTES)}
    return data


async def get_usd_brl_rate() -> dict:
    if USD_BRL_RATE:
        return {"rate": round(float(USD_BRL_RATE), 4), "source": "USD_BRL_RATE"}
    cache_key = "usd_brl_rate"
    now = datetime.utcnow()
    if cache_key in _data_cache and _data_cache[cache_key]["expires"] > now:
        return _data_cache[cache_key]["data"]
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get("https://economia.awesomeapi.com.br/json/last/USD-BRL")
        quote = r.json().get("USDBRL", {})
        rate = float(quote.get("bid") or quote.get("ask"))
        result = {"rate": round(rate, 4), "source": "AwesomeAPI USD-BRL", "updated_at": quote.get("create_date")}
    except Exception:
        result = {"rate": 5.0, "source": "fallback"}
    _data_cache[cache_key] = {"data": result, "expires": now + timedelta(minutes=CACHE_TTL_MINUTES)}
    return result


@app.get("/")
async def root():
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"status": "ok", "service": "CopyTrader Monitor API"}


@app.get("/api/status")
async def api_status():
    return {"status": "ok", "service": "CopyTrader Monitor API"}


@app.get("/accounts")
async def list_accounts():
    return [{"slug": slug, "name": info["name"], "description": info["description"], "pair": info["pair"]} for slug, info in ACCOUNTS_MAP.items()]


@app.post("/login")
async def login(credentials: dict):
    username = str(credentials.get("username", "")).strip()
    password = str(credentials.get("password", ""))
    requested_slug = str(credentials.get("client_slug", "")).strip()
    client_slug = next((slug for slug, info in CLIENTS_MAP.items() if info.get("username") == username and info.get("password") == password), None)
    if not client_slug:
        raise HTTPException(401, "Usuario ou senha invalidos")
    if requested_slug and requested_slug != client_slug:
        raise HTTPException(403, "Usuario nao autorizado para este cliente")
    return {"token": make_token(client_slug), "client_slug": client_slug, "name": CLIENTS_MAP[client_slug]["name"], "expires_in_hours": TOKEN_TTL_HOURS}


@app.get("/cliente/{slug}")
async def get_client(slug: str, authorization: Optional[str] = Header(None)):
    if slug not in CLIENTS_MAP:
        raise HTTPException(404, "Cliente nao encontrado")
    require_client_auth(slug, authorization)
    client_info = CLIENTS_MAP[slug]
    results = []
    for acc_slug in client_info["accounts"]:
        try:
            results.append(await get_account_data(acc_slug))
        except Exception as e:
            results.append({"slug": acc_slug, "name": ACCOUNTS_MAP.get(acc_slug, {}).get("name", acc_slug), "error": str(e)})
    ok = [a for a in results if not a.get("error")]
    total_balance = sum(float(a.get("balance") or 0) for a in ok)
    total_profit_day = sum(float(a.get("profit_day") or 0) for a in ok)
    total_profit_week = sum(float(a.get("profit_week") or 0) for a in ok)
    total_profit_month = sum(float(a.get("profit_month") or 0) for a in ok)
    total_profit_total = sum(float(a.get("profit_total") or 0) for a in ok)
    usd_brl = await get_usd_brl_rate()
    brl_rate = usd_brl["rate"]
    return {
        "slug": slug,
        "name": client_info["name"],
        "accounts": results,
        "usd_brl_rate": brl_rate,
        "exchange_rate_source": usd_brl["source"],
        "exchange_rate_updated_at": usd_brl.get("updated_at"),
        "total_balance": round(total_balance, 2),
        "total_balance_brl": round(total_balance * brl_rate, 2),
        "total_profit_day": round(total_profit_day, 2),
        "total_profit_day_brl": round(total_profit_day * brl_rate, 2),
        "total_profit_week": round(total_profit_week, 2),
        "total_profit_week_brl": round(total_profit_week * brl_rate, 2),
        "total_profit_month": round(total_profit_month, 2),
        "total_profit_month_brl": round(total_profit_month * brl_rate, 2),
        "total_profit_total": round(total_profit_total, 2),
        "total_profit_total_brl": round(total_profit_total * brl_rate, 2),
    }


@app.get("/account/{slug}")
async def get_account(slug: str, authorization: Optional[str] = Header(None)):
    allowed_client = next((client_slug for client_slug, info in CLIENTS_MAP.items() if slug in info["accounts"]), None)
    if not allowed_client:
        raise HTTPException(404, "Conta nao encontrada")
    require_client_auth(allowed_client, authorization)
    return await get_account_data(slug)


async def get_account_data(slug: str):
    if slug not in ACCOUNTS_MAP:
        raise HTTPException(404, "Conta nao encontrada")
    account_info = ACCOUNTS_MAP[slug]
    account_id = account_info["id"]
    try:
        session = await get_myfxbook_session()
        accounts_task = cached_get("https://www.myfxbook.com/api/get-my-accounts.json", {"session": session})
        open_trades_task = cached_get("https://www.myfxbook.com/api/get-open-trades.json", {"session": session, "id": account_id})
        history_task = cached_get("https://www.myfxbook.com/api/get-history.json", {"session": session, "id": account_id})
        daily_gain_task = cached_get("https://www.myfxbook.com/api/get-daily-gain.json", {"session": session, "id": account_id, "start": datetime(datetime.utcnow().year, 1, 1).strftime("%Y-%m-%d"), "end": datetime.utcnow().strftime("%Y-%m-%d")})
        accounts_data, open_trades_data, history_data, daily_gain_data = await asyncio.gather(accounts_task, open_trades_task, history_task, daily_gain_task)
        account_detail = next((a for a in accounts_data.get("accounts", []) if a["id"] == account_id), None)
        if not account_detail:
            raise HTTPException(404, "Conta nao encontrada no MyFXBook")
        gains = daily_gain_data.get("dailyGain", [])
        flat_gains = [item for sublist in gains for item in (sublist if isinstance(sublist, list) else [sublist])]
        today = datetime.utcnow().date()
        def sum_period(days_ago):
            cutoff = today - timedelta(days=days_ago)
            total = 0.0
            for g in flat_gains:
                try:
                    d = datetime.strptime(g["date"], "%m/%d/%Y").date()
                    if d >= cutoff:
                        total += float(g.get("profit", 0))
                except Exception:
                    pass
            return round(total, 2)
        profit_day = sum_period(1)
        profit_week = sum_period(7)
        profit_month = sum_period(30)
        growth_series = [{"date": g["date"], "value": round(float(g.get("value", 0)), 4), "profit": round(float(g.get("profit", 0)), 2)} for g in flat_gains]
        is_cents = account_info.get("cents", False)
        div = 100.0 if is_cents else 1.0
        usd_brl = await get_usd_brl_rate()
        brl_rate = usd_brl["rate"]
        def to_usd(v):
            if v is None:
                return None
            return round(float(v) / div, 2)
        def to_brl(v):
            usd = to_usd(v)
            if usd is None:
                return None
            return round(usd * brl_rate, 2)
        if is_cents:
            growth_series = [{**g, "profit": round(g["profit"] / div, 2)} for g in growth_series]
        monthly_gain_series = await get_monthly_gain_series(session, account_id, flat_gains, div)
        history = [{**trade, "openTimeLocal": myfxbook_datetime_to_local(trade.get("openTime")), "closeTimeLocal": myfxbook_datetime_to_local(trade.get("closeTime"))} for trade in history_data.get("history", [])[:50]]
        return {
            "slug": slug,
            "name": account_info["name"],
            "description": account_info["description"],
            "pair": account_info["pair"],
            "cents": is_cents,
            "usd_brl_rate": brl_rate,
            "exchange_rate_source": usd_brl["source"],
            "exchange_rate_updated_at": usd_brl.get("updated_at"),
            "balance": to_usd(account_detail.get("balance")),
            "balance_brl": to_brl(account_detail.get("balance")),
            "equity": to_usd(account_detail.get("equity")),
            "equity_brl": to_brl(account_detail.get("equity")),
            "gain": account_detail.get("gain"),
            "drawdown": account_detail.get("drawdown"),
            "profit": to_usd(account_detail.get("profit")),
            "profit_brl": to_brl(account_detail.get("profit")),
            "demo": account_detail.get("demo", False),
            "lastUpdateDate": account_detail.get("lastUpdateDate"),
            "profit_day": round(profit_day / div, 2),
            "profit_day_brl": round((profit_day / div) * brl_rate, 2),
            "profit_week": round(profit_week / div, 2),
            "profit_week_brl": round((profit_week / div) * brl_rate, 2),
            "profit_month": round(profit_month / div, 2),
            "profit_month_brl": round((profit_month / div) * brl_rate, 2),
            "profit_total": to_usd(account_detail.get("profit")),
            "profit_total_brl": to_brl(account_detail.get("profit")),
            "growth_series": growth_series,
            "monthly_gain_series": monthly_gain_series,
            "open_trades": open_trades_data.get("openTrades", []),
            "history": history,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Erro ao buscar dados: {str(e)}")


def send_email(to: str, subject: str, html_body: str):
    if not SMTP_USER or not SMTP_PASS:
        print("SMTP nao configurado, email nao enviado.")
        return
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_USER
    msg["To"] = to
    msg.attach(MIMEText(html_body, "html"))
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
        s.starttls()
        s.login(SMTP_USER, SMTP_PASS)
        s.sendmail(SMTP_USER, to, msg.as_string())


@app.post("/notify/{slug}")
async def trigger_notify(slug: str, background_tasks: BackgroundTasks):
    if slug not in ACCOUNTS_MAP:
        raise HTTPException(404, "Conta nao encontrada")
    data = await get_account_data(slug)
    html = f"""
    <div style='font-family:Arial,sans-serif;max-width:520px;margin:auto;padding:24px;border:1px solid #e0e0e0;border-radius:8px;'>
      <h2 style='color:#1D9E75;margin-bottom:4px;'>{data['name']}</h2>
      <p style='color:#888;font-size:13px;margin-top:0;'>Resultado diario - {datetime.utcnow().strftime('%d/%m/%Y')}</p>
      <p>Resultado do dia: ${data['profit_day']}</p>
      <p>Resultado semanal: ${data['profit_week']}</p>
      <p>Resultado mensal: ${data['profit_month']}</p>
      <p>Saldo atual: ${data['balance']:,.2f}</p>
    </div>
    """
    notify_emails = [email for client in CLIENTS_MAP.values() if slug in client["accounts"] for email in client.get("notify_emails", [])]
    for email in notify_emails:
        background_tasks.add_task(send_email, email, f"[{data['name']}] Resultado {datetime.utcnow().strftime('%d/%m/%Y')}", html)
    return {"sent_to": notify_emails}


@app.get("/cliente")
async def serve_client_without_slug():
    index_file = FRONTEND_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(404, "Frontend nao encontrado")
    return FileResponse(index_file)


@app.get("/{full_path:path}")
async def serve_frontend(full_path: str):
    index_file = FRONTEND_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(404, "Frontend nao encontrado")
    return FileResponse(index_file)

