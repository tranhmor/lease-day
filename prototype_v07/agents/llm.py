"""LLM Landlord & Tenant policies with disk cache, prompt hashing, JSON validation, 1-retry, and rule fallback."""
import hashlib
import http.client
import json
import os
from pathlib import Path
import socket
import sqlite3
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, List, Optional, Tuple

from .base import (
    LandlordPolicy,
    TenantPolicy,
    validate_answer_counter,
    validate_at_expiry,
    validate_pick_applicant,
    validate_price_vacant,
    validate_renewal_offer,
    validate_search,
)
from .rule import RuleLandlord, RuleTenant

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
RETRY_HTTP_CODES = {429, 500, 502, 503, 504}

# Request-body fields that switch off hybrid "thinking" per serving stack. Thinking tokens would eat
# max_tokens and truncate the JSON answer, and make the decision depend on hidden reasoning.
THINKING_OFF_FIELDS: Dict[str, Dict[str, Any]] = {
    "none": {},
    "openai": {"reasoning_effort": "none"},
    "deepseek": {"thinking": {"type": "disabled"}},
    "dashscope": {"enable_thinking": False},
    "ollama": {"reasoning_effort": "none", "think": False},
    "vllm": {"chat_template_kwargs": {"enable_thinking": False}},
}


def resolve_thinking_style(setting: str, base_url: str, model: str) -> str:
    """LLM_THINKING=auto|none|openai|deepseek|dashscope|ollama|vllm; auto infers the stack from URL/model."""
    s = (setting or "auto").strip().lower()
    if s in THINKING_OFF_FIELDS:
        return s
    if s != "auto":
        raise ValueError(f"LLM_THINKING must be auto or one of {sorted(THINKING_OFF_FIELDS)}, got {setting!r}")
    url, m = base_url.lower(), model.lower()
    if ":11434" in url or "ollama" in url:
        return "ollama"
    if "dashscope" in url or "aliyuncs" in url:
        return "dashscope"
    if "wokey" in url:
        return "openai"
    if "deepseek" in url or "deepseek" in m:
        return "deepseek"
    return "none"


def load_dotenv_config() -> Dict[str, str]:
    """Read .env files (workspace root and rental_game/) plus environment overrides without printing secrets."""
    values: Dict[str, str] = {}
    here = Path(__file__).resolve().parent
    candidates = [
        here.parent.parent.parent / ".env",  # workspace root
        here.parent.parent / ".env",         # rental_game/.env
        here.parent / ".env",                # prototype_v07/.env
    ]
    for path in candidates:
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                s = line.strip()
                if s and not s.startswith("#") and "=" in s:
                    k, v = s.split("=", 1)
                    values[k.strip()] = v.strip().strip('"').strip("'")
    for key in (
        "LLM_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY", "CLASS_API_TOKEN",
        "LLM_BASE_URL", "OPENAI_BASE_URL", "DEEPSEEK_BASE_URL",
        "LLM_MODEL", "OPENAI_MODEL", "DEEPSEEK_MODEL", "LLM_USE_PROXY",
        "LLM_THINKING", "LLM_TIMEOUT", "LLM_MAX_TOKENS",
    ):
        if key in os.environ:
            values[key] = os.environ[key]
    return values


