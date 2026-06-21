"""
memory.py
Career Memory layer: stores resume bullets, projects, skills, certs
as discrete retrievable units, embeds them, and retrieves the most
relevant ones for a given job description at generation time.

This is intentionally simple: one local embedding model
(sentence-transformers, runs on CPU, no API cost), one SQLite vector
table. No need for anything heavier at single-user scale.
"""

import json
from functools import lru_cache
import sqlite_vec
from sentence_transformers import SentenceTransformer
from db import get_connection, now

MODEL_NAME = "all-MiniLM-L6-v2"  # 384-dim, ~80MB, fast on CPU


@lru_cache(maxsize=1)
def _model():
    return SentenceTransformer(MODEL_NAME)


def embed(text: str):
    vec = _model().encode(text, normalize_embeddings=True)
    return vec.tolist()


def add_source_item(item_type: str, content: str, source_label: str = None, tags=None):
    """
    Add one atomic piece of career truth (a bullet, a project description,
    a skill, etc.) to memory and index it for retrieval.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO source_items (item_type, content, source_label, tags, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (item_type, content, source_label, json.dumps(tags or []), now()),
    )
    item_id = cur.lastrowid

    vec = embed(content)
    cur.execute(
        "INSERT INTO source_items_vec (embedding) VALUES (?)",
        (sqlite_vec.serialize_float32(vec),),
    )
    vec_rowid = cur.lastrowid
    cur.execute(
        "INSERT INTO vec_link (vec_rowid, source_item_id) VALUES (?, ?)",
        (vec_rowid, item_id),
    )
    conn.commit()
    conn.close()
    return item_id


def retrieve_relevant(query_text: str, top_k: int = 12, item_types=None):
    """
    Return the top_k source_items most semantically similar to query_text
    (typically the JD text, or a JD section). Optionally restrict to
    certain item_types (e.g. only 'bullet' and 'project').
    """
    conn = get_connection()
    cur = conn.cursor()
    qvec = embed(query_text)

    # Note: sqlite-vec's exact KNN query syntax has shifted slightly across
    # versions (some require "AND k = ?" alongside MATCH, newer versions
    # accept LIMIT alone). If this raises a SQL error on your installed
    # version, check `python -c "import sqlite_vec; print(sqlite_vec.__version__)"`
    # and consult the sqlite-vec README for the current MATCH/LIMIT syntax,
    # this is the one place in the codebase tied to that library's API shape.
    rows = cur.execute(
        """
        SELECT vec_link.source_item_id, distance
        FROM source_items_vec
        JOIN vec_link ON vec_link.vec_rowid = source_items_vec.rowid
        WHERE embedding MATCH ?
        ORDER BY distance
        LIMIT ?
        """,
        (sqlite_vec.serialize_float32(qvec), top_k * 3),  # overfetch, then filter by type below
    ).fetchall()

    item_ids = [r["source_item_id"] for r in rows]
    if not item_ids:
        conn.close()
        return []

    placeholders = ",".join("?" * len(item_ids))
    items = cur.execute(
        f"SELECT * FROM source_items WHERE id IN ({placeholders}) AND active = 1",
        item_ids,
    ).fetchall()
    conn.close()

    items = [dict(i) for i in items]
    if item_types:
        items = [i for i in items if i["item_type"] in item_types]

    # preserve similarity order from the vector search
    order = {iid: rank for rank, iid in enumerate(item_ids)}
    items.sort(key=lambda i: order.get(i["id"], 999))
    return items[:top_k]


def all_active_items(item_type: str = None):
    conn = get_connection()
    cur = conn.cursor()
    if item_type:
        rows = cur.execute(
            "SELECT * FROM source_items WHERE active = 1 AND item_type = ? ORDER BY created_at DESC",
            (item_type,),
        ).fetchall()
    else:
        rows = cur.execute(
            "SELECT * FROM source_items WHERE active = 1 ORDER BY created_at DESC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def deactivate_item(item_id: int):
    """Soft delete: career history is never hard-deleted, just hidden."""
    conn = get_connection()
    conn.execute("UPDATE source_items SET active = 0 WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()


def add_writing_preference(text: str):
    conn = get_connection()
    conn.execute(
        "INSERT INTO writing_preferences (preference_text, created_at) VALUES (?, ?)",
        (text, now()),
    )
    conn.commit()
    conn.close()


def get_active_preferences():
    conn = get_connection()
    rows = conn.execute(
        "SELECT preference_text FROM writing_preferences WHERE active = 1"
    ).fetchall()
    conn.close()
    return [r["preference_text"] for r in rows]
