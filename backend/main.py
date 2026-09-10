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
import time
import copy
from email.utils import parsedate_to_datetime
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
COMMISSION_RATE = float(os.getenv("COMMISSION_RATE", "0.30"))
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
DATABASE_URL = os.getenv("DATABASE_URL", "")
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
ACCESS_LOG_FILE = DATA_DIR / "access_logs.json"
NOTICE_FILE = DATA_DIR / "client_notices.json"
CLIENT_CONFIG_FILE = DATA_DIR / "client_config.json"
AUDIT_LOG_FILE = DATA_DIR / "audit_logs.json"
STRATEGY_ADJUSTMENTS_FILE = DATA_DIR / "strategy_adjustments.json"
SUPPORT_WHATSAPP = os.getenv("SUPPORT_WHATSAPP", "")

ACCOUNTS_MAP = {
    "gold-dragon": {"id": 11709872, "name": "Gold Dragon", "description": "Estrategia em XAUUSD", "pair": "XAUUSD", "cents": True},
    "gold-long-ictrading": {"id": 11823718, "name": "Gold Long IC Trading", "description": "Estrategia em XAUUSD", "pair": "XAUUSD", "cents": True},
    "gold-long": {"id": 11709870, "name": "Gold Long", "description": "Estrategia em XAUUSD", "pair": "XAUUSD", "cents": True},
    "rayla-conta-02": {"id": 12097380, "name": "MT5", "description": "Estrategia em XAUUSD", "pair": "XAUUSD", "cents": True},
    "rayla-estrategias-mt4": {"id": 12038682, "name": "Portfolio Estrategias MT4", "description": "Estrategia em XAUUSD", "pair": "XAUUSD", "cents": True},
    "bresolin-mt4": {"id": 12079050, "name": "Portfolio MT4", "description": "Estrategia em XAUUSD", "pair": "XAUUSD", "cents": True},
    "bresolin-mt5": {"id": 12079052, "name": "Portfolio MT5", "description": "Estrategia em XAUUSD", "pair": "XAUUSD", "cents": True},
    "gabrielly-gold-reaper": {"id": 12110642, "name": "Gold Reaper", "description": "Estrategia em XAUUSD", "pair": "XAUUSD", "cents": True},
    "gabrielly-portfolio-invictus": {"id": 12110644, "name": "Portfolio + Invictus", "description": "Estrategia em XAUUSD", "pair": "XAUUSD", "cents": True},
    "gabrielly-gold-ia": {"id": 12110646, "name": "Gold IA", "description": "Estrategia em XAUUSD", "pair": "XAUUSD", "cents": True},
    "gabrielly-goldest": {"id": 12110648, "name": "Goldest", "description": "Estrategia em XAUUSD", "pair": "XAUUSD", "cents": True},
    "gabrielly-gold-dragon": {"id": 12110650, "name": "Gold Dragon", "description": "Estrategia em XAUUSD", "pair": "XAUUSD", "cents": True},
    "jocelia-portfolio-mt4": {"id": 12112614, "name": "Portfolio MT4", "description": "Estrategia em XAUUSD", "pair": "XAUUSD", "cents": True},
    "jocelia-goldest": {"id": 12112615, "name": "Goldest", "description": "Estrategia em XAUUSD", "pair": "XAUUSD", "cents": True},
    "jocelia-gold-dragon": {"id": 12112618, "name": "Gold Dragon", "description": "Estrategia em XAUUSD", "pair": "XAUUSD", "cents": True},
    "samira-mt5": {"id": 12185469, "name": "MT5", "description": "Estrategia em XAUUSD", "pair": "XAUUSD", "cents": True},
    "samira-mt4": {"id": 12185472, "name": "MT4", "description": "Estrategia em XAUUSD", "pair": "XAUUSD", "cents": True},
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
    "bresolin": {
        "name": "Bresolin",
        "username": "bresolin",
        "password": "Bresolin@2026",
        "notice": "Acompanhe aqui os resultados consolidados das estrategias vinculadas ao seu acesso.",
        "notify_emails": [],
        "accounts": ["bresolin-mt4"],
    },
    "gabrielly": {
        "name": "Gabrielly",
        "username": "gabrielly",
        "password": "Gabrielly@2026",
        "notice": "Acompanhe aqui os resultados consolidados das estrategias vinculadas ao seu acesso.",
        "notify_emails": [],
        "accounts": ["gabrielly-gold-reaper", "gabrielly-portfolio-invictus", "gabrielly-gold-ia", "gabrielly-goldest", "gabrielly-gold-dragon"],
    },
    "jocelia": {
        "name": "Jocelia",
        "username": "jocelia",
        "password": "Jocelia@2026",
        "notice": "Acompanhe aqui os resultados consolidados das estrategias vinculadas ao seu acesso.",
        "notify_emails": [],
        "accounts": ["jocelia-portfolio-mt4", "jocelia-goldest", "jocelia-gold-dragon"],
    },
    "samira": {
        "name": "Samira",
        "username": "samira",
        "password": "Samira@2026",
        "notice": "Acompanhe aqui os resultados consolidados das estrategias vinculadas ao seu acesso.",
        "notify_emails": [],
        "accounts": ["samira-mt5", "samira-mt4"],
    },
}

