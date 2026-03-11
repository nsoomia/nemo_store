import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
import os
import json
import ast

# 페이지 설정
st.set_page_config(
    page_title="Nemostore 프리미엄 상가 분석 대시보드",
    page_icon="🏪",
    layout="wide"
)

# 컬럼명 한글 매핑 딕셔너리
COLUMN_MAPPING = {
    'title': '매물명',
    'businessLargeCodeName': '업종(대)',
    'businessMiddleCodeName': '업종(중)',
    'deposit': '보증금(만원)',
    'monthlyRent': '월세(만원)',
    'premium': '권리금(만원)',
    'sale': '매매가(만원)',
    'maintenanceFee': '관리비(만원)',
    'floor': '층수',
    'size': '전용면적(㎡)',
    'nearSubwayStation': '인근 지하철역',
    'viewCount': '조회수',
    'favoriteCount': '찜수',
    'confirmedDateUtc': '확인일자',
    'id': 'ID'
}

# 주요 지하철역 좌표 데이터 (샘플)
SUBWAY_COORDS = {
    '을지로입구역': [37.5660, 126.9822],
    '종각역': [37.5702, 126.9831],
    '광화문역': [37.5716, 126.9765],
    '을지로3가역': [37.5663, 126.9910],
    '명동역': [37.5609, 126.9863],
    '종로3가역': [37.5704, 126.9921],
    '안국역': [37.5765, 126.9854],
    '시청역': [37.5657, 126.9769],
    '충정로역': [37.5597, 126.9631],
    '서대문역': [37.5658, 126.9667]
}

# 데이터 로드 및 전처리
@st.cache_data
def load_and_preprocess():
    # 현재 파일(dashboard.py) 위치를 기준으로 DB 경로 설정
    curr_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(curr_dir)
    db_path = os.path.join(project_root, "data", "nemostore.db")
    
    if not os.path.exists(db_path):
        # 대안으로 현재 작업 디렉토리 기준 탐색
        db_path = os.path.join("nemostore", "data", "nemostore.db")
        if not os.path.exists(db_path):
            return pd.DataFrame()
    
    conn = sqlite3.connect(db_path)
    try:
        # 테이블 존재 여부 확인 후 로드
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        
        if 'items' in tables:
            df = pd.read_sql_query("SELECT * FROM items", conn)
        elif 'articles' in tables:
            df = pd.read_sql_query("SELECT * FROM articles", conn)
        elif tables:
            df = pd.read_sql_query(f"SELECT * FROM {tables[0]}", conn)
        else:
            df = pd.DataFrame()
    except Exception as e:
        st.error(f"DB 로드 중 오류 발생: {e}")
        df = pd.DataFrame()
    finally:
        conn.close()
    
    if df.empty: return df

    # 수치형 변환
    numeric_cols = ['deposit', 'monthlyRent', 'premium', 'sale', 'maintenanceFee', 'size']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    # 이미지 URL 파싱 (문자열 형태의 리스트 처리)
    def parse_images(x):
        try:
            if isinstance(x, str) and x.startswith('['):
                return ast.literal_eval(x)
            return [x] if x else []
        except:
            return []
            
    if 'smallPhotoUrls' in df.columns:
        df['images'] = df['smallPhotoUrls'].apply(parse_images)
        df['thumbnail'] = df['images'].apply(lambda x: x[0] if x else None)
    
    # 지하철역 이름 정제 (예: "을지로입구역, 도보 7분" -> "을지로입구역")
    if 'nearSubwayStation' in df.columns:
        df['station_name'] = df['nearSubwayStation'].apply(lambda x: str(x).split(',')[0].strip() if x else "정보없음")
        
    return df

df = load_and_preprocess()

# 데이터 로딩 확인
if df.empty:
    st.error("❌ 데이터를 불러올 수 없습니다. 데이터베이스 파일이 존재하고 테이블에 데이터가 있는지 확인해 주세요.")
    st.info(f"현재 탐색 경로: {os.getcwd()}")
    st.stop()
    
# 필수 컬럼 체크
required_cols = ['monthlyRent', 'deposit', 'title']
missing_cols = [col for col in required_cols if col not in df.columns]
if missing_cols:
    st.error(f"❌ 데이터베이스에 필수 컬럼이 누락되었습니다: {', '.join(missing_cols)}")
    st.write("사용 가능한 컬럼:", list(df.columns))
    st.stop()

# --- 사이드바 필터 ---
st.sidebar.title("🏪 Nemostore Filters")
search_query = st.sidebar.text_input("🔍 매물명 키워드 검색", "")