def prompt_hashes(prompts_dir: Path = PROMPTS_DIR) -> Dict[str, str]:
    """Return SHA-256 manifest of all frozen prompt files (§5.1)."""
    out: Dict[str, str] = {}
    for p in sorted(prompts_dir.glob("*.txt")):
        out[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
    return out


class DiskCache:
    """SQLite-backed persistent prompt cache keyed by (model, temperature, prompt_hash)."""

    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        self.conn.execute("PRAGMA busy_timeout=30000;")
        try:
            self.conn.execute("PRAGMA journal_mode=WAL;")
        except sqlite3.OperationalError:
            pass
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS llm_cache (
                cache_key TEXT PRIMARY KEY,
                model TEXT,
                temperature REAL,
                prompt_hash TEXT,
                content TEXT,
                tokens INTEGER
            )"""
        )
        self.conn.commit()

    def get(self, cache_key: str) -> Optional[Tuple[str, int]]:
        row = self.conn.execute("SELECT content, tokens FROM llm_cache WHERE cache_key = ?", (cache_key,)).fetchone()
        return (row[0], int(row[1])) if row else None

    def put(self, cache_key: str, model: str, temperature: float, prompt_hash: str, content: str, tokens: int) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO llm_cache (cache_key, model, temperature, prompt_hash, content, tokens) VALUES (?, ?, ?, ?, ?, ?)",
            (cache_key, model, temperature, prompt_hash, content, tokens),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()


class LLMBackend:
    """Abstract chat-completion backend returning (raw_json_text, total_tokens)."""

    model: str = "unknown"
    temperature: float = 0.0

    def complete(self, system_prompt: str, user_prompt: str) -> Tuple[str, int]:
        raise NotImplementedError


class OpenAICompatBackend(LLMBackend):
    """Zero-dependency OpenAI-compatible HTTP client (works with DeepSeek, OpenAI, vLLM, class gateways)."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 320,
        timeout: int = 90,
        disable_thinking: bool = True,
        backoff_s: Tuple[float, ...] = (1.0, 2.0, 4.0),
    ):
        cfg = load_dotenv_config()
        self.api_key = (
            api_key
            or cfg.get("LLM_API_KEY")
            or cfg.get("OPENAI_API_KEY")
            or cfg.get("DEEPSEEK_API_KEY")
            or cfg.get("CLASS_API_TOKEN")
        )
        if not self.api_key:
            raise ValueError("No API key found. Set LLM_API_KEY / DEEPSEEK_API_KEY / CLASS_API_TOKEN in .env or env.")
        self.base_url = (
            base_url
            or cfg.get("LLM_BASE_URL")
            or cfg.get("OPENAI_BASE_URL")
            or cfg.get("DEEPSEEK_BASE_URL")
            or "https://api.deepseek.com"
        ).rstrip("/")
        self.model = model or cfg.get("LLM_MODEL") or cfg.get("OPENAI_MODEL") or cfg.get("DEEPSEEK_MODEL") or "deepseek-chat"
        self.temperature = temperature
        self.max_tokens = int(cfg.get("LLM_MAX_TOKENS") or max_tokens)
        self.timeout = int(cfg.get("LLM_TIMEOUT") or timeout)
        self.disable_thinking = disable_thinking
        self.thinking_style = resolve_thinking_style(cfg.get("LLM_THINKING", "auto"), self.base_url, self.model)
        self.use_proxy = cfg.get("LLM_USE_PROXY", "1") != "0"
        self.backoff_s = backoff_s
        self.sleep = time.sleep
        self.transport_retries = 0  # rate-limit / transient retries (not counted as LLM output errors)

    def _open_json(self, opener, req) -> Dict[str, Any]:
        with opener.open(req, timeout=self.timeout) as resp:
            return json.load(resp)

    def _send_with_backoff(self, send: Callable[[], Dict[str, Any]]) -> Dict[str, Any]:
        """Retry only transport failures (429 / 5xx / timeout / network) with exponential backoff."""
        attempts = len(self.backoff_s) + 1
        for i in range(attempts):
            try:
                return send()
            except urllib.error.HTTPError as e:
                if e.code not in RETRY_HTTP_CODES or i == attempts - 1:
                    raise RuntimeError(f"LLM HTTP error {e.code}") from None
                wait = self.backoff_s[i]
                retry_after = e.headers.get("Retry-After") if e.headers else None
                if retry_after and retry_after.strip().isdigit():
                    wait = max(wait, min(float(retry_after.strip()), 60.0))
            except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, http.client.HTTPException) as e:
                if i == attempts - 1:
                    raise RuntimeError(f"LLM network/timeout error: {e}") from None
                wait = self.backoff_s[i]
            self.transport_retries += 1
            self.sleep(wait)
        raise RuntimeError("unreachable")

    def complete(self, system_prompt: str, user_prompt: str) -> Tuple[str, int]:
        url = self.base_url + "/chat/completions"
        body: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "response_format": {"type": "json_object"},
            "stream": False,
        }
        if self.disable_thinking:
            body.update(THINKING_OFF_FIELDS[self.thinking_style])

        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
        )
        opener = urllib.request.build_opener() if self.use_proxy else urllib.request.build_opener(urllib.request.ProxyHandler({}))
        data = self._send_with_backoff(lambda: self._open_json(opener, req))
        content = data["choices"][0]["message"].get("content") or ""
        usage = data.get("usage", {})
        tokens = int(usage.get("total_tokens", 0))
        return content, tokens


