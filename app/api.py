from hashlib import sha256
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload
import logging

from app.core import get_db
from app.models import Location, Post, PostLike, utc_now
from app.schemas import (
    ChatRequest, ChatResponse, LikeOut, LocationDetail, LocationListItem, 
    MessageOut, NearbyLocation, PasswordBody, PostCreate, PostCreateOut, 
    PostOut, PostUpdate
)
from app.services import (
    fallback_search_locations, generate_chat_answer, haversine_km, 
    location_detail, location_list_item, match_locations_from_chunks, 
    search_posts, search_rag_chunks, serialize_referenced_items, serialize_sources
)

router = APIRouter(tags=["api"])

logger = logging.getLogger(__name__)

# 지도 API

@router.get("/locations", response_model=list[LocationListItem])
def list_locations(
    contenttypeid: int | None = Query(default=None),
    q: str | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=1500),
    db: Session = Depends(get_db),
) -> list[dict]:
    """검색어(q)나 분류(contenttypeid)를 기준으로 장소 목록을 조회합니다."""
    stmt = select(Location).options(joinedload(Location.content_type)).order_by(Location.title)
    if contenttypeid: stmt = stmt.where(Location.content_type_id == contenttypeid)
    if q:
        like = f"%{q}%"
        stmt = stmt.where((Location.title.ilike(like)) | (Location.addr1.ilike(like)))
    stmt = stmt.limit(limit)
    return [location_list_item(loc) for loc in db.scalars(stmt).all()]

@router.get("/locations/all", response_model=list[LocationListItem])
def list_all_locations(db: Session = Depends(get_db)) -> list[dict]:
    """저장된 모든 장소 목록을 반환합니다."""
    return list_locations(contenttypeid=None, q=None, limit=1500, db=db)

@router.get("/locations/{contentid}", response_model=LocationDetail)
def get_location(contentid: str, db: Session = Depends(get_db)) -> dict:
    """contentid에 해당하는 장소의 전체 상세 정보 및 주변 음식점/숙박시설을 조회합니다."""
    location = db.scalar(
        select(Location).options(joinedload(Location.content_type), selectinload(Location.info_items), selectinload(Location.course_stops))
        .where(Location.content_id == contentid)
    )
    if not location: raise HTTPException(status_code=404, detail="Location not found")
    
    # 주변 맛집(39) 및 숙박(32) 검색 (반경 2km 이내 최대 10개)
    lat, lon = location.mapy, location.mapx
    candidates = db.scalars(
        select(Location).options(joinedload(Location.content_type))
        .where(Location.content_type_id.in_([32, 39]))
        .order_by(Location.title)
    ).all()
    
    nearby_restaurants = []
    nearby_accommodations = []
    for cand in candidates:
        if cand.content_id == location.content_id: continue
        distance = haversine_km(lat, lon, cand.mapy, cand.mapx)
        if distance <= 2.0:
            item = location_list_item(cand)
            item["distance_km"] = round(distance, 2)
            if cand.content_type_id == 39:
                nearby_restaurants.append(item)
            elif cand.content_type_id == 32:
                nearby_accommodations.append(item)
    
    nearby_restaurants.sort(key=lambda x: x["distance_km"])
    nearby_accommodations.sort(key=lambda x: x["distance_km"])
    
    result = location_detail(location)
    result["nearby_restaurants"] = nearby_restaurants[:4]
    result["nearby_accommodations"] = nearby_accommodations[:4]
    return result

# 커뮤니티 API

def _post_out(post: Post, include_content: bool = True) -> dict:
    return {
        "id": post.id, "title": post.title, "place": post.place_name,
        "content": post.content if include_content else post.content[:160],
        "category": post.category, "contentid": post.content_id,
        "like_count": post.like_count, "view_count": post.view_count,
        "created_at": post.created_at, "updated_at": post.updated_at,
    }

