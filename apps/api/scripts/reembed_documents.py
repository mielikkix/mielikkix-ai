"""One-off maintenance script: re-embeds every DocumentChunk, FAQ, and Product
with the currently configured embedding model (see app.core.config.embedding_model).

Needed whenever the embedding model changes, or when FAQ/product embeddings
were just introduced for existing rows that predate them -- embeddings from
different models (or missing entirely) aren't comparable, so cosine
similarity against stale/absent embeddings is meaningless. Run once after
any such change:

    python scripts/reembed_documents.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import SessionLocal
from app.models.document import DocumentChunk
from app.models.faq import FAQ
from app.models.product import Product
from app.rag.embeddings import embed_texts

BATCH_SIZE = 64


def _reembed(db, label, rows, text_fn):
    total = len(rows)
    print(f"Re-embedding {total} {label}...")
    for start in range(0, total, BATCH_SIZE):
        batch = rows[start:start + BATCH_SIZE]
        embeddings = embed_texts([text_fn(row) for row in batch])
        for row, emb in zip(batch, embeddings):
            row.embedding_json = json.dumps(emb)
        db.commit()
        print(f"  {min(start + BATCH_SIZE, total)}/{total}")


def main():
    db = SessionLocal()
    try:
        chunks = db.query(DocumentChunk).order_by(DocumentChunk.id).all()
        _reembed(db, "document chunks", chunks, lambda c: c.content)

        faqs = db.query(FAQ).order_by(FAQ.id).all()
        _reembed(db, "FAQs", faqs, lambda f: f.question)

        products = db.query(Product).order_by(Product.id).all()
        _reembed(
            db, "products", products,
            lambda p: f"{p.name} {p.category or ''} {p.description or ''}".strip(),
        )
        print("Done.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