class CacheOnlyBackend(LLMBackend):
    """Offline backend that strictly serves from DiskCache (auto-detects model from SQLite if omitted).

    Raises RuntimeError on any cache miss so replaying completed runs with --dump-room-states guarantees 0 API calls.
    """

    def __init__(self, cache_path: str, model: Optional[str] = None, temperature: float = 0.0):
        if model is None:
            conn = sqlite3.connect(str(cache_path), timeout=10.0)
            try:
                rows = conn.execute("SELECT model, COUNT(*) FROM llm_cache GROUP BY model ORDER BY COUNT(*) DESC").fetchall()
            finally:
                conn.close()
            if not rows:
                raise RuntimeError(f"CacheOnlyBackend: no cached entries found in {cache_path}")
            model = rows[0][0]
        self.model = model
        self.temperature = temperature

    def complete(self, system_prompt: str, user_prompt: str) -> Tuple[str, int]:
        raise RuntimeError(f"CacheOnlyBackend cache miss for model={self.model!r} (refusing live API call)")


class MockLLMBackend(LLMBackend):
    """Deterministic offline mock backend that exhibits realistic announcement-anticipation behavior.

    Used strictly for unit testing caching, JSON parsing, retries, fallback rates, and end-to-end pipeline
    wiring before spending real API tokens.
    """

    def __init__(self, model: str = "mock-anticipation-v1", inject_bad_json_rate: float = 0.0):
        self.model = model
        self.temperature = 0.0
        self.inject_bad_json_rate = inject_bad_json_rate
        self.call_count = 0

    def complete(self, system_prompt: str, user_prompt: str) -> Tuple[str, int]:
        self.call_count += 1
        # Optional simulated parse error on first attempt to verify retry logic
        if self.inject_bad_json_rate > 0 and "请修正" not in user_prompt:
            h = int(hashlib.md5(user_prompt.encode("utf-8")).hexdigest()[:8], 16) / 0xFFFFFFFF
            if h < self.inject_bad_json_rate:
                return "{invalid json", 40

        # Parse embedded JSON context (single line after the header; retry suffix may contain a format spec)
        body = user_prompt.split("\n", 1)[1].split("\n", 1)[0]
        ctx = json.loads(body)

        decision = ctx.get("_decision", "")
        ann = ctx.get("announcement")

        if decision == "renewal_offer":
            cur = ctx["current_rent"]
            v = ctx["zone_vacancy_pct"] / 100.0
            rate = max(-0.03, 0.03 - v * 0.4)
            if ann and ann.get("affects_this_zone") and not ann.get("already_open"):
                rem = ann.get("months_to_opening", 12)
                # Stronger hike as opening approaches
                rate += 0.025 + 0.02 * (1.0 - min(rem, 12) / 12.0)
                if ctx["landlord"]["risk"] == "愿意等":
                    rate += 0.015
            rent = round(cur * (1.0 + rate), 2)
            return json.dumps({"rent": rent, "reason": "mock:结合空置率与新线预期报价"}, ensure_ascii=False), 120

        if decision == "price_vacant":
            cur = ctx["current_rent"]
            v = ctx["zone_vacancy_pct"] / 100.0
            up = ctx["up_front"]
            rate = max(-0.04, 0.04 - v * 0.5) if ctx["vacant_for"] == 0 else -0.025
            if ann and ann.get("affects_this_zone") and not ann.get("already_open") and ctx["vacant_for"] == 0:
                rate += 0.045
                if ctx["landlord"]["risk"] == "愿意等" and up < 4:
                    up += 1
            rent = round(cur * (1.0 + rate), 2)
            return json.dumps({"rent": rent, "up_front": up, "reason": "mock:空房定价"}, ensure_ascii=False), 120

        if decision == "answer_counter":
            offer = ctx["initial_offer"]
            counter = ctx["counter_rent"]
            v = ctx["zone_vacancy_pct"] / 100.0
            # Tougher during announcement window in treated zones
            tight = (ann and ann.get("affects_this_zone")) or v < 0.045
            thresh = offer * (0.985 if tight else 0.95)
            acc = counter >= thresh
            return json.dumps({"accept": acc, "rent": counter if acc else offer, "reason": "mock:评估空置机会成本"}, ensure_ascii=False), 100

        if decision == "pick_applicant":
            apps = ctx["applicants"]
            best = max(apps, key=lambda a: (a["income_to_rent"], a["good_standing"]))
            return json.dumps({"tenant_id": best["tenant_id"], "reason": "mock:综合出价与收入安全度"}, ensure_ascii=False), 100

        if decision == "at_expiry":
            cur = ctx["current_room"]
            cands = ctx["candidates"]
            best_c = min(cands, key=lambda c: c["rent"]) if cands else None
            # Anticipate opening if treated zone and contract covers post-opening months
            if ann and not ann.get("already_open"):
                tr_cands = [c for c in cands if c.get("contract_months_after_open", 0) >= 3 and c["affordable"]]
                if tr_cands and _income_group(ctx["tenant"]["income"]) in ("mid", "high"):
                    pick = min(tr_cands, key=lambda c: c["rent"])
                    m = next(x["mode"] for x in pick["modes"] if x.get("feasible", True))
                    return json.dumps({"action": "move", "mode": m, "rent": None, "if_rejected": None, "apply": [{"room_id": pick["room_id"], "mode": m}], "reason": "mock:提前搬入受益区"}, ensure_ascii=False), 160
                if cur.get("contract_months_after_open", 0) >= 1 and cur["affordable"]:
                    m = next(x["mode"] for x in cur["modes"] if x.get("feasible", True))
                    return json.dumps({"action": "renew", "mode": m, "rent": cur["offer_rent"], "if_rejected": None, "apply": [], "reason": "mock:续租锁价"}, ensure_ascii=False), 150
            if cur["affordable"]:
                m = next(x["mode"] for x in cur["modes"] if x.get("feasible", True))
                if cur["offer_rent"] > cur["current_rent"] * 1.03:
                    ctr = round((cur["current_rent"] + cur["offer_rent"]) / 2.0, 2)
                    return json.dumps({"action": "counter", "mode": m, "rent": ctr, "if_rejected": "accept_offer", "apply": [], "reason": "mock:尝试还价"}, ensure_ascii=False), 150
                return json.dumps({"action": "renew", "mode": m, "rent": cur["offer_rent"], "if_rejected": None, "apply": [], "reason": "mock:续租"}, ensure_ascii=False), 140
            if best_c and best_c["affordable"]:
                m = next(x["mode"] for x in best_c["modes"] if x.get("feasible", True))
                return json.dumps({"action": "move", "mode": m, "rent": None, "if_rejected": None, "apply": [{"room_id": best_c["room_id"], "mode": m}], "reason": "mock:搬至更可负担房源"}, ensure_ascii=False), 150
            return json.dumps({"action": "leave", "mode": None, "rent": None, "if_rejected": None, "apply": [], "reason": "mock:无可行选项"}, ensure_ascii=False), 110

        if decision == "search":
            cands = [c for c in ctx["candidates"] if c["affordable"]]
            if not cands:
                return json.dumps({"apply": [], "reason": "mock:无可行房源"}, ensure_ascii=False), 90
            if ann and not ann.get("already_open") and _income_group(ctx["tenant"]["income"]) in ("mid", "high"):
                cands.sort(key=lambda c: (-c.get("contract_months_after_open", 0), c["rent"]))
            else:
                cands.sort(key=lambda c: c["rent"])
            picks = []
            for c in cands[:2]:
                fm = [x["mode"] for x in c["modes"] if x.get("feasible", True)]
                if fm:
                    picks.append({"room_id": c["room_id"], "mode": fm[0]})
            return json.dumps({"apply": picks, "reason": "mock:按偏好申请"}, ensure_ascii=False), 140

        raise ValueError(f"Unknown mock decision: {decision}")


