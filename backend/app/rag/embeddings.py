import os
from typing import List
from functools import lru_cache
from ..core.config import settings

# Even with the model already cached locally, sentence-transformers/
# huggingface_hub still makes a network call on every load to check for
# updates -- on this machine that check alone took 60-90+s (and was highly
# inconsistent depending on network conditions), vs ~5s loading purely from
# local cache. Safe to force offline since the model is already downloaded;
# if you ever need to switch to a different/uncached embedding_model, unset
# these once to let it download first.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")


@lru_cache()
def _get_model():
    from sentence_transformers import SentenceTransformer
    try:
        return SentenceTransformer(settings.embedding_model)
    except OSError:
        # HF_HUB_OFFLINE above assumes the model is already cached -- true on
        # a machine that's loaded it before, false on a genuinely fresh one
        # (empty hf_cache volume). Retry once allowing a real download so the
        # very first run on a new deployment doesn't fail outright; the cache
        # written here makes every run after this one hit the fast path above.
        os.environ["HF_HUB_OFFLINE"] = "0"
        os.environ["TRANSFORMERS_OFFLINE"] = "0"
        return SentenceTransformer(settings.embedding_model)


def embed_texts(texts: List[str]) -> List[List[float]]:
    model = _get_model()
    return model.encode(texts, convert_to_numpy=True).tolist()


def embed_query(text: str) -> List[float]:
    return embed_texts([text])[0]
