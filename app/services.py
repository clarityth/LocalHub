import json
import re
import time
from dataclasses import dataclass
from functools import lru_cache
from hashlib import sha256
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
from threading import Lock
from typing import Any, Generator
from concurrent.futures import ThreadPoolExecutor

import faiss
import numpy as np
from openai import OpenAI
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core import REPO_ROOT, get_settings
from app.models import CourseStop, Location, LocationInfoItem, Post, RagChunk

# JSON 직렬화

def _loads(value: str, fallback: Any) -> Any:
    """JSON 문자열을 파싱합니다. 실패 시 fallback 반환"""
    try:
        return json.loads(value) if value else fallback
    except json.JSONDecodeError:
        return fallback

def location_list_item(location: Location) -> dict[str, Any]:
    """목록 조회용 장소 데이터 (가벼운 메타데이터)"""
    return {
        "contentid": location.content_id,
        "contenttypeid": location.content_type_id,
        "contenttypename": location.content_type.name if location.content_type else "",
        "title": strip_html(location.title),
        "addr1": strip_html(location.addr1),
        "addr2": strip_html(location.addr2),
        "mapx": location.mapx,
        "mapy": location.mapy,
        "mlevel": location.mlevel,
        "firstimage": location.firstimage,
        "tel": strip_html(location.tel),
    }

def location_detail(location: Location) -> dict[str, Any]:
    """장소 상세 데이터 (반복 필드 및 JSON 파싱 포함)"""
    data = location_list_item(location)
    raw_fields = strip_html_from_dict(_loads(location.type_fields_json, {}))
    
    # 내부 행정용/무의미한 필드 제거
    useless_keys = {"lcnsno", "contentid", "contenttypeid", "modifiedtime", "createdtime", "cpyrhtDivCd", "booktour"}
    filtered_fields = {k: v for k, v in raw_fields.items() if k not in useless_keys and v}

    data.update({
        "zipcode": strip_html(location.zipcode),
        "firstimage2": location.firstimage2,
        "type_fields": filtered_fields,
        "detail_info": [info_item(item) for item in location.info_items],
        "course_stops": [course_stop(item) for item in sorted(location.course_stops, key=lambda x: x.sub_num)],
    })
    return data

def info_item(item: LocationInfoItem) -> dict[str, Any]:
    return {"serialnum": item.serial_num, "infoname": strip_html(item.info_name), "infotext": strip_html(item.info_text)}

def course_stop(item: CourseStop) -> dict[str, Any]:
    return {
        "subnum": item.sub_num,
        "subcontentid": item.sub_content_id,
        "subname": strip_html(item.sub_name),
        "subdetailoverview": strip_html(item.sub_overview),
        "subdetailimg": item.sub_image,
        "subdetailalt": strip_html(item.sub_alt),
    }

# Text & Geo 유틸

