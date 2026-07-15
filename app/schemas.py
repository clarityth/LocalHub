from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class LocationListItem(BaseModel):
    """장소 목록 응답 — 지도 렌더링에 필요한 최소 메타데이터"""
    contentid: str
    contenttypeid: int
    contenttypename: str
    title: str
    addr1: str
    addr2: str
    mapx: float
    mapy: float
    mlevel: str = ""
    firstimage: str = ""
    tel: str = ""


class LocationInfo(BaseModel):
    serialnum: str = ""
    infoname: str = ""
    infotext: str = ""


class CourseStopOut(BaseModel):
    subnum: int
    subcontentid: str = ""
    subname: str = ""
    subdetailoverview: str = ""
    subdetailimg: str = ""
    subdetailalt: str = ""


class NearbyLocation(LocationListItem):
    """주변 음식점/숙소 응답 — 기준 좌표로부터의 거리(km)를 포함"""
    distance_km: float


class LocationDetail(LocationListItem):
    """장소 상세 응답 — 타입별 고유 필드(type_fields)와 반복 정보를 포함"""
    zipcode: str = ""
    firstimage2: str = ""
    type_fields: dict[str, Any] = Field(default_factory=dict)
    detail_info: list[LocationInfo] = Field(default_factory=list)
    course_stops: list[CourseStopOut] = Field(default_factory=list)
    nearby_restaurants: list[NearbyLocation] = Field(default_factory=list)
    nearby_accommodations: list[NearbyLocation] = Field(default_factory=list)


class PostBase(BaseModel):
    """게시글 공통 필드. 생성(PostCreate)과 수정(PostUpdate)의 베이스"""
    title: str = Field(..., min_length=1, max_length=200)
    place: str = ""
    content: str = Field(..., min_length=1)
    category: str = Field(default="자유", max_length=80)
    contentid: str | None = None


class PostCreate(PostBase):
    """게시글 생성 요청 — 평문 비밀번호 필수"""
    password: str = Field(..., min_length=1, max_length=200)


class PostUpdate(BaseModel):
    """게시글 수정 요청 — 변경할 필드만 전송 (Partial Update 패턴)"""
    title: str | None = Field(default=None, min_length=1, max_length=200)
    place: str | None = None
    content: str | None = Field(default=None, min_length=1)
    category: str | None = Field(default=None, max_length=80)
    contentid: str | None = None
    password: str = Field(..., min_length=1, max_length=200)


class PasswordBody(BaseModel):
    password: str = Field(..., min_length=1, max_length=200)


class PostOut(BaseModel):
    """게시글 응답 — 비밀번호를 제외한 공개 필드만 포함"""
    id: int
    title: str
    place: str
    content: str
    category: str
    contentid: str | None
    like_count: int
    view_count: int
    created_at: datetime
    updated_at: datetime


class MessageOut(BaseModel):
    message: str


class PostCreateOut(MessageOut):
    id: int


class LikeOut(BaseModel):
    post_id: int
    like_count: int
    message: str
    is_liked: bool


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    """챗봇 질의 요청 — 현재 메시지와 이전 대화 히스토리를 포함"""
    message: str = Field(..., min_length=1)
    history: list[ChatMessage] = Field(default_factory=list)


class ChatSource(BaseModel):
    chunk_id: str
    source: str


class ChatResponse(BaseModel):
    """챗봇 응답 — 답변 텍스트, 참조 장소, RAG 출처를 포함"""
    answer: str
    referenced_items: list[LocationListItem] = Field(default_factory=list)
    sources: list[ChatSource] = Field(default_factory=list)
