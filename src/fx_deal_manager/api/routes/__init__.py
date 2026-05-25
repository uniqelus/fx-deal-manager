from fx_deal_manager.api.routes.audit import router as audit_router
from fx_deal_manager.api.routes.deals import router as deals_router
from fx_deal_manager.api.routes.health import router as health_router
from fx_deal_manager.api.routes.me import router as me_router
from fx_deal_manager.api.routes.nsi import router as nsi_router
from fx_deal_manager.api.routes.reports import router as reports_router

__all__ = [
    "audit_router",
    "deals_router",
    "health_router",
    "me_router",
    "nsi_router",
    "reports_router",
]