_session_cache = {"session": None, "expires": None}
_data_cache = {}
_account_snapshots = {}
_account_locks = {}
_account_retry_after = {}
_client_config_last_good = None
_login_lock = asyncio.Lock()
_login_state = {"failed_until": None, "last_error": ""}
CACHE_TTL_MINUTES = 15
LOGIN_COOLDOWN_MINUTES = 15
MYFXBOOK_REQUEST_INTERVAL_SECONDS = 1.5  # Precaucao local, nao limite oficial.
_myfxbook_request_lock = asyncio.Lock()
_myfxbook_last_request = 0.0
_login_state_loaded = False
LOGIN_STATE_KEY = "myfxbook_login_state"
LOGIN_STATE_FILE = DATA_DIR / "myfxbook_login_state.json"
SESSION_STATE_KEY = "myfxbook_session"
SESSION_FILE = DATA_DIR / "myfxbook_session.json"
_access_log_lock = threading.Lock()
_db_lock = threading.Lock()
_db_initialized = False
_db_error = ""
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
    return psycopg.connect(db_conninfo(), connect_timeout=8, prepare_threshold=None)


def ensure_db() -> None:
    global _db_initialized, _db_error
    if not db_enabled() or _db_initialized:
        return
    with _db_lock:
        if _db_initialized:
            return
        try:
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
            _db_error = ""
            _db_initialized = True
        except Exception as e:
            _db_error = str(e)
            print(f"[database] Supabase indisponivel, usando JSON local: {_db_error}")
            raise


def db_read_state(key: str, default, strict: bool = False):
    try:
        ensure_db()
        with db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT value FROM copytrader_state WHERE key = %s", (key,))
                row = cur.fetchone()
    except Exception as e:
        global _db_error
        _db_error = str(e)
        if strict:
            raise HTTPException(503, "Banco de dados temporariamente indisponivel") from None
        return default
    if not row:
        return default
    value = row[0]
    return value if isinstance(value, type(default)) else default


STATE_FALLBACK_FILES = {
    SESSION_STATE_KEY: SESSION_FILE,
    LOGIN_STATE_KEY: LOGIN_STATE_FILE,
    "client_config": CLIENT_CONFIG_FILE,
    "notice_store": NOTICE_FILE,
    "strategy_adjustments": STRATEGY_ADJUSTMENTS_FILE,
}


def db_write_state(key: str, data) -> None:
    try:
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
    except Exception as e:
        global _db_error
        _db_error = str(e)
        fallback_file = STATE_FALLBACK_FILES.get(key, NOTICE_FILE)
        write_json_file(fallback_file, data)


def db_status() -> dict:
    if not db_enabled():
        return {"enabled": False, "ok": False, "mode": "json"}
    try:
        ensure_db()
        return {"enabled": True, "ok": True, "mode": "supabase"}
    except Exception as e:
        return {"enabled": True, "ok": False, "mode": "json_fallback", "error": str(e)[:220]}


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
    global _client_config_last_good
    if db_enabled():
        try:
            config = db_read_state("client_config", {}, strict=True)
            _client_config_last_good = copy.deepcopy(config)
            try:
                write_json_file(CLIENT_CONFIG_FILE, config)
            except OSError:
                pass
            return config
        except HTTPException:
            if _client_config_last_good is not None:
                return copy.deepcopy(_client_config_last_good)
            if CLIENT_CONFIG_FILE.exists():
                return read_json_file(CLIENT_CONFIG_FILE, {})
            raise
    return read_json_file(CLIENT_CONFIG_FILE, {})


def write_client_config(config: dict) -> None:
    global _client_config_last_good
    if db_enabled():
        db_write_state("client_config", config)
    else:
        write_json_file(CLIENT_CONFIG_FILE, config)
    _client_config_last_good = copy.deepcopy(config)


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
    proposed = updates.get("username")
    if proposed and any(other != slug and str(info.get("username", "")).strip().casefold() == proposed.strip().casefold() for other, info in clients_map().items()):
        raise HTTPException(409, "Este usuario ja esta em uso por outro cliente")
    config = read_client_config()
    current = config.get(slug, {}) if isinstance(config.get(slug, {}), dict) else {}
    current.update({k: v for k, v in updates.items() if v is not None})
    config[slug] = current
    write_client_config(config)
    return clients_map()[slug]


def read_strategy_adjustments() -> dict:
    if db_enabled():
        return db_read_state("strategy_adjustments", {})
    return read_json_file(STRATEGY_ADJUSTMENTS_FILE, {})


def write_strategy_adjustments(data: dict) -> None:
    if db_enabled():
        db_write_state("strategy_adjustments", data)
        return
    write_json_file(STRATEGY_ADJUSTMENTS_FILE, data)


