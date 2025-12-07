import streamlit as st
import requests
from notion_client import Client
from datetime import datetime
import re
import json
import base64
import os
from pathlib import Path

# ============================================================================
# Streamlit 페이지 설정
# ============================================================================

st.set_page_config(
    page_title="도서 정보 자동 입력",
    page_icon="📚",
    layout="centered",
    initial_sidebar_state="expanded"
)

# ============================================================================
# 로컬 파일 저장/불러오기 유틸리티
# ============================================================================

CONFIG_FILE = Path(__file__).parent / "api_config.json"

def load_api_config():
    """로컬 파일에서 API 설정을 불러옵니다."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                return {
                    'aladin_api_key': config.get('aladin_api_key', ''),
                    'notion_api_key': config.get('notion_api_key', ''),
                    'notion_db_id': config.get('notion_db_id', '')
                }
        except Exception as e:
            st.warning(f"설정 파일을 읽는 중 오류가 발생했습니다: {str(e)}")
            return None
    return None

def save_api_config(aladin_key: str, notion_key: str, notion_db_id: str):
    """API 설정을 로컬 파일에 저장합니다."""
    try:
        # Base64 인코딩으로 간단한 보호 (완전한 암호화는 아니지만 기본적인 보호)
        config = {
            'aladin_api_key': base64.b64encode(aladin_key.encode()).decode(),
            'notion_api_key': base64.b64encode(notion_key.encode()).decode(),
            'notion_db_id': base64.b64encode(notion_db_id.encode()).decode()
        }
        
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        # 파일 권한 설정 (Windows에서는 제한적이지만 시도)
        try:
            os.chmod(CONFIG_FILE, 0o600)  # 소유자만 읽기/쓰기
        except:
            pass  # Windows에서는 무시
        
        return True
    except Exception as e:
        st.error(f"설정 파일을 저장하는 중 오류가 발생했습니다: {str(e)}")
        return False

def decode_config_value(encoded_value: str) -> str:
    """Base64로 인코딩된 값을 디코딩합니다."""
    try:
        return base64.b64decode(encoded_value.encode()).decode()
    except:
        return encoded_value  # 디코딩 실패 시 원본 반환

# ============================================================================
# 세션 상태 초기화 및 자동 로드
# ============================================================================

# 세션 상태 초기화
if 'api_configured' not in st.session_state:
    st.session_state.api_configured = False
if 'aladin_api_key' not in st.session_state:
    st.session_state.aladin_api_key = ""
if 'notion_api_key' not in st.session_state:
    st.session_state.notion_api_key = ""
if 'notion_db_id' not in st.session_state:
    st.session_state.notion_db_id = ""

# 앱 시작 시 자동으로 설정 불러오기
# 우선순위: Streamlit Secrets > 로컬 파일 > 수동 입력
if not st.session_state.api_configured:
    # 1. Streamlit Secrets에서 먼저 시도 (배포 환경용)
    try:
        if hasattr(st, 'secrets') and st.secrets:
            if 'ALADIN_API_KEY' in st.secrets and 'NOTION_API_KEY' in st.secrets and 'NOTION_DB_ID' in st.secrets:
                st.session_state.aladin_api_key = st.secrets['ALADIN_API_KEY']
                st.session_state.notion_api_key = st.secrets['NOTION_API_KEY']
                st.session_state.notion_db_id = st.secrets['NOTION_DB_ID']
                st.session_state.api_configured = True
    except:
        pass  # Secrets가 없으면 무시
    
    # 2. Secrets가 없으면 로컬 파일에서 불러오기 (로컬 개발용)
    if not st.session_state.api_configured:
        config = load_api_config()
        if config:
            st.session_state.aladin_api_key = decode_config_value(config['aladin_api_key'])
            st.session_state.notion_api_key = decode_config_value(config['notion_api_key'])
            st.session_state.notion_db_id = decode_config_value(config['notion_db_id'])
            
            # 모든 키가 있으면 설정 완료로 표시
            if st.session_state.aladin_api_key and st.session_state.notion_api_key and st.session_state.notion_db_id:
                st.session_state.api_configured = True

# ============================================================================
# API 설정 페이지
# ============================================================================

def show_api_config():
    st.title("⚙️ API 설정")
    st.markdown("---")
    
    st.markdown("""
    이 앱을 사용하려면 다음이 필요합니다:
    """)
    
    with st.expander("📋 시작하기 전 준비사항", expanded=True):
        st.markdown("""
        ### 1. Notion 데이터베이스 만들기
        
        **각 사용자는 자신의 Notion 데이터베이스를 만들어야 합니다.**
        
        #### 필수 속성(컬럼) 설정
        다음 속성들을 **정확한 이름**으로 만들어야 합니다:
        
        | 속성 이름 | 속성 타입 | 설명 |
        |---------|---------|------|
        | **제목** | Title | 책 제목 (기본 제공됨) |
        | **저자** | Text | 저자명 |
        | **출판사** | Text | 출판사명 |
        | **출판일** | Date | 출판일 |
        | **ISBN** | Text | ISBN 번호 |
        | **표지** | Files & media | 책 표지 이미지 |
        
        ⚠️ **중요**: 속성 이름이 정확히 일치해야 합니다 (대소문자 구분, 띄어쓰기 포함)
        
        #### 데이터베이스 ID 확인 방법
        1. Notion 데이터베이스 페이지에서 "Share" → "Copy link"
        2. 링크에서 32자리 ID 추출:
           ```
           https://notion.site/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
                                      ↑ 이 부분이 ID (예시)
           ```
           또는 전체 URL을 입력해도 자동으로 추출됩니다.
        
        ### 2. Notion Integration 만들기
        1. https://www.notion.so/my-integrations 접속
        2. "+ New integration" 클릭
        3. 이름 입력 후 "Submit"
        4. **"Internal Integration Token"** 복사
        5. 데이터베이스에 Integration 연결 (데이터베이스 → "···" → "Connections")
        
        ### 3. 알라n Open API 키 발급
        1. https://www.aladin.co.kr/ttb/api/api_list.aspx 접속
        2. "알라딘 Open API 신청" 클릭
        3. 회원가입/로그인 후 **TTBKey** 발급받기
        """)
    
    st.markdown("---")
    st.markdown("""
    ### 필요한 정보 입력:
    """)
    
    with st.form("api_config_form"):
        st.subheader("🔑 API 키 입력")
        
        aladin_key = st.text_input(
            "알라딘 Open API 키",
            value=st.session_state.aladin_api_key,
            type="password",
            help="알라딘 Open API에서 발급받은 키를 입력하세요"
        )
        
        notion_key = st.text_input(
            "Notion API 키 (Integration Token)",
            value=st.session_state.notion_api_key,
            type="password",
            help="Notion Integration에서 발급받은 토큰을 입력하세요"
        )
        
        notion_db_id = st.text_input(
            "Notion 데이터베이스 ID",
            value=st.session_state.notion_db_id,
            help="Notion 데이터베이스의 32자리 ID를 입력하세요 (URL에서 추출 가능)"
        )
        
        st.info("💡 **Notion 데이터베이스 ID 찾기:**\n- Notion 데이터베이스 URL: `https://notion.site/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`\n- 여기서 `xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` 부분이 32자리 ID입니다")
        
        submitted = st.form_submit_button("✅ 설정 저장", type="primary", use_container_width=True)
        
        if submitted:
            if aladin_key and notion_key and notion_db_id:
                cleaned_db_id = extract_notion_database_id(notion_db_id)
                
                # 세션 상태에 저장
                st.session_state.aladin_api_key = aladin_key
                st.session_state.notion_api_key = notion_key
                st.session_state.notion_db_id = cleaned_db_id
                st.session_state.api_configured = True
                
                # 로컬 파일에 저장 (한 번 설정하면 계속 사용 가능)
                if save_api_config(aladin_key, notion_key, cleaned_db_id):
                    st.success("✅ API 설정이 저장되었습니다! 이제 앱을 다시 시작해도 설정이 유지됩니다.")
                    st.info(f"💾 설정 파일 위치: `{CONFIG_FILE}`")
                    st.rerun()
                else:
                    st.warning("⚠️ 세션에는 저장되었지만 파일 저장에 실패했습니다. 앱을 다시 시작하면 설정을 다시 입력해야 할 수 있습니다.")
                    st.rerun()
            else:
                st.error("⚠️ 모든 필드를 입력해주세요.")

# ============================================================================
# 유틸리티 함수
# ============================================================================

def extract_notion_database_id(db_id_or_url: str) -> str:
    """Notion 데이터베이스 ID를 URL에서 추출하거나 그대로 반환합니다."""
    if not db_id_or_url:
        return ""
    
    db_id = db_id_or_url.strip()
    
    # URL 형식인 경우 ID 추출
    if "notion.site" in db_id or "notion.so" in db_id:
        match = re.search(r'([a-f0-9]{32}|[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})', db_id)
        if match:
            db_id = match.group(1)
    
    # 하이픈 제거
    db_id = re.sub(r'-', '', db_id)
    
    return db_id

def clean_isbn(isbn: str) -> str:
    """ISBN 문자열에서 하이픈과 공백을 제거합니다."""
    if not isbn:
        return ""
    return re.sub(r'[-\s]', '', isbn.strip())

# ============================================================================
# 알라딘 API 함수
# ============================================================================

def search_books(keyword: str, api_key: str, max_results: int = 10) -> list:
    """알라딘 Open API를 사용하여 키워드로 도서를 검색합니다."""
    if not api_key:
        st.error("알라딘 API 키가 설정되지 않았습니다.")
        return []
    
    ALADIN_SEARCH_URL = "https://www.aladin.co.kr/ttb/api/ItemSearch.aspx"
    
    params = {
        "ttbkey": api_key,
        "Query": keyword,
        "QueryType": "Keyword",
        "MaxResults": max_results,
        "start": 1,
        "SearchTarget": "Book",
        "output": "js",
        "Version": "20131101",
        "Cover": "Big"
    }
    
    try:
        response = requests.get(ALADIN_SEARCH_URL, params=params, timeout=10)
        response.raise_for_status()
        
        response_text = response.text.strip()
        
        # JSONP 형식 처리
        json_text = response_text
        if json_text.startswith('callback('):
            json_text = json_text[9:]
            if json_text.endswith(');'):
                json_text = json_text[:-2]
            elif json_text.endswith(')'):
                json_text = json_text[:-1]
        
        try:
            data = json.loads(json_text)
            
            # 에러 응답 확인
            if 'errorCode' in data or 'errorMessage' in data:
                error_msg = data.get('errorMessage', '알 수 없는 오류')
                if '금지' in error_msg or '금지된' in error_msg:
                    # XML 형식으로 재시도
                    st.info("JSON 형식이 허용되지 않아 XML 형식으로 재시도합니다...")
                    params["output"] = "xml"
                    response = requests.get(ALADIN_SEARCH_URL, params=params, timeout=10)
                    response.raise_for_status()
                    
                    # XML 파싱
                    import xml.etree.ElementTree as ET
                    try:
                        root = ET.fromstring(response.text)
                        items = []
                        for item in root.findall('.//item'):
                            item_dict = {}
                            for child in item:
                                tag = child.tag
                                if '}' in tag:
                                    tag = tag.split('}')[1]
                                item_dict[tag] = child.text if child.text else ""
                            if item_dict:
                                items.append(item_dict)
                        
                        book_list = []
                        for item in items:
                            book_list.append({
                                "title": item.get("title", ""),
                                "author": item.get("author", ""),
                                "publisher": item.get("publisher", ""),
                                "pub_date": item.get("pubDate", ""),
                                "cover_image": item.get("cover", ""),
                                "isbn": item.get("isbn", ""),
                                "isbn13": item.get("isbn13", ""),
                                "link": item.get("link", ""),
                                "description": item.get("description", "")
                            })
                        return book_list
                    except ET.ParseError as e:
                        st.error(f"XML 파싱 오류: {str(e)}")
                        return []
                else:
                    st.error(f"알라딘 API 오류: {error_msg}")
                    return []
            
            if 'item' not in data:
                st.warning("검색 결과가 없습니다.")
                return []
            
            items = data.get('item', [])
            book_list = []
            
            for item in items:
                book_list.append({
                    "title": item.get("title", ""),
                    "author": item.get("author", ""),
                    "publisher": item.get("publisher", ""),
                    "pub_date": item.get("pubDate", ""),
                    "cover_image": item.get("cover", ""),
                    "isbn": item.get("isbn", ""),
                    "isbn13": item.get("isbn13", ""),
                    "link": item.get("link", ""),
                    "description": item.get("description", "")
                })
            
            return book_list
            
        except (ValueError, json.JSONDecodeError) as e:
            # JSON 파싱 실패 시 XML 형식으로 재시도
            st.info("JSON 파싱 실패, XML 형식으로 재시도합니다...")
            params["output"] = "xml"
            response = requests.get(ALADIN_SEARCH_URL, params=params, timeout=10)
            response.raise_for_status()
            
            import xml.etree.ElementTree as ET
            try:
                root = ET.fromstring(response.text)
                items = []
                for item in root.findall('.//item'):
                    item_dict = {}
                    for child in item:
                        tag = child.tag
                        if '}' in tag:
                            tag = tag.split('}')[1]
                        item_dict[tag] = child.text if child.text else ""
                    if item_dict:
                        items.append(item_dict)
                
                book_list = []
                for item in items:
                    book_list.append({
                        "title": item.get("title", ""),
                        "author": item.get("author", ""),
                        "publisher": item.get("publisher", ""),
                        "pub_date": item.get("pubDate", ""),
                        "cover_image": item.get("cover", ""),
                        "isbn": item.get("isbn", ""),
                        "isbn13": item.get("isbn13", ""),
                        "link": item.get("link", ""),
                        "description": item.get("description", "")
                    })
                return book_list
            except ET.ParseError as parse_error:
                st.error(f"XML 파싱 오류: {str(parse_error)}")
                st.error(f"응답 내용: {response.text[:500]}")
                return []
            except Exception as parse_error:
                st.error(f"검색 결과를 파싱하는 중 오류가 발생했습니다: {str(parse_error)}")
                return []
        
    except requests.exceptions.RequestException as e:
        st.error(f"알라딘 API 요청 중 오류가 발생했습니다: {str(e)}")
        return []
    except Exception as e:
        st.error(f"도서 검색 중 오류가 발생했습니다: {str(e)}")
        return []

def get_book_info(isbn: str, api_key: str) -> dict:
    """알라딘 Open API를 사용하여 ISBN으로 도서 정보를 가져옵니다."""
    if not api_key:
        st.error("알라딘 API 키가 설정되지 않았습니다.")
        return None
    
    ALADIN_API_URL = "https://www.aladin.co.kr/ttb/api/ItemLookUp.aspx"
    
    params = {
        "ttbkey": api_key,
        "itemIdType": "ISBN",
        "ItemId": isbn,
        "output": "js",
        "Version": "20131101",
        "Cover": "Big"
    }
    
    try:
        response = requests.get(ALADIN_API_URL, params=params, timeout=10)
        response.raise_for_status()
        
        response_text = response.text.strip()
        
        # JSONP 형식 처리
        json_text = response_text
        if json_text.startswith('callback('):
            json_text = json_text[9:]
            if json_text.endswith(');'):
                json_text = json_text[:-2]
            elif json_text.endswith(')'):
                json_text = json_text[:-1]
        
        # JSON 응답 처리
        try:
            data = json.loads(json_text)
            
            # 에러 응답 확인
            if 'errorCode' in data or 'errorMessage' in data:
                error_msg = data.get('errorMessage', '알 수 없는 오류')
                if '금지' in error_msg or '금지된' in error_msg:
                    # XML 형식으로 재시도
                    st.info("JSON 형식이 허용되지 않아 XML 형식으로 재시도합니다...")
                    params["output"] = "xml"
                    response = requests.get(ALADIN_API_URL, params=params, timeout=10)
                    response.raise_for_status()
                    
                    # XML 파싱
                    import xml.etree.ElementTree as ET
                    try:
                        root = ET.fromstring(response.text)
                        data = {}
                        items = []
                        for item in root.findall('.//item'):
                            item_dict = {}
                            for child in item:
                                tag = child.tag
                                if '}' in tag:
                                    tag = tag.split('}')[1]
                                item_dict[tag] = child.text if child.text else ""
                            if item_dict:
                                items.append(item_dict)
                        data['item'] = items
                    except ET.ParseError as e:
                        st.error(f"XML 파싱 오류: {str(e)}")
                        return None
                else:
                    st.error(f"알라딘 API 오류: {error_msg}")
                    return None
        except (ValueError, json.JSONDecodeError):
            # JSON 파싱 실패 시 XML 형식으로 재시도
            st.info("JSON 파싱 실패, XML 형식으로 재시도합니다...")
            params["output"] = "xml"
            response = requests.get(ALADIN_API_URL, params=params, timeout=10)
            response.raise_for_status()
            
            import xml.etree.ElementTree as ET
            try:
                root = ET.fromstring(response.text)
                data = {}
                items = []
                for item in root.findall('.//item'):
                    item_dict = {}
                    for child in item:
                        tag = child.tag
                        if '}' in tag:
                            tag = tag.split('}')[1]
                        item_dict[tag] = child.text if child.text else ""
                    if item_dict:
                        items.append(item_dict)
                data['item'] = items
            except ET.ParseError as e:
                st.error(f"XML 파싱 오류: {str(e)}")
                return None
        
        # 응답 구조 확인
        if not data:
            st.error("알라딘 API에서 빈 응답을 받았습니다.")
            return None
        
        if 'errorCode' in data or 'errorMessage' in data:
            error_msg = data.get('errorMessage', '알 수 없는 오류')
            st.error(f"알라딘 API 오류: {error_msg}")
            return None
        
        if 'item' not in data:
            st.error("알라딘 API 응답에 'item' 필드가 없습니다.")
            return None
        
        items = data.get('item', [])
        if not items or len(items) == 0:
            st.error("도서 정보를 찾을 수 없습니다. ISBN을 확인해주세요.")
            return None
        
        item = items[0]
        
        book_info = {
            "title": item.get("title", ""),
            "author": item.get("author", ""),
            "publisher": item.get("publisher", ""),
            "pub_date": item.get("pubDate", ""),
            "cover_image": item.get("cover", ""),
            "isbn": item.get("isbn", ""),
            "isbn13": item.get("isbn13", ""),
            "link": item.get("link", ""),
            "description": item.get("description", "")
        }
        
        return book_info
        
    except requests.exceptions.RequestException as e:
        st.error(f"알라딘 API 요청 중 오류가 발생했습니다: {str(e)}")
        return None
    except Exception as e:
        st.error(f"도서 정보를 가져오는 중 오류가 발생했습니다: {str(e)}")
        return None

# ============================================================================
# Notion API 함수
# ============================================================================

def format_pub_date(date_str: str) -> dict:
    """출판일 문자열을 Notion Date 형식으로 변환합니다."""
    if not date_str:
        return None
    
    date_str = date_str.strip()
    
    try:
        if "-" in date_str:
            date_obj = datetime.strptime(date_str.split()[0], "%Y-%m-%d")
        elif len(date_str) == 8 and date_str.isdigit():
            date_obj = datetime.strptime(date_str, "%Y%m%d")
        else:
            date_obj = datetime.strptime(date_str.split()[0], "%Y-%m-%d")
        
        return {
            "start": date_obj.strftime("%Y-%m-%d")
        }
    except:
        return None

def save_to_notion(book_info: dict, notion_api_key: str, notion_db_id: str) -> bool:
    """도서 정보를 Notion 데이터베이스에 새 페이지로 생성합니다."""
    if not notion_api_key or not notion_db_id:
        st.error("Notion API 키 또는 데이터베이스 ID가 설정되지 않았습니다.")
        return False
    
    try:
        notion = Client(auth=notion_api_key)
        
        clean_db_id = extract_notion_database_id(notion_db_id)
        
        properties = {
            "제목": {
                "title": [
                    {
                        "text": {
                            "content": book_info.get("title", "제목 없음")
                        }
                    }
                ]
            }
        }
        
        if book_info.get("author"):
            properties["저자"] = {
                "rich_text": [
                    {
                        "text": {
                            "content": book_info.get("author", "")
                        }
                    }
                ]
            }
        
        if book_info.get("publisher"):
            properties["출판사"] = {
                "rich_text": [
                    {
                        "text": {
                            "content": book_info.get("publisher", "")
                        }
                    }
                ]
            }
        
        pub_date = format_pub_date(book_info.get("pub_date", ""))
        if pub_date:
            properties["출판일"] = {
                "date": pub_date
            }
        
        isbn_value = book_info.get("isbn13") or book_info.get("isbn", "")
        if isbn_value:
            properties["ISBN"] = {
                "rich_text": [
                    {
                        "text": {
                            "content": isbn_value
                        }
                    }
                ]
            }
        
        cover_image = book_info.get("cover_image", "")
        if cover_image:
            properties["표지"] = {
                "files": [
                    {
                        "type": "external",
                        "name": "표지 이미지",
                        "external": {
                            "url": cover_image
                        }
                    }
                ]
            }
        
        new_page = notion.pages.create(
            parent={"database_id": clean_db_id},
            properties=properties
        )
        
        if book_info.get("description"):
            notion.blocks.children.append(
                block_id=new_page["id"],
                children=[
                    {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [
                                {
                                    "type": "text",
                                    "text": {
                                        "content": book_info.get("description", "")
                                    }
                                }
                            ]
                        }
                    }
                ]
            )
        
        return True
        
    except Exception as e:
        error_msg = str(e)
        st.error(f"Notion에 저장하는 중 오류가 발생했습니다: {error_msg}")
        
        if "object_not_found" in error_msg.lower() or "database" in error_msg.lower():
            st.info("💡 **해결 방법:** Notion 데이터베이스 ID가 올바른지 확인하고, Integration이 데이터베이스에 연결되어 있는지 확인하세요.")
        elif "property" in error_msg.lower() or "schema" in error_msg.lower():
            st.info("💡 **해결 방법:** Notion 데이터베이스에 다음 속성들이 정확한 이름으로 존재하는지 확인하세요: 제목, 저자, 출판사, 출판일, ISBN, 표지")
        elif "unauthorized" in error_msg.lower() or "invalid" in error_msg.lower():
            st.info("💡 **해결 방법:** Notion API 키가 올바른지 확인하세요.")
        
        return False

# ============================================================================
# 메인 앱
# ============================================================================

def main():
    # 사이드바
    with st.sidebar:
        st.title("📚 도서 정보 자동 입력")
        st.markdown("---")
        
        if st.session_state.api_configured:
            st.success("✅ API 설정 완료")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("⚙️ 설정 변경", use_container_width=True):
                    st.session_state.api_configured = False
                    st.rerun()
            with col2:
                if st.button("🗑️ 설정 삭제", use_container_width=True):
                    # 설정 파일 삭제
                    if CONFIG_FILE.exists():
                        try:
                            CONFIG_FILE.unlink()
                            st.success("✅ 설정 파일이 삭제되었습니다.")
                        except:
                            st.error("⚠️ 설정 파일 삭제에 실패했습니다.")
                    # 세션 상태 초기화
                    st.session_state.api_configured = False
                    st.session_state.aladin_api_key = ""
                    st.session_state.notion_api_key = ""
                    st.session_state.notion_db_id = ""
                    st.rerun()
        else:
            st.warning("⚠️ API 설정 필요")
            if st.button("⚙️ API 설정", use_container_width=True):
                st.rerun()
        
        st.markdown("---")
        st.markdown("### 사용 방법")
        st.markdown("""
        1. API 키 설정
        2. 검색 방식 선택:
           - 키워드 검색: 제목/저자로 검색
           - ISBN 검색: ISBN 번호 입력
        3. 도서 선택/확인
        4. Notion에 저장
        """)
    
    # API 설정이 안 되어 있으면 설정 페이지 표시
    if not st.session_state.api_configured:
        show_api_config()
        return
    
    # 메인 페이지
    st.title("📚 도서 정보 자동 입력 웹 앱")
    st.markdown("---")
    
    st.markdown("""
    이 앱은 ISBN 번호 또는 책 제목/저자로 검색하여 알라딘 Open API에서 도서 정보를 가져와 
    Notion 데이터베이스에 자동으로 등록해줍니다.
    """)
    
    # 검색 방식 선택
    search_mode = st.radio(
        "검색 방식 선택",
        ["🔍 키워드 검색 (제목/저자)", "📖 ISBN 검색"],
        horizontal=True
    )
    
    st.markdown("---")
    
    # 선택한 책 정보 및 검색 결과 (세션 상태)
    if 'selected_book' not in st.session_state:
        st.session_state.selected_book = None
    if 'search_results' not in st.session_state:
        st.session_state.search_results = []
    
    # 키워드 검색 모드
    if search_mode == "🔍 키워드 검색 (제목/저자)":
        keyword_input = st.text_input(
            "책 제목 또는 저자명을 입력하세요",
            placeholder="예: 해리포터 또는 조앤 롤링",
            help="책 제목, 저자명, 또는 키워드로 검색할 수 있습니다."
        )
        
        col1, col2 = st.columns([1, 4])
        with col1:
            search_button = st.button("🔍 검색", type="primary", use_container_width=True)
        
        if search_button:
            if not keyword_input:
                st.warning("검색어를 입력해주세요.")
            else:
                # 새로 검색할 때는 이전 선택 초기화
                st.session_state.selected_book = None
                with st.spinner("도서를 검색하는 중..."):
                    search_results = search_books(keyword_input, st.session_state.aladin_api_key, max_results=10)
                    st.session_state.search_results = search_results if search_results else []
                    st.rerun()
        
        # 선택한 책이 없을 때만 검색 결과 표시
        if not st.session_state.selected_book and st.session_state.search_results:
            st.markdown(f"### 검색 결과 ({len(st.session_state.search_results)}건)")
            st.markdown("---")
            
            # 검색 결과 표시
            for idx, book in enumerate(st.session_state.search_results):
                with st.container():
                    col_img, col_info, col_btn = st.columns([1, 3, 1])
                    
                    with col_img:
                        if book.get("cover_image"):
                            st.image(book["cover_image"], use_container_width=True)
                        else:
                            st.write("표지 없음")
                    
                    with col_info:
                        st.markdown(f"**{book.get('title', '제목 없음')}**")
                        if book.get("author"):
                            st.markdown(f"저자: {book.get('author')}")
                        if book.get("publisher"):
                            st.markdown(f"출판사: {book.get('publisher')}")
                        if book.get("pub_date"):
                            st.markdown(f"출판일: {book.get('pub_date')}")
                        if book.get("isbn13") or book.get("isbn"):
                            isbn_display = book.get("isbn13") or book.get("isbn")
                            st.markdown(f"ISBN: `{isbn_display}`")
                    
                    with col_btn:
                        if st.button("✅ 선택", key=f"select_{idx}", use_container_width=True):
                            st.session_state.selected_book = book
                            st.rerun()
                    
                    st.markdown("---")
        elif not st.session_state.selected_book and not st.session_state.search_results:
            # 검색 결과가 없을 때 (검색 버튼을 눌렀지만 결과가 없는 경우는 이미 위에서 처리됨)
            pass
        
        # 선택한 책이 있으면 등록 처리
        if st.session_state.selected_book:
            st.markdown("---")
            st.success("✅ 책이 선택되었습니다!")
            
            book_info = st.session_state.selected_book
            
            col_img, col_info = st.columns([1, 2])
            
            with col_img:
                if book_info.get("cover_image"):
                    st.image(book_info["cover_image"], use_container_width=True)
            
            with col_info:
                st.markdown(f"### {book_info.get('title', '제목 없음')}")
                if book_info.get("author"):
                    st.markdown(f"**저자:** {book_info.get('author')}")
                if book_info.get("publisher"):
                    st.markdown(f"**출판사:** {book_info.get('publisher')}")
                if book_info.get("pub_date"):
                    st.markdown(f"**출판일:** {book_info.get('pub_date')}")
                if book_info.get("isbn13") or book_info.get("isbn"):
                    isbn_display = book_info.get("isbn13") or book_info.get("isbn")
                    st.markdown(f"**ISBN:** {isbn_display}")
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("📝 Notion에 등록", type="primary", use_container_width=True):
                    # 키워드 검색 결과는 일부 필드가 누락될 수 있으므로,
                    # ISBN으로 다시 한 번 상세 정보를 가져와서 저장
                    isbn_for_lookup = book_info.get("isbn13") or book_info.get("isbn", "")
                    detailed_book_info = None
                    success = False
                    
                    if isbn_for_lookup:
                        # ISBN으로 상세 정보 다시 가져오기
                        with st.spinner("도서 정보를 확인하는 중..."):
                            detailed_book_info = get_book_info(
                                clean_isbn(isbn_for_lookup),
                                st.session_state.aladin_api_key
                            )
                        
                        if detailed_book_info:
                            # 상세 정보로 저장
                            with st.spinner("Notion에 저장하는 중..."):
                                success = save_to_notion(
                                    detailed_book_info,
                                    st.session_state.notion_api_key,
                                    st.session_state.notion_db_id
                                )
                        else:
                            # 상세 정보를 가져오지 못한 경우, 검색 결과로 저장 시도
                            st.warning("상세 정보를 가져오지 못했습니다. 검색 결과로 저장을 시도합니다...")
                            with st.spinner("Notion에 저장하는 중..."):
                                success = save_to_notion(
                                    book_info,
                                    st.session_state.notion_api_key,
                                    st.session_state.notion_db_id
                                )
                    else:
                        # ISBN이 없는 경우, 검색 결과로 저장 시도
                        st.warning("ISBN 정보가 없습니다. 검색 결과로 저장을 시도합니다...")
                        with st.spinner("Notion에 저장하는 중..."):
                            success = save_to_notion(
                                book_info,
                                st.session_state.notion_api_key,
                                st.session_state.notion_db_id
                            )
                    
                    if success:
                        st.success("✅ 도서 정보가 성공적으로 Notion에 등록되었습니다!")
                        # 링크는 상세 정보가 있으면 상세 정보에서, 없으면 검색 결과에서 가져오기
                        final_link = None
                        if detailed_book_info:
                            final_link = detailed_book_info.get("link")
                        if not final_link:
                            final_link = book_info.get("link")
                        if final_link:
                            st.markdown(f"[알라딘에서 확인하기]({final_link})")
                        st.session_state.selected_book = None
                        st.rerun()
                    else:
                        st.error("Notion에 저장하는 중 오류가 발생했습니다.")
            
            with col2:
                if st.button("❌ 선택 취소", use_container_width=True):
                    st.session_state.selected_book = None
                    st.session_state.search_results = []  # 검색 결과도 초기화
                    st.rerun()
    
    # ISBN 검색 모드
    else:
        isbn_input = st.text_input(
            "ISBN 번호를 입력하세요",
            placeholder="예: 9788959897179 또는 978-89-5989-717-9",
            help="ISBN-10 또는 ISBN-13 형식으로 입력할 수 있습니다."
        )
        
        col1, col2 = st.columns([1, 4])
        
        with col1:
            submit_button = st.button("등록하기", type="primary", use_container_width=True)
        
        # 등록 버튼 클릭 시 처리
        if submit_button:
            if not isbn_input:
                st.warning("ISBN 번호를 입력해주세요.")
            else:
                cleaned_isbn = clean_isbn(isbn_input)
                
                if not cleaned_isbn:
                    st.warning("올바른 ISBN 번호를 입력해주세요.")
                else:
                    # 로딩 표시
                    with st.spinner("도서 정보를 가져오는 중..."):
                        book_info = get_book_info(cleaned_isbn, st.session_state.aladin_api_key)
                    
                    if book_info:
                        # 도서 정보 확인 화면
                        st.markdown("---")
                        st.subheader("📖 도서 정보")
                        
                        col_img, col_info = st.columns([1, 2])
                        
                        with col_img:
                            if book_info.get("cover_image"):
                                st.image(book_info["cover_image"], use_container_width=True)
                        
                        with col_info:
                            st.markdown(f"### {book_info.get('title', '제목 없음')}")
                            if book_info.get("author"):
                                st.markdown(f"**저자:** {book_info.get('author')}")
                            if book_info.get("publisher"):
                                st.markdown(f"**출판사:** {book_info.get('publisher')}")
                            if book_info.get("pub_date"):
                                st.markdown(f"**출판일:** {book_info.get('pub_date')}")
                            if book_info.get("isbn13") or book_info.get("isbn"):
                                isbn_display = book_info.get("isbn13") or book_info.get("isbn")
                                st.markdown(f"**ISBN:** {isbn_display}")
                        
                        # Notion에 저장
                        st.markdown("---")
                        with st.spinner("Notion에 저장하는 중..."):
                            success = save_to_notion(
                                book_info,
                                st.session_state.notion_api_key,
                                st.session_state.notion_db_id
                            )
                        
                        if success:
                            st.success("✅ 도서 정보가 성공적으로 Notion에 등록되었습니다!")
                            if book_info.get("link"):
                                st.markdown(f"[알라딘에서 확인하기]({book_info.get('link')})")
                        else:
                            st.error("Notion에 저장하는 중 오류가 발생했습니다.")

if __name__ == "__main__":
    main()

