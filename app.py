import streamlit as st
from supabase import create_client, Client
import datetime
import pandas as pd
import plotly.figure_factory as ff
import time

# --- 1. 페이지 설정 및 스타일 ---
st.set_page_config(page_title="중장비 배차 관리 시스템", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
    <style>
    .stButton > button { width: 100%; height: 3em; font-size: 18px !important; margin-bottom: 10px; }
    .login-container { max-width: 400px; margin: auto; padding: 20px; border-radius: 10px; background-color: #f0f2f6; }
    </style>
    """, unsafe_allow_html=True)

# Supabase 연결
URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(URL, KEY)

# --- 2. 로그인 세션 관리 로직 ---
if 'user' not in st.session_state:
    st.session_state.user = None

def login():
    with st.container():
        st.markdown("<div class='login-container'>", unsafe_allow_html=True)
        st.subheader("🔒 관리자 로그인")
        email = st.text_input("이메일")
        password = st.text_input("비밀번호", type="password")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("로그인"):
                try:
                    res = supabase.auth.sign_in_with_password({"email": email, "password": password})
                    st.session_state.user = res.user
                    st.success("로그인 성공!")
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error("이메일 또는 비밀번호가 틀립니다.")
        with col2:
            st.caption("계정이 없으신가요? 관리자에게 문의하세요.")
        st.markdown("</div>", unsafe_allow_html=True)

def logout():
    supabase.auth.sign_out()
    st.session_state.user = None
    st.rerun()

# --- 3. 앱 메인 로직 ---
# 로그인이 안 되어 있으면 로그인 화면만 출력
if st.session_state.user is None:
    login()
    st.stop() # 이후 코드 실행 중단

# 로그인 된 경우에만 아래 내용 표시
with st.sidebar:
    st.write(f"👤 {st.session_state.user.email}")
    if st.button("로그아웃"):
        logout()

# --- 기존 배차 관리 로직 시작 ---
# (이전 버전의 공통 함수 및 탭 구성 코드가 여기에 포함됩니다)

if 'is_processing' not in st.session_state:
    st.session_state.is_processing = False

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

@st.dialog("📋 예약 일정 수정/삭제")
def edit_rental_dialog(item):
    st.write(f"**장비:** {item['equip_name']}\n**고객:** {item['client_name']}")
    with st.form("edit_form"):
        new_start = st.date_input("시작일", value=datetime.date.fromisoformat(item['start_date']))
        new_end = st.date_input("종료일", value=datetime.date.fromisoformat(item['end_date']))
        new_price = st.number_input("금액", value=int(item['total_price']), step=10000)
        if st.form_submit_button("💾 수정 저장"):
            is_overlap, period = check_overlap(item['equipment_id'], new_start, new_end, exclude_id=item['id'])
            if is_overlap: st.error(f"❌ 날짜 중복! ({period})")
            else:
                supabase.table("rentals").update({"start_date": new_start.isoformat(), "end_date": new_end.isoformat(), "total_price": new_price}).eq("id", item['id']).execute()
                st.success("수정 완료"); time.sleep(1); st.rerun()
        if st.form_submit_button("🗑️ 일정 삭제", type="primary"):
            supabase.table("rentals").delete().eq("id", item['id']).execute()
            st.warning("삭제 완료"); time.sleep(1); st.rerun()

st.title("🚜 배차 관리 시스템")
tab1, tab2, tab3 = st.tabs(["📊 현황", "📝 예약", "⚙️ 관리"])

# --- Tab 1: 현황 ---
with tab1:
    raw_rentals = supabase.table("rentals").select("*, equipments(name, spec), clients(company_name)").execute().data
    if not raw_rentals: st.info("등록된 일정이 없습니다.")
    else:
        df_chart_list = [dict(Task=f"{r['equipments']['name']}", Start=r['start_date'], Finish=(datetime.date.fromisoformat(r['end_date']) + datetime.timedelta(days=1)).isoformat(), Resource=r['clients']['company_name']) for r in raw_rentals]
        fig = ff.create_gantt(pd.DataFrame(df_chart_list), index_col='Resource', show_colorbar=True, group_tasks=True, showgrid_x=True)
        fig.update_layout(height=450, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
        st.subheader("✏️ 상세 관리")
        for r in raw_rentals:
            with st.expander(f"{r['start_date']} | {r['equipments']['name']}"):
                st.write(f"고객: {r['clients']['company_name']} / {r['total_price']:,}원")
                if st.button("수정/삭제", key=f"btn_{r['id']}"):
                    edit_rental_dialog({"id": r['id'], "equipment_id": r['equipment_id'], "equip_name": r['equipments']['name'], "client_name": r['clients']['company_name'], "start_date": r['start_date'], "end_date": r['end_date'], "total_price": r['total_price']})

# --- Tab 2: 예약 ---
with tab2:
    e_data = supabase.table("equipments").select("*").execute().data
    c_data = supabase.table("clients").select("*").execute().data
    if not e_data or not c_data: st.info("기초 정보를 등록하세요.")
    else:
        c_dict = {c['company_name']: c['id'] for c in c_data}
        e_dict = {f"{e['name']} ({e['spec']})": e['id'] for e in e_data}
        sel_client = st.selectbox("🏢 고객사", options=list(c_dict.keys()))
        sel_equip_name = st.selectbox("🚜 장비 선택", options=list(e_dict.keys()))
        target_id = e_dict[sel_equip_name]
        booked = supabase.table("rentals").select("start_date, end_date").eq("equipment_id", target_id).execute().data
        if booked: st.warning("기존 예약:\n" + "\n".join([f"• {b['start_date']} ~ {b['end_date']}" for b in booked]))
        else: st.success("✅ 예약 가능")
        with st.form("rental_form", clear_on_submit=True):
            date_range = st.date_input("🗓️ 대여 기간", [datetime.date.today(), datetime.date.today() + datetime.timedelta(days=1)])
            price = st.number_input("💰 대여 금액", min_value=0, step=10000)
            if st.form_submit_button("🚀 예약 확정 저장"):
                if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
                    is_overlap, period = check_overlap(target_id, date_range[0], date_range[1])
                    if is_overlap: st.error(f"❌ 중복: {period}")
                    else:
                        supabase.table("rentals").insert({"equipment_id": target_id, "client_id": c_dict[sel_client], "start_date": date_range[0].isoformat(), "end_date": date_range[1].isoformat(), "total_price": price, "rental_status": "Confirmed"}).execute()
                        st.success("저장 완료!"); st.balloons(); time.sleep(1); st.rerun()

# --- Tab 3: 관리 ---
with tab3:
    st.write("### ⚙️ 시스템 관리")
    with st.expander("장비 추가"):
        with st.form("e_reg"):
            en, es = st.text_input("장비명"), st.text_input("규격")
            if st.form_submit_button("저장"): supabase.table("equipments").insert({"name": en, "spec": es, "status": "Available"}).execute(); st.rerun()
    with st.expander("고객사 추가"):
        with st.form("c_reg"):
            cn = st.text_input("고객사명")
            if st.form_submit_button("저장"): supabase.table("clients").insert({"company_name": cn}).execute(); st.rerun()