# Fixed, semantically grouped key order (property -> people -> market -> line). Alphabetical order put
# "announcement" first in every P-group payload, giving it a salience the S group never has. Unlisted keys
# follow in alphabetical order.
KEY_ORDER = [
    "_decision", "month", "landlord", "landlord_vacant_rooms", "room_id", "zone_label", "amenity_score", "kind", "station_dist_m",
    "current_rent", "start_rent", "offer_rent", "rent", "rent_pct_income", "up_front", "upfront_cash_needed",
    "cash_gap", "modes", "affordable", "contract_months_after_open",
    "vacant_for", "last_vacant_months", "initial_offer", "counter_rent",
    "tenant", "tenant_tenure_months", "tenant_good_standing", "applicants",
    "current_room", "candidates",
    "zone_vacancy_pct", "nearby_avg_rent", "recent_apps_per_vacant",
    "mode", "min", "transfers", "month_fare", "post_open_min", "monthly_residual",
    "tenant_id", "income", "income_to_rent", "couple", "household_size", "car", "cash", "locked_deposit",
    "available_move_cash", "comfort_ratio", "stretch_ratio", "good_standing",
    "landlord_id", "risk", "zones", "n_rooms",
    "text", "opens_at_month", "months_to_opening", "already_open", "affects_this_zone",
    "expected_time_saving_min", "lease_months_after_open", "note",
    "announcement",
]
_KEY_RANK = {k: i for i, k in enumerate(KEY_ORDER)}


