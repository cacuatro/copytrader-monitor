from fastapi import FastAPI, HTTPException, BackgroundTasks, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Request
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
from zoneinfo import ZoneInfo
from typing import Optional
import smtplib
import threading
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
try:
    import psycopg
    from psycopg.types.json import Jsonb
except Exception:
    psycopg = None
    Jsonb = None

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
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
DATABASE_URL = os.getenv("DATABASE_URL", "")
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
ACCESS_LOG_FILE = DATA_DIR / "access_logs.json"
NOTICE_FILE = DATA_DIR / "client_notices.json"
CLIENT_CONFIG_FILE = DATA_DIR / "client_config.json"
AUDIT_LOG_FILE = DATA_DIR / "audit_logs.json"
SUPPORT_WHATSAPP = os.getenv("SUPPORT_WHATSAPP", "")

ACCOUNTS_MAP = {
    "gold-dragon": {"id": 11709872, "name": "Gold Dragon", "description": "Estrategia em XAUUSD", "pair": "XAUUSD", "cents": True},
    "gold-long-ictrading": {"id": 11823718, "name": "Gold Long IC Trading", "description": "Estrategia em XAUUSD", "pair": "XAUUSD", "cents": True},
    "gold-long": {"id": 11709870, "name": "Gold Long", "description": "Estrategia em XAUUSD", "pair": "XAUUSD", "cents": True},
    "rayla-conta-02": {"id": 12056626, "name": "Rayla Estrategia MT5", "description": "Estrategia em XAUUSD", "pair": "XAUUSD", "cents": True},
    "rayla-estrategias-mt4": {"id": 12038682, "name": "Portfolio Estrategias MT4", "description": "Estrategia em XAUUSD", "pair": "XAUUSD", "cents": True},
}

CLIENTS_MAP = {
    "cliente-teste": {
        "name": "Cliente Teste",
        "username": "cliente-teste",
        "password": "teste123",
        "notice": "Bem-vindo ao painel. Os resultados sao atualizados conforme disponibilidade do MyFXBook.",
        "notify_emails": [],
        "accounts": ["gold-dragon", "gold-long-ictrading", "gold-long"],
    },
    "rayla": {
        "name": "Rayla",
        "username": "rayla",
        "password": "Rayla@2026",
        "notice": "Acompanhe aqui os resultados consolidados das estrategias vinculadas ao seu acesso.",
        "notify_emails": [],
        "accounts": ["rayla-conta-02", "rayla-estrategias-mt4"],
    },
}

_session_cache = {"session": None, "expires": None}
_data_cache = {}
CACHE_TTL_MINUTES = 15
_access_log_lock = threading.Lock()
_db_lock = threading.Lock()
_db_initialized = False
LOCAL_TZ = ZoneInfo("America/Sao_Paulo")


def local_now() -> datetime:
    return datetime.now(LOCAL_TZ)


def local_timestamp() -> dict:
    now = local_now()
    return {
        "at": now.strftime("%d/%m/%Y %H:%M"),
        "ts": now.isoformat(timespec="microseconds"),
        "timezone": "America/Sao_Paulo",
    }


def db_enabled() -> bool:
    return bool(DATABASE_URL)


def db_conninfo() -> str:
    if "sslmode=" in DATABASE_URL or "localhost" in DATABASE_URL or "127.0.0.1" in DATABASE_URL:
        return DATABASE_URL
    separator = "&" if "?" in DATABASE_URL else "?"
    return f"{DATABASE_URL}{separator}sslmode=require"


def db_connect():
    if psycopg is None:
        raise RuntimeError("psycopg nao esta instalado. Rode pip install -r backend/requirements.txt")
    return psycopg.connect(db_conninfo(), connect_timeout=8)


