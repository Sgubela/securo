# Trading 212 read-only brokerage connection

Securo can connect to Trading 212 as a brokerage provider. The integration is read-only: it imports cash, current positions, dividends, interest exports, and historical order fills for portfolio tracking, but it does not place trades, cancel orders, or call deprecated pie write endpoints.

## Create Trading 212 credentials

1. In Trading 212, create an API key/secret for the account you want to track.
2. Grant only the read scopes Securo needs:
   - `account`
   - `portfolio`
   - `metadata`
   - `history:transactions`
   - `history:dividends`
   - `history:orders`
3. Do not grant write or trading scopes, including:
   - `orders:execute`
   - order cancellation/write scopes
   - `pies:write`

Securo stores both the API key and API secret encrypted server-side and never returns them to the frontend.

## Connect in Securo

1. Open Accounts.
2. Click Connect account.
3. Choose Trading 212 under brokerage providers.
4. Select Live or Demo.
5. Paste the API key and API secret.
6. Leave “Import history on first sync” enabled if you want deposits, withdrawals, fees, dividends, interest exports, and historical order fills imported during the first sync.
7. Optionally set a history start date to limit the first import window.

After connection, Securo shows a Trading 212 Cash account under Brokerage Connections. Holdings are synced as assets grouped under the Trading 212 wallet/group.

## Read-only guarantees

The provider allow-list only includes read endpoints for account summary, positions, instruments, history transactions, dividends, historical orders, and report export listing. Securo rejects deprecated `/api/v0/equity/pies*` endpoints, does not implement order execution/cancellation calls, and deliberately disables Trading 212 export creation (`POST /api/v0/equity/history/exports`). Export download links are resolved only against the configured Trading 212 live/demo host before the Authorization header is attached.

Disabling “Import history” skips Trading 212 cash history and historical order/fill import entirely while still syncing the current cash account and positions. Setting a history start date limits which fetched history rows are stored in Securo.

Trade history is imported for accounting only. Buy/sell fills create investment ledger entries and matching cash settlements are ignored/internal so they do not appear as ordinary spending or income.
