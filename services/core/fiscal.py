import asyncio
import logging
import sys
import uuid
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone
from typing import Optional

# Path to gbil-fiscal packages
GBIL_FISCAL_PATH = Path(__file__).parent.parent.parent.parent / "gbil-fiscal"

sys.path.insert(0, str(GBIL_FISCAL_PATH / "shared"))
sys.path.insert(0, str(GBIL_FISCAL_PATH / "packages" / "core"))
sys.path.insert(0, str(GBIL_FISCAL_PATH / "packages" / "noop"))

from gbil.fiscal_core import FiscalComplianceService
from gbil.fiscal_noop import NoopAdapter
from fiscal_types import (
    Sale as FiscalSale,
    SaleLine as FiscalSaleLine,
    SalePayment as FiscalSalePayment
)

logger = logging.getLogger("alpine.fiscal")

# Singleton fiscal service
_fiscal_service: FiscalComplianceService | None = None


async def get_fiscal_service() -> FiscalComplianceService:
    global _fiscal_service
    if _fiscal_service is None:
        # Load noop adapter by default
        # When MRA creds arrive — swap adapter here
        adapter = NoopAdapter()
        _fiscal_service = FiscalComplianceService(
            adapter=adapter,
            storage_path="/tmp/alpine_fiscal"
        )
        await _fiscal_service.init()
        logger.info(
            f"Fiscal service initialized: "
            f"{adapter.provider_name}"
        )
    return _fiscal_service


def build_fiscal_sale(
    sale_id: str,
    tenant_id: str,
    terminal_id: str,
    cashier_id: str,
    lines: list[dict],
    payments: list[dict],
    subtotal: float,
    tax: float,
    total: float,
    receipt_counter: int
) -> FiscalSale:
    """
    Convert Alpine sale data to FiscalSale type.
    """
    return FiscalSale(
        id=str(sale_id),
        tenant_id=str(tenant_id),
        terminal_id=str(terminal_id),
        cashier_id=str(cashier_id),
        lines=[
            FiscalSaleLine(
                product_id=str(line.get("product_id", "")),
                name=line.get("name", "Product"),
                quantity=Decimal(str(line.get("quantity", 1))),
                unit_price=Decimal(
                    str(line.get("unit_price", 0))
                ),
                tax_rate=Decimal("0.165"),
                tax_amount=Decimal(
                    str(line.get("tax", 0))
                ),
                line_total=Decimal(
                    str(line.get("line_total", 0))
                ),
                unspsc_code=line.get("unspsc_code")
            )
            for line in lines
        ],
        payments=[
            FiscalSalePayment(
                method=p.get("method", "cash"),
                amount=Decimal(str(p.get("amount", 0)))
            )
            for p in payments
        ],
        subtotal=Decimal(str(subtotal)),
        tax=Decimal(str(tax)),
        total=Decimal(str(total)),
        receipt_counter=receipt_counter,
        timestamp=datetime.now(timezone.utc)
    )
