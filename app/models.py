from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core import Base


def utc_now() -> datetime:
    """현재 UTC 시각을 반환한다. SQLAlchemy 컬럼 기본값으로 사용"""
    return datetime.now(timezone.utc)


class ContentType(Base):
    """장소 분류 코드

    한국관광공사 API의 contenttypeid를 그대로 PK로 사용
    (12=관광지, 14=문화시설, 15=축제, 25=여행코스, 28=레포츠, 32=숙박, 38=쇼핑, 39=음식점)
    """
    __tablename__ = "content_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)

    locations: Mapped[list["Location"]] = relationship(back_populates="content_type")


class Location(Base):
    """장소 정보 — 프로젝트의 핵심 엔티티

    한국관광공사 API에서 수집한 관광 데이터를 저장한다
    contenttypeid마다 상이한 상세 필드는 type_fields_json에 JSON 문자열로 보존하여
    고정 스키마 변경 없이 모든 타입을 수용한다 (Flexible Schema 패턴)
    """
    __tablename__ = "locations"

    content_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    content_type_id: Mapped[int] = mapped_column(ForeignKey("content_types.id"), index=True)
    region: Mapped[str] = mapped_column(String(50), default="대전/충청")
    title: Mapped[str] = mapped_column(String(200), index=True)
    addr1: Mapped[str] = mapped_column(String(300), default="")
    addr2: Mapped[str] = mapped_column(String(300), default="")
    mapx: Mapped[float] = mapped_column(Float, index=True)
    mapy: Mapped[float] = mapped_column(Float, index=True)
    mlevel: Mapped[str] = mapped_column(String(20), default="")
    firstimage: Mapped[str] = mapped_column(Text, default="")
    firstimage2: Mapped[str] = mapped_column(Text, default="")
    tel: Mapped[str] = mapped_column(String(100), default="")
    zipcode: Mapped[str] = mapped_column(String(30), default="")
    # 원본 JSON 보존
    raw_json: Mapped[str] = mapped_column(Text, default="{}")
    # contenttypeid마다 다른 상세 필드는 JSON 문자열로 저장
    type_fields_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    content_type: Mapped[ContentType] = relationship(back_populates="locations")
    info_items: Mapped[list["LocationInfoItem"]] = relationship(
        back_populates="location", cascade="all, delete-orphan"
    )
    course_stops: Mapped[list["CourseStop"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )
    posts: Mapped[list["Post"]] = relationship(back_populates="location")


class LocationInfoItem(Base):
    """장소 반복 정보 (메뉴, 입장료, 이용 안내 등)

    한국관광공사 detailInfo API의 반복 항목을 저장
    contentypeid == 25(여행코스)는 CourseStop으로 분리하고, 나머지는 이 테이블에 적재
    """
    __tablename__ = "location_info_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    content_id: Mapped[str] = mapped_column(ForeignKey("locations.content_id"), index=True)
    serial_num: Mapped[str] = mapped_column(String(30), default="")
    info_name: Mapped[str] = mapped_column(String(100), default="")
    info_text: Mapped[str] = mapped_column(Text, default="")
    fldgubun: Mapped[str] = mapped_column(String(20), default="")

    location: Mapped[Location] = relationship(back_populates="info_items")


class CourseStop(Base):
    """여행코스(contenttypeid=25)의 경유지 정보

    코스에 포함된 하위 장소를 순서(sub_num) 기준으로 저장
    경유지 자체도 독립 Location일 수 있으나, 원본 API 구조상 별도 엔티티로 관리
    """
    __tablename__ = "course_stops"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_content_id: Mapped[str] = mapped_column(ForeignKey("locations.content_id"), index=True)
    sub_num: Mapped[int] = mapped_column(Integer, default=0)
    sub_content_id: Mapped[str] = mapped_column(String(30), default="")
    sub_name: Mapped[str] = mapped_column(String(200), default="")
    sub_overview: Mapped[str] = mapped_column(Text, default="")
    sub_image: Mapped[str] = mapped_column(Text, default="")
    sub_alt: Mapped[str] = mapped_column(String(200), default="")

    course: Mapped[Location] = relationship(back_populates="course_stops")


class Post(Base):
    """익명 커뮤니티 게시글

    의뢰서 요구사항에 따라 회원가입 없이 평문 비밀번호로 수정/삭제 권한을 확인
    place_name과 content_id(FK)로 특정 장소와 연결할 수 있다
    """
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), index=True)
    content: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(80), index=True, default="자유")
    place_name: Mapped[str] = mapped_column(String(200), default="")
    content_id: Mapped[str | None] = mapped_column(ForeignKey("locations.content_id"), nullable=True)
    password: Mapped[str] = mapped_column(String(200)) # 개발 의뢰서에서 평문 저장을 요구
    like_count: Mapped[int] = mapped_column(Integer, default=0)
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    likes: Mapped[list["PostLike"]] = relationship(back_populates="post", cascade="all, delete-orphan")
    location: Mapped[Location | None] = relationship(back_populates="posts")


class PostLike(Base):
    """게시글 좋아요 기록

    로그인 없는 익명 환경에서 IP + User-Agent 조합의 SHA-256 해시를
    fingerprint로 사용하여 동일 클라이언트의 중복 좋아요를 방지
    UNIQUE 제약으로 DB 수준에서도 중복을 차단
    """
    __tablename__ = "post_likes"
    __table_args__ = (
        UniqueConstraint("post_id", "fingerprint", name="uq_post_like"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"), index=True)
    fingerprint: Mapped[str] = mapped_column(String(64))  # SHA-256 hex digest
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    post: Mapped["Post"] = relationship(back_populates="likes")


class RagSource(Base):
    """RAG 청크의 출처 문서 정보

    PDF 파일명과 라이선스 정보를 관리하여 챗봇 답변의 출처 표기에 활용
    """
    __tablename__ = "rag_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_name: Mapped[str] = mapped_column(String(300), unique=True, index=True)
    license_note: Mapped[str] = mapped_column(Text, default="Provided project data")

    chunks: Mapped[list["RagChunk"]] = relationship(back_populates="source", cascade="all, delete-orphan")


class RagChunk(Base):
    """RAG 검색용 텍스트 청크

    PDF에서 추출한 텍스트를 chunk 단위로 저장
    FAISS 벡터 인덱스에 임베딩되어 챗봇의 의미 검색에 사용
    chunk_id에 UNIQUE 제약을 걸어 중복 적재를 방지
    """
    __tablename__ = "rag_chunks"
    __table_args__ = (UniqueConstraint("chunk_id", name="uq_rag_chunk_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("rag_sources.id"), index=True)
    chunk_id: Mapped[str] = mapped_column(String(400), index=True)
    content: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")

    source: Mapped[RagSource] = relationship(back_populates="chunks")
