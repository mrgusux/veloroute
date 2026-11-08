from fastapi import APIRouter
from .auth import router as auth_router
from .dashboard import router as dashboard_router
from .providers import router as providers_router
from .routing import router as routing_router
from .console import router as console_router
from .proxy import router as proxy_router
from .gateway import router as gateway_router
from .anthropic import router as anthropic_router
from .webhooks_api import router as webhooks_router
from .mcp import router as mcp_router
from .cache import router as cache_router
from .prompts import router as prompts_router
from .transforms import router as transforms_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(dashboard_router)
router.include_router(providers_router)
router.include_router(routing_router)
router.include_router(console_router)
router.include_router(proxy_router)
router.include_router(gateway_router)
router.include_router(anthropic_router)
router.include_router(webhooks_router)
router.include_router(mcp_router)
router.include_router(cache_router)
router.include_router(prompts_router)
router.include_router(transforms_router)