def _ordered(obj: Any) -> Any:
    if isinstance(obj, dict):
        keys = sorted(obj, key=lambda k: (_KEY_RANK.get(k, len(KEY_ORDER)), k))
        return {k: _ordered(obj[k]) for k in keys}
    if isinstance(obj, list):
        return [_ordered(x) for x in obj]
    return obj


def render_user_prompt(payload: Dict[str, Any]) -> str:
    """Single-line compact JSON (no spaces after separators: ~10% fewer input tokens, same content)."""
    return "当前决策信息（JSON）：\n" + json.dumps(_ordered(payload), ensure_ascii=False, separators=(",", ":"))


def _extract_json(text: Optional[str]) -> Optional[Dict[str, Any]]:
    if not isinstance(text, str):
        return None
    s = text.strip()
    if s.startswith("```"):
        lines = [ln for ln in s.splitlines() if not ln.strip().startswith("```")]
        s = "\n".join(lines).strip()
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        a, b = s.find("{"), s.rfind("}")
        if a != -1 and b > a:
            try:
                obj = json.loads(s[a:b + 1])
                return obj if isinstance(obj, dict) else None
            except json.JSONDecodeError:
                return None
        return None


# Experimental-design labels: kept in logs and rule policies, never shown to the LLM.
HIDDEN_LANDLORD_KEYS = {"treated"}
HIDDEN_TENANT_KEYS = {"group", "good_standing"}
# Own tenure is shown at expiry (the landlord sees tenant_tenure_months too); meaningless for searchers.
HIDDEN_TENANT_KEYS_SEARCH = HIDDEN_TENANT_KEYS | {"tenure_months"}
# Rule-engine internals: unexplained in prompts, would act as artificial anchors. hard_floor is already encoded in
# `affordable`; zone duplicates zone_label.
HIDDEN_TOP_KEYS = {"cell_vacancy", "demand_signal", "floor_rent", "hard_floor", "zone"}
# Card compression (prompt only; validators and rule policies read the full ctx). Candidate cards: rent is the price,
# current_rent/offer_rent repeat it. Current room: offer_rent/current_rent carry the prices, no move-in cash applies.
HIDDEN_CARD_COMMON = {"rule_score", "rule_best_mode", "rule_within_stretch", "zone", "contract_months"}
HIDDEN_CAND_KEYS = HIDDEN_CARD_COMMON | {"current_rent", "offer_rent"}
HIDDEN_CUR_KEYS = HIDDEN_CARD_COMMON | {"rent", "upfront_cash_needed", "cash_gap"}
# Constant across applicants of one room (same rent, same terms, cash always verified): no information.
HIDDEN_APPLICANT_KEYS = {"offered_rent", "requested_up_front", "cash_verified"}
# Modes shown in a fixed name order, not by the hidden generalized cost (the first entry was always the rule optimum).
MODE_NAME_ORDER = ["地铁", "骑车接地铁", "公交直达", "公交换乘", "电动车", "自行车", "步行", "私家车"]


