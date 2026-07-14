# LocalHub API 상세 명세서

**Base URL (Production - Render):** `https://[Render_Backend_URL]/api`
**Base URL (Local):** `http://localhost:8000/api`

> [!NOTE]  
> 본 서비스의 **프론트엔드(Vue.js)는 Netlify**에 배포되며, **백엔드(FastAPI)는 Render**에 배포되어 연동됩니다.
> 모든 API 응답은 `application/json` 포맷을 사용하며, `/chat` 엔드포인트에 한하여 `text/event-stream` 포맷을 사용합니다. 본 명세서의 장소 관련 속성 명칭(예: `firstimage`, `mapx`, `addr1`)은 데이터 호환성을 고려하여 한국관광공사(TourAPI)의 원본 규격을 준수합니다.

---

## 1. 장소 (Locations) API

### 1.1 전체 장소 목록 조회
- **Method:** `GET`
- **Endpoint:** `/locations/all`
- **Description:** 시스템에 등록된 모든 장소의 메타데이터를 반환합니다. (최대 1500개 제한)

#### Request
파라미터 없음

#### Response (200 OK)
반환 타입: JSON Array
```json
[
  {
    "contentid": "741957",
    "contenttypeid": 12,
    "contenttypename": "관광지",
    "title": "대전엑스포시민광장",
    "addr1": "대전광역시 서구 둔산대로 169",
    "addr2": "(만년동)",
    "mapx": 127.3845,
    "mapy": 36.3504,
    "mlevel": "6",
    "firstimage": "http://tong.visitkorea.or.kr/cms/resource/58/2558558_image2_1.jpg",
    "tel": "042-250-1400"
  }
]
```
- **`contentid`** (`str`): 장소의 고유 식별자 (한국관광공사 원본 ID)
- **`contenttypeid`** (`int`): 카테고리 식별 코드
- **`contenttypename`** (`str`): 카테고리 명칭 ("관광지", "음식점" 등)
- **`title`** (`str`): 장소 공식 명칭
- **`addr1`** (`str`): 기본 도로명/지번 주소
- **`addr2`** (`str`): 상세 주소 (데이터 부재 시 `""`)
- **`mapx`** (`float`): 경도 (Longitude)
- **`mapy`** (`float`): 위도 (Latitude)
- **`mlevel`** (`str`): 권장 지도 확대(Zoom) 레벨
- **`firstimage`** (`str`): 대표 원본 이미지 URL (데이터 부재 시 `""`)
- **`tel`** (`str`): 전화번호 (데이터 부재 시 `""`)

---

### 1.2 조건부 장소 목록 조회
- **Method:** `GET`
- **Endpoint:** `/locations`
- **Description:** 검색어 또는 카테고리에 해당하는 장소 목록을 반환합니다.

#### Request (Query Parameters)
| Parameter | Type | Required | Description | Example |
|---|---|---|---|---|
| `contenttypeid` | `int` | No | 카테고리 필터링 (12:관광지, 14:문화시설, 15:축제, 25:여행코스, 28:레포츠, 32:숙박, 38:쇼핑, 39:음식점) | `12` |
| `q` | `str` | No | 장소명(title) 또는 주소(addr1) 키워드 | `"엑스포"` |
| `limit` | `int` | No | 반환받을 최대 장소 개수 (기본 500) | `50` |

#### Response (200 OK)
반환 타입: JSON Array (응답 스키마는 `1.1 전체 장소 목록 조회`와 동일합니다)

---

### 1.3 특정 장소 상세 조회
- **Method:** `GET`
- **Endpoint:** `/locations/{contentid}`

**응답 예시 (`200 OK`):**
```json
{
  "contentid": "12345",
  "contenttypeid": 12,
  "contenttypename": "관광지",
  "title": "국립대전현충원",
  "addr1": "대전광역시 유성구 현충원로 251",
  "mapx": 127.2982,
  "mapy": 36.3687,
  "type_fields": {
    "usetime": "06:00~18:00",
    "parking": "주차 가능"
  },
  "detail_info": [],
  "course_stops": [],
  "nearby_restaurants": [
    {
      "contentid": "67890",
      "contenttypeid": 39,
      "contenttypename": "음식점",
      "title": "현충원 인근 맛집",
      "addr1": "대전광역시 유성구",
      "mapx": 127.3000,
      "mapy": 36.3700,
      "distance_km": 1.2
    }
  ],
  "nearby_accommodations": []
}
```
- **Description:** 특정 장소에 대한 상세 속성(영업시간, 부대시설 등) 및 반복 항목 데이터를 조회하고, 해당 장소 기준 반경 2km 이내의 **주변 추천 식당(최대 4개) 및 숙소(최대 4개) 정보**를 동적 계산하여 함께 반환합니다.