def get_strategy_adjustment(slug: str) -> dict:
    entry = read_strategy_adjustments().get(slug)
    if not isinstance(entry, dict):
        return {"value": 0.0, "reason": "", "at": ""}
    return entry


def audit_log(actor: str, action: str, target: str, details: dict | None = None) -> None:
    entry = {**local_timestamp(), "actor": actor, "action": action, "target": target, "details": details or {}}
    if db_enabled():
        try:
            ensure_db()
            with db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("INSERT INTO copytrader_audit_logs (data) VALUES (%s)", (Jsonb(entry),))
                conn.commit()
            return
        except Exception as e:
            global _db_error
            _db_error = str(e)
    logs = read_json_file(AUDIT_LOG_FILE, [])
    logs.append(entry)
    write_json_file(AUDIT_LOG_FILE, logs[-1000:])


def read_audit_logs(limit: int = 200) -> list:
    if db_enabled():
        try:
            ensure_db()
            with db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT data FROM copytrader_audit_logs ORDER BY id DESC LIMIT %s", (limit,))
                    return [row[0] for row in cur.fetchall()]
        except Exception as e:
            global _db_error
            _db_error = str(e)
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
        try:
            ensure_db()
            with db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT data FROM copytrader_access_logs ORDER BY id DESC LIMIT %s", (limit,))
                    return [row[0] for row in cur.fetchall()]
        except Exception as e:
            global _db_error
            _db_error = str(e)
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
        try:
            ensure_db()
            with db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("INSERT INTO copytrader_access_logs (data) VALUES (%s)", (Jsonb(entry),))
                conn.commit()
            return
        except Exception as e:
            global _db_error
            _db_error = str(e)
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
    issues = []
    total = healthy = unavailable = 0
    for client in clients:
        if client.get("error"):
            issues.append({"client": client.get("name"), "reason": "Cliente indisponivel"})
            continue
        for acc in (client.get("data") or {}).get("accounts", []):
            total += 1
            updated = parse_myfxbook_update(acc.get("myfxbook_updated_at") or acc.get("lastUpdateDate"))
            reason = ""
            if acc.get("error"):
                unavailable += 1
                reason = "Sem consulta valida salva"
            elif acc.get("stale"):
                reason = "Dados salvos: " + str(acc.get("fetched_at", "sem data"))
            elif not updated or local_now() - updated > timedelta(hours=12):
                reason = "Fonte desatualizada ou sem horario informado"
            else:
                healthy += 1
            if reason:
                issues.append({"client": client.get("name"), "strategy": acc.get("name"), "reason": reason,
                               "updated_at": acc.get("myfxbook_updated_at")})
    return {"accounts": total, "ok": healthy, "stale": len(issues), "unavailable": unavailable, "stale_accounts": issues}


def month_ranges_from_year_start():
    now = local_now().replace(tzinfo=None)
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
    today = local_now().date()
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


def _load_persisted_session() -> None:
    """Carrega a sessao MyFXBook salva (sobrevive a reinicios do Render free plan)."""
    if _session_cache["session"]:
        return
    try:
        if db_enabled():
            stored = db_read_state(SESSION_STATE_KEY, {})
        else:
            stored = read_json_file(SESSION_FILE, {})
    except Exception:
        stored = {}
    if not isinstance(stored, dict) or not stored.get("session"):
        return
    try:
        expires = datetime.fromisoformat(stored["expires"])
    except Exception:
        return
    if expires > datetime.utcnow() + timedelta(minutes=5):
        _session_cache["session"] = stored["session"]
        _session_cache["expires"] = expires


def _persist_session(session: str, expires: datetime) -> None:
    payload = {"session": session, "expires": expires.isoformat()}
    try:
        if db_enabled():
            db_write_state(SESSION_STATE_KEY, payload)
        else:
            write_json_file(SESSION_FILE, payload)
    except Exception:
        pass


def _drop_session(expected_session: Optional[str] = None) -> None:
    # Uma resposta antiga nao pode invalidar uma sessao ja renovada.
    if expected_session is not None and _session_cache["session"] != expected_session:
        return
    _session_cache["session"] = None
    _session_cache["expires"] = None
    try:
        if db_enabled():
            db_write_state(SESSION_STATE_KEY, {})
        else:
            write_json_file(SESSION_FILE, {})
    except Exception:
        pass


def _load_login_state() -> None:
    global _login_state_loaded
    if _login_state_loaded:
        return
    _login_state_loaded = True
    try:
        stored = db_read_state(LOGIN_STATE_KEY, {}) if db_enabled() else {}
        if not stored:
            stored = read_json_file(LOGIN_STATE_FILE, {})
        until = datetime.fromisoformat(stored["failed_until"])
        if until > datetime.utcnow():
            _login_state.update(failed_until=until, last_error=str(stored.get("last_error", "Falha anterior")))
    except (KeyError, ValueError, TypeError, OSError):
        pass


