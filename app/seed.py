"""
데이터베이스 스키마 생성 및 초기 데이터 적재(Seed) 모듈.
제공된 JSON 파일 및 PDF 텍스트 데이터를 읽어 DB에 저장합니다.
"""

import json
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core import REPO_ROOT
from app.models import (
    ContentType,
    CourseStop,
    Location,
    LocationInfoItem,
    Post,
    RagChunk,
    RagSource,
)


DATA_DIR = REPO_ROOT / "data"
JSON_DIR = DATA_DIR / "json"
RAG_DIR = DATA_DIR / "rag"

COMMON_KEYS = {
    "addr1",
    "addr2",
    "areacode",
    "cat1",
    "cat2",
    "cat3",
    "contentid",
    "contenttypeid",
    "createdtime",
    "firstimage",
    "firstimage2",
    "cpyrhtDivCd",
    "mapx",
    "mapy",
    "mlevel",
    "modifiedtime",
    "sigungucode",
    "tel",
    "title",
    "zipcode",
    "lDongRegnCd",
    "lDongSignguCd",
    "lclsSystm1",
    "lclsSystm2",
    "lclsSystm3",
    "detail_info",
    "pet_info",
}


def create_schema(db: Session) -> None:
    """
    데이터베이스 모델을 기반으로 모든 테이블을 생성합니다.
    """
    from app.core import Base, engine

    Base.metadata.create_all(bind=engine)


def seed_if_empty(db: Session) -> None:
    """
    데이터베이스가 비어있을 경우, 장소(Location) 데이터와 
    RAG(Retrieval-Augmented Generation) 텍스트 청크를 DB에 적재합니다.
    """
    location_count = db.scalar(select(func.count(Location.content_id))) or 0
    rag_count = db.scalar(select(func.count(RagChunk.id))) or 0
    if location_count == 0:
        # 제공된 JSON 데이터는 공공 API를 매번 호출하지 않도록 초기 DB 데이터로 적재합니다.
        seed_locations(db)
    if rag_count == 0:
        # PDF에서 추출된 텍스트 청크(chunk)는 챗봇의 근거 문서로 활용하기 위해 적재합니다.
        seed_rag_chunks(db)
    db.commit()


def reset_and_seed(db: Session) -> None:
    """
    기존 데이터베이스의 모든 데이터를 삭제(Reset)한 뒤,
    초기 데이터 적재(Seed)를 처음부터 다시 수행합니다.
    """
    db.execute(delete(Post))
    db.execute(delete(LocationInfoItem))
    db.execute(delete(CourseStop))
    db.execute(delete(Location))
    db.execute(delete(ContentType))
    db.execute(delete(RagChunk))
    db.execute(delete(RagSource))
    db.commit()
    seed_locations(db)
    seed_rag_chunks(db)
    db.commit()


def seed_locations(db: Session) -> None:
    """
    'data/json' 디렉토리에 있는 JSON 파일을 파싱하여, 
    콘텐츠 타입(ContentType)과 장소(Location) 데이터를 DB에 저장합니다.
    """
    if not JSON_DIR.exists():
        return

    for path in sorted(JSON_DIR.glob("*.json")):
        payload = _read_json(path)
        if not isinstance(payload, dict):
            continue

        content_type_id = int(payload.get("contentTypeId") or 0)
        content_type_name = str(payload.get("contentType") or content_type_id)
        if not content_type_id:
            continue

        content_type = db.get(ContentType, content_type_id)
        if not content_type:
            content_type = ContentType(id=content_type_id, name=content_type_name)
            db.add(content_type)

        for item in payload.get("items", []):
            if not isinstance(item, dict) or not item.get("contentid"):
                continue

            location = Location(
                content_id=str(item.get("contentid", "")),
                content_type_id=content_type_id,
                region=str(payload.get("region") or "대전/충청"),
                title=str(item.get("title") or ""),
                addr1=str(item.get("addr1") or ""),
                addr2=str(item.get("addr2") or ""),
                mapx=_to_float(item.get("mapx")),
                mapy=_to_float(item.get("mapy")),
                mlevel=str(item.get("mlevel") or ""),
                firstimage=str(item.get("firstimage") or ""),
                firstimage2=str(item.get("firstimage2") or ""),
                tel=str(item.get("tel") or ""),
                zipcode=str(item.get("zipcode") or ""),
                raw_json=json.dumps(item, ensure_ascii=False),
                type_fields_json=json.dumps(_type_fields(item), ensure_ascii=False),
            )
            db.merge(location)
            db.flush()
            _seed_location_children(db, item, content_type_id)


