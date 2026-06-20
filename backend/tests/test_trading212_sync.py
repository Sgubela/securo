from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.asset import Asset
from app.models.asset_transaction import AssetTransaction
from app.models.asset_group import AssetGroup
from app.models.asset_value import AssetValue
from app.models.bank_connection import BankConnection
from app.models.transaction import Transaction
from app.models.user import User
from app.providers import register_provider
from app.providers.trading212 import Trading212Provider
from app.services.connection_service import sync_connection
from app.services.transaction_service import get_transactions


SUMMARY_ONE = {
    "id": 222333444,
    "currency": "EUR",
    "cash": {"availableToTrade": 100.10, "inPies": 25.40, "reservedForOrders": 4.50},
    "investments": {"currentValue": 501.0, "totalCost": 450.0},
    "totalValue": 631.0,
}

SUMMARY_TWO = {
    "id": 222333444,
    "currency": "EUR",
    "cash": {"availableToTrade": 120.00, "inPies": 5.00, "reservedForOrders": 0.00},
    "investments": {"currentValue": 520.0, "totalCost": 450.0},
    "totalValue": 645.0,
}

POSITIONS_ONE = [
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
        "walletImpact": {"currency": "EUR", "currentValue": 501.0, "totalCost": 450.0},
    }
]

POSITIONS_TWO = [
    {
        **POSITIONS_ONE[0],
        "quantity": 3.0,
        "quantityInPies": 1.0,
        "walletImpact": {"currency": "EUR", "currentValue": 520.0, "totalCost": 450.0},
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
        "reference": "fee-1",
        "type": "FEE",
        "amount": 1.50,
        "currency": "EUR",
        "dateTime": "2026-01-03T10:00:00Z",
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

HISTORICAL_ORDERS = [
    {
        "order": {
            "id": 9001,
            "ticker": "AAPL_US_EQ",
            "side": "BUY",
            "currency": "USD",
            "instrument": {
                "ticker": "AAPL_US_EQ",
                "name": "Apple Inc.",
                "isin": "US0378331005",
                "currency": "USD",
            },
        },
        "fill": {
            "id": 7001,
            "type": "TRADE",
            "filledAt": "2026-01-10T14:30:00Z",
            "quantity": 1.0,
            "price": 100.00,
            "walletImpact": {
                "currency": "EUR",
                "netValue": -95.00,
                "taxes": [{"name": "TRANSACTION_FEE", "quantity": 0.50, "currency": "EUR"}],
            },
        },
    },
    {
        "order": {
            "id": 9002,
            "ticker": "AAPL_US_EQ",
            "side": "BUY",
            "currency": "USD",
            "instrument": {
                "ticker": "AAPL_US_EQ",
                "name": "Apple Inc.",
                "isin": "US0378331005",
                "currency": "USD",
            },
        },
        "fill": {
            "id": 7002,
            "type": "TRADE",
            "filledAt": "2026-01-11T14:30:00Z",
            "quantity": 2.0,
            "price": 110.00,
            "walletImpact": {"currency": "EUR", "netValue": -209.00, "taxes": []},
        },
    },
    {
        "order": {
            "id": 9003,
            "ticker": "AAPL_US_EQ",
            "side": "SELL",
            "currency": "USD",
            "instrument": {
                "ticker": "AAPL_US_EQ",
                "name": "Apple Inc.",
                "isin": "US0378331005",
                "currency": "USD",
            },
        },
        "fill": {
            "id": 7003,
            "type": "TRADE",
            "filledAt": "2026-02-10T14:30:00Z",
            "quantity": 0.5,
            "price": 120.00,
            "walletImpact": {"currency": "EUR", "netValue": 56.00, "taxes": []},
        },
    },
    {
        "order": {"id": 9004, "ticker": "AAPL_US_EQ", "side": "BUY"},
        "fill": {"id": 7004, "type": "STOCK_SPLIT", "quantity": 1, "price": 0},
    },
]


def _patched_t212_client(summary: dict, positions: list[dict], calls: list[tuple[str, str]]):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        assert request.method == "GET"
        assert "/pies" not in request.url.path
        if request.url.path == "/api/v0/equity/account/summary":
            return httpx.Response(200, json=summary)
        if request.url.path == "/api/v0/equity/positions":
            return httpx.Response(200, json=positions)
        if request.url.path == "/api/v0/equity/history/transactions":
            return httpx.Response(200, json={"items": HISTORY_TRANSACTIONS})
        if request.url.path == "/api/v0/equity/history/dividends":
            return httpx.Response(200, json={"items": DIVIDENDS})
        if request.url.path == "/api/v0/equity/history/orders":
            return httpx.Response(200, json={"items": HISTORICAL_ORDERS})
        raise AssertionError(f"unexpected Trading 212 endpoint {request.method} {request.url.path}")

    transport = httpx.MockTransport(handler)

    async def fake_client(self, credentials=None):  # noqa: ANN001
        return httpx.AsyncClient(transport=transport, timeout=30)

    return pytest.MonkeyPatch.context(), fake_client


@pytest.mark.asyncio
async def test_trading212_sync_creates_cash_account_asset_wallet_and_is_idempotent(
    session: AsyncSession, test_user: User
):
    connection = BankConnection(
        id=uuid.uuid4(),
        user_id=test_user.id,
        provider="trading212",
        kind="brokerage",
        external_id="222333444",
        institution_name="Trading 212",
        credentials={"api_key": "key", "api_secret": "secret", "environment": "demo"},
        status="active",
        created_at=datetime.now(timezone.utc),
    )
    session.add(connection)
    await session.commit()
    register_provider("trading212", Trading212Provider)

    calls: list[tuple[str, str]] = []
    ctx, fake_client = _patched_t212_client(SUMMARY_ONE, POSITIONS_ONE, calls)
    with ctx as mp:
        mp.setattr(Trading212Provider, "_client", fake_client)
        await sync_connection(session, connection.id, connection.workspace_id, test_user.id)
    await session.commit()

    accounts = (
        await session.execute(select(Account).where(Account.connection_id == connection.id))
    ).scalars().all()
    assert len(accounts) == 1
    account = accounts[0]
    assert account.external_id == "trading212:222333444:cash"
    assert account.type == "investment"
    assert account.balance == Decimal("130.00")
    assert account.currency == "EUR"
    assert account.external_metadata["trading212"]["cash"]["inPies"] == "25.4"

    assets = (
        await session.execute(select(Asset).where(Asset.connection_id == connection.id))
    ).scalars().all()
    assert len(assets) == 1
    asset = assets[0]
    assert asset.external_id == "trading212:position:AAPL_US_EQ"
    assert asset.source == "trading212"
    assert asset.type == "investment"
    assert asset.currency == "EUR"
    assert asset.units == Decimal("2.500000")
    assert asset.purchase_price == Decimal("450.00")
    assert asset.isin == "US0378331005"
    assert asset.external_metadata["trading212"]["quantityInPies"] == "0.5"
    assert asset.group_id is not None
    wallet = await session.get(AssetGroup, asset.group_id)
    assert wallet is not None
    assert wallet.name == "Trading 212"

    values = (
        await session.execute(select(AssetValue).where(AssetValue.asset_id == asset.id))
    ).scalars().all()
    assert len(values) == 1
    assert values[0].amount == Decimal("501.00")

    imported_cash = (
        await session.execute(
            select(Transaction).where(
                Transaction.account_id == account.id,
                Transaction.external_id.in_(
                    [
                        "t212:cash:dep-1",
                        "t212:cash:fee-1",
                        "t212:dividend:div-1",
                        "t212:settlement:7001",
                        "t212:settlement:7002",
                        "t212:settlement:7003",
                    ]
                ),
            )
        )
    ).scalars().all()
    cash_by_external_id = {tx.external_id: tx for tx in imported_cash}
    assert cash_by_external_id["t212:cash:dep-1"].type == "credit"
    assert cash_by_external_id["t212:cash:dep-1"].raw_data["trading212"]["source"] == "history/transactions"
    assert cash_by_external_id["t212:cash:fee-1"].type == "debit"
    assert cash_by_external_id["t212:dividend:div-1"].type == "credit"
    assert cash_by_external_id["t212:settlement:7001"].is_ignored is True
    assert cash_by_external_id["t212:settlement:7001"].type == "debit"
    assert cash_by_external_id["t212:settlement:7003"].is_ignored is True
    assert cash_by_external_id["t212:settlement:7003"].type == "credit"

    asset_txs = (
        await session.execute(select(AssetTransaction).where(AssetTransaction.asset_id == asset.id))
    ).scalars().all()
    assert {tx.external_id for tx in asset_txs} == {
        "t212:fill:7001",
        "t212:fill:7002",
        "t212:fill:7003",
    }
    assert [tx.kind for tx in sorted(asset_txs, key=lambda tx: tx.external_id or "")] == [
        "buy",
        "buy",
        "sell",
    ]
    assert {tx.external_id: tx for tx in asset_txs}["t212:fill:7001"].raw_data["fill"]["id"] == 7001

    _, _, summary = await get_transactions(
        session, connection.workspace_id, test_user.id, include_summary=True
    )
    assert summary["expense"] < Decimal("100")
    assert summary["excluded"] >= Decimal("360")

    # Re-sync same account/position with changed balances. Existing rows update;
    # no duplicate cash account, asset, wallet, or same-day value row appears.
    calls.clear()
    ctx, fake_client = _patched_t212_client(SUMMARY_TWO, POSITIONS_TWO, calls)
    with ctx as mp:
        mp.setattr(Trading212Provider, "_client", fake_client)
        await sync_connection(session, connection.id, connection.workspace_id, test_user.id)
    await session.commit()

    accounts = (
        await session.execute(select(Account).where(Account.connection_id == connection.id))
    ).scalars().all()
    assert len(accounts) == 1
    assert accounts[0].balance == Decimal("125.00")
    assert accounts[0].external_metadata["trading212"]["cash"]["inPies"] == "5.0"

    assets = (
        await session.execute(select(Asset).where(Asset.connection_id == connection.id))
    ).scalars().all()
    assert len(assets) == 1
    assert assets[0].units == Decimal("3.000000")
    assert assets[0].external_metadata["trading212"]["quantityInPies"] == "1.0"
    values = (
        await session.execute(select(AssetValue).where(AssetValue.asset_id == assets[0].id))
    ).scalars().all()
    assert len(values) == 1
    assert values[0].amount == Decimal("520.00")
    assert (
        await session.execute(select(Transaction).where(Transaction.external_id.like("t212:%")))
    ).scalars().unique().all().__len__() == 6
    assert (
        await session.execute(select(AssetTransaction).where(AssetTransaction.external_id.like("t212:%")))
    ).scalars().unique().all().__len__() == 3
    assert calls == [
        ("GET", "/api/v0/equity/account/summary"),
        ("GET", "/api/v0/equity/history/transactions"),
        ("GET", "/api/v0/equity/history/dividends"),
        ("GET", "/api/v0/equity/history/orders"),
        ("GET", "/api/v0/equity/positions"),
    ]


@pytest.mark.asyncio
async def test_trading212_sync_respects_disabled_history_import(
    session: AsyncSession, test_user: User
):
    connection = BankConnection(
        id=uuid.uuid4(),
        user_id=test_user.id,
        provider="trading212",
        kind="brokerage",
        external_id="222333444",
        institution_name="Trading 212",
        credentials={"api_key": "key", "api_secret": "secret", "environment": "demo"},
        settings={"trading212": {"history_import_enabled": False}},
        status="active",
        created_at=datetime.now(timezone.utc),
    )
    session.add(connection)
    await session.commit()
    register_provider("trading212", Trading212Provider)

    calls: list[tuple[str, str]] = []
    ctx, fake_client = _patched_t212_client(SUMMARY_ONE, POSITIONS_ONE, calls)
    with ctx as mp:
        mp.setattr(Trading212Provider, "_client", fake_client)
        await sync_connection(session, connection.id, connection.workspace_id, test_user.id)
    await session.commit()

    assert calls == [
        ("GET", "/api/v0/equity/account/summary"),
        ("GET", "/api/v0/equity/positions"),
    ]
    assert (
        await session.execute(select(Transaction).where(Transaction.external_id.like("t212:%")))
    ).scalars().unique().all() == []
    assert (
        await session.execute(select(AssetTransaction).where(AssetTransaction.external_id.like("t212:%")))
    ).scalars().unique().all() == []


@pytest.mark.asyncio
async def test_trading212_sync_applies_history_start_to_imported_rows(
    session: AsyncSession, test_user: User
):
    connection = BankConnection(
        id=uuid.uuid4(),
        user_id=test_user.id,
        provider="trading212",
        kind="brokerage",
        external_id="222333444",
        institution_name="Trading 212",
        credentials={"api_key": "key", "api_secret": "secret", "environment": "demo"},
        settings={"trading212": {"history_start": "2026-01-04"}},
        status="active",
        created_at=datetime.now(timezone.utc),
    )
    session.add(connection)
    await session.commit()
    register_provider("trading212", Trading212Provider)

    calls: list[tuple[str, str]] = []
    ctx, fake_client = _patched_t212_client(SUMMARY_ONE, POSITIONS_ONE, calls)
    with ctx as mp:
        mp.setattr(Trading212Provider, "_client", fake_client)
        await sync_connection(session, connection.id, connection.workspace_id, test_user.id)
    await session.commit()

    rows = (
        await session.execute(select(Transaction).where(Transaction.external_id.like("t212:%")))
    ).scalars().unique().all()
    external_ids = {tx.external_id for tx in rows}
    assert "t212:cash:dep-1" not in external_ids
    assert "t212:cash:fee-1" not in external_ids
    assert "t212:dividend:div-1" in external_ids
    assert {"t212:settlement:7001", "t212:settlement:7002", "t212:settlement:7003"}.issubset(
        external_ids
    )

    asset_txs = (
        await session.execute(select(AssetTransaction).where(AssetTransaction.external_id.like("t212:%")))
    ).scalars().unique().all()
    assert {tx.external_id for tx in asset_txs} == {
        "t212:fill:7001",
        "t212:fill:7002",
        "t212:fill:7003",
    }
    assert min(tx.date for tx in asset_txs) >= date(2026, 1, 4)
