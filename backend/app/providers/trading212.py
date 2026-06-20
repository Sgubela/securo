"""Read-only Trading 212 brokerage provider.

Trading 212 exposes account summary, positions, and history endpoints behind
HTTP Basic auth. This provider intentionally implements only read methods. It
must never call order execution/cancel or deprecated pie endpoints.
"""
from __future__ import annotations

import base64
import csv
import hashlib
import io
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

from app.agents.services.crypto import decrypt, encrypt
from app.providers.base import AccountData, BankProvider, ConnectionData, HoldingData, TransactionData

TRADING212_LIVE_BASE_URL = "https://live.trading212.com"
TRADING212_DEMO_BASE_URL = "https://demo.trading212.com"
TRADING212_TIMEOUT = 30.0

_READ_ONLY_PATHS = frozenset(
    {
        "/api/v0/equity/account/summary",
        "/api/v0/equity/positions",
        "/api/v0/equity/history/transactions",
        "/api/v0/equity/history/dividends",
        "/api/v0/equity/history/orders",
        "/api/v0/equity/history/exports",
        "/api/v0/equity/metadata/instruments",
        "/api/v0/equity/metadata/exchanges",
        "/api/v0/equity/orders",
    }
)


def _to_decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    if value is None or value == "":
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return default


def _decimal_string(value: Any) -> str:
    return str(_to_decimal(value))


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, float):
        return str(Decimal(str(value)))
    return value


