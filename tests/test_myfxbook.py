import asyncio
import copy
import unittest
import time
from types import SimpleNamespace
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock

import httpx
from backend import main as m


class MyfxbookTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.state = {}
        self.calls = []
        self.real_client = httpx.AsyncClient
        self.clock = 100.0
        self.sleeps = []
        async def sleep(seconds):
            self.sleeps.append(seconds)
            self.clock += seconds
        def save(path, value):
            self.state[str(path)] = copy.deepcopy(value)
        patches = {
            "MYFXBOOK_EMAIL": "test@example.invalid",
            "MYFXBOOK_PASSWORD": "test-secret",
            "_session_cache": {"session": None, "expires": None},
            "_login_state": {"failed_until": None, "last_error": ""},
            "_login_state_loaded": False,
            "_data_cache": {},
            "_login_lock": asyncio.Lock(),
            "_myfxbook_request_lock": asyncio.Lock(),
            "_myfxbook_last_request": 0.0,
        }
        for key, value in patches.items():
            p = patch.object(m, key, value); p.start(); self.addCleanup(p.stop)
        for p in (
            patch.object(m, "db_enabled", return_value=False),
            patch.object(m, "write_json_file", side_effect=save),
            patch.object(m, "read_json_file", side_effect=lambda path, default: copy.deepcopy(self.state.get(str(path), default))),
            patch.object(m, "time", SimpleNamespace(monotonic=lambda: self.clock, time=time.time)),
            patch.object(m.asyncio, "sleep", side_effect=sleep),
        ):
            p.start(); self.addCleanup(p.stop)

    def transport(self, handler):
        def record(request):
            self.calls.append(request)
            return handler(request)
        p = patch.object(m.httpx, "AsyncClient", side_effect=lambda **kw: self.real_client(transport=httpx.MockTransport(record), **kw))
        p.start(); self.addCleanup(p.stop)

    async def test_login_failure_survives_restart_and_cache_clear(self):
        self.transport(lambda r: httpx.Response(200, json={"error": True, "message": "Wrong email/password."}))
        with self.assertRaises(m.HTTPException): await m.get_myfxbook_session()
        m._login_state = {"failed_until": None, "last_error": ""}
        m._login_state_loaded = False
        m.clear_myfxbook_cache()
        with self.assertRaises(m.HTTPException): await m.get_myfxbook_session()
        self.assertEqual(len(self.calls), 1)
        self.assertIsNotNone(m._login_state["failed_until"])

    async def test_expired_pause_allows_login_and_session_reuse_after_restart(self):
        self.state[str(m.LOGIN_STATE_FILE)] = {"failed_until": (datetime.utcnow()-timedelta(seconds=1)).isoformat(), "last_error": "old"}
        self.transport(lambda r: httpx.Response(200, json={"error": False, "session": "new"}))
        self.assertEqual(await m.get_myfxbook_session(), "new")
        self.assertGreater(m._session_cache["expires"], datetime.utcnow()+timedelta(days=28))
        m._session_cache = {"session": None, "expires": None}
        self.assertEqual(await m.get_myfxbook_session(), "new")
        self.assertEqual(len(self.calls), 1)

    async def test_identical_concurrent_queries_share_cache(self):
        self.transport(lambda r: httpx.Response(200, json={"error": False, "accounts": []}))
        await asyncio.gather(*(m.cached_get("https://test.invalid/accounts", {"session": "s"}) for _ in range(5)))
        self.assertEqual(len(self.calls), 1)

    async def test_distinct_queries_are_spaced(self):
        self.transport(lambda r: httpx.Response(200, json={"error": False}))
        await asyncio.gather(*(m.cached_get("https://test.invalid/"+str(i), {}) for i in range(3)))
        self.assertEqual(len(self.calls), 3)
        self.assertEqual(self.sleeps, [m.MYFXBOOK_REQUEST_INTERVAL_SECONDS]*2)

    async def test_rate_limit_stops_queued_queries_and_honors_retry_after(self):
        self.transport(lambda r: httpx.Response(429, headers={"Retry-After": "3600"}))
        results = await asyncio.gather(*(m.cached_get("https://test.invalid/"+str(i), {}) for i in range(3)), return_exceptions=True)
        self.assertTrue(all(isinstance(r, m.HTTPException) for r in results))
        self.assertEqual(len(self.calls), 1)
        self.assertGreater(m._login_state["failed_until"], datetime.utcnow()+timedelta(minutes=59))

    async def test_json_rate_limit_does_not_trigger_login(self):
        self.transport(lambda r: httpx.Response(200, json={"error": True, "message": "Too many requests, please try again later"}))
        with self.assertRaises(m.HTTPException): await m.cached_get("https://test.invalid/accounts", {"session": "s"})
        self.assertEqual(len(self.calls), 1)
        self.assertIsNotNone(m._login_state["failed_until"])

    async def test_old_failure_cannot_discard_new_session(self):
        m._session_cache.update(session="new", expires=datetime.utcnow()+timedelta(days=1))
        m._drop_session(expected_session="old")
        self.assertEqual(m._session_cache["session"], "new")
        self.assertEqual(self.state, {})

    async def test_failed_accounts_do_not_become_zero_totals(self):
        with patch.object(m, "get_client_info", return_value={"accounts": ["test"]}), patch.object(m, "get_account_data", AsyncMock(side_effect=m.HTTPException(502, "failed"))):
            with self.assertRaises(m.HTTPException): await m.build_client_data("test")

    async def test_transport_errors_do_not_expose_credentials(self):
        def fail(request):
            raise httpx.ConnectError(str(request.url), request=request)
        self.transport(fail)
        with self.assertRaises(m.HTTPException) as ctx: await m.get_myfxbook_session()
        self.assertNotIn("test-secret", str(ctx.exception.detail))
        self.assertNotIn("test@example.invalid", str(self.state))

    def test_database_fallbacks_do_not_overwrite_notices(self):
        self.assertEqual(m.STATE_FALLBACK_FILES[m.SESSION_STATE_KEY], m.SESSION_FILE)
        self.assertEqual(m.STATE_FALLBACK_FILES[m.LOGIN_STATE_KEY], m.LOGIN_STATE_FILE)


if __name__ == "__main__":
    unittest.main()
