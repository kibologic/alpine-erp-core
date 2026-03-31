import logging
import sys
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

# Country → provider mapping
COUNTRY_PROVIDER_MAP = {
    "MW": "mra",      # Malawi → MRA EIS
    "ZW": "zimra",    # Zimbabwe → ZIMRA FDMS
    "KE": "kra",      # Kenya → KRA eTIMS
    "UG": "ura",      # Uganda → URA EFRIS
    "TZ": "tza",      # Tanzania → TRA
    "default": "noop" # Everything else → noop
}

# Per-tenant cache: tenant_id → FiscalComplianceService
_fiscal_services: dict[str, FiscalComplianceService] = {}


def _load_adapter(provider: str, fiscal_config: dict):
    """
    Load the correct adapter for a provider string.
    Add new adapters here as they are certified.
    """
    if provider == "mra":
        # MRA EIS — Malawi
        # Requires credentials in fiscal_config: terminal_id, token, tpin
        try:
            from gbil.fiscal_mra import MRAEISAdapter
            return MRAEISAdapter(
                terminal_id=fiscal_config.get("terminal_id", ""),
                token=fiscal_config.get("token", ""),
                tpin=fiscal_config.get("tpin", ""),
                sandbox=fiscal_config.get("sandbox", True)
            )
        except Exception as e:
            logger.warning(f"MRA adapter failed to load: {e}. Falling back to noop.")
            return NoopAdapter()

    if provider == "zimra":
        # ZIMRA FDMS — Zimbabwe (future)
        logger.info("ZIMRA adapter not yet available. Using noop.")
        return NoopAdapter()

    if provider == "kra":
        # KRA eTIMS — Kenya (future)
        logger.info("KRA adapter not yet available. Using noop.")
        return NoopAdapter()

    # Default — noop
    return NoopAdapter()


async def get_fiscal_service_for_tenant(
    tenant_id: str,
    country: str,
    fiscal_provider: Optional[str] = None,
    fiscal_config: Optional[dict] = None
) -> FiscalComplianceService:
    """
    Get or create fiscal service for a specific tenant.
    Each tenant gets their own service instance with the correct adapter.
    """
    cache_key = str(tenant_id)

    if cache_key in _fiscal_services:
        return _fiscal_services[cache_key]

    # Determine provider
    provider = (
        fiscal_provider
        or COUNTRY_PROVIDER_MAP.get(country, COUNTRY_PROVIDER_MAP["default"])
    )

    config = fiscal_config or {}

    logger.info(
        f"Initializing fiscal service for tenant {tenant_id}: "
        f"country={country} provider={provider}"
    )

    adapter = _load_adapter(provider, config)
    service = FiscalComplianceService(
        adapter=adapter,
        storage_path=f"/tmp/alpine_fiscal/{tenant_id}"
    )
    await service.init()

    _fiscal_services[cache_key] = service

    logger.info(
        f"Fiscal service ready for tenant {tenant_id}: {adapter.provider_name}"
    )
    return service


def invalidate_fiscal_cache(tenant_id: str) -> None:
    """Clear cached fiscal service for a tenant."""
    cache_key = str(tenant_id)
    if cache_key in _fiscal_services:
        del _fiscal_services[cache_key]
        logger.info(f"Fiscal cache cleared for tenant {tenant_id}")


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
    """Convert Alpine sale data to FiscalSale type."""
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
                unit_price=Decimal(str(line.get("unit_price", 0))),
                tax_rate=Decimal("0.165"),
                tax_amount=Decimal(str(line.get("tax", 0))),
                line_total=Decimal(str(line.get("line_total", 0))),
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