def strip_html(text: str | None) -> str:
    """텍스트 내의 HTML 태그(<br>, <b> 등)를 제거합니다."""
    if not text:
        return ""
    text = re.sub(r'<br\s*/?>', ' ', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    return re.sub(r'\s+', ' ', text).strip()

def strip_html_from_dict(d: dict[str, Any]) -> dict[str, Any]:
    """딕셔너리 내부의 모든 문자열 값에서 HTML 태그를 재귀적으로 제거합니다."""
    result = {}
    for k, v in d.items():
        if isinstance(v, str):
            result[k] = strip_html(v)
        elif isinstance(v, dict):
            result[k] = strip_html_from_dict(v)
        elif isinstance(v, list):
            result[k] = [strip_html(i) if isinstance(i, str) else i for i in v]
        else:
            result[k] = v
    return result

CATEGORY_HINTS = {
    "관광": 12, "명소": 12, "문화": 14, "전시": 14, "축제": 15, "행사": 15,
    "코스": 25, "여행코스": 25, "레포츠": 28, "체험": 28, "숙박": 32, "호텔": 32,
    "쇼핑": 38, "시장": 38, "맛집": 39, "음식": 39, "식당": 39, "카페": 39,
}

@lru_cache(maxsize=512)
def tokenize(text: str) -> list[str]:
    """기본 키워드 검색을 위한 간단한 토큰화 (LRU 캐시 적용)."""
    tokens = re.findall(r"[0-9A-Za-z가-힣]+", text.lower())
    return [token for token in tokens if len(token) > 1]

def infer_content_type(message: str) -> int | None:
    """질문에서 장소 카테고리 힌트 추출."""
    for keyword, content_type_id in CATEGORY_HINTS.items():
        if keyword in message:
            return content_type_id
    return None

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """하버사인 공식으로 두 위경도 사이의 거리를 km 단위로 계산합니다."""
    radius = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    c = 2 * asin(sqrt(a))
    return radius * c

# Vector Index (FAISS)
@dataclass
class RagHit:
    doc_id: str
    content: str
    chunk_id: str
    source: str
    kind: str
    score: float
    content_id: str | None = None

class FaissRagIndex:
    """FAISS를 활용한 RAG 인덱스 관리자"""
    def __init__(self) -> None:
        self.dimension = 0
        self.index: faiss.IndexFlatIP | None = None
        self.doc_ids: list[str] = []
        self.documents: dict[str, RagHit] = {}
        self.fingerprint = ""
        self._lock = Lock()
        self._doc_count: int = 0
        self._last_check_time: float = 0.0 # 성능 개선: 캐시 확인용 타이머

    def build(self, db: Session) -> None:
        documents = _load_documents(db)
        fingerprint = _fingerprint(documents)
        vectors = self._load_cached_vectors(fingerprint, documents)
        if vectors is None:
            vectors = self._embed_documents([doc.content for doc in documents])
            self._save_cached_vectors(fingerprint, documents, vectors)

        dimension = vectors.shape[1] if vectors.size else 0

        with self._lock:
            self.dimension = dimension
            self.index = faiss.IndexFlatIP(dimension) if dimension else None
            if self.index is not None and len(documents):
                self.index.add(vectors)
            self.doc_ids = [doc.doc_id for doc in documents]
            self.documents = {doc.doc_id: doc for doc in documents}
            self.fingerprint = fingerprint
            self._doc_count = len(documents)
            self._last_check_time = time.time()

    def ensure_built(self, db: Session) -> None:
        """실시간 COUNT 쿼리에 60초 쿨타임(TTL) 적용"""
        current_time = time.time()
        if current_time - self._last_check_time < 60.0 and self.index is not None:
            return

        current_count = (
            (db.scalar(select(func.count(RagChunk.id))) or 0)
            + (db.scalar(select(func.count(Location.content_id))) or 0)
        )
        
        with self._lock:
            self._last_check_time = time.time()
            if self.index is not None and getattr(self, '_doc_count', 0) == current_count:
                return
        
        self.build(db)

    def search(self, db: Session, query: str, limit: int = 4) -> list[RagHit]:
        self.ensure_built(db)
        query_vector = self._embed_documents([query])
        with self._lock:
            if self.index is None or not self.doc_ids:
                return []
            scores, positions = self.index.search(query_vector, min(limit, len(self.doc_ids)))
            results = []
            for position, score in zip(positions[0], scores[0], strict=False):
                if position < 0:
                    continue
                doc = self.documents.get(self.doc_ids[position])
                if doc is not None:
                    results.append(
                        RagHit(
                            doc_id=doc.doc_id, content=doc.content, chunk_id=doc.chunk_id,
                            source=doc.source, kind=doc.kind, score=float(score), content_id=doc.content_id,
                        )
                    )
            return results

    def _embed_documents(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 0), dtype="float32")
        settings = get_settings()
        if settings.openai_api_key:
            client = OpenAI(api_key=settings.openai_api_key)
            vectors: list[list[float]] = []
            batch_size = 100
            for index in range(0, len(texts), batch_size):
                batch = texts[index : index + batch_size]
                response = client.embeddings.create(model=settings.openai_embedding_model, input=batch)
                vectors.extend(item.embedding for item in response.data)
            array = np.array(vectors, dtype="float32")
        else:
            array = np.vstack([_hash_embed(text) for text in texts]).astype("float32")
        faiss.normalize_L2(array)
        return array

    def _load_cached_vectors(self, fingerprint: str, documents: list[RagHit]) -> np.ndarray | None:
        path = _cache_path()
        if not path.exists():
            return None
        try:
            cache = np.load(path, allow_pickle=False)
            if str(cache["fingerprint"]) == fingerprint and [str(item) for item in cache["doc_ids"]] == [doc.doc_id for doc in documents]:
                return cache["vectors"].astype("float32")
        except Exception:
            return None
        return None

    def _save_cached_vectors(self, fingerprint: str, documents: list[RagHit], vectors: np.ndarray) -> None:
        np.savez_compressed(
            _cache_path(),
            fingerprint=np.array(fingerprint),
            doc_ids=np.array([doc.doc_id for doc in documents]),
            vectors=vectors,
        )

