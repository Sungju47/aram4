# streamlit_aram_ps_app_champion.py
# ----------------------------------------------
# ARAM PS Dashboard (Champion-centric)
# CSV: 참가자 단위 + 타임라인/룬/스펠/아이템/코어템시각 포함
# ----------------------------------------------
import ast
from typing import List, Tuple

import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px

st.set_page_config(page_title="ARAM PS Dashboard", layout="wide")

# 좌측: 데이터 선택
st.sidebar.title("데이터")
DEFAULT_CSV = "./aram_participants_with_full_runes_merged_plus.csv"
uploaded = st.sidebar.file_uploader("CSV 업로드(선택)", type=["csv"])
CSV_PATH = DEFAULT_CSV if uploaded is None else uploaded

# ---------- 유틸 ----------
def _yes(x) -> int:
    s = str(x).strip().lower()
    return 1 if s in ("1", "true", "t", "yes") else 0

def _first_nonempty(*vals):
    for v in vals:
        if v is None:
            continue
        s = str(v).strip()
        if s and s.lower() not in ("nan", "none"):
            return s
    return ""

def _as_list(s):
    # "['A','B']" 같은 문자열을 실제 리스트로 바꿔보기
    if isinstance(s, list):
        return s
    if not isinstance(s, str):
        return []
    s = s.strip()
    if not s:
        return []
    try:
        v = ast.literal_eval(s)
        if isinstance(v, list):
            return v
    except Exception:
        pass
    # 파이프/쉼표로 적힌 경우도 분해
    if "|" in s:
        return [t.strip() for t in s.split("|") if t.strip()]
    if "," in s:
        return [t.strip() for t in s.split(",") if t.strip()]
    return [s]

# ---------- 데이터 로드 ----------
@st.cache_data(show_spinner=False)
def load_data(csv) -> pd.DataFrame:
    df = pd.read_csv(csv)

    # win -> 0/1
    win_col = "win" if "win" in df.columns else None
    if win_col:
        df["win_clean"] = df[win_col].apply(_yes)
    else:
        df["win_clean"] = 0

    # spell 이름 컬럼 정규화
    # (spell1_name/spell2_name 이 있으면 그걸 사용, 없으면 spell1/spell2)
    s1 = "spell1_name" if "spell1_name" in df.columns else ("spell1" if "spell1" in df.columns else None)
    s2 = "spell2_name" if "spell2_name" in df.columns else ("spell2" if "spell2" in df.columns else None)
    df["spell1_final"] = df[s1].astype(str) if s1 else ""
    df["spell2_final"] = df[s2].astype(str) if s2 else ""

    # 아이템 문자열 정제
    item_cols = [c for c in df.columns if c.startswith("item")]
    for c in item_cols:
        df[c] = df[c].fillna("").astype(str).str.strip()

    # 팀/상대 조합 문자열 → 리스트
    for col in ("team_champs", "enemy_champs"):
        if col in df.columns:
            df[col] = df[col].apply(_as_list)

    # 경기시간(분)
    # game_end_min 있으면 사용, 없으면 damage_total/(딜분당?) 보정은 패스하고 평균값으로 대체
    if "game_end_min" in df.columns:
        df["duration_min"] = pd.to_numeric(df["game_end_min"], errors="coerce")
    else:
        df["duration_min"] = np.nan
    # 너무 작거나 NaN이면 18분으로 보정(칼바람 평균 근처)
    df["duration_min"] = df["duration_min"].fillna(18.0).clip(lower=6.0, upper=40.0)

    # 분당딜
    if "damage_total" in df.columns:
        df["dpm"] = df["damage_total"] / df["duration_min"].replace(0, np.nan)
    else:
        df["dpm"] = np.nan

    # KDA
    for c in ("kills", "deaths", "assists"):
        if c not in df.columns:
            df[c] = 0
    df["kda"] = (df["kills"] + df["assists"]) / df["deaths"].replace(0, np.nan)
    df["kda"] = df["kda"].fillna(df["kills"] + df["assists"])

    # 스펠 조합 키
    df["spell_combo"] = (df["spell1_final"] + " + " + df["spell2_final"]).str.strip()

    return df

with st.spinner("데이터 로딩 중..."):
    df = load_data(CSV_PATH)

# ---------- 사이드바: 필터 ----------
st.sidebar.markdown("---")
champs = sorted(df["champion"].dropna().unique().tolist())
champ = st.sidebar.selectbox("챔피언 선택", champs)

# ---------- 챔피언 서브셋 ----------
dfc = df[df["champion"] == champ].copy()
total_matches = df["matchId"].nunique()
champ_games   = len(dfc)
win_rate      = round(dfc["win_clean"].mean() * 100, 2) if champ_games else 0.0
pick_rate     = round(champ_games / total_matches * 100, 2) if total_matches else 0.0
avg_kills     = round(dfc["kills"].mean(), 2)
avg_deaths    = round(dfc["deaths"].mean(), 2)
avg_assists   = round(dfc["assists"].mean(), 2)
avg_kda       = round(dfc["kda"].mean(), 2)
avg_dpm       = round(dfc["dpm"].mean(), 1)

st.title(f"ARAM — {champ}")

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("게임 수", champ_games)
m2.metric("승률(%)", win_rate)
m3.metric("픽률(%)", pick_rate)
m4.metric("평균 K/D/A", f"{avg_kills}/{avg_deaths}/{avg_assists}")
m5.metric("평균 DPM", avg_dpm)