# 가격 및 면적 필터
min_rent, max_rent = int(df['monthlyRent'].min()), int(df['monthlyRent'].max())
rent_range = st.sidebar.slider("월세 (만원)", min_rent, max_rent, (min_rent, max_rent))

min_deposit, max_deposit = int(df['deposit'].min()), int(df['deposit'].max())
deposit_range = st.sidebar.slider("보증금 (만원)", min_deposit, max_deposit, (min_deposit, max_deposit))

if 'businessLargeCodeName' in df.columns:
    biz_types = ["전체"] + sorted(df['businessLargeCodeName'].unique().tolist())
    selected_biz = st.sidebar.selectbox("업종 선택", biz_types)

# 데이터 필터링 적용
filtered_df = df.copy()
if search_query:
    filtered_df = filtered_df[filtered_df['title'].str.contains(search_query, case=False, na=False)]
filtered_df = filtered_df[
    (filtered_df['monthlyRent'] >= rent_range[0]) & (filtered_df['monthlyRent'] <= rent_range[1]) &
    (filtered_df['deposit'] >= deposit_range[0]) & (filtered_df['deposit'] <= deposit_range[1])
]
if selected_biz != "전체":
    filtered_df = filtered_df[filtered_df['businessLargeCodeName'] == selected_biz]

# --- 화면 전환 관리 (session_state) ---
if 'view' not in st.session_state:
    st.session_state.view = 'main'
if 'selected_item_id' not in st.session_state:
    st.session_state.selected_item_id = None

def set_view(view, item_id=None):
    st.session_state.view = view
    st.session_state.selected_item_id = item_id

# --- 상단 내비게이션 태스크 ---
tab1, tab2, tab3, tab4 = st.tabs(["📊 통계 대시보드", "🖼️ 매물 갤러리", "🗺️ 지역별 지도", "🏢 층별 분석"])

# --- Tab 1: 통계 대시보드 ---
with tab1:
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("검색된 매물", f"{len(filtered_df)}건")
    col2.metric("평균 월세", f"{filtered_df['monthlyRent'].mean():,.0f}만원")
    col3.metric("평균 보증금", f"{filtered_df['deposit'].mean():,.0f}만원")
    col4.metric("평균 면적", f"{filtered_df['size'].mean():.1f}㎡")
    
    st.write("---")
    c1, c2 = st.columns(2)
    with c1:
        # 업종별 분포
        fig_biz = px.pie(filtered_df, names='businessLargeCodeName', title="업종별 매물 비중", hole=0.5)
        st.plotly_chart(fig_biz, use_container_width=True)
    with c2:
        # 면적 vs 월세
        fig_scatter = px.scatter(filtered_df, x='size', y='monthlyRent', color='businessLargeCodeName',
                                 hover_data=['title'], title="면적 대비 월세 상관관계")
        st.plotly_chart(fig_scatter, use_container_width=True)

# --- Tab 2: 매물 갤러리 ---
with tab2:
    st.subheader("🖼️ 매물 갤러리")
    
    # 상세 페이지 보기 모드일 때
    if st.session_state.selected_item_id:
        item = df[df['id'] == st.session_state.selected_item_id].iloc[0]
        
        if st.button("⬅️ 목록으로 돌아가기"):
            set_view('main', None)
            st.rerun()
            
        st.write(f"## {item['title']}")
        d_col1, d_col2 = st.columns([1, 1])
        
        with d_col1:
            if item['images']:
                st.image(item['images'][0], use_container_width=True)
                if len(item['images']) > 1:
                    st.write("추가 이미지")
                    cols = st.columns(4)
                    for idx, img in enumerate(item['images'][1:5]):
                        cols[idx].image(img, use_container_width=True)
            else:
                st.info("이미지가 없습니다.")
                
        with d_col2:
            st.markdown(f"### 📍 상세 정보")
            info_df = pd.DataFrame({
                "항목": [COLUMN_MAPPING.get(k, k) for k in ['businessLargeCodeName', 'deposit', 'monthlyRent', 'premium', 'floor', 'size', 'nearSubwayStation']],
                "값": [item.get(k, '-') for k in ['businessLargeCodeName', 'deposit', 'monthlyRent', 'premium', 'floor', 'size', 'nearSubwayStation']]
            })
            st.table(info_df)
            
            # --- 벤치마킹 (상대적 가치 평가) ---
            st.markdown("### ⚖️ 상대적 가치 평가")
            biz_type = item['businessLargeCodeName']
            avg_rent_biz = df[df['businessLargeCodeName'] == biz_type]['monthlyRent'].mean()
            diff_pct = ((item['monthlyRent'] - avg_rent_biz) / avg_rent_biz * 100) if avg_rent_biz > 0 else 0
            
            color = "red" if diff_pct > 0 else "blue"
            compare_text = "비쌈" if diff_pct > 0 else "저렴"
            st.markdown(f"이 매물은 **{biz_type}** 평균 월세({avg_rent_biz:,.0f}만원) 대비 <span style='color:{color}; font-size:1.2em; font-weight:bold;'>{abs(diff_pct):.1f}% {compare_text}</span> 합니다.", unsafe_allow_html=True)

    else:
        # 갤러리 그리드 표시
        cols_per_row = 4
        for i in range(0, len(filtered_df), cols_per_row):
            cols = st.columns(cols_per_row)
            for j in range(cols_per_row):
                if i + j < len(filtered_df):
                    row = filtered_df.iloc[i + j]
                    with cols[j]:
                        if row['thumbnail']:
                            st.image(row['thumbnail'], use_container_width=True)
                        else:
                            st.write("No Image")
                        st.write(f"**{row['title'][:20]}...**")
                        st.write(f"{row['monthlyRent']}만원 / {row['deposit']}만원")
                        if st.button("상세보기", key=f"btn_{row['id']}"):
                            set_view('detail', row['id'])
                            st.rerun()