def _save_login_state() -> None:
    until = _login_state["failed_until"]
    payload = {"failed_until": until.isoformat() if until else None,
               "last_error": _login_state["last_error"]}
    try:
        if db_enabled():
            db_write_state(LOGIN_STATE_KEY, payload)
        else:
            write_json_file(LOGIN_STATE_FILE, payload)
    except Exception:
        pass


def _pause_myfxbook(reason: str, seconds: float = LOGIN_COOLDOWN_MINUTES * 60) -> None:
    until = datetime.utcnow() + timedelta(seconds=seconds)
    if not _login_state["failed_until"] or until > _login_state["failed_until"]:
        _login_state.update(failed_until=until, last_error=reason)
        _save_login_state()


def _check_myfxbook_pause() -> None:
    _load_login_state()
    until = _login_state["failed_until"]
    if until and until > datetime.utcnow():
        wait_s = max(1, int((until - datetime.utcnow()).total_seconds()))
        raise HTTPException(503, f"Consultas MyFXBook pausadas pelo monitor por mais {wait_s}s. Motivo: {_login_state['last_error']}")


async def _myfxbook_request(url: str, params: dict, cache_key: Optional[str] = None) -> dict:
    global _myfxbook_last_request
    async with _myfxbook_request_lock:
        # Pedidos iguais que aguardaram na fila aproveitam a primeira resposta.
        if cache_key in _data_cache and _data_cache[cache_key]["expires"] > datetime.utcnow():
            return _data_cache[cache_key]["data"]
        _check_myfxbook_pause()
        delay = MYFXBOOK_REQUEST_INTERVAL_SECONDS - (time.monotonic() - _myfxbook_last_request)
        if delay > 0:
            await asyncio.sleep(delay)
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(url, params=params)
        except httpx.RequestError as exc:
            raise HTTPException(502, f"Falha de comunicacao MyFXBook ({type(exc).__name__})") from None
        finally:
            _myfxbook_last_request = time.monotonic()
        if r.status_code == 429:
            delay = LOGIN_COOLDOWN_MINUTES * 60
            retry = r.headers.get("Retry-After", "")
            try:
                delay = max(delay, float(retry))
            except ValueError:
                try:
                    delay = max(delay, parsedate_to_datetime(retry).timestamp() - time.time())
                except (ValueError, TypeError, OverflowError):
                    pass
            _pause_myfxbook("Limite de requisicoes informado pela API (HTTP 429)", delay)
            raise HTTPException(503, "MyFXBook limitou as requisicoes. Consultas pausadas.")
        if r.status_code != 200:
            raise HTTPException(502, f"MyFXBook HTTP {r.status_code}")
        try:
            data = r.json()
            if not isinstance(data, dict):
                raise ValueError()
        except ValueError:
            raise HTTPException(502, "Resposta MyFXBook em formato invalido") from None
        msg = str(data.get("message") or "")
        rate_limited = any(term in msg.lower() for term in ("too many request", "rate limit"))
        for secret in (MYFXBOOK_EMAIL, MYFXBOOK_PASSWORD, params.get("session")):
            if secret:
                msg = msg.replace(str(secret), "[oculto]")
        data["message"] = msg[:250]
        if data.get("error") and rate_limited:
            _pause_myfxbook("Limite de requisicoes informado pela API")
            raise HTTPException(503, "MyFXBook limitou as requisicoes. Consultas pausadas.")
        if cache_key and not data.get("error"):
            _data_cache[cache_key] = {"data": data, "expires": datetime.utcnow() + timedelta(minutes=CACHE_TTL_MINUTES)}
        return data


async def _myfxbook_login() -> str:
    """Autentica uma vez; o intervalo local evita repetir falhas em sequencia."""
    _check_myfxbook_pause()
    if not MYFXBOOK_EMAIL or not MYFXBOOK_PASSWORD:
        raise HTTPException(503, "Credenciais MyFXBook nao configuradas no servidor.")
    try:
        data = await _myfxbook_request(
            "https://www.myfxbook.com/api/login.json",
            {"email": MYFXBOOK_EMAIL, "password": MYFXBOOK_PASSWORD},
        )
    except HTTPException as exc:
        data = None
        err = str(exc.detail)
    else:
        err = data.get("message") or "Resposta sem sessao valida"

    if data is not None and not data.get("error") and data.get("session"):
        expires = datetime.utcnow() + timedelta(days=29)
        _session_cache["session"] = data["session"]
        _session_cache["expires"] = expires
        _login_state["failed_until"] = None
        _login_state["last_error"] = ""
        _save_login_state()
        _persist_session(data["session"], expires)
        return data["session"]

    _pause_myfxbook(err)
    raise HTTPException(502, (
        f"MyFXBook login falhou: {err}. Nova tentativa em "
        f"{LOGIN_COOLDOWN_MINUTES} min por precaucao do monitor."
    ))


