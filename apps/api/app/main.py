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
from .api import auth, businesses, faqs, documents, products, chat, leads, analytics, websites, admin, agents_voice, agents_booking, agents_support, agents_seo, agents_reviews, calendar_oauth

# Without this, every module's logger.info() call (e.g. agents_voice.py's
# own tool-call tracing) is silently dropped -- Python's root logger
# defaults to WARNING, and nothing else in this app configures it.
# uvicorn's own access/error logs already print at INFO regardless of this;
# this just makes the app's OWN module loggers equally visible instead of
# only ever showing up for actual errors.
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Loading sentence-transformers can take a long time on a cold process
    # (downloading/initializing the model). Pay that cost once here, at
    # startup, instead of on whichever user's chat message or document
    # upload happens to be first.
    from .rag.embeddings import embed_texts

    embed_texts(["warmup"])
    yield


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
app.include_router(agents_voice.router)
app.include_router(agents_booking.router)
app.include_router(agents_support.router)
app.include_router(agents_seo.router)
app.include_router(agents_reviews.router)
app.include_router(calendar_oauth.router)

os.makedirs(settings.upload_dir, exist_ok=True)


@app.get("/health")
def health():
    return {"status": "ok"}
