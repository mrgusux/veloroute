from fastapi import APIRouter
from .auth import router as auth_router
from .dashboard import router as dashboard_router
from .providers import router as providers_router
from .routing import router as routing_router
from .console import router as console_router
from .proxy import router as proxy_router
from .gateway import router as gateway_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(dashboard_router)
router.include_router(providers_router)
router.include_router(routing_router)
router.include_router(console_router)
router.include_router(proxy_router)
router.include_router(gateway_router)
