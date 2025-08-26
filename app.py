# app.py — ARAM PS Dashboard (Champion-centric, with icons)
import os, glob, ast
from typing import Optional, List
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px

st.set_page_config(page_title="ARAM PS Dashboard", layout="wide")

# -------------------- 파일 경로 --------------------
HARD_NAME = "aram_participants_with_icons.csv"
CANDIDATES = [
    HARD_NAME,
    "*with_icons*.csv",
    "*merged_plus*.csv",
    "*full_runes_merged*.csv",
]

def discover_csv() -> Optional[str]:
    if os.path.exists(HARD_NAME):  # 네가 말한 파일명 우선
        return HARD_NAME
    for pat in CANDIDATES:
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[0]
    return None

# -------------------- 유틸 --------------------
def _yes(x) -> int:
    s = str(x).strip().lower()
    return 1 if s in ("1","true","t","yes") else 0

def _as_list(s):
    if isinstance(s, list): return s
    if not isinstance(s, str): return []
    s = s.strip()
    if not s: return []
    try:
        v = ast.literal_eval(s)
        if isinstance(v, list): return v
    except Exception:
        pass
    if "|" in s:  return [t.strip() for t in s.split("|") if t.strip()]
    if "," in s:  return [t.strip() for t in s.split(",") if t.strip()]
    return [s]

def pick_first_existing(cols: List[str], df_cols) -> Optional[str]:
    for c in cols:
        if c in df_cols: return c
    return None

# -------------------- 로딩 --------------------
@st.cache_data(show_spinner=False)
def load_df(src) -> pd.DataFrame:
    df = pd.read_csv(src)

    # 승패 → 0/1
    df["win_clean"] = df["win"].apply(_yes) if "win" in df.columns else 0

    # 스펠 이름 정규화
    s1 = "spell1_name" if "spell1_name" in df.columns else ("spell1" if "spell1" in df.columns else None)
    s2 = "spell2_name" if "spell2_name" in df.columns else ("spell2" if "spell2" in df.columns else None)
    df["spell1_final"] = df[s1].astype(str) if s1 else ""
    df["spell2_final"] = df[s2].astype(str) if s2 else ""
    df["spell_combo"]  = (df["spell1_final"] + " + " + df["spell2_final"]).str.strip()

    # 아이템 문자열 정리
    for c in [c for c in df.columns if c.startswith("item")]:
        df[c] = df[c].fillna("").astype(str).str.strip()

    # 팀/상대 조합 → 리스트
    for col in ("team_champs","enemy_champs"):
        if col in df.columns:
            df[col] = df[col].apply(_as_list)

    # 경기시간(분) & DPM, KDA
    if "game_end_min" in df.columns:
        df["duration_min"] = pd.to_numeric(df["game_end_min"], errors="coerce")
    else:
        df["duration_min"] = np.nan
    df["duration_min"] = df["duration_min"].fillna(18.0).clip(lower=6.0, upper=40.0)

    if "damage_total" in df.columns:
        df["dpm"] = df["damage_total"] / df["duration_min"].replace(0, np.nan)
    else:
        df["dpm"] = np.nan

    for c in ("kills","deaths","assists"):
        if c not in df.columns: df[c] = 0
    df["kda"] = (df["kills"] + df["assists"]) / df["deaths"].replace(0, np.nan)
    df["kda"] = df["kda"].fillna(df["kills"] + df["assists"])

    # 아이콘 컬럼 자동 탐지(있을 때만 사용)
    icon_candidates = ["champion_icon","championIcon","champion_icon_url","icon","icon_url"]
    df.attrs["champ_icon_col"] = pick_first_existing(icon_candidates, df.columns)

    # 스펠/아이템 아이콘 후보(있을 경우 표에 함께 노출)
    for key in ["spell1_icon","spell2_icon"]:
        if key not in df.columns:
            # 없는 경우도 자연스럽게 패스
            df[key] = np.nan

    for i in range(7):  # item0..item6
        ic = f"item{i}_icon"
        if ic not in df.columns:
            df[ic] = np.nan

    return df

# -------------------- 파일 입력 UI --------------------
st.sidebar.title("데이터")
auto_path = discover_csv()
st.sidebar.write("🔎 자동 검색:", auto_path if auto_path else "없음")
uploaded = st.sidebar.file_uploader("CSV 업로드(선택)", type=["csv"])

if uploaded is not None:
    df = load_df(uploaded)
elif auto_path is not None:
    df = load_df(auto_path)
else:
    st.error("CSV를 찾지 못했습니다. 레포 루트에 파일을 넣거나 업로드하세요.")
    st.stop()

# -------------------- 필터 --------------------
st.sidebar.markdown("---")
if "champion" not in df.columns:
    st.error("CSV에 'champion' 컬럼이 없습니다.")
    st.stop()