#### Request (Path Parameter)
| Parameter | Type | Required | Description | Example |
|---|---|---|---|---|
| `contentid` | `str` | **Yes** | 조회할 장소의 고유 식별자 | `741957` |

#### Response (200 OK)
반환 타입: JSON Object
```json
{
  "contentid": "741957",
  "contenttypeid": 12,
  "contenttypename": "관광지",
  "title": "대전엑스포시민광장",
  "addr1": "대전광역시 서구 둔산대로 169",
  "addr2": "(만년동)",
  "mapx": 127.3845,
  "mapy": 36.3504,
  "mlevel": "6",
  "firstimage": "http://...",
  "tel": "042-250-1400",
  "zipcode": "35204",
  "firstimage2": "http://..._thumb.jpg",
  "type_fields": {
    "chkbabycarriage": "유모차 대여 가능",
    "parking": "주차 가능 (최초 3시간 무료)"
  },
  "detail_info": [
    {
      "serialnum": "1",
      "infoname": "화장실",
      "infotext": "남녀 분리형 화장실 구비"
    }
  ],
  "course_stops": [
    {
      "subnum": 1,
      "subcontentid": "123001",
      "subname": "A 전시관",
      "subdetailoverview": "최신 과학 기술을 체험할 수 있는 공간입니다.",
      "subdetailimg": "http://...",
      "subdetailalt": "A 전시관 전경 사진"
    }
  ]
}
```
**세부 정보 필드 스키마:**
- **`zipcode`** (`str`): 우편번호
- **`firstimage2`** (`str`): 썸네일 해상도 이미지 URL
- **`type_fields`** (`dict`): 해당 장소 카테고리의 고유 부가 정보를 포함하는 키-값 쌍 (동적 객체)
- **`detail_info`** (`list`): 세부 정보 항목 배열
  - `serialnum` (`str`): 데이터 정렬 순번
  - `infoname` (`str`): 세부 정보 항목 명칭 (예: "이용요금")
  - `infotext` (`str`): 세부 정보 내용
- **`course_stops`** (`list`): 장소 유형이 '여행코스(25)'일 경우, 해당 코스에 포함된 하위 방문지 정보. 일반 카테고리의 경우 빈 배열(`[]`) 반환
  - `subnum` (`int`): 코스 방문 순서
  - `subcontentid` (`str`): 방문지 식별자
  - `subname` (`str`): 방문지 명칭
  - `subdetailoverview` (`str`): 방문지 개요
  - `subdetailimg` (`str`): 방문지 사진 URL
  - `subdetailalt` (`str`): 대체 텍스트
- **`nearby_restaurants`** (`list`): 기준 반경 2km 이내의 '음식점(39)' 객체 배열 (거리순 최대 4개). `distance_km` 필드가 포함됩니다.
- **`nearby_accommodations`** (`list`): 기준 반경 2km 이내의 '숙박(32)' 객체 배열 (거리순 최대 4개). `distance_km` 필드가 포함됩니다.

#### Error Response (404 Not Found)
```json
{
  "detail": "Location not found"
}
```

---

## 2. 커뮤니티 (Posts) API

### 2.1 게시글 목록 조회
- **Method:** `GET`
- **Endpoint:** `/posts`
- **Description:** 익명 커뮤니티 게시글을 최신 작성일 기준으로 내림차순 정렬하여 반환합니다. 본문은 트래픽 최적화를 위해 첫 160자로 제한되어 반환됩니다.

#### Request (Query Parameters)
| Parameter | Type | Required | Description | Example |
|---|---|---|---|---|
| `category` | `str` | No | 카테고리 필터 ("자유", "여행 후기", "맛집 추천" 등) | `"여행 후기"` |
| `q` | `str` | No | 제목, 본문, 연관 장소명 검색 키워드 | `"성심당"` |
| `search_type` | `str` | No | 검색 대상 ("both"(제목+내용 기본값), "title", "content") | `"title"` |
| `sort_by` | `str` | No | 정렬 기준 ("latest"(최신순 기본값), "likes"(추천순)) | `"likes"` |
| `limit` | `int` | No | 응답 최대 개수 (기본 50) | `20` |

#### Response (200 OK)
반환 타입: JSON Array
```json
[
  {
    "id": 1,
    "title": "대전역 맛집 추천",
    "place": "성심당 대전역점",
    "content": "대전역 도착하자마자 들렀는데 튀김소보로 줄이...",
    "category": "맛집 추천",
    "contentid": "54321",
    "like_count": 5,
    "view_count": 23,
    "created_at": "2024-03-21T05:22:11.123Z",
    "updated_at": "2024-03-21T05:22:11.123Z"
  }
]
```
- **`id`** (`int`): 게시글 고유 번호 (Primary Key)
- **`title`** (`str`): 게시글 제목
- **`place`** (`str`): 연관 장소명
- **`content`** (`str`): 요약된 본문 텍스트
- **`category`** (`str`): 게시판 분류명
- **`contentid`** (`str` | `null`): 연동된 DB 장소 고유 식별자
- **`like_count`** (`int`): 누적 추천 수
- **`view_count`** (`int`): 조회수
- **`created_at`** (`str`): 작성 일시 (ISO 8601 포맷)
- **`updated_at`** (`str`): 최종 수정 일시 (ISO 8601 포맷)

