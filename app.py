# app.py  — 파일 자동 감지 + 아이콘 표시 대시보드 (간결판)
import os, re
import pandas as pd
import streamlit as st

st.set_page_config(page_title="ARAM PS Dashboard", layout="wide")

# 1) 플레이어 CSV 자동 선택 (있으면 superlight 우선)
PLAYER_CANDIDATES = [
    "aram_participants_with_icons_superlight.csv",
    "aram_participants_with_icons.csv",
    "aram_participants_clean_preprocessed.csv",   # 최후 폴백(아이콘 없을 수 있음)
]
ITEM_SUM_CSV = "item_summary_with_icons.csv"

def pick_first_exists(paths):
    for p in paths:
        if os.path.exists(p):
            return p
    return None

PLAYERS_CSV = pick_first_exists(PLAYER_CANDIDATES)

def _coerce_bool_to01(s: pd.Series) -> pd.Series:
    s = s.astype(str).str.lower()
    return s.isin(["1","true","t","yes","y"]).astype(int)

@st.cache_data
def load_players(path: str) -> pd.DataFrame:
    if not path or not os.path.exists(path):
        st.error(f"플레이어 CSV를 찾지 못했습니다. 현재 폴더: {os.listdir('.')}")
        st.stop()
    df = pd.read_csv(path)
    # 승패 플래그
    if "win_clean" not in df.columns:
        if "win" in df.columns:
            df["win_clean"] = _coerce_bool_to01(df["win"])
        else:
            df["win_clean"] = 0
    # 문자열 정리
    for c in df.columns:
        if c.endswith("_name") or c.endswith("_name_fix"):
            df[c] = df[c].fillna("").astype(str).str.strip()
    return df

@st.cache_data
def load_item_summary(path: str, df: pd.DataFrame) -> pd.DataFrame:
    # 1) 요약 CSV 있으면 그대로 사용
    if os.path.exists(path):
        g = pd.read_csv(path)
        need = {"item","icon_url","total_picks","wins","win_rate"}
        if need.issubset(g.columns):
            return g
        st.warning(f"`{path}` 컬럼 일부 누락 → 런타임 계산으로 대체")
    # 2) 런타임 계산(아이템 아이콘이 없으면 빈 DF 반환)
    name_cols = [c for c in df.columns if re.fullmatch(r"item[0-6]_name", c)]
    icon_cols = [c for c in df.columns if re.fullmatch(r"item[0-6]_icon", c)]
    if not name_cols or not icon_cols:
        return pd.DataFrame(columns=["item","icon_url","total_picks","wins","win_rate"])
    stacks=[]
    for i in range(7):
        n,f = f"item{i}_name", f"item{i}_icon"
        if n in df.columns and f in df.columns:
            tmp = df[[n,f,"matchId","win_clean"]].rename(columns={n:"item", f:"icon_url"})
            stacks.append(tmp)
    if not stacks:
        return pd.DataFrame(columns=["item","icon_url","total_picks","wins","win_rate"])
    u = pd.concat(stacks, ignore_index=True)
    u = u[u["item"].astype(str).str.len()>0]
    g = (u.groupby(["item","icon_url"])
           .agg(total_picks=("matchId","count"), wins=("win_clean","sum"))
           .reset_index())
    g["win_rate"] = (g["wins"]/g["total_picks"]*100).round(2)
    return g.sort_values(["total_picks","win_rate"], ascending=[False,False]).reset_index(drop=True)

# ===== 데이터 로드 =====
st.sidebar.caption(f"읽은 파일: **{PLAYERS_CSV}**")
df = load_players(PLAYERS_CSV)
item_sum = load_item_summary(ITEM_SUM_CSV, df)

# ===== 사이드바 =====
st.sidebar.title("ARAM PS Controls")
champions = sorted(df["champion"].dropna().unique().tolist())
selected = st.sidebar.selectbox("Champion", champions, index=0)

# ===== 챔피언 요약 =====
dsel = df[df["champion"]==selected].copy()
games = len(dsel)
total_matches = df["matchId"].nunique()
winrate = round(dsel["win_clean"].mean()*100,2) if games else 0.0
pickrate = round((dsel["matchId"].nunique()/total_matches)*100,2) if total_matches else 0.0

c1,c2,c3 = st.columns(3)
c1.metric("Games", games)
c2.metric("Win Rate", f"{winrate}%")
c3.metric("Pick Rate", f"{pickrate}%")
st.markdown(f"### {selected}")

# ===== 아이템 추천 =====
st.subheader("Recommended Items")
if len(item_sum):
    top_items = item_sum.head(20)
    st.dataframe(
        top_items[["icon_url","item","total_picks","wins","win_rate"]],
        use_container_width=True,
        column_config={
            "icon_url": st.column_config.ImageColumn("아이콘", width="small"),
            "item": "아이템",
            "total_picks": "픽수",
            "wins": "승수",
            "win_rate": "승률(%)",
        }
    )
else:
    st.info("아이템 요약을 표시할 수 없습니다. (`item_summary_with_icons.csv` 확인)")

# ===== 스펠 추천 =====
st.subheader("Recommended Spell Combos")
if {"spell1_icon","spell2_icon","spell1_name_fix","spell2_name_fix"}.issubset(dsel.columns):
    sp = (dsel.groupby(["spell1_icon","spell1_name_fix","spell2_icon","spell2_name_fix"])
            .agg(games=("matchId","count"), wins=("win_clean","sum")).reset_index())
    sp["win_rate"] = (sp["wins"]/sp["games"]*100).round(2)
    sp = sp.sort_values(["games","win_rate"], ascending=[False,False]).head(10)
    st.dataframe(
        sp[["spell1_icon","spell1_name_fix","spell2_icon","spell2_name_fix","games","wins","win_rate"]],
        use_container_width=True,
        column_config={
            "spell1_icon": st.column_config.ImageColumn("스펠1", width="small"),
            "spell2_icon": st.column_config.ImageColumn("스펠2", width="small"),
            "spell1_name_fix": "스펠1",
            "spell2_name_fix": "스펠2",
            "games": "게임수","wins":"승수","win_rate":"승률(%)",
        }
    )
else:
    st.info("스펠 아이콘/이름 컬럼이 없습니다.")

# ===== 룬 추천 =====
st.subheader("Recommended Rune Combos")
if {"rune_core_icon","rune_sub_icon","rune_core","rune_sub"}.issubset(dsel.columns):
    ru = (dsel.groupby(["rune_core_icon","rune_core","rune_sub_icon","rune_sub"])
            .agg(games=("matchId","count"), wins=("win_clean","sum")).reset_index())
    ru["win_rate"] = (ru["wins"]/ru["games"]*100).round(2)
    ru = ru.sort_values(["games","win_rate"], ascending=[False,False]).head(10)
    st.dataframe(
        ru[["rune_core_icon","rune_core","rune_sub_icon","rune_sub","games","wins","win_rate"]],
        use_container_width=True,
        column_config={
            "rune_core_icon": st.column_config.ImageColumn("핵심룬", width="small"),
            "rune_sub_icon":  st.column_config.ImageColumn("보조트리", width="small"),
            "rune_core":"핵심룬", "rune_sub":"보조트리",
            "games":"게임수","wins":"승수","win_rate":"승률(%)",
        }
    )
else:
    st.info("룬 아이콘/이름 컬럼이 없습니다.")

# ===== 원본 보기 =====
with st.expander("Raw rows (selected champion)"):
    st.dataframe(dsel, use_container_width=True)
