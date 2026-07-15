import json
import glob
import os

def filter_daejeon_batch(directory_path):
    # 지정된 디렉터리 내의 'enriched_*.json' 패턴을 가진 모든 파일 검색
    file_pattern = os.path.join(directory_path, "enriched_*.json")
    file_list = glob.glob(file_pattern)
    
    for file_path in file_list:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # '대전' 데이터 필터링 (items 키가 없거나 비어있는 경우 대비)
        items = data.get('items', [])
        filtered_items = [item for item in items if '대전' in item.get('addr1', '')]
        
        # 데이터 갱신
        data['items'] = filtered_items
        data['total'] = len(filtered_items)
        
        # 새 파일명 생성 (예: filtered_enriched_대전_충청권_관광지.json)
        file_name = os.path.basename(file_path)
        new_file_path = os.path.join(directory_path, f"filtered_{file_name}")
        
        # 결과 저장
        with open(new_file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

# 실행 예시 (현재 터미널 경로인 data/json 폴더 지정)
filter_daejeon_batch(r'C:\Users\SSAFY\PycharmProjects\ssafy-startcamp\data\json')