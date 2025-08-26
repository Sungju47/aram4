# app.py  — ARAM PS Dashboard (icons ready)
# ----------------------------------------
import os
import re
import pandas as pd
import streamlit as st

st.set_page_config(page_title="ARAM PS Dashboard", layout="wide")

# ====== CSV 파일명 (레포 루트) ======
PLAYERS_CSV = "aram_participants_with_icons_superlight.csv"
ITEM_SUM_CSV = "item_summary_with_icons.csv"  # item, icon_url, total_picks, wins, win_rate

# ====== 로더 ======
@st.cache_data
def load_players(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        raise FileNotFoundError(f"'{path}' 가 레포에 없습니다.")
    df = pd.read_csv(path)

    # 승패 플래그
    if "win" in df.columns:
        df["win_clean"] = (
            df["win"].astype(str).str.lower().isin(["true", "1", "t", "yes"]).astype(int)
        )
    else:
        df["win_clean"] = 0

    # 아이템 이름/아이콘 컬럼 정리
    item_name_cols = [c for c in df.columns if re.fullmatch(r"item[0-6]_name", c)]
    item_icon_cols = [c for c in df.columns if re.fullmatch(r"item[0-6]_icon", c)]
    for c in item_name_cols + item_icon_cols:
        df[c] = df[c].fillna("").astype(str).str.strip()

    # 스펠/룬 이름 컬럼 기본값
    for c in ["spell1", "spell2", "rune_core", "rune_sub", "rune_shards"]:
        if c not in df.columns:
            df[c] = ""

    return df


@st.cache_data
def load_item_summary(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        # 없으면 빈 DF 반환(앱은 런타임 계산 결과만 사용하도록)
        return pd.DataFrame(columns=["item", "icon_url", "total_picks", "wins", "win_rate"])
    g = pd.read_csv(path)
    # 안전 처리
    for c in ["item", "icon_url"]:
        if c in g.columns:
            g[c] = g[c].fillna("").astype(str)
    for c in ["total_picks", "wins", "win_rate"]:
        if c in g.columns:
            g[c] = pd.to_numeric(g[c], errors="coerce")
    return g


# ====== 통계 함수 ======
@st.cache_data
def compute_champion_agg(df: pd.DataFrame, champion: str) -> dict:
    dsel = df[df["champion"] == champion].copy()
    if dsel.empty:
        return dict(games=0, winrate=0.0, pickrate=0.0)
    games = len(dsel)
    winrate = round(dsel["win_clean"].mean() * 100, 2)
    pickrate = round(games / df["matchId"].nunique() * 100, 2) if "matchId" in df.columns else 0.0
    return dict(games=games, winrate=winrate, pickrate=pickrate)


@st.cache_data
def compute_item_stats_for_champion(df: pd.DataFrame, champion: str) -> pd.DataFrame:
    dsel = df[df["champion"] == champion].copy()
    if dsel.empty:
        return pd.DataFrame(columns=["icon_url", "item", "total_picks", "wins", "win_rate"])

    name_cols = [c for c in dsel.columns if re.fullmatch(r"item[0-6]_name", c)]
    icon_cols = [c for c in dsel.columns if re.fullmatch(r"item[0-6]_icon", c)]

    stacks = []
    for i in range(7):
        ncol = f"item{i}_name"
        icol = f"item{i}_icon"
        if ncol in dsel.columns and icol in dsel.columns:
            tmp = dsel[[ncol, icol, "win_clean"]].rename(columns={ncol: "item", icol: "icon_url"})
            stacks.append(tmp)

    if not stacks:
        return pd.DataFrame(columns=["icon_url", "item", "total_picks", "wins", "win_rate"])

    u = pd.concat(stacks, ignore_index=True)
    u = u[u["item"].astype(str) != ""]
    g = (
        u.groupby(["item", "icon_url"])
        .agg(total_picks=("item", "count"), wins=("win_clean", "sum"))
        .reset_index()
    )
    g["win_rate"] = (g["wins"] / g["total_picks"] * 100).round(2)
    g = g.sort_values(["total_picks", "win_rate"], ascending=[False, False])
    return g


@st.cache_data
def compute_spell_stats_for_champion(df: pd.DataFrame, champion: str) -> pd.DataFrame:
    dsel = df[df["champion"] == champion].copy()
    if dsel.empty or not {"spell1", "spell2"}.issubset(dsel.columns):
        return pd.DataFrame(columns=["spell1", "spell2", "games", "wins", "win_rate"])
    g = (
        dsel.groupby(["spell1", "spell2"])
        .agg(games=("spell1", "count"), wins=("win_clean", "sum"))
        .reset_index()
    )
    g["win_rate"] = (g["wins"] / g["games"] * 100).round(2)
    g = g.sort_values(["games", "win_rate"], ascending=[False, False])
    return g


@st.cache_data
def compute_rune_stats_for_champion(df: pd.DataFrame, champion: str) -> pd.DataFrame:
    dsel = df[df["champion"] == champion].copy()
    cols = {"rune_core", "rune_sub", "rune_shards"}
    if dsel.empty or not cols.issubset(dsel.columns):
        return pd.DataFrame(columns=["rune_core", "rune_sub", "rune_shards", "games", "wins", "win_rate"])
    g = (
        dsel.groupby(["rune_core", "rune_sub", "rune_shards"])
        .agg(games=("rune_core", "count"), wins=("win_clean", "sum"))
        .reset_index()
    )
    g["win_rate"] = (g["wins"] / g["games"] * 100).round(2)
    g = g.sort_values(["games", "win_rate"], ascending=[False, False])
    return g


# ====== 데이터 로드 ======
with st.spinner("데이터 로딩 중..."):
    df = load_players(PLAYERS_CSV)
    item_sum_global = load_item_summary(ITEM_SUM_CSV)

# ====== 사이드바 ======
st.sidebar.title("ARAM PS Controls")
champions = sorted(df["champion"].dropna().unique().tolist())
default_idx = 0 if champions else None
selected = st.sidebar.selectbox("Champion", champions, index=default_idx)

# ====== 본문 ======
st.title("ARAM PS Dashboard")
if not selected:
    st.info("좌측에서 챔피언을 선택해주세요.")
    st.stop()

# 상단 메트릭
agg = compute_champion_agg(df, selected)
m1, m2, m3 = st.columns(3)
m1.metric("Games", f"{agg['games']}")
m2.metric("Win Rate", f"{agg['winrate']}%")
m3.metric("Pick Rate", f"{agg['pickrate']}%")
st.markdown(f"### {selected}")

# 1) 추천 아이템 (챔피언별)
st.subheader("Recommended Items (Champion)")
items_champ = compute_item_stats_for_champion(df, selected).head(20)
if not items_champ.empty:
    st.dataframe(
        items_champ[["icon_url", "item", "total_picks", "wins", "win_rate"]],
        use_container_width=True,
        column_config={
            "icon_url": st.column_config.ImageColumn("아이콘", width="small"),
            "item": "아이템",
            "total_picks": "픽수",
            "wins": "승수",
            "win_rate": "승률(%)",
        },
    )
else:
    st.info("아이템 정보가 없습니다.")

# 2) 글로벌 아이템 요약 (선택 챔피언과 무관, 레퍼런스)
st.subheader("Global Item Summary")
if not item_sum_global.empty:
    st.dataframe(
        item_sum_global[["icon_url", "item", "total_picks", "wins", "win_rate"]].head(30),
        use_container_width=True,
        column_config={
            "icon_url": st.column_config.ImageColumn("아이콘", width="small"),
            "item": "아이템",
            "total_picks": "픽수",
            "wins": "승수",
            "win_rate": "승률(%)",
        },
    )
else:
    st.caption("item_summary_with_icons.csv 가 없어서 글로벌 요약은 건너뜀(챔피언별 표만 표기).")

# 3) 스펠 조합
st.subheader("Spell Combos")
sp = compute_spell_stats_for_champion(df, selected).head(10)
if not sp.empty:
    st.dataframe(
        sp[["spell1", "spell2", "games", "wins", "win_rate"]],
        use_container_width=True,
        column_config={"spell1": "스펠1", "spell2": "스펠2", "games": "게임수", "wins": "승수", "win_rate": "승률(%)"},
    )
else:
    st.info("스펠 정보가 없습니다.")

# 4) 룬 조합
st.subheader("Rune Combos")
ru = compute_rune_stats_for_champion(df, selected).head(10)
if not ru.empty:
    st.dataframe(
        ru[["rune_core", "rune_sub", "rune_shards", "games", "wins", "win_rate"]],
        use_container_width=True,
        column_config={
            "rune_core": "핵심룬",
            "rune_sub": "보조트리",
            "rune_shards": "파편",
            "games": "게임수",
            "wins": "승수",
            "win_rate": "승률(%)",
        },
    )
else:
    st.info("룬 정보가 없습니다.")

# 5) 선택 챔피언 원본 로우 확인
with st.expander("Raw rows (selected champion)"):
    st.dataframe(df[df["champion"] == selected], use_container_width=True)
