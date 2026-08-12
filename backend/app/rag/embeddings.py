import os
from pathlib import Path
from typing import List
from functools import lru_cache
from ..core.config import settings


def _model_is_cached() -> bool:
    """Whether settings.embedding_model already has a local HF Hub cache
    snapshot (mounted from the hf_cache volume in Docker). Must be checked
    BEFORE sentence_transformers/transformers/huggingface_hub are ever
    imported: those libraries read HF_HUB_OFFLINE/TRANSFORMERS_OFFLINE once
    at import time and cache it internally, so setting os.environ after the
    fact (e.g. in a retry-on-failure) has no effect once they're imported --
    only deciding correctly up front actually works.
    """
    cache_home = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface"))
    model_id = settings.embedding_model
    namespaced = model_id if "/" in model_id else f"sentence-transformers/{model_id}"
    snapshots_dir = cache_home / "hub" / f"models--{namespaced.replace('/', '--')}" / "snapshots"
    return snapshots_dir.is_dir() and any(snapshots_dir.iterdir())


# Even with the model already cached locally, sentence-transformers/
# huggingface_hub still makes a network call on every load to check for
# updates -- on this machine that check alone took 60-90+s (and was highly
# inconsistent depending on network conditions), vs ~5s loading purely from
# local cache. Only force offline once we've confirmed a cache actually
# exists -- forcing it unconditionally broke the very first run on a fresh
# machine (empty hf_cache volume): offline mode with nothing to load from.
if _model_is_cached():
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")


@lru_cache()
def _get_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(settings.embedding_model)


def embed_texts(texts: List[str]) -> List[List[float]]:
    model = _get_model()
    return model.encode(texts, convert_to_numpy=True).tolist()


def embed_query(text: str) -> List[float]:
    return embed_texts([text])[0]