---

### 2.2 단일 게시글 상세 조회
- **Method:** `GET`
- **Endpoint:** `/posts/{post_id}`
- **Description:** 게시글 상세 원문(전체 본문 포함)을 반환하며 내부 조회수를 증가시킵니다.

#### Request (Path Parameter)
| Parameter | Type | Required | Description | Example |
|---|---|---|---|---|
| `post_id` | `int` | **Yes** | 조회할 대상 게시글 번호 | `1` |

#### Response (200 OK)
반환 타입: JSON Object (`2.1 게시글 목록 조회` 스키마와 동일하나, `content` 필드에 요약되지 않은 본문 데이터가 포함됩니다.)
```json
{
  "id": 1,
  "title": "대전역 맛집 추천",
  "place": "성심당 대전역점",
  "content": "대전역 도착하자마자 들렀는데 튀김소보로 줄이 엄청 길었습니다. 그래도 금방 줄어드니 포기하지 말고 꼭 사드세요.",
  "category": "맛집 추천",
  "contentid": "54321",
  "like_count": 5,
  "view_count": 24,
  "created_at": "2024-03-21T05:22:11.123Z",
  "updated_at": "2024-03-21T05:22:11.123Z"
}
```

---

### 2.3 익명 게시글 등록
- **Method:** `POST`
- **Endpoint:** `/posts`
- **Description:** 평문 비밀번호 검증 시스템을 포함하여 신규 게시글 데이터를 추가합니다.

#### Request (Body - JSON)
| Field | Type | Required | Description |
|---|---|---|---|
| `title` | `str` | **Yes** | 게시글 제목 (최대 200자) |
| `content` | `str` | **Yes** | 게시글 본문 |
| `password` | `str` | **Yes** | 수정 및 삭제용 암호 지정 (평문) |
| `category` | `str` | No | 분류명 (기본값: "자유") |
| `place` | `str` | No | 연관 장소명 기재 |
| `contentid` | `str` | No | 연관 장소 식별 번호 |

```json
{
  "title": "엑스포 야경",
  "place": "엑스포 다리",
  "content": "가족들과 산책하기 좋습니다.",
  "category": "여행 후기",
  "contentid": "999999",
  "password": "userpassword123"
}
```

#### Response (201 Created)
반환 타입: JSON Object
```json
{
  "message": "게시글이 성공적으로 등록되었습니다.",
  "id": 2
}
```

---

### 2.4 게시글 수정
- **Method:** `PUT`
- **Endpoint:** `/posts/{post_id}`
- **Description:** 게시글 작성 시 기재한 비밀번호에 대한 권한을 확인하고 특정 항목의 데이터를 수정(Partial Update)합니다.

#### Request (Path Parameter & Body - JSON)
- **Path Parameter:** `post_id` (수정 대상 게시글 번호)
- **Body:** `password` 필드는 필수이며, 갱신할 필드 속성만 포함하여 전송합니다.
```json
{
  "title": "수정할 제목",
  "content": "새로운 본문 내용",
  "password": "userpassword123"
}
```

#### Response (200 OK)
```json
{
  "message": "게시글이 성공적으로 수정되었습니다."
}
```

#### Error Responses
- **403 Forbidden**: 비밀번호 검증 실패
- **404 Not Found**: 존재하지 않는 식별 번호

---

### 2.5 게시글 삭제
- **Method:** `DELETE`
- **Endpoint:** `/posts/{post_id}`
- **Description:** 비밀번호 검증 후 게시글 데이터 및 연관 데이터를 영구 삭제합니다.

#### Request (Path Parameter & Body - JSON)
- **Path Parameter:** `post_id` (삭제 대상 게시글 번호)
- **Body:**
```json
{
  "password": "userpassword123"
}
```

#### Response (200 OK)
```json
{
  "message": "게시글이 삭제되었습니다."
}
```

---

### 2.6 게시글 추천(좋아요)
- **Method:** `POST`
- **Endpoint:** `/posts/{post_id}/like`
- **Description:** 특정 게시글에 대한 추천 수를 상향합니다. 접속 클라이언트의 IP 주소와 `User-Agent` 기반 해싱 알고리즘을 적용하여 단일 대상에 대한 중복 처리를 제어합니다.