# ---------- 퍼블/첫포탑/게임시간/골드 스파이크 ----------
tl_cols = ["first_blood_min","blue_first_tower_min","red_first_tower_min","game_end_min","gold_spike_min"]
has_timeline = any(c in dfc.columns for c in tl_cols)
if has_timeline:
    st.subheader("타임라인 요약")
    t1, t2, t3 = st.columns(3)
    if "first_blood_min" in dfc.columns:
        t1.metric("퍼블 평균시각(분)", round(dfc["first_blood_min"].dropna().mean(), 2))
    if "blue_first_tower_min" in dfc.columns or "red_first_tower_min" in dfc.columns:
        bt = round(dfc["blue_first_tower_min"].dropna().mean(), 2) if "blue_first_tower_min" in dfc.columns else np.nan
        rt = round(dfc["red_first_tower_min"].dropna().mean(), 2)  if "red_first_tower_min"  in dfc.columns else np.nan
        t2.metric("첫 포탑 평균시각(블루/레드)", f"{bt} / {rt}")
    if "game_end_min" in dfc.columns:
        t3.metric("평균 게임시간(분)", round(dfc["game_end_min"].dropna().mean(), 2))

    # 골드 스파이크 분포
    if "gold_spike_min" in dfc.columns and dfc["gold_spike_min"].notna().any():
        fig = px.histogram(dfc, x="gold_spike_min", nbins=20, title="골드 스파이크 시각 분포(분)")
        st.plotly_chart(fig, use_container_width=True)

# ---------- 코어 아이템 구매 시각 ----------
core_time_cols = [c for c in ["first_core_item_min","first_core_item_name",
                              "second_core_item_min","second_core_item_name"] if c in dfc.columns]
if core_time_cols:
    st.subheader("코어 아이템 구매 타이밍")
    # 평균 요약
    a, b = st.columns(2)
    if "first_core_item_min" in dfc.columns and dfc["first_core_item_min"].notna().any():
        a.metric("1코어 평균 분", round(dfc["first_core_item_min"].mean(), 2))
        fig1 = px.histogram(dfc.dropna(subset=["first_core_item_min"]),
                            x="first_core_item_min", nbins=24, title="1코어 시각 분포")
        st.plotly_chart(fig1, use_container_width=True)
    if "second_core_item_min" in dfc.columns and dfc["second_core_item_min"].notna().any():
        b.metric("2코어 평균 분", round(dfc["second_core_item_min"].mean(), 2))
        fig2 = px.histogram(dfc.dropna(subset=["second_core_item_min"]),
                            x="second_core_item_min", nbins=24, title="2코어 시각 분포")
        st.plotly_chart(fig2, use_container_width=True)

    # 코어 아이템별 성과
    core_rows = []
    if "first_core_item_name" in dfc.columns:
        core_rows.append(
            dfc[["matchId","win_clean","first_core_item_name"]]
            .rename(columns={"first_core_item_name":"core_item"})
        )
    if "second_core_item_name" in dfc.columns:
        core_rows.append(
            dfc[["matchId","win_clean","second_core_item_name"]]
            .rename(columns={"second_core_item_name":"core_item"})
        )
    if core_rows:
        core_union = pd.concat(core_rows, ignore_index=True)
        core_union = core_union[core_union["core_item"].astype(str) != ""]
        core_stats = (core_union.groupby("core_item")
                      .agg(games=("matchId","count"),
                           wins=("win_clean","sum"))
                      .reset_index())
        core_stats["win_rate"] = (core_stats["wins"]/core_stats["games"]*100).round(2)
        core_stats = core_stats.sort_values(["games","win_rate"], ascending=[False,False])
        st.dataframe(core_stats.head(20), use_container_width=True)

# ---------- 아이템 성과 ----------
st.subheader("아이템 성과(슬롯 무시, 전체 합산)")
def item_stats(sub: pd.DataFrame) -> pd.DataFrame:
    item_cols = [c for c in sub.columns if c.startswith("item")]
    recs = []
    for c in item_cols:
        recs.append(sub[["matchId","win_clean",c]].rename(columns={c:"item"}))
    u = pd.concat(recs, ignore_index=True)
    u = u[u["item"].astype(str)!=""]
    g = (u.groupby("item")
         .agg(total_picks=("matchId","count"),
              wins=("win_clean","sum"))
         .reset_index())
    g["win_rate"] = (g["wins"]/g["total_picks"]*100).round(2)
    g = g.sort_values(["total_picks","win_rate"], ascending=[False,False])
    return g

items = item_stats(dfc)
st.dataframe(items.head(25), use_container_width=True)

# ---------- 스펠/룬 조합 ----------
c1, c2 = st.columns(2)
with c1:
    st.subheader("스펠 조합")
    if "spell_combo" in dfc.columns and dfc["spell_combo"].str.strip().any():
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
    rc, rs = ("rune_core" in dfc.columns), ("rune_sub" in dfc.columns)
    if rc and rs:
        rn = (dfc.groupby(["rune_core","rune_sub"])
                .agg(games=("matchId","count"), wins=("win_clean","sum"))
                .reset_index())
        rn["win_rate"] = (rn["wins"]/rn["games"]*100).round(2)
        rn = rn.sort_values(["games","win_rate"], ascending=[False,False])
        st.dataframe(rn.head(10), use_container_width=True)
    else:
        st.info("룬 정보가 부족합니다.")

# ---------- 원본 표(챔피언 필터) ----------
st.subheader("원본 데이터 (필터 적용)")
show_cols = [c for c in dfc.columns if c not in ("team_champs","enemy_champs")]
st.dataframe(dfc[show_cols], use_container_width=True)

st.markdown("---")
st.caption("CSV 기반 로컬 대시보드 · 누락 컬럼은 자동으로 건너뜁니다.")
