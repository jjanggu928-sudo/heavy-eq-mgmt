import streamlit as st
from supabase import create_client, Client
import datetime
import pandas as pd
import plotly.figure_factory as ff
import time

# 1. Supabase 연결 설정
URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(URL, KEY)

st.set_page_config(page_title="건설중기 스마트 관리 v2.2", layout="wide")

if 'is_processing' not in st.session_state:
    st.session_state.is_processing = False

# --- 공통 함수: 날짜 중복 검사 ---
def check_overlap(equip_id, start_dt, end_dt, exclude_id=None):
    query = supabase.table("rentals").select("*").eq("equipment_id", equip_id)
    if exclude_id:
        query = query.neq("id", exclude_id)
    existing = query.execute()
    
    for r in existing.data:
        r_start = datetime.date.fromisoformat(r['start_date'])
        r_end = datetime.date.fromisoformat(r['end_date'])
        if start_dt <= r_end and end_dt >= r_start:
            return True, f"{r_start} ~ {r_end}"
    return False, ""

# --- 수정 팝업창 ---
@st.dialog("📋 예약 일정 수정/삭제")
def edit_rental_dialog(item):
    st.write(f"**장비:** {item['equip_name']} | **고객:** {item['client_name']}")
    with st.form("edit_form"):
        new_start = st.date_input("시작일", value=datetime.date.fromisoformat(item['start_date']))
        new_end = st.date_input("종료일", value=datetime.date.fromisoformat(item['end_date']))
        new_price = st.number_input("금액", value=int(item['total_price']), step=10000)
        
        col1, col2 = st.columns(2)
        with col1:
            if st.form_submit_button("💾 수정 내용 저장"):
                is_overlap, period = check_overlap(item['equipment_id'], new_start, new_end, exclude_id=item['id'])
                if is_overlap:
                    st.error(f"❌ 날짜 중복! ({period})")
                else:
                    supabase.table("rentals").update({
                        "start_date": new_start.isoformat(),
                        "end_date": new_end.isoformat(),
                        "total_price": new_price
                    }).eq("id", item['id']).execute()
                    st.success("저장 완료!")
                    time.sleep(1)
                    st.rerun()
        with col2:
            if st.form_submit_button("🗑️ 일정 삭제", type="primary"):
                supabase.table("rentals").delete().eq("id", item['id']).execute()
                st.warning("삭제 완료")
                time.sleep(1)
                st.rerun()

st.title("🚜 건설중기 배차 관리 시스템")

tab1, tab2, tab3 = st.tabs(["📊 스케줄 대시보드", "📝 대여 예약", "⚙️ 기초 정보 관리"])

# --- Tab 1: 대시보드 (가트 차트) ---
with tab1:
    st.subheader("📊 전체 배차 일정표")
    raw_rentals = supabase.table("rentals").select("*, equipments(name, spec), clients(company_name)").execute().data
    
    if not raw_rentals:
        st.info("등록된 일정이 없습니다.")
    else:
        df_chart_list = []
        for r in raw_rentals:
            # 시각화 공백 제거 (+1일 로직)
            visual_end = (datetime.date.fromisoformat(r['end_date']) + datetime.timedelta(days=1)).isoformat()
            df_chart_list.append(dict(
                Task=f"{r['equipments']['name']} ({r['equipments']['spec']})",
                Start=r['start_date'], Finish=visual_end, Resource=r['clients']['company_name']
            ))
        
        df_chart = pd.DataFrame(df_chart_list)
        fig = ff.create_gantt(df_chart, index_col='Resource', show_colorbar=True, group_tasks=True, showgrid_x=True, showgrid_y=True)
        st.plotly_chart(fig, use_container_width=True)

        st.divider()
        st.subheader("✏️ 일정 상세 관리")
        for r in raw_rentals:
            with st.expander(f"📅 {r['start_date']} ~ {r['end_date']} | {r['equipments']['name']} | {r['clients']['company_name']}"):
                if st.button("수정/삭제", key=f"btn_{r['id']}"):
                    edit_rental_dialog({
                        "id": r['id'], "equipment_id": r['equipment_id'],
                        "equip_name": r['equipments']['name'], "client_name": r['clients']['company_name'],
                        "start_date": r['start_date'], "end_date": r['end_date'], "total_price": r['total_price']
                    })

