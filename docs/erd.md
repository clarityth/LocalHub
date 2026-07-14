# LocalHub 데이터베이스 ERD (Entity-Relationship Diagram)

본 프로젝트는 공공데이터 기반 장소 정보와 익명 커뮤니티, RAG 챗봇 데이터를 관리하기 위해 SQLite와 SQLAlchemy ORM을 사용하여 데이터베이스 스키마를 설계했습니다.

```mermaid
erDiagram
    CONTENT_TYPES ||--o{ LOCATIONS : "has (1:N)"
    LOCATIONS ||--o{ LOCATION_INFO_ITEMS : "has (1:N)"
    LOCATIONS ||--o{ COURSE_STOPS : "has (1:N)"
    LOCATIONS ||--o{ POSTS : "referenced_by (1:N)"
    POSTS ||--o{ POST_LIKES : "has (1:N)"
    RAG_SOURCES ||--o{ RAG_CHUNKS : "has (1:N)"

    CONTENT_TYPES {
        int id PK "카테고리 ID"
        string name "관광지, 음식점 등"
    }

    LOCATIONS {
        string content_id PK "한국관광공사 고유 ID"
        int content_type_id FK
        string region "권역"
        string title "장소명"
        string addr1 "기본 주소"
        string addr2 "상세 주소"
        float mapx "경도"
        float mapy "위도"
        string mlevel "지도 확대 레벨"
        text firstimage "대표 이미지 원본"
        text firstimage2 "대표 이미지 썸네일"
        string tel "전화번호"
        string zipcode "우편번호"
        text raw_json "공공데이터 JSON 원본"
        text type_fields_json "유연한 스키마 보관용 JSON"
        datetime created_at
        datetime updated_at
    }

    LOCATION_INFO_ITEMS {
        int id PK
        string content_id FK
        string serial_num "정렬 순번"
        string info_name "항목명 (예: 화장실)"
        text info_text "상세 내용"
        string fldgubun
    }

    COURSE_STOPS {
        int id PK
        string course_content_id FK
        int sub_num "코스 내 방문 순서"
        string sub_content_id "방문지 고유 ID"
        string sub_name "방문지 이름"
        text sub_overview "방문지 개요"
        text sub_image "방문지 사진"
        string sub_alt "사진 대체 텍스트"
    }

    POSTS {
        int id PK
        string title "게시글 제목"
        text content "게시글 본문"
        string category "게시판 카테고리"
        string place_name "연관 장소 이름"
        string content_id FK "연관 장소 ID (nullable)"
        string password "권한 확인용 비밀번호 (평문)"
        int like_count "누적 추천 수"
        int view_count "조회수"
        datetime created_at
        datetime updated_at
    }

    POST_LIKES {
        int id PK
        int post_id FK
        string fingerprint "IP+User-Agent SHA-256 해시"
        datetime created_at
    }

    RAG_SOURCES {
        int id PK
        string source_name "문서/PDF 원본 파일명 (Unique)"
        text license_note "라이선스 정보"
    }

    RAG_CHUNKS {
        int id PK
        int source_id FK
        string chunk_id "청크 단위 고유 ID (Unique)"
        text content "벡터 검색용 텍스트"
        text metadata_json "부록 메타데이터"
    }
```

### 주요 설계 포인트
1. **Flexible Schema (유연한 스키마)**: 
   - `LOCATIONS` 테이블은 관광지, 축제, 음식점 등 각 카테고리(`CONTENT_TYPES`)마다 상이한 속성을 가집니다. 이를 고정 컬럼으로 만들지 않고 `type_fields_json`이라는 Text 필드에 JSON으로 밀어넣어 유연하게 수용했습니다.
2. **익명 환경 중복 방지 (Fingerprinting)**:
   - `POST_LIKES` 테이블은 로그인 및 회원이 없는 익명 시스템에서 중복 좋아요를 방지하기 위해 사용자의 IP와 브라우저 헤더를 조합해 해싱한 `fingerprint`를 기록합니다.
3. **평문 비밀번호**:
   - `POSTS` 테이블의 `password`는 의뢰서의 '교육 목적' 설계 지침에 따라 의도적으로 암호화 없이 평문으로 저장됩니다.
4. **Vector DB 이중화 구조**:
   - RAG 챗봇을 위한 임베딩 자체는 파일 기반 FAISS(.cache 폴더)에 저장되지만, 해당 원본 텍스트 및 메타데이터는 관계형 DB인 `RAG_SOURCES`와 `RAG_CHUNKS`에 저장하여 무결성을 유지합니다.