champions = sorted(df["champion"].dropna().unique().tolist())
sel_champ = st.sidebar.selectbox("챔피언 선택", champions)

# -------------------- 헤더 (아이콘 + 지표) --------------------
dfc = df[df["champion"]==sel_champ].copy()
total_matches = df["matchId"].nunique() if "matchId" in df.columns else max(1, len(dfc))
games = len(dfc)
winrate = round(dfc["win_clean"].mean()*100,2) if games else 0.0
pickrate = round(games / max(1,total_matches) * 100, 2)

avg_k = round(dfc["kills"].mean(),2) if "kills" in dfc else 0
avg_d = round(dfc["deaths"].mean(),2) if "deaths" in dfc else 0
avg_a = round(dfc["assists"].mean(),2) if "assists" in dfc else 0
avg_kda = round(dfc["kda"].mean(),2) if "kda" in dfc else 0
avg_dpm = round(dfc["dpm"].mean(),1) if "dpm" in dfc else 0

st.title("ARAM Dashboard")
hc = df.attrs.get("champ_icon_col")
if hc and hc in dfc.columns:
    # 선택 챔피언 행 중 첫 아이콘 URL 사용
    url = dfc[hc].dropna().astype(str).str.strip()
    icon_url = url.iloc[0] if len(url) else None
else:
    icon_url = None

c0, c1, c2, c3, c4, c5 = st.columns([0.6,1,1,1,1,1])
if icon_url:
    c0.image(icon_url, width=72, caption=sel_champ)
else:
    c0.markdown(f"### {sel_champ}")

c1.metric("게임 수", games)
c2.metric("승률(%)", winrate)
c3.metric("픽률(%)", pickrate)
c4.metric("평균 K/D/A", f"{avg_k}/{avg_d}/{avg_a}")
c5.metric("평균 DPM", avg_dpm)

# -------------------- 타임라인 요약 (있으면 표시) --------------------
tl_cols = ["first_blood_min","blue_first_tower_min","red_first_tower_min","game_end_min","gold_spike_min"]
if any(c in dfc.columns for c in tl_cols):
    st.subheader("타임라인 요약")
    t1, t2, t3 = st.columns(3)
    if "first_blood_min" in dfc and dfc["first_blood_min"].notna().any():
        t1.metric("퍼블 평균(분)", round(dfc["first_blood_min"].mean(), 2))
    if ("blue_first_tower_min" in dfc) or ("red_first_tower_min" in dfc):
        bt = round(dfc["blue_first_tower_min"].dropna().mean(), 2) if "blue_first_tower_min" in dfc else np.nan
        rt = round(dfc["red_first_tower_min"].dropna().mean(), 2) if "red_first_tower_min" in dfc else np.nan
        t2.metric("첫 포탑 평균(블루/레드)", f"{bt} / {rt}")
    if "game_end_min" in dfc and dfc["game_end_min"].notna().any():
        t3.metric("평균 게임시간(분)", round(dfc["game_end_min"].mean(), 2))

    if "gold_spike_min" in dfc and dfc["gold_spike_min"].notna().any():
        st.plotly_chart(px.histogram(dfc, x="gold_spike_min", nbins=20, title="골드 스파이크 분포"), use_container_width=True)

# -------------------- 코어템 구매시각 --------------------
core_cols = [c for c in ["first_core_item_min","first_core_item_name",
                         "second_core_item_min","second_core_item_name"] if c in dfc.columns]
if core_cols:
    st.subheader("코어 아이템 구매 타이밍")
    a, b = st.columns(2)
    if "first_core_item_min" in dfc and dfc["first_core_item_min"].notna().any():
        a.metric("1코어 평균(분)", round(dfc["first_core_item_min"].mean(),2))
        st.plotly_chart(px.histogram(dfc.dropna(subset=["first_core_item_min"]),
                                     x="first_core_item_min", nbins=24, title="1코어 시각 분포"),
                        use_container_width=True)
    if "second_core_item_min" in dfc and dfc["second_core_item_min"].notna().any():
        b.metric("2코어 평균(분)", round(dfc["second_core_item_min"].mean(),2))
        st.plotly_chart(px.histogram(dfc.dropna(subset=["second_core_item_min"]),
                                     x="second_core_item_min", nbins=24, title="2코어 시각 분포"),
                        use_container_width=True)
    core_rows = []
    if "first_core_item_name" in dfc:
        core_rows.append(dfc[["matchId","win_clean","first_core_item_name"]]
                         .rename(columns={"first_core_item_name":"core_item"}))
    if "second_core_item_name" in dfc:
        core_rows.append(dfc[["matchId","win_clean","second_core_item_name"]]
                         .rename(columns={"second_core_item_name":"core_item"}))
    if core_rows:
        union = pd.concat(core_rows, ignore_index=True)
        union = union[union["core_item"].astype(str)!=""]
        g = (union.groupby("core_item")
             .agg(games=("matchId","count"), wins=("win_clean","sum"))
             .reset_index())
        g["win_rate"] = (g["wins"]/g["games"]*100).round(2)
        g = g.sort_values(["games","win_rate"], ascending=[False,False])
        st.dataframe(g.head(20), use_container_width=True)

