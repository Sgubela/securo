from __future__ import annotations

import base64
from datetime import date
from decimal import Decimal
from unittest.mock import patch

import httpx
import pytest

from app.providers.trading212 import Trading212Provider


ACCOUNT_SUMMARY = {
    "id": 123456789,
    "currency": "EUR",
    "cash": {
        "availableToTrade": 100.10,
        "inPies": 25.40,
        "reservedForOrders": 4.50,
    },
    "investments": {
        "currentValue": 1000.00,
        "totalCost": 900.00,
        "realizedProfitLoss": 12.34,
        "unrealizedProfitLoss": 100.00,
    },
    "totalValue": 1130.00,
}

POSITIONS = [
    {
        "ticker": "AAPL_US_EQ",
        "quantity": 2.5,
        "quantityInPies": 0.5,
        "averagePricePaid": 180.12,
        "currentPrice": 200.34,
        "instrument": {
            "ticker": "AAPL_US_EQ",
            "name": "Apple Inc.",
            "isin": "US0378331005",
            "currency": "USD",
        },
        "walletImpact": {
            "currency": "EUR",
            "currentValue": 501.00,
            "totalCost": 450.00,
            "unrealizedProfitLoss": 51.00,
        },
    }
]

HISTORY_TRANSACTIONS = [
    {
        "reference": "dep-1",
        "type": "DEPOSIT",
        "amount": 1000.00,
        "currency": "EUR",
        "dateTime": "2026-01-02T10:00:00Z",
    },
    {
        "reference": "wd-1",
        "type": "WITHDRAW",
        "amount": 200.00,
        "currency": "EUR",
        "dateTime": "2026-01-05T10:00:00Z",
    },
    {
        "reference": "fee-1",
        "type": "FEE",
        "amount": 1.50,
        "currency": "EUR",
        "dateTime": "2026-01-06T10:00:00Z",
    },
    {
        "reference": "transfer-1",
        "type": "TRANSFER",
        "amount": 10.00,
        "currency": "EUR",
        "dateTime": "2026-01-07T10:00:00Z",
    },
]

DIVIDENDS = [
    {
        "reference": "div-1",
        "type": "DIVIDEND",
        "amount": 5.25,
        "currency": "EUR",
        "ticker": "AAPL_US_EQ",
        "paidOn": "2026-02-01T12:00:00Z",
        "instrument": {"name": "Apple Inc.", "ticker": "AAPL_US_EQ"},
    }
]

INTEREST_CSV = """Action,Time,Currency,Total,Reference\nInterest on cash,2026-02-03 08:30:00,EUR,2.75,int-1\n"""


def _patched_client(handler):
    transport = httpx.MockTransport(handler)

    async def fake_client(self, credentials=None):  # noqa: ANN001
        return httpx.AsyncClient(transport=transport, timeout=30)

    return patch.object(Trading212Provider, "_client", fake_client)


@pytest.mark.asyncio
async def test_handle_oauth_callback_validates_key_and_masks_credentials():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["host"] = request.url.host
        seen["authorization"] = request.headers.get("Authorization")
        return httpx.Response(200, json=ACCOUNT_SUMMARY)

    with _patched_client(handler):
        conn = await Trading212Provider().handle_oauth_callback(
            "demo:api-key-123:api-secret-456"
        )

    assert seen["host"] == "demo.trading212.com"
    assert seen["path"] == "/api/v0/equity/account/summary"
    expected = base64.b64encode(b"api-key-123:api-secret-456").decode("ascii")
    assert seen["authorization"] == f"Basic {expected}"
    assert conn.external_id == "123456789"
    assert conn.institution_name == "Trading 212"
    assert conn.accounts == []
    assert conn.credentials["environment"] == "demo"
    assert "api_key" not in conn.credentials
    assert "api_secret" not in conn.credentials
    assert Trading212Provider._api_key(conn.credentials) == "api-key-123"
    assert Trading212Provider._api_secret(conn.credentials) == "api-secret-456"
    assert "api-key-123" not in str(conn.credentials)
    assert "api-secret-456" not in str(conn.credentials)