# --- Tab 3: 지도 시각화 ---
with tab3:
    st.subheader("🗺️ 지역별 매물 밀집도 (Choropleth Density View)")
    st.info("💡 인근 지하철역을 중심으로 한 매물 밀집도를 히트맵(Density Map) 형태로 시각화합니다.")
    
    # 좌표 매핑
    map_data = filtered_df.copy()
    map_data['lat'] = map_data['station_name'].apply(lambda x: SUBWAY_COORDS.get(x, [None, None])[0])
    map_data['lon'] = map_data['station_name'].apply(lambda x: SUBWAY_COORDS.get(x, [None, None])[1])
    
    # 좌표가 있는 데이터만 사용
    valid_map_df = map_data.dropna(subset=['lat', 'lon'])
    
    if not valid_map_df.empty:
        # 역별 집계 (밀도 표현을 위해 매물 수를 가중치로 사용하거나 개별 포인트를 여러 번 배치)
        # Plotly density_mapbox는 포인트들의 밀집도를 자동으로 계산하거나 z값을 가중치로 사용 가능
        
        station_agg = valid_map_df.groupby(['station_name', 'lat', 'lon']).agg({
            'id': 'count',
            'monthlyRent': 'mean'
        }).reset_index()
        station_agg.columns = ['지하철역', 'lat', 'lon', '매물수', '평균월세']
        
        # Choropleth 느낌을 주는 Density Mapbox
        fig_map = px.density_mapbox(station_agg, lat="lat", lon="lon", z="매물수",
                                    radius=40, # 밀집도 표현을 위한 반경
                                    hover_name="지하철역", 
                                    center={"lat": 37.568, "lon": 126.983},
                                    zoom=12,
                                    mapbox_style="carto-positron",
                                    color_continuous_scale="Reds",
                                    title="역세권별 매물 밀집도 (Choropleth 스타일)")
        
        st.plotly_chart(fig_map, use_container_width=True)
        
        # 보조 테이블
        st.write("📍 **역별 주요 지표 요약**")
        st.dataframe(station_agg.sort_values(by='매물수', ascending=False), hide_index=True)
    else:
        st.warning("지도 표시를 위한 위치 데이터(좌표)가 부족합니다. 주요 역 인근 매물을 필터링해 보세요.")

# --- Tab 4: 층별 분석 ---
with tab4:
    st.subheader("🏢 층수별 임대료 비중 분석")
    if 'floor' in filtered_df.columns:
        # 층수 데이터 정제 (숫자만 추출 등)
        filtered_df['floor_clean'] = filtered_df['floor'].astype(str)
        fig_floor = px.box(filtered_df, x='floor_clean', y='monthlyRent', color='floor_clean',
                           title="층별 월세 분포 (Box Plot)",
                           labels={'floor_clean': '층수', 'monthlyRent': '월세 (만원)'})
        st.plotly_chart(fig_floor, use_container_width=True)

# --- 하단 데이터 테이블 (한글 컬럼 적용) ---
st.write("---")
st.subheader("📋 전체 매물 데이터 리스트")
display_df = filtered_df.copy()
display_df = display_df.rename(columns=COLUMN_MAPPING)

# 표시할 컬럼만 선택
final_cols = [c for c in COLUMN_MAPPING.values() if c in display_df.columns]
st.dataframe(display_df[final_cols], use_container_width=True)