async def get_myfxbook_session() -> str:
    now = datetime.utcnow()
    if _session_cache["session"] and _session_cache["expires"] > now:
        return _session_cache["session"]
    async with _login_lock:
        # Outra corrotina pode ter renovado a sessao enquanto esperavamos o lock.
        now = datetime.utcnow()
        if _session_cache["session"] and _session_cache["expires"] > now:
            return _session_cache["session"]
        _load_persisted_session()
        if _session_cache["session"] and _session_cache["expires"] > now:
            return _session_cache["session"]
        return await _myfxbook_login()


async def cached_get(url: str, params: dict, _retry_session: bool = True) -> dict:
    key = url + json.dumps(params, sort_keys=True)
    now = datetime.utcnow()
    if key in _data_cache and _data_cache[key]["expires"] > now:
        return _data_cache[key]["data"]
    data = await _myfxbook_request(url, params, cache_key=key)
    if data.get("error"):
        msg = data.get("message", "")
        session_expired = "session" in params and (
            "session" in msg.lower() or "authorized" in msg.lower() or "login" in msg.lower()
        )
        if session_expired and _retry_session:
            _drop_session(expected_session=params["session"])
            fresh = await get_myfxbook_session()
            return await cached_get(url, {**params, "session": fresh}, _retry_session=False)
        if session_expired:
            _drop_session(expected_session=params["session"])
        raise HTTPException(502, f"MyFXBook API error: {msg} ({url})")
    return data


def clear_myfxbook_cache(drop_session: bool = False) -> int:
    removed = 0
    for key in list(_data_cache.keys()):
        if "myfxbook.com" in key:
            _data_cache.pop(key, None)
            removed += 1
    _account_retry_after.clear()
    for saved in _account_snapshots.values():
        if saved:
            saved["stale"] = True
    # Limpar dados nao exige novo login nem remove a pausa apos falha.
    if drop_session:
        _drop_session()
    return removed


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
    return {"status": "ok", "service": "CopyTrader Monitor API", "database": db_status()}


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
    client_slug = next((slug for slug, info in all_clients.items() if str(info.get("username", "")).strip().casefold() == username.casefold() and info.get("password") == password), None)
    if not client_slug:
        write_access_log("login", requested_slug or "desconhecido", request, success=False, username=username)
        raise HTTPException(401, "Usuario ou senha invalidos")
    if requested_slug and requested_slug != client_slug:
        write_access_log("login", requested_slug, request, success=False, username=username)
        raise HTTPException(403, "Usuario nao autorizado para este cliente")
    write_access_log("login", client_slug, request, username=username)
    return {"token": make_token(client_slug), "role": "client", "client_slug": client_slug, "name": all_clients[client_slug]["name"], "expires_in_hours": TOKEN_TTL_HOURS}


async def build_client_data(slug: str, lite: bool = False) -> dict:
    client_info = get_client_info(slug)
    results = []
    for acc_slug in client_info["accounts"]:
        try:
            results.append(await get_account_data(acc_slug, lite=lite))
        except Exception as e:
            results.append({"slug": acc_slug, "name": ACCOUNTS_MAP.get(acc_slug, {}).get("name", acc_slug), "error": str(e)})
    ok = [a for a in results if not a.get("error")]
    total_balance = sum(float(a.get("balance") or 0) for a in ok)
    total_profit_day = sum(float(a.get("profit_day") or 0) for a in ok)
    total_profit_week = sum(float(a.get("profit_week") or 0) for a in ok)
    total_profit_month = sum(float(a.get("profit_month") or 0) for a in ok)
    total_profit_year = sum(float(a.get("profit_year") or 0) for a in ok)
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
    total_gain_year = consolidated_gain(total_profit_year)
    total_gain_total = consolidated_gain(total_profit_total)
    commission_day = round(total_profit_day * COMMISSION_RATE, 2)
    commission_week = round(total_profit_week * COMMISSION_RATE, 2)
    commission_month = round(total_profit_month * COMMISSION_RATE, 2)
    commission_year = round(total_profit_year * COMMISSION_RATE, 2)
    commission_total = round(total_profit_total * COMMISSION_RATE, 2)
    usd_brl = await get_usd_brl_rate()
    brl_rate = usd_brl["rate"]
    manual_withdrawals = round(float(client_info.get("manual_withdrawals") or 0), 2)
    manual_commission = round(float(client_info.get("manual_commission") or 0), 2)
    result = {
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
        "total_withdrawals_commission": round(total_withdrawals_commission + manual_withdrawals + manual_commission, 2),
        "total_withdrawals_commission_brl": round((total_withdrawals_commission + manual_withdrawals + manual_commission) * brl_rate, 2),
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
        "total_profit_year": round(total_profit_year, 2),
        "total_gain_year": total_gain_year,
        "total_profit_year_brl": round(total_profit_year * brl_rate, 2),
        "total_profit_total": round(total_profit_total, 2),
        "total_gain_total": total_gain_total,
        "total_profit_total_brl": round(total_profit_total * brl_rate, 2),
        "commission_rate": COMMISSION_RATE,
        "commission_day": commission_day,
        "commission_day_brl": round(commission_day * brl_rate, 2),
        "commission_week": commission_week,
        "commission_week_brl": round(commission_week * brl_rate, 2),
        "commission_month": commission_month,
        "commission_month_brl": round(commission_month * brl_rate, 2),
        "commission_year": commission_year,
        "commission_year_brl": round(commission_year * brl_rate, 2),
        "commission_total": commission_total,
        "commission_total_brl": round(commission_total * brl_rate, 2),
    }
    for field, manual in (("withdrawals", manual_withdrawals), ("paid_commission", manual_commission)):
        value = round(sum(a[field] for a in ok) + manual, 2) if ok and all(a.get(field) is not None for a in ok) else None
        result["total_" + field] = value
        result["total_" + field + "_brl"] = round(value * brl_rate, 2) if value is not None else None
    missing = len(ok) != len(results) or not results
    saved_accounts = [a for a in ok if a.get("stale")]
    result.update(data_unavailable=missing, stale=bool(saved_accounts),
                  last_success_at=min((a.get("fetched_at", "") for a in ok), default=""),
                  sync_warning=("Algumas contas ainda nao possuem dados salvos; totais indisponiveis." if missing else
                                "Exibindo ultimos dados salvos. A atualizacao esta temporariamente indisponivel." if saved_accounts else ""))
    if missing:
        for key in result:
            if key.startswith("total_") or (key.startswith("commission_") and key != "commission_rate"):
                result[key] = None
    return result