# -------------------- 아이템 성과(아이콘 포함) --------------------
st.subheader("아이템 성과(슬롯 무시, 아이콘 렌더링)")

def item_stats_with_icon(sub: pd.DataFrame) -> pd.DataFrame:
    rows = []
    # item0..item6 + 대응 아이콘(item0_icon..)
    for i in range(7):
        name_col = f"item{i}"
        icon_col = f"item{i}_icon"
        if name_col not in sub.columns:
            continue
        tmp = sub[[ "matchId", "win_clean", name_col ]].rename(columns={name_col: "item"})
        tmp["icon"] = sub[icon_col] if icon_col in sub.columns else np.nan
        rows.append(tmp)

    if not rows:
        return pd.DataFrame(columns=["item","icon","total_picks","wins","win_rate"])

    u = pd.concat(rows, ignore_index=True)
    # 빈 값/0/NaN 제거
    u["item"] = u["item"].astype(str).str.strip()
    u = u[(u["item"]!="") & (u["item"]!="0") & (u["item"]!="nan")]

    # 아이콘은 첫 유효 URL 하나만 대표로 사용
    def first_icon(x):
        x = x.dropna().astype(str).str.strip()
        return x.iloc[0] if len(x) else np.nan

    g = (u.groupby("item")
           .agg(total_picks=("matchId","count"),
                wins=("win_clean","sum"),
                icon=("icon", first_icon))
           .reset_index())

    g["win_rate"] = (g["wins"]/g["total_picks"]*100).round(2)
    g = g.sort_values(["total_picks","win_rate"], ascending=[False,False]).reset_index(drop=True)
    return g

items_df = item_stats_with_icon(dfc)

# st.dataframe 도 column_config를 받지만, data_editor가 이미지 렌더링이 더 안정적
st.data_editor(
    items_df.head(25),
    use_container_width=True,
    column_config={
        "icon": st.column_config.ImageColumn("아이템", help="아이템 아이콘", width="small"),
        "item": st.column_config.TextColumn("아이템 이름"),
        "total_picks": st.column_config.NumberColumn("픽수", format="%d"),
        "wins": st.column_config.NumberColumn("승수", format="%d"),
        "win_rate": st.column_config.NumberColumn("승률(%)", format="%.2f"),
    },
    hide_index=True,
)


# -------------------- 스펠/룬 --------------------
c1, c2 = st.columns(2)
with c1:
    st.subheader("스펠 조합")
    if "spell_combo" in dfc and dfc["spell_combo"].str.strip().any():
        sp = (dfc.groupby("spell_combo")
              .agg(games=("matchId","count"), wins=("win_clean","sum"))
              .reset_index())
        sp["win_rate"] = (sp["wins"]/sp["games"]*100).round(2)
        sp = sp.sort_values(["games","win_rate"], ascending=[False,False])
        st.dataframe(sp.head(10), use_container_width=True)
    else:
        st.info("스펠 정보가 부족합니다.")
with c2:
    st.subheader("룬 조합(메인/보조)")
    if ("rune_core" in dfc.columns) and ("rune_sub" in dfc.columns):
        rn = (dfc.groupby(["rune_core","rune_sub"])
              .agg(games=("matchId","count"), wins=("win_clean","sum"))
              .reset_index())
        rn["win_rate"] = (rn["wins"]/rn["games"]*100).round(2)
        rn = rn.sort_values(["games","win_rate"], ascending=[False,False])
        st.dataframe(rn.head(10), use_container_width=True)
    else:
        st.info("룬 정보가 부족합니다.")

# -------------------- 원본(아이콘 컬럼은 좌측으로) --------------------
st.subheader("원본 데이터 (필터 적용)")
columns = list(dfc.columns)
# 아이콘 컬럼들을 앞으로 끌어와 가독성 ↑
icon_order = [c for c in columns if c.endswith("_icon")] + \
             [df.attrs.get("champ_icon_col")] if df.attrs.get("champ_icon_col") else []
icon_order = [c for c in icon_order if c and c in columns]
others = [c for c in columns if c not in icon_order]
disp_cols = icon_order + others
st.dataframe(dfc[disp_cols], use_container_width=True)

st.markdown("---")
st.caption("아이콘 컬럼이 있으면 자동으로 활용합니다. 파일명은 aram_participants_with_icons.csv가 우선입니다.")