def _card_for_prompt(card: Dict[str, Any], hidden: set) -> Dict[str, Any]:
    out = {k: v for k, v in card.items() if k not in hidden}
    if isinstance(card.get("modes"), list):
        modes = []
        for m in card["modes"]:
            if not m.get("feasible", True):
                continue
            mm = {k: v for k, v in m.items() if k != "feasible" and not (k == "transfers" and v == 0)}
            modes.append(mm)
        rank = {n: i for i, n in enumerate(MODE_NAME_ORDER)}
        modes.sort(key=lambda m: (rank.get(m["mode"], len(rank)), m["mode"]))
        out["modes"] = modes
    return out


def output_format_spec(template_text: str) -> str:
    """Return the '输出格式：...' block of a prompt template (used for retries and wording overrides)."""
    i = template_text.find("输出格式")
    return template_text[i:].strip() if i != -1 else ""


def _income_group(income: float) -> str:
    """Mock-only: recover the income band from income (mirrors LOW_TOP/MID_TOP in lease_day_v07)."""
    return "low" if income <= 7000 else "mid" if income < 15000 else "high"


def _strip_private(ctx: Dict[str, Any], decision_name: str) -> Dict[str, Any]:
    """Build clean JSON-serializable prompt payload (removes private _rng and rule-only scoring hints)."""
    out: Dict[str, Any] = {"_decision": decision_name}
    for k, v in ctx.items():
        if k.startswith("_") or k in HIDDEN_TOP_KEYS:
            continue
        if k == "announcement" and v is None:
            continue  # no-line state: omit the key entirely, not just its value
        if k == "landlord" and isinstance(v, dict):
            out[k] = {lk: lv for lk, lv in v.items() if lk not in HIDDEN_LANDLORD_KEYS}
        elif k == "tenant" and isinstance(v, dict):
            hidden = HIDDEN_TENANT_KEYS if decision_name == "at_expiry" else HIDDEN_TENANT_KEYS_SEARCH
            out[k] = {tk: tv for tk, tv in v.items() if tk not in hidden}
        elif k == "zone_vacancy_smooth":
            # Shown as a percentage: round-1 diagnostics suggested 0.13 was read as "low vacancy"
            out["zone_vacancy_pct"] = round(v * 100, 2)
        elif k == "current_room" and isinstance(v, dict):
            out[k] = _card_for_prompt(v, HIDDEN_CUR_KEYS)
        elif k == "candidates" and isinstance(v, list):
            out[k] = [_card_for_prompt(c, HIDDEN_CAND_KEYS) for c in v]
        elif k == "applicants" and isinstance(v, list):
            out[k] = [{ak: av for ak, av in a.items() if ak not in HIDDEN_APPLICANT_KEYS} for a in v]
        else:
            out[k] = v
    return out


