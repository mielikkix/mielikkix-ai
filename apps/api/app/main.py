import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
import os

from .core.config import settings
from .core.cors import PublicRouteCORSMiddleware
from .core.database import Base, engine
from .core.limiter import limiter
from .api import auth, businesses, faqs, documents, products, chat, leads, analytics, websites, admin, admin_articles, public_articles, agents_voice, agents_booking, agents_support, agents_seo, agents_seo_audit, agents_reviews, calendar_oauth, review_oauth, mailchimp_oauth, google_oauth, campaigns, consent

# Without this, every module's logger.info() call (e.g. agents_voice.py's
# own tool-call tracing) is silently dropped -- Python's root logger
# defaults to WARNING, and nothing else in this app configures it.
# uvicorn's own access/error logs already print at INFO regardless of this;
# this just makes the app's OWN module loggers equally visible instead of
# only ever showing up for actual errors.
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

# Dev-only convenience: a fresh local checkout gets its schema for free on
# first run, without remembering to run `alembic upgrade head` first. NOT
# gated by settings.debug before 2026-08-31 -- that ran this unconditionally
# in production too, which raced ahead of Alembic: a deploy shipping both a
# new model AND its migration hit `psycopg2.errors.DuplicateTable` the
# moment `alembic upgrade head` tried to create a table this line had
# already created seconds earlier at import time. Production stays on
# migrations as the only source of schema truth; local dev keeps the
# convenience, since settings.debug already defaults to True in
# .env.example's local values. (tests/conftest.py has its own separate
# create_all() against TEST_DATABASE_URL and is unaffected by this either
# way.)
if settings.debug:
    Base.metadata.create_all(bind=engine)


async def _run_due_seo_audits_tick() -> None:
    """APScheduler job, ticked every seo_schedule_service.
    CHECK_INTERVAL_MINUTES -- see that module's own docstring for why this
    is a narrow, single-purpose scheduler and not the general "shared job
    queue" root CLAUDE.md still calls aspirational. Opens its own DB
    session (the same "background work opens its own session" convention
    seo_audit_service.run_audit already follows) and never lets one tick's
    failure stop future ticks -- APScheduler would otherwise silently drop
    the job entirely after an unhandled exception."""
    from .core.database import SessionLocal
    from .services import seo_schedule_service

    db = SessionLocal()
    try:
        await seo_schedule_service.run_due_audits(db)
    except Exception:
        logging.getLogger(__name__).exception("Scheduled SEO audit tick failed")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Loading sentence-transformers can take a long time on a cold process
    # (downloading/initializing the model). Pay that cost once here, at
    # startup, instead of on whichever user's chat message or document
    # upload happens to be first.
    from .rag.embeddings import embed_texts

    embed_texts(["warmup"])

    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from .services import seo_schedule_service

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        _run_due_seo_audits_tick,
        "interval",
        minutes=seo_schedule_service.CHECK_INTERVAL_MINUTES,
        id="seo_due_audits_tick",
        # Skip a tick that's still running past the next one's fire time
        # rather than stacking overlapping runs -- a tick that takes longer
        # than CHECK_INTERVAL_MINUTES (a slow audit) just resumes at the
        # next interval instead of running two audits of the same website
        # concurrently.
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()

    yield

    scheduler.shutdown(wait=False)


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Wraps the middleware above: lets public widget routes (chat/leads) through
# from any origin, since those get embedded on client business websites we
# can't know in advance. Everything else still goes through the restrictive
# CORSMiddleware configured just above.
app.add_middleware(PublicRouteCORSMiddleware)

app.include_router(auth.router)
app.include_router(businesses.router)
app.include_router(faqs.router)
app.include_router(documents.router)
app.include_router(products.router)
app.include_router(chat.router)
app.include_router(leads.router)
app.include_router(analytics.router)
app.include_router(websites.router)
app.include_router(admin.router)
app.include_router(admin_articles.router)
app.include_router(public_articles.router)
app.include_router(agents_voice.router)
app.include_router(agents_booking.router)
app.include_router(agents_support.router)
app.include_router(agents_seo.router)
app.include_router(agents_seo_audit.router)
app.include_router(agents_seo_audit.audits_router)
app.include_router(agents_seo_audit.findings_router)
app.include_router(agents_reviews.router)
app.include_router(calendar_oauth.router)
app.include_router(review_oauth.router)
app.include_router(mailchimp_oauth.router)
app.include_router(google_oauth.router)
app.include_router(campaigns.router)
app.include_router(consent.router)

os.makedirs(settings.upload_dir, exist_ok=True)


@app.get("/health")
def health():
    return {"status": "ok"}