# --- Tab 2: 대여 예약 (실시간 반응형으로 수정) ---
with tab2:
    st.subheader("📝 신규 예약 등록")
    e_data = supabase.table("equipments").select("*").execute().data
    c_data = supabase.table("clients").select("*").execute().data

    if not e_data or not c_data:
        st.info("기초 정보를 먼저 등록하세요.")
    else:
        # 1. 셀렉트박스를 폼 외부로 이동 (실시간 리프레쉬 가능)
        c_dict = {c['company_name']: c['id'] for c in c_data}
        e_dict = {f"{e['name']} ({e['spec']})": e['id'] for e in e_data}
        
        sel_client = st.selectbox("고객사 선택", options=list(c_dict.keys()))
        sel_equip_name = st.selectbox("장비 선택", options=list(e_dict.keys()))
        
        # 2. 선택된 장비에 대한 데이터 즉시 호출
        target_id = e_dict[sel_equip_name]
        booked = supabase.table("rentals").select("start_date, end_date").eq("equipment_id", target_id).execute().data
        
        # 3. 예약 현황 실시간 표시
        if booked:
            formatted_list = [f"• {b['start_date']} ~ {b['end_date']}" for b in booked]
            st.warning(f"⚠️ **{sel_equip_name}**의 기존 예약 일정입니다:\n" + "\n".join(formatted_list))
        else:
            st.success(f"✅ **{sel_equip_name}** 장비는 현재 확정된 예약이 없어 자유롭게 선택 가능합니다.")
        
        # 4. 날짜와 금액 입력만 폼으로 구성
        with st.form("rental_form", clear_on_submit=True):
            date_range = st.date_input("대여 기간", [datetime.date.today(), datetime.date.today() + datetime.timedelta(days=1)])
            price = st.number_input("대여 금액", min_value=0, step=10000)
            
            if st.form_submit_button("🚀 예약 저장"):
                if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
                    is_overlap, period = check_overlap(target_id, date_range[0], date_range[1])
                    if is_overlap:
                        st.error(f"❌ 중복 일정: {period}")
                    else:
                        # 저장 로직 (이전에 선택한 sel_client, target_id 사용)
                        supabase.table("rentals").insert({
                            "equipment_id": target_id, 
                            "client_id": c_dict[sel_client],
                            "start_date": date_range[0].isoformat(), 
                            "end_date": date_range[1].isoformat(),
                            "total_price": price, 
                            "rental_status": "Confirmed"
                        }).execute()
                        st.success("저장 완료!")
                        st.balloons()
                        time.sleep(1)
                        st.rerun()
# --- Tab 3: 기초 정보 관리 (검색 기능 유지) ---
with tab3:
    st.subheader("🔍 기초 정보 관리")
    col_reg, col_view = st.columns([1, 2])
    with col_reg:
        st.write("### 데이터 추가")
        with st.expander("장비 추가"):
            with st.form("e_reg"):
                en, es = st.text_input("장비명"), st.text_input("규격")
                if st.form_submit_button("저장"):
                    supabase.table("equipments").insert({"name": en, "spec": es, "status": "Available"}).execute()
                    st.rerun()
        with st.expander("고객사 추가"):
            with st.form("c_reg"):
                cn = st.text_input("고객사명")
                if st.form_submit_button("저장"):
                    supabase.table("clients").insert({"company_name": cn}).execute()
                    st.rerun()
    with col_view:
        st.write("### 현황 검색")
        e_list = supabase.table("equipments").select("*").execute().data
        c_list = supabase.table("clients").select("*").execute().data
        c1, c2 = st.columns(2)
        with c1:
            s_e = st.text_input("🚜 장비 검색")
            if e_list:
                df_e = pd.DataFrame(e_list)
                st.dataframe(df_e[df_e['name'].str.contains(s_e, na=False)][['name', 'spec']], use_container_width=True)
        with c2:
            s_c = st.text_input("🏢 고객사 검색")
            if c_list:
                df_c = pd.DataFrame(c_list)
                st.dataframe(df_c[df_c['company_name'].str.contains(s_c, na=False)][['company_name']], use_container_width=True)