@app.get("/cliente/{slug}")
async def get_client(slug: str, request: Request, authorization: Optional[str] = Header(None)):
    require_client_auth(slug, authorization)
    write_access_log("panel", slug, request)
    return await build_client_data(slug)


@app.get("/admin/summary")
async def admin_summary(authorization: Optional[str] = Header(None)):
    require_admin_auth(authorization)
    clients = []
    for i, (slug, info) in enumerate(clients_map().items()):
        if i > 0:
            await asyncio.sleep(1)
        try:
            data = await build_client_data(slug, lite=True)
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


@app.post("/admin/refresh-myfxbook")
async def refresh_myfxbook(authorization: Optional[str] = Header(None)):
    require_admin_auth(authorization)
    removed = clear_myfxbook_cache()
    audit_log("admin", "myfxbook_refresh", "all", {"cache_entries_removed": removed})
    return {"refreshed": True, "cache_entries_removed": removed, **local_timestamp()}


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


@app.post("/admin/strategy-adjustment/{slug}")
async def update_strategy_adjustment(slug: str, payload: dict, authorization: Optional[str] = Header(None)):
    require_admin_auth(authorization)
    if slug not in ACCOUNTS_MAP:
        raise HTTPException(404, "Estrategia nao encontrada")
    reason = str(payload.get("reason", "")).strip()
    if not reason:
        raise HTTPException(400, "Informe o motivo do ajuste (ex: divergencia de sincronizacao com a MyFXBook)")
    try:
        value = round(float(payload.get("value", 0) or 0), 2)
    except Exception:
        raise HTTPException(400, "Valor de ajuste invalido")
    for_date = str(payload.get("for_date", "")).strip()
    if not for_date:
        for_date = local_now().strftime("%Y-%m-%d")
    try:
        datetime.strptime(for_date, "%Y-%m-%d")
    except Exception:
        raise HTTPException(400, "Data de referencia invalida (use AAAA-MM-DD)")
    adjustments = read_strategy_adjustments()
    previous = adjustments.get(slug) if isinstance(adjustments.get(slug), dict) else {}
    entry = {"value": value, "reason": reason, "for_date": for_date, **local_timestamp()}
    adjustments[slug] = entry
    write_strategy_adjustments(adjustments)
    audit_log("admin", "strategy_adjustment", slug, {
        "previous_value": previous.get("value", 0),
        "previous_reason": previous.get("reason", ""),
        "previous_for_date": previous.get("for_date", ""),
        "new_value": value,
        "reason": reason,
        "for_date": for_date,
    })
    return {"slug": slug, "adjustment": entry}


@app.get("/account/{slug}")
async def get_account(slug: str, authorization: Optional[str] = Header(None)):
    allowed_client = next((client_slug for client_slug, info in clients_map().items() if slug in info["accounts"]), None)
    if not allowed_client:
        raise HTTPException(404, "Conta nao encontrada")
    require_client_auth(allowed_client, authorization)
    return await get_account_data(slug)


def _snapshot_location(slug: str):
    identity = f"{slug}_{ACCOUNTS_MAP[slug]['id']}"
    key = "account_snapshot_" + identity
    path = DATA_DIR / (key + ".json")
    STATE_FALLBACK_FILES[key] = path
    return key, path


def _read_account_snapshot(slug: str) -> dict:
    key, path = _snapshot_location(slug)
    if key not in _account_snapshots:
        stored = db_read_state(key, {}) if db_enabled() else {}
        _account_snapshots[key] = stored or read_json_file(path, {})
    return copy.deepcopy(_account_snapshots[key])