#### Request
- **Path Parameter:** `post_id`
- *(Body 없음)*

#### Response (200 OK)
```json
{
  "post_id": 1,
  "like_count": 13,
  "message": "좋아요가 반영되었습니다."
}
```

#### Error Response (409 Conflict)
식별된 클라이언트의 기 추천 이력이 존재할 경우 반환됩니다.
```json
{
  "detail": "이미 좋아요를 누르셨습니다."
}
```

---

## 3. AI 챗봇 (Chat) API

### 3.1 챗봇 질의 및 스트리밍(SSE) 응답 수신
- **Method:** `POST`
- **Endpoint:** `/chat`
- **Description:** 사용자 발화 및 대화 이력을 바탕으로 FAISS 지식 베이스 검토 결과를 포함한 OpenAI 응답을 Server-Sent Events(SSE) 프로토콜 규격으로 제공합니다.

#### Request (Body - JSON)
| Field | Type | Required | Description |
|---|---|---|---|
| `message` | `str` | **Yes** | 현재 사용자 질의 텍스트 |
| `history` | `list` | No | 이전 챗봇 대화 이력 객체 배열 (`role`, `content` 구조) |

```json
{
  "message": "아이들과 갈만한 곳을 알려줘",
  "history": [
    {
      "role": "user",
      "content": "안녕하세요 대전 여행을 계획 중입니다."
    },
    {
      "role": "assistant",
      "content": "반갑습니다! 무엇을 도와드릴까요?"
    }
  ]
}
```

#### Response (`Content-Type: text/event-stream`)
서버와 커넥션이 체결된 이후 `data: ` 프리픽스를 지닌 문자열이 점진적으로 전송됩니다. 프론트엔드는 이 스트림 응답을 개행 문자(`\n\n`) 단위로 파싱하여 처리해야 합니다.

**1. 메타데이터 이벤트 (최초 1회 수신)**
챗봇 답변 생성의 배경이 된 장소 데이터 및 RAG 출처 정보를 `type: metadata` 형태로 전송합니다.
```text
data: {"type": "metadata", "referenced_items": [{"contentid": "741957", "contenttypeid": 12, "contenttypename": "관광지", "title": "대전엑스포시민광장", "addr1": "대전광역시 서구 둔산대로 169", "addr2": "(만년동)", "mapx": 127.3845, "mapy": 36.3504, "mlevel": "6", "firstimage": "http://...", "tel": "042-250-1400"}], "sources": [{"chunk_id": "pdf-chunk-12", "source": "대전 반려동물 동반여행안내서.pdf"}]}

```

**2. 텍스트 스트리밍 이벤트 (다수 수신)**
AI 추론을 통해 생성된 텍스트 스트림 버퍼가 `type: content` 형태로 지속 발송됩니다. 클라이언트는 이 `text` 속성값을 누적 연산하여 텍스트 렌더링에 반영해야 합니다.
```text
data: {"type": "content", "text": "아이"}

data: {"type": "content", "text": "들과 "}

data: {"type": "content", "text": "함께 가기 좋은..."}

```

**3. 스트리밍 종료 시그널**
텍스트 스트리밍 전송이 완료될 경우 시스템은 `[DONE]` 시그널을 출력 후 커넥션을 반환합니다.
```text
data: [DONE]

```

**4. 런타임 에러 이벤트**
생성 중 API 통신 장애 등 오류가 식별될 경우, 강제 종료를 방지하기 위해 예외 메시지를 텍스트 스트림 형태로 1회 전송 후 커넥션을 반환합니다.
```text
data: {"type": "content", "text": "\n\n**[시스템 알림]** 챗봇 응답 생성 중 오류가 발생했습니다: 오류 상세 메시지"}

data: [DONE]

```

#### (참고) 클라이언트 파싱 로직 구현 예시
```javascript
const response = await fetch('/api/chat', { method: 'POST', body: JSON.stringify(payload) });
const reader = response.body.getReader();
const decoder = new TextDecoder('utf-8');
let buffer = '';

while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  buffer += decoder.decode(value, { stream: true });
  const lines = buffer.split('\n');
  buffer = lines.pop() || ''; // 완전하지 않은 마지막 데이터 블록 보존

  for (const line of lines) {
    if (line.startsWith('data: ')) {
      const dataStr = line.slice(6).trim();
      if (dataStr === '[DONE]') return; // 스트리밍 종료
      if (!dataStr) continue;

      const data = JSON.parse(dataStr);
      if (data.type === 'metadata') {
        // data.referenced_items 및 data.sources 렌더링 수행
      } else if (data.type === 'content') {
        // data.text 속성을 기존 출력 문자열 객체에 누적 
      }
    }
  }
}
```
