"""Read-only group + member exposure for the agent.

Splits are written through `propose_create_transaction` (with its
`group_id` + `splits` parameters) — there's no `propose_create_split`
tool because splits live attached to the parent transaction, not as
standalone rows.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import group_service
from mcp_server.auth import CallContext
from mcp_server.registry import tool


@tool(
    name="list_groups",
    description=(
        "List the user's expense-sharing groups (Splitwise-style: 'Amigos', "
        "'Roommates', etc.) along with their members. Returns each group "
        "with `members: [{id, name, is_self}]` so a single call gives the "
        "model everything it needs to propose a transaction with equal/"
        "exact/percent splits. The `is_self` flag marks the member that "
        "represents the user (used to compute who-owes-who balances)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "include_archived": {"type": "boolean", "default": False},
        },
        "additionalProperties": False,
    },
    tags=["read", "groups"],
)
async def list_groups(
    *,
    session: AsyncSession,
    ctx: CallContext,
    include_archived: bool = False,
) -> dict[str, Any]:
    groups = await group_service.list_groups(session, ctx.user_id, include_archived=include_archived)
    return {
        "items": [
            {
                "id": str(g.id),
                "name": g.name,
                "kind": g.kind,
                "default_currency": g.default_currency,
                "is_archived": bool(g.is_archived),
                "members": [
                    {
                        "id": str(m.id),
                        "name": m.name,
                        "is_self": bool(m.is_self),
                    }
                    for m in (g.members or [])
                ],
            }
            for g in groups
        ],
        "total": len(groups),
    }
