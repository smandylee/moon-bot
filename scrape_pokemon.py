#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
from bs4 import BeautifulSoup
import re
import json
import time

def scrape_pokemon_data():
    """포켓몬 스칼렛/바이올렛 위치 정보를 스크래핑합니다."""
    urls = [
        "https://mlove1039.tistory.com/60",
        "https://mlove1039.tistory.com/66", 
        "https://mlove1039.tistory.com/67"
    ]
    
    pokemon_data = {}
    
    for url in urls:
        print(f"스크래핑 중: {url}")
        
        try:
            response = requests.get(url)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # 테이블 찾기
            tables = soup.find_all('table')
            
            for table in tables:
                rows = table.find_all('tr')
                
                for row in rows:
                    cells = row.find_all('td')
                    
                    if len(cells) >= 4:  # 최소 4개 셀이 있어야 함
                        try:
                            # 도감번호 추출 (첫 번째 셀)
                            number_cell = cells[0]
                            number_text = number_cell.get_text(strip=True)
                            number_match = re.search(r'(\d+)', number_text)
                            
                            if not number_match:
                                continue
                                
                            number = int(number_match.group(1))
                            
                            # 포켓몬 이름 추출 (세 번째 셀)
                            name_cell = cells[2]
                            name_text = name_cell.get_text(strip=True)
                            
                            if not name_text or name_text == '':
                                continue
                                
                            pokemon_name = name_text
                            
                            # 위치 정보 추출 (네 번째 셀)
                            location_cell = cells[3]
                            location_text = location_cell.get_text(strip=True)
                            
                            # 위치 맵 이미지 추출
                            map_image = ""
                            img_tag = location_cell.find('img')
                            if img_tag:
                                map_image = img_tag.get('src', '')
                            
                            # 맵 이미지가 없으면 텍스트 링크 확인
                            if not map_image:
                                link_tag = location_cell.find('a')
                                if link_tag:
                                    map_image = link_tag.get('href', '')
                            
                            # 진화 조건 추출 (다섯 번째 셀)
                            evolution_cell = cells[4] if len(cells) > 4 else None
                            evolution_text = evolution_cell.get_text(strip=True) if evolution_cell else ""
                            
                            # 기본 위치 정보 (전체 텍스트에서 괄호 제거)
                            basic_location = location_text.strip()
                            # 괄호 안의 텍스트가 있으면 그것을 사용
                            location_match = re.search(r'\((.*?)\)', location_text)
                            if location_match:
                                basic_location = location_match.group(1)
                            
                            # 데이터 저장
                            pokemon_data[number] = {
                                "number": number,
                                "name": pokemon_name,
                                "map_image": map_image,
                                "evolution": evolution_text,
                                "basic_location": basic_location
                            }
                            
                            print(f"추출됨: {number:03d} - {pokemon_name}")
                            
                        except Exception as e:
                            print(f"행 처리 중 오류: {e}")
                            continue
            
            # 요청 간 딜레이
            time.sleep(2)
            
        except Exception as e:
            print(f"URL 처리 중 오류 ({url}): {e}")
            continue
    
    print(f"\n총 {len(pokemon_data)}개 포켓몬 데이터를 추출했습니다!")
    return pokemon_data

def save_pokemon_data(pokemon_data):
    """포켓몬 데이터를 Python 파일로 저장합니다."""
    
    # 번호순으로 정렬
    sorted_data = dict(sorted(pokemon_data.items()))
    
    with open('pokemon_data_new.py', 'w', encoding='utf-8') as f:
        f.write("# 포켓몬 스칼렛/바이올렛 위치 정보 데이터베이스\n")
        f.write("# 블로그: https://mlove1039.tistory.com/60, 66, 67\n")
        f.write("# 자동 스크래핑으로 생성됨\n\n")
        
        f.write("pokemon_maps = {\n")
        
        for number, data in sorted_data.items():
            f.write(f"    {number}: {{\n")
            f.write(f"        'number': {number},\n")
            f.write(f"        'name': '{data['name']}',\n")
            f.write(f"        'map_image': '{data['map_image']}',\n")
            f.write(f"        'evolution': '{data['evolution']}',\n")
            f.write(f"        'basic_location': '{data['basic_location']}'\n")
            f.write("    },\n")
        
        f.write("}\n\n")
        
        # 헬퍼 함수들 추가
        f.write("def get_pokemon_by_number(number):\n")
        f.write("    return pokemon_maps.get(number)\n\n")
        
        f.write("def get_pokemon_by_name(name):\n")
        f.write("    for pokemon in pokemon_maps.values():\n")
        f.write("        if pokemon['name'] == name:\n")
        f.write("            return pokemon\n")
        f.write("    return None\n")
    
    print(f"총 {len(sorted_data)}개 포켓몬 데이터가 pokemon_data_new.py에 저장되었습니다!")

def main():
    print("포켓몬 스칼렛/바이올렛 위치 정보 스크래핑을 시작합니다...")
    
    pokemon_data = scrape_pokemon_data()
    
    if pokemon_data:
        save_pokemon_data(pokemon_data)
        print("\n스크래핑 완료!")
    else:
        print("스크래핑된 데이터가 없습니다.")

if __name__ == "__main__":
    main() 