@router.get("/posts", response_model=list[PostOut])
def get_list_posts(
    category: str | None = Query(default=None),
    q: str | None = Query(default=None),
    search_type: str = Query(default="both"),
    sort_by: str = Query(default="latest"),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[dict]:
    """게시글 목록을 최신순 또는 추천순으로 조회합니다."""
    stmt = select(Post)
    if category: stmt = stmt.where(Post.category == category)
    if q:
        like = f"%{q}%"
        if search_type == "title":
            stmt = stmt.where(Post.title.ilike(like))
        elif search_type == "content":
            stmt = stmt.where(Post.content.ilike(like))
        else:
            stmt = stmt.where((Post.title.ilike(like)) | (Post.content.ilike(like)))            
    if sort_by == "likes":
        stmt = stmt.order_by(Post.like_count.desc(), Post.created_at.desc())
    else:
        stmt = stmt.order_by(Post.created_at.desc())
        
    stmt = stmt.limit(limit)
    return [_post_out(post, include_content=False) for post in db.scalars(stmt).all()]


@router.get("/posts/popular")
def get_popular_posts(
    limit: int = Query(default=5, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[dict]:
    """좋아요 순으로 상위 게시글을 반환합니다. 반환 필드: title, category, place, like_count, view_count, created_at"""
    posts = db.scalars(select(Post).order_by(Post.like_count.desc(), Post.created_at.desc()).limit(limit)).all()
    result: list[dict] = []
    for p in posts:
        result.append({
            "title": p.title,
            "category": p.category,
            "place": p.place_name,
            "like_count": p.like_count,
            "view_count": p.view_count,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        })
    return result

@router.get("/posts/{post_id}", response_model=PostOut)
def get_single_post(post_id: int, db: Session = Depends(get_db)) -> dict:
    """단일 게시글의 상세 내용을 조회하고 조회수를 1 증가시킵니다."""
    post = db.get(Post, post_id)
    if not post: raise HTTPException(status_code=404, detail="Post not found")
    try:
        post.view_count += 1
        db.commit()
        db.refresh(post)
        return _post_out(post)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception("Failed to increment view_count for post %s: %s", post_id, str(e))
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/posts", response_model=PostCreateOut, status_code=201)
def create_new_post(payload: PostCreate, db: Session = Depends(get_db)) -> dict:
    """새로운 익명 게시글을 작성합니다."""
    post = Post(title=payload.title, place_name=payload.place, content=payload.content, category=payload.category, content_id=payload.contentid, password=payload.password)
    try:
        db.add(post)
        db.commit()
        db.refresh(post)
        return {"id": post.id, "message": "게시글이 성공적으로 등록되었습니다."}
    except Exception as e:
        db.rollback()
        logger.exception("Failed to create post: %s", str(e))
        raise HTTPException(status_code=500, detail="게시글 생성 중 내부 오류가 발생했습니다.")

def _client_fingerprint(request: Request, post_id: int) -> str:
    ip = request.client.host if request.client else "unknown"
    ua = request.headers.get("user-agent", "")
    return sha256(f"{ip}:{ua}:{post_id}".encode()).hexdigest()

@router.post("/posts/{post_id}/like", response_model=LikeOut)
def like_single_post(post_id: int, request: Request, db: Session = Depends(get_db)) -> dict:
    """단일 게시글에 좋아요를 누르거나 취소합니다 (핑거프린트 필터링으로 클라이언트당 1회 토글)."""
    post = db.get(Post, post_id)
    if not post: raise HTTPException(status_code=404, detail="Post not found")
    fp = _client_fingerprint(request, post_id)
    try:
        existing = db.scalar(select(PostLike).where(PostLike.post_id == post_id, PostLike.fingerprint == fp))
        if existing:
            db.delete(existing)
            post.like_count -= 1
            db.commit()
            db.refresh(post)
            return {"post_id": post.id, "like_count": post.like_count, "message": "좋아요가 취소되었습니다.", "is_liked": False}
        else:
            db.add(PostLike(post_id=post_id, fingerprint=fp))
            post.like_count += 1
            db.commit()
            db.refresh(post)
            return {"post_id": post.id, "like_count": post.like_count, "message": "좋아요가 반영되었습니다.", "is_liked": True}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception("Failed to toggle like for post %s: %s", post_id, str(e))
        raise HTTPException(status_code=500, detail="Internal server error")

@router.put("/posts/{post_id}", response_model=MessageOut)
def update_existing_post(post_id: int, payload: PostUpdate, db: Session = Depends(get_db)) -> dict[str, str]:
    """비밀번호 검증 후 게시글을 수정합니다."""
    post = db.get(Post, post_id)
    if not post: raise HTTPException(status_code=404, detail="Post not found")
    if post.password != payload.password: raise HTTPException(status_code=403, detail="Password does not match")
    try:
        for field, value in {"title": payload.title, "place_name": payload.place, "content": payload.content, "category": payload.category, "content_id": payload.contentid}.items():
            if value is not None: setattr(post, field, value)
        post.updated_at = utc_now()
        db.commit()
        return {"message": "게시글이 성공적으로 수정되었습니다."}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception("Failed to update post %s: %s", post_id, str(e))
        raise HTTPException(status_code=500, detail="Internal server error")

@router.delete("/posts/{post_id}", response_model=MessageOut)
def delete_existing_post(post_id: int, payload: PasswordBody, db: Session = Depends(get_db)) -> dict[str, str]:
    """비밀번호 검증 후 게시글을 삭제합니다."""
    post = db.get(Post, post_id)
    if not post: raise HTTPException(status_code=404, detail="Post not found")
    if post.password != payload.password: raise HTTPException(status_code=403, detail="Password does not match")
    try:
        db.delete(post)
        db.commit()
        return {"message": "게시글이 삭제되었습니다."}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception("Failed to delete post %s: %s", post_id, str(e))
        raise HTTPException(status_code=500, detail="Internal server error")

# 챗봇 API

@router.post("/chat")
def chat_endpoint(payload: ChatRequest, db: Session = Depends(get_db)):
    """사용자의 메시지를 받아 FAISS 검색 후 OpenAI 챗봇 스트리밍 응답을 반환합니다."""
    from app.services import search_rag_chunks, match_locations_from_chunks, search_posts, fallback_search_locations, _build_prompt, serialize_referenced_items, serialize_sources, _fallback_answer, generate_chat_stream

    try:
        rag_hits = search_rag_chunks(db, payload.message)
        chunk_locations = match_locations_from_chunks(db, rag_hits, limit=8)
        posts = search_posts(db, payload.message, limit=3)

        direct_locations = []
        if not chunk_locations:
            direct_locations = fallback_search_locations(db, payload.message, limit=8)

        seen = set()
        referenced_items = []
        for loc in [*chunk_locations, *direct_locations]:
            if loc.content_id not in seen:
                seen.add(loc.content_id)
                referenced_items.append(loc)

        prompt = _build_prompt(payload.message, referenced_items, rag_hits, posts)
        metadata = {
            "type": "metadata",
            "referenced_items": serialize_referenced_items(referenced_items[:5]),
            "sources": serialize_sources(rag_hits, posts),
        }
        fallback_text = _fallback_answer(referenced_items, rag_hits, posts)

        history_dicts = [{"role": m.role, "content": m.content} for m in payload.history]
        stream = generate_chat_stream(prompt, metadata, fallback_text, history=history_dicts)
        return StreamingResponse(stream, media_type="text/event-stream")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Chat endpoint failed: %s", str(e))
        raise HTTPException(status_code=500, detail="Internal server error")
