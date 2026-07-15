import requests
from bs4 import BeautifulSoup
import re
import json
import concurrent.futures
from langchain_text_splitters import RecursiveCharacterTextSplitter

# HTTP 요청 헤더
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# 요청하신 URL별 Source 명칭 매핑
SOURCE_MAP = {
    "https://daejeontour.co.kr/month_djt": "대전관광 - 이달의 대전",
    "https://daejeontour.co.kr/recommend_djt": "대전관광 - 추천코스",
    "https://daejeontour.co.kr/find_djt": "대전관광 - 대전 구석구석",
    "https://daejeontour.co.kr/subway_djt": "대전관광 - 지하철 여행",
    "https://daejeontour.co.kr/work_djt": "대전관광 - 도보 여행길"
}

def clean_text(text):
    """연속된 공백 및 줄바꿈을 단일 공백으로 정제"""
    return re.sub(r'\s+', ' ', text).strip()

def extract_detail_text(url):
    """상세 페이지에 접속하여 노이즈 DOM을 제거하고 본문 텍스트 추출"""
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # 임베딩 노이즈 일괄 제거
        for tag in soup(['header', 'footer', 'nav', 'script', 'style']):
            tag.decompose()
            
        noise_classes = ['add_section_wrap', 'rb_bbs_top', 'btns_gr_wrap', 'rb_bo_top', 'rb_bo_btm', 'pg_wrap']
        for noise in noise_classes:
            for el in soup.find_all(class_=noise):
                el.decompose()

        raw_text = soup.get_text(separator=' ')
        return clean_text(raw_text)

    except Exception as e:
        return ""

def get_all_detail_urls(base_url):
    """페이지네이션을 순회하며 해당 게시판의 모든 상세 URL 수집"""
    detail_urls = set()
    try:
        response = requests.get(base_url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        max_page = 1
        pagination_links = soup.select('.pg_wrap a.pg_page')
        
        for link in pagination_links:
            href = link.get('href', '')
            match = re.search(r'page=(\d+)', href)
            if match:
                max_page = max(max_page, int(match.group(1)))
                
        for page in range(1, max_page + 1):
            page_url = f"{base_url}?page={page}"
            page_response = requests.get(page_url, headers=HEADERS, timeout=10)
            page_soup = BeautifulSoup(page_response.text, 'html.parser')
            
            board_list = page_soup.select('#fboardlist ul div.rb_bbs_for_wrap a')
            for a_tag in board_list:
                href = a_tag.get('href', '')
                if href and re.search(r'\d+$', href):
                    detail_urls.add(href)
                    
    except Exception as e:
        print(f"[오류] 목록 페이지 수집 실패 ({base_url}): {e}")
        
    return list(detail_urls)

def process_url_with_chunking(detail_url, source_name, text_splitter):
    """상세 페이지 텍스트 추출 후 청크 단위로 분할하여 반환"""
    text = extract_detail_text(detail_url)
    if not text:
        return []
        
    post_id = detail_url.split('/')[-1]
    
    # Langchain Text Splitter 구동
    docs = text_splitter.create_documents([text])
    
    chunks = []
    for idx, doc in enumerate(docs, 1):
        chunks.append({
            "chunk_id": f"{source_name}_{post_id}_{idx}",
            "source": source_name,
            "url": detail_url, # 참조 용이성을 위해 원본 URL 추가
            "content": doc.page_content.strip()
        })
    return chunks

if __name__ == "__main__":
    # 요청하신 청킹 전략 설정
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=100,
        separators=["\n\n", "\n", ". ", " "]
    )

    all_tasks = []
    
    # 1. 대상 게시판들을 순회하며 수집할 상세 URL 목록(Task) 생성
    for base_url, source_name in SOURCE_MAP.items():
        print(f"[스캔] '{source_name}' 게시판 탐색 중...")
        d_urls = get_all_detail_urls(base_url)
        print(f"       -> {len(d_urls)}건의 상세 페이지 발견")
        for url in d_urls:
            all_tasks.append((url, source_name))

    print(f"\n[작업 시작] 총 {len(all_tasks)}개의 문서 병렬 수집 및 청킹 진행 중...")
    
    final_chunked_data = []
    
    # 2. 병렬 처리로 데이터 추출 및 청킹 수행
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_task = {
            executor.submit(process_url_with_chunking, task[0], task[1], text_splitter): task 
            for task in all_tasks
        }
        
        completed = 0
        for future in concurrent.futures.as_completed(future_to_task):
            completed += 1
            task_url, task_source = future_to_task[future]
            try:
                chunks = future.result()
                if chunks:
                    final_chunked_data.extend(chunks)
                    print(f"  [{completed}/{len(all_tasks)}] 완료: {task_url} -> {len(chunks)}개 청크 분할")
            except Exception as e:
                print(f"  [{completed}/{len(all_tasks)}] 실패: {task_url} -> {e}")

    # 3. JSON 최종 저장
    output_filename = "daejeon_tour_chunked_data.json"
    with open(output_filename, "w", encoding="utf-8") as f:
        json.dump(final_chunked_data, f, ensure_ascii=False, indent=2)
        
    print(f"\n[작업 완료] {output_filename} 저장 완료 (총 생성된 청크: {len(final_chunked_data)}개)")