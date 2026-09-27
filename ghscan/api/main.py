import asyncio
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .. import __version__
from ..github_client import GitHubError, RateLimited, UserNotFound, make_client
from .cache import ReportCache
from .deps import RateLimiter, Settings, get_settings
from .routes import router

DEFAULT_RETRY_AFTER = 60


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = settings
        app.state.cache = ReportCache(settings.cache_ttl_seconds)
        app.state.limiter = RateLimiter(settings.rate_limit_per_minute)
        app.state.github_sem = asyncio.Semaphore(settings.max_concurrent_github)
        async with make_client(settings.github_token) as client:
            app.state.http = client
            yield

    app = FastAPI(
        title="ghscan API",
        description="Analyze and compare GitHub profiles: stars, languages and activity.",
        version=__version__,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET"],
        allow_headers=["*"],
        expose_headers=["X-Cache", "Retry-After"],
    )

    @app.exception_handler(UserNotFound)
    async def user_not_found(request: Request, exc: UserNotFound) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": str(exc)})

    @app.exception_handler(RateLimited)
    async def github_rate_limited(request: Request, exc: RateLimited) -> JSONResponse:
        retry_after = max(1, exc.reset_at - int(time.time())) if exc.reset_at else DEFAULT_RETRY_AFTER
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"detail": "GitHub rate limit reached, try again later"},
            headers={"Retry-After": str(retry_after)},
        )

    @app.exception_handler(GitHubError)
    async def github_error(request: Request, exc: GitHubError) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_502_BAD_GATEWAY, content={"detail": str(exc)})

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(router)
    return app


app = create_app()