def _cache_path() -> Path:
    settings = get_settings()
    provider = "openai" if settings.openai_api_key else "local"
    model = settings.openai_embedding_model if settings.openai_api_key else "hash"
    cache_dir = Path(settings.vector_cache_dir)
    if not cache_dir.is_absolute():
        cache_dir = REPO_ROOT / cache_dir
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"faiss_{provider}_{model.replace('/', '_')}.npz"

def _load_documents(db: Session) -> list[RagHit]:
    documents: list[RagHit] = []
    rag_chunks = db.scalars(select(RagChunk).options(joinedload(RagChunk.source)).order_by(RagChunk.id)).all()
    for chunk in rag_chunks:
        source = chunk.source.source_name if chunk.source else ""
        documents.append(RagHit(doc_id=f"rag:{chunk.id}", content=chunk.content, chunk_id=chunk.chunk_id, source=source, kind="rag", score=0.0))

    locations = db.scalars(select(Location).options(joinedload(Location.content_type), selectinload(Location.info_items)).order_by(Location.content_id)).all()
    for location in locations:
        content_type = location.content_type.name if location.content_type else str(location.content_type_id)
        info_lines = [f"{item.info_name}: {item.info_text}" for item in location.info_items if item.info_name and item.info_text]
        parts = [
            f"장소명: {location.title}", f"분류: {content_type} ({location.content_type_id})",
            f"주소: {location.addr1} {location.addr2}".strip(), f"전화: {location.tel}",
        ]
        if info_lines: parts.append("부가정보: " + " | ".join(info_lines[:10]))
        parts.append(f"상세: {location.type_fields_json[:1200]}")
        documents.append(RagHit(doc_id=f"location:{location.content_id}", content="\n".join(parts), chunk_id=f"location:{location.content_id}", source="structured_location_json", kind="location", score=0.0, content_id=location.content_id))

    posts = db.scalars(select(Post).order_by(Post.id)).all()
    for post in posts:
        post_content = f"게시글: {post.title}\n카테고리: {post.category}\n장소: {post.place_name}\n내용: {post.content[:600]}"
        documents.append(RagHit(doc_id=f"post:{post.id}", content=post_content, chunk_id=f"post:{post.id}", source="community_post", kind="post", score=0.0))

    return documents

def _fingerprint(documents: list[RagHit]) -> str:
    digest = sha256()
    settings = get_settings()
    digest.update((settings.openai_embedding_model if settings.openai_api_key else "hash").encode("utf-8"))
    for doc in documents:
        digest.update(doc.doc_id.encode("utf-8"))
        digest.update(doc.content.encode("utf-8"))
    return digest.hexdigest()

def _hash_embed(text: str, dimension: int = 512) -> np.ndarray:
    vector = np.zeros(dimension, dtype="float32")
    for token in tokenize(text):
        digest = sha256(token.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:4], "little") % dimension
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[bucket] += sign
    return vector

_rag_index = FaissRagIndex()
def get_rag_index() -> FaissRagIndex: return _rag_index

# 검색 로직

def fallback_search_locations(db: Session, message: str, limit: int = 5) -> list[Location]:
    """[성능 개선] 루프 내 무거운 연산 최소화"""
    tokens = tokenize(message)
    content_type_id = infer_content_type(message)
    if not tokens and content_type_id is None:
        return []

    stmt = select(Location).options(joinedload(Location.content_type))
    if content_type_id:
        stmt = stmt.where(Location.content_type_id == content_type_id)

    locations = db.scalars(stmt).all()
    if not tokens:
        return locations[:limit]

    scored: list[tuple[int, Location]] = []
    for location in locations:
        # DB 컬럼을 단순 연결 후 한 번만 lower 처리 (메모리 단편화 감소)
        blob = f"{location.title or ''} {location.addr1 or ''} {location.addr2 or ''} {location.tel or ''} {location.type_fields_json or ''}".lower()
        title_lower = (location.title or "").lower()
        
        score = sum(3 if token in title_lower else 1 for token in tokens if token in blob)
        if score > 0:
            if content_type_id and location.content_type_id == content_type_id: 
                score += 2
            scored.append((score, location))

    if scored: 
        scored.sort(key=lambda item: item[0], reverse=True)
        return [location for _, location in scored[:limit]]

    return locations[:limit]