def ensure_db() -> None:
    global _db_initialized
    if not db_enabled() or _db_initialized:
        return
    with _db_lock:
        if _db_initialized:
            return
        with db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS copytrader_state (
                        key TEXT PRIMARY KEY,
                        value JSONB NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS copytrader_access_logs (
                        id BIGSERIAL PRIMARY KEY,
                        data JSONB NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS copytrader_audit_logs (
                        id BIGSERIAL PRIMARY KEY,
                        data JSONB NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute("CREATE INDEX IF NOT EXISTS idx_copytrader_access_logs_created ON copytrader_access_logs (created_at DESC)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_copytrader_audit_logs_created ON copytrader_audit_logs (created_at DESC)")
            conn.commit()
        _db_initialized = True


def db_read_state(key: str, default):
    ensure_db()
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT value FROM copytrader_state WHERE key = %s", (key,))
            row = cur.fetchone()
    if not row:
        return default
    value = row[0]
    return value if isinstance(value, type(default)) else default


def db_write_state(key: str, data) -> None:
    ensure_db()
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO copytrader_state (key, value, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (key)
                DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
                """,
                (key, Jsonb(data)),
            )
        conn.commit()


def read_json_file(path: Path, default):
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, type(default)) else default
    except Exception:
        return default


def write_json_file(path: Path, data) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def read_client_config() -> dict:
    if db_enabled():
        return db_read_state("client_config", {})
    return read_json_file(CLIENT_CONFIG_FILE, {})


def write_client_config(config: dict) -> None:
    if db_enabled():
        db_write_state("client_config", config)
        return
    write_json_file(CLIENT_CONFIG_FILE, config)


def clients_map() -> dict:
    overrides = read_client_config()
    merged = {slug: dict(info) for slug, info in CLIENTS_MAP.items()}
    for slug, data in overrides.items():
        if slug not in merged or not isinstance(data, dict):
            continue
        merged[slug].update({k: v for k, v in data.items() if v is not None})
    return merged


def get_client_info(slug: str) -> dict:
    clients = clients_map()
    if slug not in clients:
        raise HTTPException(404, "Cliente nao encontrado")
    return clients[slug]


def update_client_config(slug: str, updates: dict) -> dict:
    if slug not in CLIENTS_MAP:
        raise HTTPException(404, "Cliente nao encontrado")
    config = read_client_config()
    current = config.get(slug, {}) if isinstance(config.get(slug, {}), dict) else {}
    current.update({k: v for k, v in updates.items() if v is not None})
    config[slug] = current
    write_client_config(config)
    return clients_map()[slug]


def audit_log(actor: str, action: str, target: str, details: dict | None = None) -> None:
    entry = {**local_timestamp(), "actor": actor, "action": action, "target": target, "details": details or {}}
    if db_enabled():
        ensure_db()
        with db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO copytrader_audit_logs (data) VALUES (%s)", (Jsonb(entry),))
            conn.commit()
        return
    logs = read_json_file(AUDIT_LOG_FILE, [])
    logs.append(entry)
    write_json_file(AUDIT_LOG_FILE, logs[-1000:])


def read_audit_logs(limit: int = 200) -> list:
    if db_enabled():
        ensure_db()
        with db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT data FROM copytrader_audit_logs ORDER BY id DESC LIMIT %s", (limit,))
                return [row[0] for row in cur.fetchall()]
    return list(reversed(read_json_file(AUDIT_LOG_FILE, [])[-limit:]))


def make_token(subject: str, role: str = "client") -> str:
    expires = int((datetime.utcnow() + timedelta(hours=TOKEN_TTL_HOURS)).timestamp())
    payload = f"{subject}:{role}:{expires}"
    signature = hmac.new(AUTH_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}:{signature}".encode()).decode()


def verify_token(token: str) -> dict:
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        parts = raw.rsplit(":", 3)
        if len(parts) == 4:
            subject, role, expires, signature = parts
        else:
            subject, expires, signature = raw.rsplit(":", 2)
            role = "client"
    except Exception:
        raise HTTPException(401, "Token invalido")
    payload = f"{subject}:{role}:{expires}"
    expected = hmac.new(AUTH_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(401, "Token invalido")
    if int(expires) < int(datetime.utcnow().timestamp()):
        raise HTTPException(401, "Sessao expirada")
    if role == "client" and subject not in clients_map():
        raise HTTPException(401, "Cliente invalido")
    if role == "admin" and subject != "admin":
        raise HTTPException(401, "Administrador invalido")
    return {"subject": subject, "role": role}


def require_client_auth(slug: str, authorization: Optional[str]) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Login necessario")
    token_data = verify_token(authorization.replace("Bearer ", "", 1))
    if token_data["role"] != "client" or token_data["subject"] != slug:
        raise HTTPException(403, "Acesso negado")


def require_admin_auth(authorization: Optional[str]) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Login necessario")
    token_data = verify_token(authorization.replace("Bearer ", "", 1))
    if token_data["role"] != "admin":
        raise HTTPException(403, "Acesso negado")


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


def read_access_logs(limit: int = 200) -> list:
    if db_enabled():
        ensure_db()
        with db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT data FROM copytrader_access_logs ORDER BY id DESC LIMIT %s", (limit,))
                return [row[0] for row in cur.fetchall()]
    if not ACCESS_LOG_FILE.exists():
        return []
    try:
        with ACCESS_LOG_FILE.open("r", encoding="utf-8") as f:
            logs = json.load(f)
    except Exception:
        return []
    return list(reversed(logs[-limit:]))


def write_access_log(event: str, client_slug: str, request: Request, success: bool = True, username: str = "") -> None:
    stamp = local_timestamp()
    entry = {
        **stamp,
        "event": event,
        "client_slug": client_slug,
        "client_name": clients_map().get(client_slug, {}).get("name", client_slug),
        "username": username,
        "success": success,
        "ip": client_ip(request),
        "user_agent": request.headers.get("user-agent", "")[:180],
    }
    if db_enabled():
        ensure_db()
        with db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO copytrader_access_logs (data) VALUES (%s)", (Jsonb(entry),))
            conn.commit()
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with _access_log_lock:
        logs = []
        if ACCESS_LOG_FILE.exists():
            try:
                with ACCESS_LOG_FILE.open("r", encoding="utf-8") as f:
                    logs = json.load(f)
            except Exception:
                logs = []
        logs.append(entry)
        logs = logs[-1000:]
        with ACCESS_LOG_FILE.open("w", encoding="utf-8") as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)


def recent_client_access(client_slug: str) -> Optional[dict]:
    for log in read_access_logs(1000):
        if log.get("client_slug") == client_slug and log.get("success") and log.get("event") in {"login", "panel"}:
            return log
    return None


def notice_entry(text: str, scope: str, client_slug: str = "") -> dict:
    stamp = local_timestamp()
    return {
        "id": hashlib.sha1(f"{scope}:{client_slug}:{stamp['ts']}:{text}".encode()).hexdigest()[:12],
        **stamp,
        "scope": scope,
        "client_slug": client_slug,
        "text": text[:1000],
    }


def read_notice_store() -> dict:
    if db_enabled():
        return db_read_state("notice_store", {"global": [], "clients": {}})
    if not NOTICE_FILE.exists():
        return {"global": [], "clients": {}}
    try:
        with NOTICE_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {"global": [], "clients": {}}
    if not isinstance(data, dict):
        return {"global": [], "clients": {}}
    if "global" in data or "clients" in data:
        return {
            "global": data.get("global", []) if isinstance(data.get("global", []), list) else [],
            "clients": data.get("clients", {}) if isinstance(data.get("clients", {}), dict) else {},
        }
    clients = {}
    for slug, text in data.items():
        if isinstance(text, str) and text.strip():
            clients[slug] = [notice_entry(text.strip(), "client", slug)]
    return {"global": [], "clients": clients}


def write_notice_store(store: dict) -> None:
    if db_enabled():
        db_write_state("notice_store", store)
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with NOTICE_FILE.open("w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)


def append_notice(scope: str, text: str, client_slug: str = "") -> dict:
    text = text.strip()[:1000]
    if not text:
        raise HTTPException(400, "Comunicado vazio")
    store = read_notice_store()
    entry = notice_entry(text, scope, client_slug)
    if scope == "global":
        store["global"] = [entry] + list(store.get("global", []))
        store["global"] = store["global"][:50]
    else:
        clients = store.setdefault("clients", {})
        clients[client_slug] = [entry] + list(clients.get(client_slug, []))
        clients[client_slug] = clients[client_slug][:50]
    write_notice_store(store)
    return entry


def notice_history(client_slug: str, limit: int = 10) -> list:
    store = read_notice_store()
    entries = []
    for entry in store.get("global", []):
        if isinstance(entry, dict):
            entries.append({**entry, "scope_label": "Todos"})
    for entry in store.get("clients", {}).get(client_slug, []):
        if isinstance(entry, dict):
            entries.append({**entry, "scope_label": "Cliente"})
    entries.sort(key=lambda item: item.get("ts") or item.get("at", ""), reverse=True)
    return entries[:limit]


def client_notice(client_slug: str) -> str:
    history = notice_history(client_slug, 1)
    if history:
        return str(history[0].get("text", ""))
    return clients_map().get(client_slug, {}).get("notice", "")


def myfxbook_datetime_to_local(value: Optional[str]) -> Optional[str]:
    if not value:
        return value
    try:
        dt = datetime.strptime(value, "%m/%d/%Y %H:%M") - timedelta(hours=3)
        return dt.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return value


def parse_myfxbook_update(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%m/%d/%Y %H:%M").replace(tzinfo=LOCAL_TZ)
    except Exception:
        return None


def health_from_clients(clients: list) -> dict:
    accounts = []
    stale = []
    now = local_now()
    for client in clients:
        data = client.get("data") or {}
        for acc in data.get("accounts", []):
            if acc.get("error"):
                stale.append({"client": client.get("name"), "strategy": acc.get("name"), "reason": "erro"})
                continue
            updated = parse_myfxbook_update(acc.get("myfxbook_updated_at") or acc.get("lastUpdateDate"))
            item = {"client": client.get("name"), "strategy": acc.get("name"), "updated_at": acc.get("myfxbook_updated_at") or acc.get("lastUpdateDate")}
            accounts.append(item)
            if not updated or (now - updated) > timedelta(hours=12):
                stale.append(item)
    return {"accounts": len(accounts), "stale": len(stale), "ok": max(0, len(accounts) - len(stale)), "stale_accounts": stale[:20]}


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
        profit_value = round(profit / div, 2)
        if profit_value != 0 or (gain_value is not None and gain_value != 0):
            rows.append({"month": start.strftime("%Y-%m"), "label": start.strftime("%m/%Y"), "gain": gain_value, "profit": profit_value})
    return rows


async def get_period_gain_values(session: str, account_id: int) -> dict:
    today = datetime.utcnow().date()
    ranges = {
        "gain_day": (today, today),
        "gain_week": (today - timedelta(days=7), today),
        "gain_month": (today - timedelta(days=30), today),
    }
    tasks = {
        key: cached_get(
            "https://www.myfxbook.com/api/get-gain.json",
            {"session": session, "id": account_id, "start": start.strftime("%Y-%m-%d"), "end": end.strftime("%Y-%m-%d")},
        )
        for key, (start, end) in ranges.items()
    }
    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    values = {}
    for key, result in zip(tasks.keys(), results):
        try:
            values[key] = round(float(result.get("value", 0)), 2) if not isinstance(result, Exception) else None
        except Exception:
            values[key] = None
    return values


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
        r.raise_for_status()
        quote = r.json().get("USDBRL", {})
        rate = float(quote.get("bid") or quote.get("ask"))
        result = {"rate": round(rate, 4), "source": "AwesomeAPI USD-BRL", "updated_at": quote.get("create_date")}
    except Exception:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get("https://open.er-api.com/v6/latest/USD")
            r.raise_for_status()
            data = r.json()
            result = {
                "rate": round(float(data["rates"]["BRL"]), 4),
                "source": "Open Exchange Rates USD-BRL",
                "updated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
            }
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


@app.get("/api/exchange-rate")
async def exchange_rate_status():
    return await get_usd_brl_rate()


@app.get("/accounts")
async def list_accounts():
    return [{"slug": slug, "name": info["name"], "description": info["description"], "pair": info["pair"]} for slug, info in ACCOUNTS_MAP.items()]


@app.post("/login")
async def login(credentials: dict, request: Request):
    username = str(credentials.get("username", "")).strip()
    password = str(credentials.get("password", ""))
    requested_slug = str(credentials.get("client_slug", "")).strip()
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        return {"token": make_token("admin", "admin"), "role": "admin", "name": "Administrador", "expires_in_hours": TOKEN_TTL_HOURS}
    all_clients = clients_map()
    client_slug = next((slug for slug, info in all_clients.items() if info.get("username") == username and info.get("password") == password), None)
    if not client_slug:
        write_access_log("login", requested_slug or "desconhecido", request, success=False, username=username)
        raise HTTPException(401, "Usuario ou senha invalidos")
    if requested_slug and requested_slug != client_slug:
        write_access_log("login", requested_slug, request, success=False, username=username)
        raise HTTPException(403, "Usuario nao autorizado para este cliente")
    write_access_log("login", client_slug, request, username=username)
    return {"token": make_token(client_slug), "role": "client", "client_slug": client_slug, "name": all_clients[client_slug]["name"], "expires_in_hours": TOKEN_TTL_HOURS}


async def build_client_data(slug: str) -> dict:
    client_info = get_client_info(slug)
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
    total_withdrawals_commission = sum(float(a.get("withdrawals_commission") or 0) for a in ok)
    total_open_trades = sum(int(a.get("open_trades_count") or 0) for a in ok)
    total_open_trades_profit = sum(float(a.get("open_trades_profit") or 0) for a in ok)
    def consolidated_gain(profit: float) -> float:
        if not total_balance:
            return 0.0
        return round((profit / total_balance) * 100, 2)
    total_gain_day = consolidated_gain(total_profit_day)
    total_gain_week = consolidated_gain(total_profit_week)
    total_gain_month = consolidated_gain(total_profit_month)
    total_gain_total = consolidated_gain(total_profit_total)
    usd_brl = await get_usd_brl_rate()
    brl_rate = usd_brl["rate"]
    manual_withdrawals = round(float(client_info.get("manual_withdrawals") or 0), 2)
    manual_commission = round(float(client_info.get("manual_commission") or 0), 2)
    return {
        "slug": slug,
        "name": client_info["name"],
        "username": client_info.get("username", ""),
        "support_whatsapp": client_info.get("support_whatsapp") or SUPPORT_WHATSAPP,
        "financial_notes": client_info.get("financial_notes", ""),
        "manual_withdrawals": manual_withdrawals,
        "manual_commission": manual_commission,
        "manual_withdrawals_brl": round(manual_withdrawals * brl_rate, 2),
        "manual_commission_brl": round(manual_commission * brl_rate, 2),
        "notice": client_notice(slug),
        "notice_history": notice_history(slug),
        "accounts": results,
        "usd_brl_rate": brl_rate,
        "exchange_rate_source": usd_brl["source"],
        "exchange_rate_updated_at": usd_brl.get("updated_at"),
        "total_balance": round(total_balance, 2),
        "total_balance_brl": round(total_balance * brl_rate, 2),
        "total_withdrawals_commission": round(total_withdrawals_commission, 2),
        "total_withdrawals_commission_brl": round(total_withdrawals_commission * brl_rate, 2),
        "total_open_trades": total_open_trades,
        "total_open_trades_profit": round(total_open_trades_profit, 2),
        "total_open_trades_profit_brl": round(total_open_trades_profit * brl_rate, 2),
        "total_profit_day": round(total_profit_day, 2),
        "total_gain_day": total_gain_day,
        "total_profit_day_brl": round(total_profit_day * brl_rate, 2),
        "total_profit_week": round(total_profit_week, 2),
        "total_gain_week": total_gain_week,
        "total_profit_week_brl": round(total_profit_week * brl_rate, 2),
        "total_profit_month": round(total_profit_month, 2),
        "total_gain_month": total_gain_month,
        "total_profit_month_brl": round(total_profit_month * brl_rate, 2),
        "total_profit_total": round(total_profit_total, 2),
        "total_gain_total": total_gain_total,
        "total_profit_total_brl": round(total_profit_total * brl_rate, 2),
    }


@app.get("/cliente/{slug}")
async def get_client(slug: str, request: Request, authorization: Optional[str] = Header(None)):
    require_client_auth(slug, authorization)
    write_access_log("panel", slug, request)
    return await build_client_data(slug)


@app.get("/admin/summary")
async def admin_summary(authorization: Optional[str] = Header(None)):
    require_admin_auth(authorization)
    clients = []
    for slug, info in clients_map().items():
        try:
            data = await build_client_data(slug)
            last_access = recent_client_access(slug)
            clients.append({
                "slug": slug,
                "name": info["name"],
                "username": info.get("username"),
                "notice": client_notice(slug),
                "last_access": last_access,
                "data": data,
            })
        except Exception as e:
            clients.append({"slug": slug, "name": info["name"], "error": str(e), "last_access": recent_client_access(slug)})
    return {
        "clients": clients,
        "access_logs": read_access_logs(200),
        "audit_logs": read_audit_logs(200),
        "global_notices": read_notice_store().get("global", [])[:10],
        "health": health_from_clients(clients),
    }


@app.post("/cliente/{slug}/profile")
async def update_profile(slug: str, payload: dict, authorization: Optional[str] = Header(None)):
    require_client_auth(slug, authorization)
    info = get_client_info(slug)
    updates = {}
    name = str(payload.get("name", "")).strip()
    username = str(payload.get("username", "")).strip()
    current_password = str(payload.get("current_password", ""))
    new_password = str(payload.get("new_password", ""))
    if name:
        updates["name"] = name
    if username:
        updates["username"] = username
    if new_password:
        if current_password != info.get("password"):
            raise HTTPException(403, "Senha atual invalida")
        updates["password"] = new_password
    if not updates:
        return {"updated": False}
    updated = update_client_config(slug, updates)
    audit_log(slug, "profile_update", slug, {"fields": list(updates.keys())})
    return {"updated": True, "name": updated.get("name"), "username": updated.get("username")}


@app.post("/admin/client/{slug}")
async def update_admin_client(slug: str, payload: dict, authorization: Optional[str] = Header(None)):
    require_admin_auth(authorization)
    if slug not in clients_map():
        raise HTTPException(404, "Cliente nao encontrado")
    allowed = {
        "name": str(payload.get("name", "")).strip() or None,
        "username": str(payload.get("username", "")).strip() or None,
        "password": str(payload.get("password", "")).strip() or None,
        "support_whatsapp": str(payload.get("support_whatsapp", "")).strip(),
        "financial_notes": str(payload.get("financial_notes", "")).strip(),
    }
    for money_field in ("manual_withdrawals", "manual_commission"):
        if payload.get(money_field) not in (None, ""):
            try:
                allowed[money_field] = round(float(payload.get(money_field)), 2)
            except Exception:
                raise HTTPException(400, f"{money_field} invalido")
    updated = update_client_config(slug, allowed)
    audit_log("admin", "client_update", slug, {"fields": [k for k, v in allowed.items() if v is not None]})
    return {"slug": slug, "client": {k: updated.get(k) for k in ("name", "username", "support_whatsapp", "financial_notes", "manual_withdrawals", "manual_commission")}}


@app.post("/admin/notice/{slug}")
async def update_client_notice(slug: str, payload: dict, authorization: Optional[str] = Header(None)):
    require_admin_auth(authorization)
    if slug not in clients_map():
        raise HTTPException(404, "Cliente nao encontrado")
    entry = append_notice("client", str(payload.get("notice", "")), slug)
    audit_log("admin", "client_notice", slug, {"notice_id": entry.get("id")})
    return {"slug": slug, "notice": entry}


@app.post("/admin/notice-all")
async def update_global_notice(payload: dict, authorization: Optional[str] = Header(None)):
    require_admin_auth(authorization)
    entry = append_notice("global", str(payload.get("notice", "")))
    audit_log("admin", "global_notice", "all", {"notice_id": entry.get("id")})
    return {"notice": entry}


@app.get("/account/{slug}")
async def get_account(slug: str, authorization: Optional[str] = Header(None)):
    allowed_client = next((client_slug for client_slug, info in clients_map().items() if slug in info["accounts"]), None)
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
        period_gains = await get_period_gain_values(session, account_id)
        def normalize_trade_money(trade: dict) -> dict:
            converted = dict(trade)
            for field in ("profit", "commission", "swap"):
                if converted.get(field) is None:
                    continue
                try:
                    converted[field] = round(float(converted[field]) / div, 2)
                except Exception:
                    pass
            return converted

        open_trades = [normalize_trade_money(trade) for trade in open_trades_data.get("openTrades", [])]
        open_trades_profit = round(sum(float(trade.get("profit") or 0) for trade in open_trades), 2)
        withdrawals = to_usd(account_detail.get("withdrawals")) or 0
        commission = to_usd(account_detail.get("commission")) or 0
        withdrawals_commission = round(withdrawals + commission, 2)
        history = [
            {
                **normalize_trade_money(trade),
                "openTimeLocal": myfxbook_datetime_to_local(trade.get("openTime")),
                "closeTimeLocal": myfxbook_datetime_to_local(trade.get("closeTime")),
            }
            for trade in history_data.get("history", [])[:30]
        ]
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
            "withdrawals": withdrawals,
            "withdrawals_brl": round(withdrawals * brl_rate, 2),
            "commission": commission,
            "commission_brl": round(commission * brl_rate, 2),
            "withdrawals_commission": withdrawals_commission,
            "withdrawals_commission_brl": round(withdrawals_commission * brl_rate, 2),
            "demo": account_detail.get("demo", False),
            "lastUpdateDate": account_detail.get("lastUpdateDate"),
            "myfxbook_updated_at": account_detail.get("lastUpdateDate"),
            "profit_day": round(profit_day / div, 2),
            "gain_day": period_gains.get("gain_day"),
            "profit_day_brl": round((profit_day / div) * brl_rate, 2),
            "profit_week": round(profit_week / div, 2),
            "gain_week": period_gains.get("gain_week"),
            "profit_week_brl": round((profit_week / div) * brl_rate, 2),
            "profit_month": round(profit_month / div, 2),
            "gain_month": period_gains.get("gain_month"),
            "profit_month_brl": round((profit_month / div) * brl_rate, 2),
            "profit_total": to_usd(account_detail.get("profit")),
            "profit_total_brl": to_brl(account_detail.get("profit")),
            "growth_series": growth_series,
            "monthly_gain_series": monthly_gain_series,
            "open_trades_count": len(open_trades),
            "open_trades_profit": open_trades_profit,
            "open_trades_profit_brl": round(open_trades_profit * brl_rate, 2),
            "open_trades": open_trades,
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
      <p>Resultado ultimos 30 dias: ${data['profit_month']}</p>
      <p>Saldo atual: ${data['balance']:,.2f}</p>
    </div>
    """
    notify_emails = [email for client in clients_map().values() if slug in client["accounts"] for email in client.get("notify_emails", [])]
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