class _LLMBase:
    def __init__(
        self,
        backend: LLMBackend,
        cache: Optional[DiskCache] = None,
        prompts_dir: Path = PROMPTS_DIR,
    ):
        self.backend = backend
        self.cache = cache
        self.prompts_dir = Path(prompts_dir)
        self._templates: Dict[str, str] = {}

    def _get_template(self, filename: str) -> str:
        if filename not in self._templates:
            self._templates[filename] = (self.prompts_dir / filename).read_text(encoding="utf-8").strip()
        return self._templates[filename]

    def _query_and_validate(
        self,
        prompt_file: str,
        decision_name: str,
        ctx: Dict[str, Any],
        validator: Callable[[Dict[str, Any], Dict[str, Any]], Tuple[Optional[Dict[str, Any]], str]],
        fallback_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
        system_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        sys_prompt = system_override if system_override is not None else self._get_template(prompt_file)
        payload = _strip_private(ctx, decision_name)
        user_prompt = render_user_prompt(payload)
        p_hash = hashlib.sha256((sys_prompt + "\n---\n" + user_prompt).encode("utf-8")).hexdigest()[:24]
        cache_key = f"{self.backend.model}|{self.backend.temperature}|{p_hash}"

        total_tokens = 0
        cached_hit = False

        # Attempt 1 (check cache first)
        raw_text = None
        if self.cache is not None:
            got = self.cache.get(cache_key)
            if got is not None:
                raw_text, total_tokens = got
                cached_hit = True

        if raw_text is None:
            try:
                raw_text, toks = self.backend.complete(sys_prompt, user_prompt)
                total_tokens += toks
            except Exception as exc:
                fb = fallback_fn(ctx)
                fb["_meta"] = {"prompt_hash": p_hash, "tokens": total_tokens, "fallback": True, "error": str(exc), "cached": False}
                return fb

        parsed = _extract_json(raw_text)
        validated, err = validator(parsed, ctx) if parsed is not None else (None, "json_parse_error")

        # Retry once if invalid (§4.3)
        if validated is None:
            spec = output_format_spec(self._get_template(prompt_file))
            retry_prompt = user_prompt + f"\n\n上一次输出不合法（原因：{err}）。请修正并仅输出合法 JSON。\n{spec}"
            try:
                raw_text2, toks2 = self.backend.complete(sys_prompt, retry_prompt)
                total_tokens += toks2
                parsed2 = _extract_json(raw_text2)
                validated, err = validator(parsed2, ctx) if parsed2 is not None else (None, "json_parse_error_retry")
                if validated is not None:
                    raw_text = raw_text2
            except Exception as exc:
                err = f"retry_exception:{exc}"

        if validated is None:
            fb = fallback_fn(ctx)
            fb["_meta"] = {"prompt_hash": p_hash, "tokens": total_tokens, "fallback": True, "error": err, "cached": False}
            return fb

        if self.cache is not None and not cached_hit:
            self.cache.put(cache_key, self.backend.model, self.backend.temperature, p_hash, raw_text, total_tokens)

        validated["_meta"] = {"prompt_hash": p_hash, "tokens": total_tokens, "fallback": False, "cached": cached_hit}
        return validated


class LLMLandlord(_LLMBase, LandlordPolicy):
    def __init__(self, backend: LLMBackend, cache: Optional[DiskCache] = None, prompts_dir: Path = PROMPTS_DIR):
        super().__init__(backend, cache, prompts_dir)
        self._fb = RuleLandlord()

    def renewal_offer(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        return self._query_and_validate("landlord_renewal_offer.txt", "renewal_offer", ctx, validate_renewal_offer, self._fb.renewal_offer)

    def answer_counter(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        return self._query_and_validate("landlord_answer_counter.txt", "answer_counter", ctx, validate_answer_counter, self._fb.answer_counter)

    def price_vacant(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        return self._query_and_validate("landlord_price_vacant.txt", "price_vacant", ctx, validate_price_vacant, self._fb.price_vacant)

    def pick_applicant(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        return self._query_and_validate("landlord_pick_applicant.txt", "pick_applicant", ctx, validate_pick_applicant, self._fb.pick_applicant)


class LLMTenant(_LLMBase, TenantPolicy):
    def __init__(self, backend: LLMBackend, cache: Optional[DiskCache] = None, prompts_dir: Path = PROMPTS_DIR):
        super().__init__(backend, cache, prompts_dir)
        self._fb = RuleTenant()

    def at_expiry(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        return self._query_and_validate("tenant_at_expiry.txt", "at_expiry", ctx, validate_at_expiry, self._fb.at_expiry)

    def search(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        return self._query_and_validate("tenant_search.txt", "search", ctx, validate_search, self._fb.search)
