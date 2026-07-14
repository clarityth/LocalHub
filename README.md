# LocalHub

LocalHub는 대전/충청 권역의 지역 정보를 공유하는 공공데이터 기반 익명 커뮤니티 프로젝트입니다.
FastAPI 기반의 백엔드와 SQLite 데이터베이스, 그리고 테스트용 Vue.js 클라이언트로 구성되어 있습니다.

## 핵심 아키텍처

- `data/json` 내부의 공공데이터를 정규화된 테이블(`locations`)에 적재합니다.
- `data/rag` 내부의 가이드북 데이터를 `rag_sources`와 `rag_chunks` 테이블에 적재합니다.
- `OPENAI_API_KEY` 환경변수가 설정된 경우, FAISS와 OpenAI Embedding API를 활용하여 RAG 검색을 수행합니다.
- FAISS 검색 결과를 기반으로 OpenAI Chat API가 응답을 생성합니다.
- 챗봇 응답은 객관적인 출처 문서(`sources`)와 화면상에 렌더링될 장소 데이터(`referenced_items`)를 구분하여 반환합니다.

## 환경 설정

프로젝트 최상단 디렉토리에 `.env` 파일을 생성하고 다음 환경 변수를 설정합니다:

```bash
OPENAI_API_KEY=your_key
DATABASE_URL=sqlite:///./localhub.db
AUTO_SEED=true
FRONTEND_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_CHAT_MODEL=gpt-4o-mini
VECTOR_CACHE_DIR=.cache/localhub
```

## 백엔드 실행 방법

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- `AUTO_SEED=true` 설정 시, 최초 실행 단계에서 SQLite 데이터베이스에 공공데이터 시딩이 자동 수행됩니다.
- 초기 실행 시 OpenAI API를 호출하여 `.cache/localhub` 경로에 임베딩 캐시를 구축합니다.

## 프론트엔드 테스트 클라이언트

```bash
cd frontend
npm install
npm run dev
```

브라우저에서 `http://127.0.0.1:5173`으로 접속하여 테스트할 수 있습니다.

## API 명세 요약

자세한 API 스펙은 `docs/api_specification.md` 문서를 참조하십시오.

- `GET /api/locations` (장소 목록 검색)
- `GET /api/locations/{contentid}` (단일 장소 상세 조회 및 주변 추천)
- `GET /api/posts` (커뮤니티 글 목록)
- `GET /api/posts/{post_id}` (커뮤니티 글 상세 조회)
- `POST /api/posts` (커뮤니티 글 등록)
- `PUT /api/posts/{post_id}` (커뮤니티 글 수정)
- `DELETE /api/posts/{post_id}` (커뮤니티 글 삭제)
- `POST /api/posts/{post_id}/like` (게시글 추천/좋아요)
- `POST /api/chat` (AI 챗봇 질의응답 및 SSE 스트리밍)

## 배포 (Render)

프로젝트 루트의 `render.yaml` 파일을 사용하여 백엔드를 자동 배포할 수 있습니다. 
SQLite 데이터 보존 및 FAISS 캐시 관리를 위해 `/var/data` 경로에 영구 디스크(Persistent Disk)가 마운트됩니다.

Render 대시보드의 환경변수 설정에서 `OPENAI_API_KEY`를 반드시 기입해야 합니다.
(참고: `DATABASE_URL` 및 `VECTOR_CACHE_DIR`은 `render.yaml` 내부에 `/var/data` 기준으로 설정되어 있습니다.)