def search_rag_chunks(db: Session, message: str, limit: int = 8) -> list[RagHit]:
    hits = get_rag_index().search(db, message, limit=limit)
    content_type_id = infer_content_type(message)
    if content_type_id and len(hits) > 1:
        typed = [h for h in hits if h.kind == "location" and h.content_id and f"({content_type_id})" in h.content]
        others = [h for h in hits if not (h.kind == "location" and h.content_id and f"({content_type_id})" in h.content)]
        hits = (typed + others)[:limit]
    return hits

def match_locations_from_chunks(db: Session, hits: list[RagHit], limit: int = 5) -> list[Location]:
    if not hits: return []
    content_ids = [hit.content_id for hit in hits if hit.content_id]
    if content_ids:
        locations = db.scalars(select(Location).options(joinedload(Location.content_type)).where(Location.content_id.in_(content_ids))).all()
        by_id = {loc.content_id: loc for loc in locations}
        ordered, seen = [], set()
        for cid in content_ids:
            if cid in by_id and cid not in seen:
                seen.add(cid)
                ordered.append(by_id[cid])
            if len(ordered) >= limit: return ordered

    text = "\n".join(hit.content for hit in hits)
    candidates = db.scalars(select(Location).options(joinedload(Location.content_type))).all()
    # [성능 개선] text.count()와 같은 중복 검색 방지, 단순 포함 여부만 체크
    matched = [(len(loc.title), loc) for loc in candidates if loc.title and loc.title in text]
    matched.sort(key=lambda item: item[0], reverse=True)
    
    deduped, seen_ids = [], set()
    for _, loc in matched:
        if loc.content_id not in seen_ids:
            seen_ids.add(loc.content_id)
            deduped.append(loc)
        if len(deduped) >= limit: break
    return deduped

def search_posts(db: Session, message: str, limit: int = 3) -> list[Post]:
    tokens = tokenize(message)
    if not tokens: return []
    conditions = []
    for token in tokens[:6]:
        like = f"%{token}%"
        conditions.extend([Post.title.ilike(like), Post.content.ilike(like), Post.place_name.ilike(like)])
    if not conditions: return []
    return list(db.scalars(select(Post).where(or_(*conditions)).order_by(Post.created_at.desc()).limit(limit)).all())

def serialize_sources(rag_hits: list[RagHit], posts: list[Post] | None = None) -> list[dict[str, str]]:
    sources = [{"chunk_id": h.chunk_id, "source": h.source} for h in rag_hits if h.kind == "rag"]
    if posts:
        for p in posts:
            sources.append({"chunk_id": f"post-{p.id}", "source": f"커뮤니티: {p.title}"})
    return sources

def serialize_referenced_items(locations: list[Location]) -> list[dict]:
    return [location_list_item(loc) for loc in locations]

# AI 챗봇

def generate_chat_answer(message: str, locations: list[Location], rag_hits: list[RagHit], posts: list[Post], history: list[dict] | None = None) -> str:
    """사용자 메시지와 문맥을 바탕으로 OpenAI 답변을 생성합니다"""
    settings = get_settings()
    if not settings.openai_api_key:
        return _fallback_answer(locations, rag_hits, posts)

    client = OpenAI(api_key=settings.openai_api_key)
    messages = [{"role": "system", "content": "너는 대전/충청권 지역 정보 공유 서비스 LocalHub의 한국어 챗봇이다. 제공된 컨텍스트 안에서만 답변하고, 추천 시 2~4개를 요약된 이유와 함께 제공한다. 단, 좌표 정보는 제외한다. 답변은 개조식으로 하며, 마크다운 문법을 적극 활용하라."}]
    if history:
        for msg in history[-6:]: messages.append({"role": msg["role"], "content": msg["content"]})
    
    messages.append({"role": "user", "content": _build_prompt(message, locations, rag_hits, posts)})
    response = client.chat.completions.create(model=settings.openai_chat_model, messages=messages, temperature=0.4)
    return response.choices[0].message.content or ""

