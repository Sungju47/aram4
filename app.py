# app.py  (Streamlit Cloud / GitHub 바로 실행용)
# -------------------------------------------------
import os, re
import pandas as pd
import streamlit as st

st.set_page_config(page_title="ARAM PS Dashboard", layout="wide")

# ====== 파일 경로 (리포 루트 그대로) ======
PLAYERS_CSV = "aram_participants_with_icons.csv"          # 1단계에서 만든 파일
ITEM_SUM_CSV = "item_summary_with_icons.csv"              # 1단계에서 만든 파일 (없으면 런타임 계산)

# ====== 로딩 ======
@st.cache_data
def load_players(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    # 승패 플래그
    if "win" in df.columns:
        df["win_clean"] = df["win"].astype(str).str.lower().isin(["true","1","t","yes"]).astype(int)
    elif "win_clean" not in df.columns:
        df["win_clean"] = 0
    # 문자열 정리
    for c in [c for c in df.columns if c.startswith("item") and c.endswith("_name")]:
        df[c] = df[c].fillna("").astype(str).str.strip()
    return df

@st.cache_data
def load_item_summary(path: str, df: pd.DataFrame|None) -> pd.DataFrame:
    if os.path.exists(path):
        return pd.read_csv(path)
    # 없으면 런타임 계산(아이콘 컬럼이 있어야 함)
    item_cols = [c for c in df.columns if re.fullmatch(r"item[0-6]_name", c)]
    stacks = []
    for base in [c.replace("_name","") for c in item_cols]:
        tmp = df[[f"{base}_name", f"{base}_icon", "matchId", "win_clean"]].rename(
            columns={f"{base}_name":"item", f"{base}_icon":"icon_url"}
        )
        stacks.append(tmp)
    u = pd.concat(stacks, ignore_index=True)
    u = u[u["item"].astype(str).str.len() > 0]
    g = (u.groupby(["item","icon_url"])
           .agg(total_picks=("matchId","count"), wins=("win_clean","sum"))
           .reset_index())
    g["win_rate"] = (g["wins"]/g["total_picks"]*100).round(2)
    g = g.sort_values(["total_picks","win_rate"], ascending=[False, False])
    return g

# ====== 데이터 로드 ======
if not os.path.exists(PLAYERS_CSV):
    st.error(f"`{PLAYERS_CSV}` 파일이 리포지토리 루트에 없습니다.")
    st.stop()

df = load_players(PLAYERS_CSV)
item_sum = load_item_summary(ITEM_SUM_CSV, df)

# ====== 사이드바 ======
st.sidebar.title("ARAM PS Controls")
champions = sorted(df["champion"].dropna().unique().tolist())
selected = st.sidebar.selectbox("Champion", champions, index=0)

# ====== 상단 요약 ======
dsel = df[df["champion"] == selected].copy()
match_cnt = dsel["matchId"].nunique()
games = len(dsel)
winrate = round(dsel["win_clean"].mean()*100, 2) if games else 0.0
pickrate = round(games / df["matchId"].nunique() * 100, 2) if games else 0.0

c1,c2,c3 = st.columns(3)
c1.metric("Games", f"{games}")
c2.metric("Win Rate", f"{winrate}%")
c3.metric("Pick Rate", f"{pickrate}%")

st.markdown(f"### {selected}")

# ====== 아이템 추천(아이콘 표시) ======
st.subheader("Recommended Items")
item_filter = item_sum.merge(
    dsel[["matchId"]].drop_duplicates().assign(_flag=1), on="matchId", how="left"
) if "matchId" in item_sum.columns else item_sum

top_items = item_sum[item_sum["item"].notna()].copy()
top_items = top_items.sort_values(["total_picks","win_rate"], ascending=[False, False]).head(20)

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

# ====== 스펠 추천 ======
st.subheader("Recommended Spell Combos")
if {"spell1_icon","spell2_icon"}.issubset(dsel.columns):
    sp = (dsel.groupby(["spell1_icon","spell1_name_fix","spell2_icon","spell2_name_fix"])
              .agg(games=("matchId","count"), wins=("win_clean","sum"))
              .reset_index())
    sp["win_rate"] = (sp["wins"]/sp["games"]*100).round(2)
    sp = sp.sort_values(["games","win_rate"], ascending=[False,False]).head(10)
    st.dataframe(
        sp[["spell1_icon","spell1_name_fix","spell2_icon","spell2_name_fix","games","wins","win_rate"]],
        use_container_width=True,
        column_config={
            "spell1_icon": st.column_config.ImageColumn("스펠1", width="small"),
            "spell2_icon": st.column_config.ImageColumn("스펠2", width="small"),
            "spell1_name_fix": "스펠1 이름",
            "spell2_name_fix": "스펠2 이름",
            "games": "게임수", "wins":"승수", "win_rate":"승률(%)"
        }
    )
else:
    st.info("스펠 아이콘 컬럼이 없습니다(사전 매핑 CSV 필요).")

# ====== 룬 조합 ======
st.subheader("Recommended Rune Combos")
cols_needed = {"rune_core","rune_core_icon","rune_sub","rune_sub_icon"}
if cols_needed.issubset(dsel.columns):
    ru = (dsel.groupby(["rune_core_icon","rune_core","rune_sub_icon","rune_sub"])
             .agg(games=("matchId","count"), wins=("win_clean","sum"))
             .reset_index())
    ru["win_rate"] = (ru["wins"]/ru["games"]*100).round(2)
    ru = ru.sort_values(["games","win_rate"], ascending=[False,False]).head(10)
    st.dataframe(
        ru[["rune_core_icon","rune_core","rune_sub_icon","rune_sub","games","wins","win_rate"]],
        use_container_width=True,
        column_config={
            "rune_core_icon": st.column_config.ImageColumn("핵심룬", width="small"),
            "rune_sub_icon":  st.column_config.ImageColumn("보조트리", width="small"),
            "rune_core":"핵심룬 이름","rune_sub":"보조트리 이름",
            "games":"게임수","wins":"승수","win_rate":"승률(%)"
        }
    )
else:
    st.info("룬 아이콘 컬럼이 없습니다(사전 매핑 CSV 필요).")

# ====== 원본(선택 챔피언) ======
with st.expander("Raw rows (selected champion)"):
    st.dataframe(dsel, use_container_width=True)