def _parse_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    text = str(value or "").strip()
    if not text:
        return date.today()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    for fmt in (None, "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            parsed = datetime.fromisoformat(text) if fmt is None else datetime.strptime(text, fmt)
            return parsed.date()
        except ValueError:
            continue
    return date.today()


def _raw(source: str, payload: dict) -> dict:
    return {"trading212": {"source": source, "payload": _json_safe(payload)}}


def _stable_row_id(row: dict) -> str:
    seed = "|".join(str(row.get(k) or "") for k in sorted(row))
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


class Trading212Provider(BankProvider):
    """Trading 212 read-only brokerage connector."""

    @property
    def name(self) -> str:
        return "trading212"

    @property
    def flow_type(self) -> str:
        return "token"

    @property
    def kind(self) -> str:
        return "brokerage"

    async def _client(self, credentials: dict | None = None) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=TRADING212_TIMEOUT)

    @staticmethod
    def _base_url(credentials: dict) -> str:
        env = str((credentials or {}).get("environment") or "live").lower()
        if env == "demo":
            return TRADING212_DEMO_BASE_URL
        return TRADING212_LIVE_BASE_URL

    @staticmethod
    def _api_key(credentials: dict) -> str:
        enc = (credentials or {}).get("api_key_enc")
        if enc:
            decoded = decrypt(enc)
            if decoded:
                return decoded
        # Dev/test/legacy compatibility: older locally-created connections and
        # tests may still carry a plaintext key. New callbacks store only
        # api_key_enc so both Basic auth components are encrypted at rest.
        return (credentials or {}).get("api_key") or ""

    @staticmethod
    def _api_secret(credentials: dict) -> str:
        enc = (credentials or {}).get("api_secret_enc")
        if enc:
            decoded = decrypt(enc)
            if decoded:
                return decoded
        # Dev/test compatibility: allow plaintext in injected fixtures but never
        # store it from handle_oauth_callback.
        return (credentials or {}).get("api_secret") or ""

    @classmethod
    def _auth_header(cls, credentials: dict) -> str:
        api_key = cls._api_key(credentials)
        api_secret = cls._api_secret(credentials)
        if not api_key or not api_secret:
            raise ValueError("Trading 212 API key and secret are required")
        token = base64.b64encode(f"{api_key}:{api_secret}".encode("utf-8")).decode("ascii")
        return f"Basic {token}"

    @staticmethod
    def _parse_token(raw: str) -> dict:
        """Parse the pasted Trading 212 credential payload.

        Accepted minimal format for the existing token callback surface:
        ``demo:<api_key>:<api_secret>`` or ``live:<api_key>:<api_secret>``.
        If no environment prefix is supplied, live is used.
        """
        parts = (raw or "").strip().split(":", 2)
        if len(parts) == 3 and parts[0].lower() in {"demo", "live"}:
            environment, api_key, api_secret = parts[0].lower(), parts[1].strip(), parts[2].strip()
        elif len(parts) == 2:
            environment, api_key, api_secret = "live", parts[0].strip(), parts[1].strip()
        else:
            raise ValueError(
                "Trading 212 credentials must be '<api_key>:<api_secret>' or "
                "'<demo|live>:<api_key>:<api_secret>'"
            )
        if not api_key or not api_secret:
            raise ValueError("Trading 212 API key and secret are required")
        return {
            "api_key_enc": encrypt(api_key),
            "api_secret_enc": encrypt(api_secret),
            "environment": environment,
        }

    async def _get_json(self, credentials: dict, path: str, params: Optional[dict] = None) -> Any:
        if path not in _READ_ONLY_PATHS:
            raise ValueError(f"Trading 212 endpoint is not allowed: {path}")
        if "/pies" in path:
            raise ValueError("Deprecated Trading 212 pie endpoints are not allowed")
        headers = {
            "Accept": "application/json",
            "Authorization": self._auth_header(credentials),
            "User-Agent": "Securo/0.1",
        }
        async with await self._client(credentials) as client:
            response = await client.get(
                f"{self._base_url(credentials)}{path}", params=params, headers=headers
            )
        response.raise_for_status()
        return response.json() or {}

    async def _get_paginated(self, credentials: dict, path: str, params: Optional[dict] = None) -> list[dict]:
        items: list[dict] = []
        next_path: Optional[str] = path
        next_params = params or {}
        while next_path:
            data = await self._get_json(credentials, next_path, next_params)
            page_items = data.get("items") if isinstance(data, dict) else data
            if isinstance(page_items, list):
                items.extend(page_items)
            next_page = data.get("nextPagePath") if isinstance(data, dict) else None
            if not next_page:
                break
            if "?" in next_page:
                next_path, query = next_page.split("?", 1)
                next_params = dict(httpx.QueryParams(query))
            else:
                next_path, next_params = next_page, {}
        return items

    def get_oauth_url(self, *args, **kwargs):  # type: ignore[override]
        raise NotImplementedError("Trading 212 uses an API key token flow, not OAuth redirect")

    async def handle_oauth_callback(self, code: str) -> ConnectionData:
        credentials = self._parse_token(code)
        summary = await self.get_account_summary(credentials)
        account_id = str(summary.get("id") or "")
        if not account_id:
            raise ValueError("Trading 212 account summary did not include an account id")
        return ConnectionData(
            external_id=account_id,
            institution_name="Trading 212",
            credentials=credentials,
            accounts=[],
        )

    async def get_account_summary(self, credentials: dict) -> dict:
        return await self._get_json(credentials, "/api/v0/equity/account/summary")

    async def get_positions(self, credentials: dict) -> list[dict]:
        data = await self._get_json(credentials, "/api/v0/equity/positions")
        return data if isinstance(data, list) else data.get("items", [])

    async def get_history_transactions(self, credentials: dict, limit: int = 50) -> list[dict]:
        return await self._get_paginated(
            credentials, "/api/v0/equity/history/transactions", {"limit": str(limit)}
        )

    async def get_dividends(self, credentials: dict, limit: int = 50) -> list[dict]:
        return await self._get_paginated(
            credentials, "/api/v0/equity/history/dividends", {"limit": str(limit)}
        )

    async def get_historical_orders(self, credentials: dict, limit: int = 50) -> list[dict]:
        return await self._get_paginated(
            credentials, "/api/v0/equity/history/orders", {"limit": str(limit)}
        )

    async def request_export(
        self,
        credentials: dict,
        time_from: str,
        time_to: str,
        *,
        include_interest: bool = True,
        include_dividends: bool = False,
        include_orders: bool = False,
        include_transactions: bool = False,
    ) -> dict:
        raise NotImplementedError(
            "Trading 212 export creation is disabled in Securo's read-only connector. "
            "Use the normal history endpoints or import a CSV generated directly in Trading 212."
        )

    async def list_exports(self, credentials: dict) -> list[dict]:
        data = await self._get_json(credentials, "/api/v0/equity/history/exports")
        return data if isinstance(data, list) else []

    async def download_export(self, credentials: dict, download_link: str) -> str:
        download_url = self._safe_export_download_url(credentials, download_link)
        headers = {
            "Accept": "text/csv,*/*",
            "Authorization": self._auth_header(credentials),
            "User-Agent": "Securo/0.1",
        }
        async with await self._client(credentials) as client:
            response = await client.get(download_url, headers=headers)
        response.raise_for_status()
        return response.text

    def _safe_export_download_url(self, credentials: dict, download_link: str) -> str:
        """Build a Trading 212-only export download URL.

        Never forward the Basic auth header to an arbitrary URL from the API
        payload. Relative links are resolved against the configured live/demo
        Trading 212 base URL; absolute links must already point to that same
        host and are then reconstructed from our trusted base URL.
        """
        base_url = self._base_url(credentials)
        base = urlparse(base_url)
        parsed = urlparse(str(download_link or "").strip())
        if not parsed.scheme and not parsed.netloc:
            path = parsed.path if parsed.path.startswith("/") else f"/{parsed.path}"
            query = parsed.query
        else:
            if parsed.scheme != "https" or parsed.hostname != base.hostname:
                raise ValueError("Trading 212 export download URL must use the configured Trading 212 host")
            if parsed.username or parsed.password:
                raise ValueError("Trading 212 export download URL must not contain credentials")
            path = parsed.path
            query = parsed.query
        if not path.startswith("/api/"):
            raise ValueError("Trading 212 export download URL must be an API path")
        return f"{base_url}{path}" + (f"?{query}" if query else "")

    async def get_accounts(self, credentials: dict) -> list[AccountData]:
        summary = await self.get_account_summary(credentials)
        cash = summary.get("cash") or {}
        account_id = str(summary.get("id") or "unknown")
        cash_total = (
            _to_decimal(cash.get("availableToTrade"))
            + _to_decimal(cash.get("inPies"))
            + _to_decimal(cash.get("reservedForOrders"))
        )
        metadata = {
            "trading212": {
                "accountId": account_id,
                "cash": _json_safe(cash),
                "investments": _json_safe(summary.get("investments") or {}),
                "totalValue": _decimal_string(summary.get("totalValue")),
            }
        }
        return [
            AccountData(
                external_id=f"trading212:{account_id}:cash",
                name="Trading 212 Cash",
                type="investment",
                balance=cash_total,
                currency=str(summary.get("currency") or "EUR"),
                metadata=metadata,
            )
        ]

    async def get_transactions(
        self, credentials: dict, account_external_id: str, since=None, payee_source: str = "auto"
    ) -> list[TransactionData]:
        transactions = [
            self._map_history_transaction(item)
            for item in await self.get_history_transactions(credentials)
        ]
        transactions.extend(
            self._map_dividend(item) for item in await self.get_dividends(credentials)
        )
        csv_text = (credentials or {}).get("interest_export_csv")
        if csv_text:
            transactions.extend(self.parse_interest_export_csv(str(csv_text)))
        if since is not None:
            cutoff = since.date() if isinstance(since, datetime) else since
            transactions = [tx for tx in transactions if tx.date >= cutoff]
        return transactions

    @staticmethod
    def _map_history_transaction(item: dict) -> TransactionData:
        tx_type = str(item.get("type") or "").upper()
        amount = abs(_to_decimal(item.get("amount")))
        is_credit = tx_type == "DEPOSIT" or (_to_decimal(item.get("amount")) > 0 and tx_type == "TRANSFER")
        is_ignored = tx_type == "TRANSFER"
        reference = item.get("reference") or _stable_row_id(item)
        return TransactionData(
            external_id=f"t212:cash:{reference}",
            description=f"Trading 212 {tx_type.lower()}",
            amount=amount,
            date=_parse_date(item.get("dateTime")),
            type="credit" if is_credit else "debit",
            currency=item.get("currency"),
            raw_data=_raw("history/transactions", item),
            is_ignored=is_ignored,
        )

    @staticmethod
    def _map_dividend(item: dict) -> TransactionData:
        ticker = item.get("ticker") or (item.get("instrument") or {}).get("ticker") or ""
        reference = item.get("reference") or _stable_row_id(item)
        description = "Trading 212 dividend" + (f" {ticker}" if ticker else "")
        return TransactionData(
            external_id=f"t212:dividend:{reference}",
            description=description,
            amount=abs(_to_decimal(item.get("amount"))),
            date=_parse_date(item.get("paidOn")),
            type="credit",
            currency=item.get("currency"),
            raw_data=_raw("history/dividends", item),
        )

    @staticmethod
    def parse_interest_export_csv(csv_text: str) -> list[TransactionData]:
        rows = csv.DictReader(io.StringIO(csv_text or ""))
        transactions: list[TransactionData] = []
        for row in rows:
            normalized = {str(k or "").strip().lower(): v for k, v in row.items()}
            action = str(normalized.get("action") or normalized.get("type") or "").lower()
            if "interest" not in action:
                continue
            amount_raw = (
                normalized.get("total")
                or normalized.get("amount")
                or normalized.get("value")
                or normalized.get("net amount")
            )
            amount = _to_decimal(str(amount_raw or "").replace(",", ""))
            if amount == 0:
                continue
            reference = normalized.get("reference") or normalized.get("id") or _stable_row_id(row)
            when = normalized.get("time") or normalized.get("date") or normalized.get("date/time")
            currency = normalized.get("currency") or normalized.get("currency code")
            transactions.append(
                TransactionData(
                    external_id=f"t212:interest:{reference}",
                    description="Trading 212 interest",
                    amount=abs(amount),
                    date=_parse_date(when),
                    type="credit" if amount >= 0 else "debit",
                    currency=str(currency or "").upper() or None,
                    raw_data=_raw("history/exports:interest", row),
                )
            )
        return transactions

    async def refresh_credentials(self, credentials: dict) -> dict:
        return credentials

    async def get_holdings(self, credentials: dict) -> list[HoldingData]:
        positions = await self.get_positions(credentials)
        holdings: list[HoldingData] = []
        for position in positions:
            instrument = position.get("instrument") or {}
            wallet = position.get("walletImpact") or {}
            ticker = position.get("ticker") or instrument.get("ticker")
            if not ticker:
                continue
            metadata = {
                "trading212": _json_safe(
                    {
                        **position,
                        "quantityInPies": _decimal_string(position.get("quantityInPies")),
                        "instrument": instrument,
                        "walletImpact": wallet,
                    }
                )
            }
            holdings.append(
                HoldingData(
                    external_id=f"trading212:position:{ticker}",
                    name=instrument.get("name") or ticker,
                    currency=str(wallet.get("currency") or position.get("currency") or "EUR"),
                    current_value=_to_decimal(wallet.get("currentValue")),
                    quantity=_to_decimal(position.get("quantity")),
                    unit_price=_to_decimal(position.get("currentPrice")),
                    purchase_price=_to_decimal(wallet.get("totalCost")),
                    isin=instrument.get("isin"),
                    metadata=metadata,
                )
            )
        return holdings