def _write_account_snapshot(slug: str, data: dict) -> None:
    key, path = _snapshot_location(slug)
    _account_snapshots[key] = copy.deepcopy(data)
    try:
        if db_enabled():
            db_write_state(key, data)
        else:
            write_json_file(path, data)
    except Exception:
        pass


async def get_account_data(slug: str, lite: bool = False):
    if slug not in ACCOUNTS_MAP:
        raise HTTPException(404, "Conta nao encontrada")
    lock = _account_locks.setdefault(slug, asyncio.Lock())
    async with lock:
        saved = _read_account_snapshot(slug)
        now = datetime.utcnow()
        try:
            recent = now - datetime.fromisoformat(saved["fetched_at"].removesuffix("Z")) < timedelta(minutes=CACHE_TTL_MINUTES)
        except (KeyError, ValueError, TypeError):
            recent = False
        if recent and (lite or saved.get("details_complete") or saved.get("details_warning")) and not saved.get("stale"):
            return saved
        if saved and _account_retry_after.get(slug, datetime.min) > now:
            return {**saved, "stale": True, "sync_warning": "Exibindo a ultima consulta valida; nova tentativa aguardando."}
        try:
            fresh = await _fetch_account_data(slug, lite=lite)
            if not isinstance(fresh, dict) or fresh.get("balance") is None:
                raise HTTPException(502, "Resposta financeira incompleta")
        except Exception:
            _account_retry_after[slug] = now + timedelta(minutes=LOGIN_COOLDOWN_MINUTES)
            if saved:
                return {**saved, "stale": True, "sync_warning": "Falha na atualizacao. Valores preservados da ultima consulta valida."}
            raise
        fresh.update(fetched_at=datetime.utcnow().isoformat() + "Z", stale=False,
                     details_complete=fresh.get("details_complete", not lite), sync_warning="")
        if not fresh["details_complete"] and saved.get("history"):
            for field in ("history", "open_trades", "open_trades_count", "open_trades_profit", "open_trades_profit_brl"):
                fresh[field] = saved.get(field)
            fresh["details_fetched_at"] = saved.get("details_fetched_at", saved.get("fetched_at"))
        elif fresh["details_complete"]:
            fresh["details_fetched_at"] = fresh["fetched_at"]
        _write_account_snapshot(slug, fresh)
        _account_retry_after.pop(slug, None)
        return fresh