def seed_rag_chunks(db: Session) -> None:
    """
    'data/rag' 디렉토리에 있는 JSON 파일을 파싱하여, 
    챗봇이 참고할 문서 출처(RagSource)와 청크(RagChunk) 데이터를 DB에 저장합니다.
    """
    if not RAG_DIR.exists():
        return

    sources: dict[str, RagSource] = {}
    for path in sorted(RAG_DIR.glob("*.json")):
        chunks = _read_json(path)
        if not isinstance(chunks, list):
            continue

        for chunk in chunks:
            if not isinstance(chunk, dict) or not chunk.get("chunk_id"):
                continue
            source_name = str(chunk.get("source") or path.name)
            source = sources.get(source_name)
            if source is None:
                source = db.scalar(select(RagSource).where(RagSource.source_name == source_name))
                if source is None:
                    source = RagSource(source_name=source_name)
                    db.add(source)
                    db.flush()
                sources[source_name] = source

            db.merge(
                RagChunk(
                    chunk_id=str(chunk.get("chunk_id")),
                    source_id=source.id,
                    content=str(chunk.get("content") or ""),
                    metadata_json=json.dumps(
                        {
                            "file": path.name,
                            "source": source_name,
                            "note": "Coordinates are intentionally not inferred from PDF chunks.",
                        },
                        ensure_ascii=False,
                    ),
                )
            )


def _seed_location_children(db: Session, item: dict[str, Any], content_type_id: int) -> None:
    """
    주어진 장소(item)의 하위 세부 정보(상세 설명, 코스 정보 등)를 파싱하여 DB에 저장합니다.
    """
    detail_info = item.get("detail_info")
    if not isinstance(detail_info, list):
        return

    content_id = str(item.get("contentid"))
    for row in detail_info:
        if not isinstance(row, dict):
            continue
        if content_type_id == 25:
            db.add(
                CourseStop(
                    course_content_id=content_id,
                    sub_num=_to_int(row.get("subnum")),
                    sub_content_id=str(row.get("subcontentid") or ""),
                    sub_name=str(row.get("subname") or ""),
                    sub_overview=str(row.get("subdetailoverview") or ""),
                    sub_image=str(row.get("subdetailimg") or ""),
                    sub_alt=str(row.get("subdetailalt") or ""),
                )
            )
        else:
            db.add(
                LocationInfoItem(
                    content_id=content_id,
                    serial_num=str(row.get("serialnum") or ""),
                    info_name=str(row.get("infoname") or ""),
                    info_text=str(row.get("infotext") or ""),
                    fldgubun=str(row.get("fldgubun") or ""),
                )
            )


def _read_json(path: Path) -> Any:
    """
    주어진 경로의 JSON 파일을 읽어 파이썬 객체로 반환합니다.
    """
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _type_fields(item: dict[str, Any]) -> dict[str, Any]:
    """
    공통 필드를 제외한 관광 타입별 고유 상세 필드만 추출하여 딕셔너리로 반환합니다.
    """
    # 공통 필드 외 나머지는 콘텐츠 타입별로 상이하므로, JSON 객체 형태로 보존하기 위해 필터링합니다.
    return {
        key: value
        for key, value in item.items()
        if key not in COMMON_KEYS and value not in (None, "", [], {})
    }


def _to_float(value: Any) -> float:
    """
    주어진 값을 실수(float)로 안전하게 변환합니다. 변환에 실패하면 0.0을 반환합니다.
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_int(value: Any) -> int:
    """
    주어진 값을 정수(int)로 안전하게 변환합니다. 변환에 실패하면 0을 반환합니다.
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


if __name__ == "__main__":
    from app.core import SessionLocal

    with SessionLocal() as session:
        create_schema(session)
        reset_and_seed(session)
        print("Seed completed.")