@pytest.mark.asyncio
async def test_get_accounts_maps_cash_breakdown_to_investment_account():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/api/v0/equity/account/summary"
        return httpx.Response(200, json=ACCOUNT_SUMMARY)

    credentials = {
        "api_key": "api-key-123",
        "api_secret": "api-secret-456",
        "environment": "live",
    }
    with _patched_client(handler):
        accounts = await Trading212Provider().get_accounts(credentials)

    assert len(accounts) == 1
    account = accounts[0]
    assert account.external_id == "trading212:123456789:cash"
    assert account.name == "Trading 212 Cash"
    assert account.type == "investment"
    assert account.currency == "EUR"
    assert account.balance == Decimal("130.00")
    assert account.metadata["trading212"]["cash"]["inPies"] == "25.4"
    assert account.metadata["trading212"]["cash"]["availableToTrade"] == "100.1"
    assert account.metadata["trading212"]["totalValue"] == "1130.0"


@pytest.mark.asyncio
async def test_get_holdings_maps_positions_and_avoids_deprecated_or_write_endpoints():
    called: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        called.append((request.method, request.url.path))
        assert "/pies" not in request.url.path
        assert request.method == "GET"
        if request.url.path == "/api/v0/equity/positions":
            return httpx.Response(200, json=POSITIONS)
        raise AssertionError(f"unexpected endpoint {request.method} {request.url.path}")

    with _patched_client(handler):
        holdings = await Trading212Provider().get_holdings(
            {"api_key": "key", "api_secret": "secret", "environment": "live"}
        )

    assert called == [("GET", "/api/v0/equity/positions")]
    assert len(holdings) == 1
    holding = holdings[0]
    assert holding.external_id == "trading212:position:AAPL_US_EQ"
    assert holding.name == "Apple Inc."
    assert holding.currency == "EUR"
    assert holding.current_value == Decimal("501.00")
    assert holding.quantity == Decimal("2.5")
    assert holding.purchase_price == Decimal("450.00")
    assert holding.isin == "US0378331005"
    assert holding.metadata["trading212"]["quantityInPies"] == "0.5"
    assert holding.metadata["trading212"]["instrument"]["currency"] == "USD"
    assert holding.metadata["trading212"]["walletImpact"]["currentValue"] == "501.0"


@pytest.mark.asyncio
async def test_paginated_history_uses_next_page_path_only():
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(str(request.url.path) + (f"?{request.url.query.decode()}" if request.url.query else ""))
        assert request.method == "GET"
        assert "/pies" not in request.url.path
        if request.url.params.get("cursor") == "abc":
            return httpx.Response(200, json={"items": [{"reference": "second"}]})
        return httpx.Response(
            200,
            json={
                "items": [{"reference": "first"}],
                "nextPagePath": "/api/v0/equity/history/transactions?limit=50&cursor=abc",
            },
        )

    with _patched_client(handler):
        items = await Trading212Provider().get_history_transactions(
            {"api_key": "key", "api_secret": "secret", "environment": "demo"},
            limit=50,
        )

    assert [item["reference"] for item in items] == ["first", "second"]
    assert paths == [
        "/api/v0/equity/history/transactions?limit=50",
        "/api/v0/equity/history/transactions?limit=50&cursor=abc",
    ]


@pytest.mark.asyncio
async def test_request_export_is_disabled_for_read_only_safety():
    with pytest.raises(NotImplementedError):
        await Trading212Provider().request_export(
            {"api_key": "key", "api_secret": "secret", "environment": "demo"},
            "2026-01-01T00:00:00Z",
            "2026-02-01T00:00:00Z",
        )


@pytest.mark.asyncio
async def test_download_export_rejects_non_trading212_urls_before_sending_auth():
    with pytest.raises(ValueError):
        await Trading212Provider().download_export(
            {"api_key": "key", "api_secret": "secret", "environment": "demo"},
            "https://example.invalid/export.csv",
        )