async def _fetch_account_data(slug: str, lite: bool = False):
    if slug not in ACCOUNTS_MAP:
        raise HTTPException(404, "Conta nao encontrada")
    account_info = ACCOUNTS_MAP[slug]
    account_id = account_info["id"]
    last_exc: Exception = None
    for attempt in range(2):
        try:
            session = await get_myfxbook_session()
            today_local = local_now().date()
            accounts_task = cached_get("https://www.myfxbook.com/api/get-my-accounts.json", {"session": session})
            daily_gain_task = cached_get("https://www.myfxbook.com/api/get-daily-gain.json", {"session": session, "id": account_id, "start": datetime(today_local.year, 1, 1).strftime("%Y-%m-%d"), "end": today_local.strftime("%Y-%m-%d")})
            accounts_data, daily_gain_data = await asyncio.gather(accounts_task, daily_gain_task)
            details_ok = False
            open_trades_data, history_data = {"openTrades": []}, {"history": []}
            if not lite:
                optional = await asyncio.gather(
                    cached_get("https://www.myfxbook.com/api/get-open-trades.json", {"session": session, "id": account_id}),
                    cached_get("https://www.myfxbook.com/api/get-history.json", {"session": session, "id": account_id}),
                    return_exceptions=True,
                )
                details_ok = all(isinstance(item, dict) for item in optional)
                if details_ok:
                    open_trades_data, history_data = optional
            account_detail = next((a for a in accounts_data.get("accounts", []) if a["id"] == account_id), None)
            if not account_detail:
                raise HTTPException(404, "Conta nao encontrada no MyFXBook")
            gains = daily_gain_data.get("dailyGain", [])
            flat_gains = [item for sublist in gains for item in (sublist if isinstance(sublist, list) else [sublist])]
            today = local_now().date()
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
            def sum_since(cutoff_date):
                total = 0.0
                for g in flat_gains:
                    try:
                        d = datetime.strptime(g["date"], "%m/%d/%Y").date()
                        if d >= cutoff_date:
                            total += float(g.get("profit", 0))
                    except Exception:
                        pass
                return round(total, 2)
            profit_day = sum_period(1)
            profit_week = sum_period(7)
            profit_month = sum_period(30)
            profit_year = sum_since(today.replace(month=1, day=1))
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
            if lite:
                monthly_gain_series = []
                period_gains = {}
            else:
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
            adjustment = get_strategy_adjustment(slug)
            adjustment_value = round(float(adjustment.get("value", 0) or 0), 2)
            adjustment_reason = adjustment.get("reason", "")
            adjustment_for_date_str = adjustment.get("for_date", "")
            try:
                adjustment_for_date = datetime.strptime(adjustment_for_date_str, "%Y-%m-%d").date() if adjustment_for_date_str else None
            except Exception:
                adjustment_for_date = None
            def adjustment_in_period(days_ago: int) -> bool:
                if adjustment_for_date is None or not adjustment_value:
                    return False
                return adjustment_for_date >= (today - timedelta(days=days_ago))
            adj_day = adjustment_value if adjustment_in_period(1) else 0.0
            adj_week = adjustment_value if adjustment_in_period(7) else 0.0
            adj_month = adjustment_value if adjustment_in_period(30) else 0.0
            adj_year = adjustment_value if (adjustment_for_date and adjustment_value and adjustment_for_date >= today.replace(month=1, day=1)) else 0.0
            raw_balance = to_usd(account_detail.get("balance"))
            raw_profit_total = to_usd(account_detail.get("profit"))
            adj_balance = round(raw_balance + adjustment_value, 2) if raw_balance is not None else raw_balance
            adj_profit_total = round(raw_profit_total + adjustment_value, 2) if raw_profit_total is not None else raw_profit_total
            adj_balance_brl = round(adj_balance * brl_rate, 2) if adj_balance is not None else None
            adj_profit_total_brl = round(adj_profit_total * brl_rate, 2) if adj_profit_total is not None else None
            history = [
                {
                    **normalize_trade_money(trade),
                    "openTimeLocal": myfxbook_datetime_to_local(trade.get("openTime")),
                    "closeTimeLocal": myfxbook_datetime_to_local(trade.get("closeTime")),
                }
                for trade in history_data.get("history", [])[:30]
            ]
            return {
                "withdrawals": withdrawals,
                "paid_commission": commission,
                "details_complete": details_ok,
                "details_warning": "" if lite or details_ok else "Historico indisponivel; resumo financeiro preservado.",
                "slug": slug,
                "name": account_info["name"],
                "description": account_info["description"],
                "pair": account_info["pair"],
                "cents": is_cents,
                "usd_brl_rate": brl_rate,
                "exchange_rate_source": usd_brl["source"],
                "exchange_rate_updated_at": usd_brl.get("updated_at"),
                "balance": adj_balance,
                "balance_brl": adj_balance_brl,
                "balance_raw": raw_balance,
                "balance_raw_brl": to_brl(account_detail.get("balance")),
                "equity": to_usd(account_detail.get("equity")),
                "equity_brl": to_brl(account_detail.get("equity")),
                "gain": account_detail.get("gain"),
                "drawdown": account_detail.get("drawdown"),
                "profit": adj_profit_total,
                "profit_brl": adj_profit_total_brl,
                "withdrawals": withdrawals,
                "withdrawals_brl": round(withdrawals * brl_rate, 2),
                "commission": commission,
                "commission_brl": round(commission * brl_rate, 2),
                "withdrawals_commission": withdrawals_commission,
                "withdrawals_commission_brl": round(withdrawals_commission * brl_rate, 2),
                "demo": account_detail.get("demo", False),
                "lastUpdateDate": account_detail.get("lastUpdateDate"),
                "myfxbook_updated_at": account_detail.get("lastUpdateDate"),
                "profit_day": round(profit_day / div + adj_day, 2),
                "gain_day": period_gains.get("gain_day"),
                "profit_day_brl": round((profit_day / div + adj_day) * brl_rate, 2),
                "profit_week": round(profit_week / div + adj_week, 2),
                "gain_week": period_gains.get("gain_week"),
                "profit_week_brl": round((profit_week / div + adj_week) * brl_rate, 2),
                "profit_month": round(profit_month / div + adj_month, 2),
                "gain_month": period_gains.get("gain_month"),
                "profit_month_brl": round((profit_month / div + adj_month) * brl_rate, 2),
                "profit_year": round(profit_year / div + adj_year, 2),
                "profit_year_brl": round((profit_year / div + adj_year) * brl_rate, 2),
                "profit_total": adj_profit_total,
                "profit_total_brl": adj_profit_total_brl,
                "profit_total_raw": raw_profit_total,
                "profit_total_raw_brl": to_brl(account_detail.get("profit")),
                "adjustment_value": adjustment_value,
                "adjustment_value_brl": round(adjustment_value * brl_rate, 2),
                "adjustment_reason": adjustment_reason,
                "adjustment_for_date": adjustment_for_date_str,
                "adjustment_at": adjustment.get("at", ""),
                "growth_series": growth_series,
                "monthly_gain_series": monthly_gain_series,
                "open_trades_count": len(open_trades),
                "open_trades_profit": open_trades_profit,
                "open_trades_profit_brl": round(open_trades_profit * brl_rate, 2),
                "open_trades": open_trades,
                "history": history,
            }
        except HTTPException as e:
            if attempt == 0 and e.status_code == 502:
                last_exc = e
                continue
            raise
        except Exception as e:
            raise HTTPException(500, f"Erro ao buscar dados: {str(e)}")
    raise last_exc


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