def generate_chat_stream(prompt: str, metadata: dict, fallback_text: str, history: list[dict] | None = None) -> Generator[str, None, None]:
    """사용자 메시지와 문맥을 바탕으로 OpenAI 답변을 스트리밍(SSE) 방식으로 생성합니다."""
    try:
        yield f"data: {json.dumps(metadata, ensure_ascii=False)}\n\n"

        settings = get_settings()
        if not settings.openai_api_key:
            chunk_data = {"type": "content", "text": fallback_text}
            yield f"data: {json.dumps(chunk_data, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
            return

        client = OpenAI(api_key=settings.openai_api_key)
        system_prompt = (
            "너는 대전/충청권 지역 정보 공유 서비스 LocalHub의 한국어 챗봇이다. "
            "제공된 컨텍스트 안에서만 답변하고, 사용자의 요청에 대해 정확하고 많은 정보를 제공해야한다. 단, 좌표 정보는 제외한다. "
            "추천 시 2~4개를 이유와 함께 제공한다. "
            "답변은 개조식으로 하며, 마크다운 문법을 적극 활용하라. "
            "특히 제공된 정보에 이미지 URL이 포함되어 있다면 이미지가 렌더링되도록 마크다운 형태로 텍스트 내에 삽입하라."
        )
        messages = [{"role": "system", "content": system_prompt}]
        if history:
            for msg in history[-6:]: messages.append({"role": msg["role"], "content": msg["content"]})
        
        messages.append({"role": "user", "content": prompt})
        
        response = client.chat.completions.create(
            model=settings.openai_chat_model, 
            messages=messages, 
            temperature=0.4,
            stream=True
        )

        for chunk in response:
            content = chunk.choices[0].delta.content
            if content:
                chunk_data = {"type": "content", "text": content}
                yield f"data: {json.dumps(chunk_data, ensure_ascii=False)}\n\n"
    except Exception as e:
        import traceback
        traceback.print_exc()
        chunk_data = {"type": "content", "text": f"\n\n**[시스템 알림]** 챗봇 응답 생성 중 내부 오류가 발생했습니다: {str(e)}"}
        yield f"data: {json.dumps(chunk_data, ensure_ascii=False)}\n\n"

    yield "data: [DONE]\n\n"

def _build_prompt(message: str, locations: list[Location], rag_hits: list[RagHit], posts: list[Post]) -> str:
    return "\n\n".join([
        f"[사용자 질문]\n{message}",
        f"[구조화 장소 데이터]\n{_location_context(locations)}",
        f"[PDF/RAG 검색 근거]\n{_rag_context(rag_hits)}",
        f"[커뮤니티 게시글 검색 결과]\n{_post_context(posts)}",
        "[출력 지침]\n- 한국어로 답변한다.\n- 지도 표시는 구조화 장소 데이터에 있는 항목뿐이다.\n- 모르는 내용은 모른다고 말한다."
    ])

def _location_context(locations: list[Location]) -> str:
    if not locations: return "검색된 장소 없음"
    rows = []
    for loc in locations[:8]:
        try: type_fields = json.loads(loc.type_fields_json or "{}")
        except json.JSONDecodeError: type_fields = {}
        info_items = [{"name": it.info_name, "text": it.info_text} for it in getattr(loc, 'info_items', []) if it.info_name and it.info_text]
        if info_items: type_fields["info"] = info_items
        
        # 데이터베이스에서 로드한 이미지 데이터를 확보
        img_url = loc.firstimage or loc.firstimage2 or ""
        
        # LLM 프롬프트 생성용 JSON에 image 속성 포함
        rows.append(json.dumps({
            "contentid": loc.content_id, 
            "contenttypeid": loc.content_type_id, 
            "title": loc.title, 
            "addr1": loc.addr1, 
            "mapx": loc.mapx, 
            "mapy": loc.mapy, 
            "tel": loc.tel, 
            "image": img_url, 
            "fields": type_fields
        }, ensure_ascii=False))
    return "\n".join(rows)

def _rag_context(rag_hits: list[RagHit]) -> str:
    rag_rows = [h for h in rag_hits if h.kind == "rag"]
    if not rag_rows: return "검색된 PDF 근거 없음"
    return "\n\n".join(f"source={h.source}, chunk_id={h.chunk_id}, score={h.score:.3f}\n{h.content[:900]}" for h in rag_rows[:5])

def _post_context(posts: list[Post]) -> str:
    if not posts: return "검색된 게시글 없음"
    return "\n".join(json.dumps({"id": p.id, "title": p.title, "place": p.place_name, "category": p.category, "content": p.content[:400]}, ensure_ascii=False) for p in posts)

def _fallback_answer(locations: list[Location], rag_hits: list[RagHit], posts: list[Post]) -> str:
    lines = ["OpenAI API 키가 없어 개발용 검색 결과만 반환합니다."]
    for loc in locations[:3]: lines.append(f"- {loc.title}: {loc.addr1}")
    rag_sources = list({h.source for h in rag_hits if h.kind == "rag"})
    if rag_sources: lines.append(f"참고 문서: {', '.join(rag_sources[:3])}")
    if posts: lines.append(f"관련 게시글: {posts[0].title}")
    return "\n".join(lines)