@pytest.mark.asyncio
async def test_download_export_reconstructs_url_on_configured_trading212_host():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["host"] = request.url.host
        seen["path"] = request.url.path
        seen["query"] = request.url.query.decode()
        seen["authorization"] = request.headers.get("Authorization")
        return httpx.Response(200, text="Action,Time,Currency,Total,Reference\n")

    credentials = Trading212Provider._parse_token("demo:key:secret")
    with _patched_client(handler):
        csv_text = await Trading212Provider().download_export(
            credentials,
            "https://demo.trading212.com/api/v0/equity/history/exports/file-1/download?format=csv",
        )

    assert csv_text.startswith("Action,Time")
    assert seen["method"] == "GET"
    assert seen["host"] == "demo.trading212.com"
    assert seen["path"] == "/api/v0/equity/history/exports/file-1/download"
    assert seen["query"] == "format=csv"
    expected = base64.b64encode(b"key:secret").decode("ascii")
    assert seen["authorization"] == f"Basic {expected}"


@pytest.mark.asyncio
async def test_get_transactions_maps_cash_dividends_interest_and_internal_transfers():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert "/pies" not in request.url.path
        if request.url.path == "/api/v0/equity/history/transactions":
            return httpx.Response(200, json={"items": HISTORY_TRANSACTIONS})
        if request.url.path == "/api/v0/equity/history/dividends":
            return httpx.Response(200, json={"items": DIVIDENDS})
        raise AssertionError(f"unexpected endpoint {request.method} {request.url.path}")

    credentials = {
        "api_key": "key",
        "api_secret": "secret",
        "environment": "demo",
        "interest_export_csv": INTEREST_CSV,
    }
    with _patched_client(handler):
        txs = await Trading212Provider().get_transactions(
            credentials, "trading212:123456789:cash"
        )

    by_external_id = {tx.external_id: tx for tx in txs}
    assert by_external_id["t212:cash:dep-1"].type == "credit"
    assert by_external_id["t212:cash:dep-1"].amount == Decimal("1000.0")
    assert by_external_id["t212:cash:dep-1"].date == date(2026, 1, 2)
    assert by_external_id["t212:cash:wd-1"].type == "debit"
    assert by_external_id["t212:cash:wd-1"].amount == Decimal("200.0")
    assert by_external_id["t212:cash:fee-1"].type == "debit"
    assert by_external_id["t212:cash:transfer-1"].is_ignored is True
    assert by_external_id["t212:dividend:div-1"].type == "credit"
    assert by_external_id["t212:dividend:div-1"].description == "Trading 212 dividend AAPL_US_EQ"
    assert by_external_id["t212:interest:int-1"].type == "credit"
    assert by_external_id["t212:interest:int-1"].amount == Decimal("2.75")
    assert by_external_id["t212:cash:dep-1"].raw_data["trading212"]["source"] == "history/transactions"


@pytest.mark.asyncio
async def test_get_transactions_filters_before_history_start_date():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        if request.url.path == "/api/v0/equity/history/transactions":
            return httpx.Response(200, json={"items": HISTORY_TRANSACTIONS})
        if request.url.path == "/api/v0/equity/history/dividends":
            return httpx.Response(200, json={"items": DIVIDENDS})
        raise AssertionError(f"unexpected endpoint {request.method} {request.url.path}")

    credentials = {
        "api_key": "key",
        "api_secret": "secret",
        "environment": "demo",
        "interest_export_csv": INTEREST_CSV,
    }
    with _patched_client(handler):
        txs = await Trading212Provider().get_transactions(
            credentials, "trading212:123456789:cash", since=date(2026, 1, 4)
        )

    external_ids = {tx.external_id for tx in txs}
    assert "t212:cash:dep-1" not in external_ids
    assert "t212:cash:wd-1" in external_ids
    assert "t212:dividend:div-1" in external_ids
    assert "t212:interest:int-1" in external_ids


def test_parse_interest_export_csv_accepts_common_export_columns():
    txs = Trading212Provider.parse_interest_export_csv(INTEREST_CSV)

    assert len(txs) == 1
    assert txs[0].external_id == "t212:interest:int-1"
    assert txs[0].description == "Trading 212 interest"
    assert txs[0].amount == Decimal("2.75")
    assert txs[0].currency == "EUR"
    assert txs[0].date == date(2026, 2, 3)
