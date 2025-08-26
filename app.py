# app.py  — ARAM 챔피언 대시보드 (아이콘 표시 OK / GitHub-Streamlit 바로 실행용)
import os
import re
import pandas as pd
import streamlit as st

st.set_page_config(page_title="ARAM PS Dashboard", layout="wide")

# ── 파일 경로 ───────────────────────────────────────────
PLAYERS_CSV = "aram_participants_with_icons_superlight.csv"  # 참가자 데이터(아이템/스펠/룬 이름, 일부 아이콘 포함)
ITEM_SUM_CSV = "item_summary_with_icons.csv"                 # 아이템 요약(아이콘 포함) ← 헤더: item, icon_url, total_picks, wins, win_rate

# ── 로더 ────────────────────────────────────────────────
@st.cache_data
def load_players(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        st.error(f"`{path}` 파일이 리포지토리 루트에 없습니다.")
        st.stop()
    df = pd.read_csv(path)
    # 승패 플래그 통일
    if "win_clean" in df.columns:
        pass
    elif "win" in df.columns:
        df["win_clean"] = df["win"].astype(str).str.lower().isin(["true","1","t","yes"]).astype(int)
    else:
        df["win_clean"] = 0

    # 아이템 이름 칼럼 정규화
    item_name_cols = [c for c in df.columns if re.fullmatch(r"item[0-6]_name", c)]
    for c in item_name_cols:
        df[c] = df[c].fillna("").astype(str).str.strip()

    # 텍스트 스펠/룬 컬럼도 있으면 정리
    for c in ["spell1","spell2","rune_core","rune_sub"]:
        if c in df.columns:
            df[c] = df[c].fillna("").astype(str).str.strip()

    # 아이콘 컬럼 존재여부는 상황에 따라 다름(없어도 동작하게)
    return df

@st.cache_data
def load_item_summary(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        st.error(f"`{path}` 파일이 리포지토리 루트에 없습니다.")
        st.stop()
    g = pd.read_csv(path)
    # 기대 헤더: ['item','icon_url','total_picks','wins','win_rate']
    need = {"item","icon_url","total_picks","wins","win_rate"}
    miss = need - set(g.columns)
    if miss:
        st.error(f"`{path}` 헤더가 예상과 다릅니다. 누락: {sorted(miss)} / 실제: {list(g.columns)}")
        st.stop()
    # 빈/NaN 아이템 제거
    g = g[g["item"].astype(str).str.strip() != ""].copy()
    return g

# ── 데이터 로드 ─────────────────────────────────────────
df = load_players(PLAYERS_CSV)
item_sum = load_item_summary(ITEM_SUM_CSV)

# 아이템명 → 아이콘 빠른 매핑 dict (참고: 일부 항목은 아이콘이 없을 수 있음)
ICON_MAP = dict(zip(item_sum["item"], item_sum["icon_url"]))

# ── 사이드바 ───────────────────────────────────────────
st.sidebar.title("ARAM PS Controls")
champions = sorted(df["champion"].dropna().unique().tolist())
selected = st.sidebar.selectbox("Champion", champions, index=0)

# ── 상단 요약 ───────────────────────────────────────────
dsel = df[df["champion"] == selected].copy()
games = len(dsel)
match_cnt = dsel["matchId"].nunique() if "matchId" in dsel.columns else games
all_matches = df["matchId"].nunique() if "matchId" in df.columns else len(df)

winrate = round(dsel["win_clean"].mean()*100, 2) if games else 0.0
pickrate = round(match_cnt / all_matches * 100, 2) if all_matches else 0.0

st.title(f"{selected}")
c1, c2, c3 = st.columns(3)
c1.metric("Games", f"{games}")
c2.metric("Win Rate", f"{winrate}%")
c3.metric("Pick Rate", f"{pickrate}%")

# ── 아이템 추천 (선택 챔피언 기준 + 아이콘 표시) ─────────
st.subheader("Recommended Items")

# 선택 챔피언의 아이템 집계 (참가자 CSV에서 직접 계산)
item_name_cols = [c for c in dsel.columns if re.fullmatch(r"item[0-6]_name", c)]
if item_name_cols:
    stacks = []
    for c in item_name_cols:
        tmp = dsel[[c, "win_clean"]].rename(columns={c: "item"})
        stacks.append(tmp)
    iu = pd.concat(stacks, ignore_index=True)
    iu = iu[iu["item"].astype(str).str.strip() != ""]
    top_items = (iu.groupby("item")
                   .agg(total_picks=("item", "count"), wins=("win_clean","sum"))
                   .reset_index())
    top_items["win_rate"] = (top_items["wins"]/top_items["total_picks"]*100).round(2)
    # 아이콘 붙이기 (요약 CSV의 icon_url 기준)
    top_items["icon_url"] = top_items["item"].map(ICON_MAP)
    top_items = top_items.sort_values(["total_picks", "win_rate"], ascending=[False, False]).head(20)

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
    st.info("아이템 이름 컬럼(item0_name ~ item6_name)이 없어 챔피언별 집계를 표시할 수 없습니다.")

# ── 스펠 추천 (아이콘 있으면 아이콘 표기) ────────────────
st.subheader("Recommended Spell Combos")
spell_has_icon = {"spell1_icon","spell2_icon"}.issubset(dsel.columns)
spell_name_cols = {"spell1_name_fix","spell2_name_fix"} if {"spell1_name_fix","spell2_name_fix"}.issubset(dsel.columns) else {"spell1","spell2"}

if spell_has_icon and spell_name_cols.issubset(dsel.columns):
    sp = (dsel.groupby(["spell1_icon","spell2_icon", *spell_name_cols])
              .agg(games=("win_clean","count"), wins=("win_clean","sum"))
              .reset_index())
    sp["win_rate"] = (sp["wins"]/sp["games"]*100).round(2)
    sp = sp.sort_values(["games","win_rate"], ascending=[False,False]).head(10)
    vis_cols = ["spell1_icon","spell2_icon", *spell_name_cols, "games", "wins", "win_rate"]
    st.dataframe(
        sp[vis_cols],
        use_container_width=True,
        column_config={
            "spell1_icon": st.column_config.ImageColumn("스펠1", width="small"),
            "spell2_icon": st.column_config.ImageColumn("스펠2", width="small"),
            list(spell_name_cols)[0]: "스펠1 이름",
            list(spell_name_cols)[1]: "스펠2 이름",
            "games":"게임수","wins":"승수","win_rate":"승률(%)"
        }
    )
else:
    # 아이콘이 없으면 텍스트만
    if {"spell1","spell2"}.issubset(dsel.columns):
        sp = (dsel.groupby(["spell1","spell2"])
                  .agg(games=("win_clean","count"), wins=("win_clean","sum"))
                  .reset_index())
        sp["win_rate"] = (sp["wins"]/sp["games"]*100).round(2)
        sp = sp.sort_values(["games","win_rate"], ascending=[False,False]).head(10)
        st.dataframe(sp, use_container_width=True)
    else:
        st.info("스펠 관련 컬럼이 없습니다.")

# ── 룬 추천 (아이콘 있으면 아이콘 표기) ──────────────────
st.subheader("Recommended Rune Combos")
rune_has_icon = {"rune_core_icon","rune_sub_icon"}.issubset(dsel.columns)
if rune_has_icon and {"rune_core","rune_sub"}.issubset(dsel.columns):
    ru = (dsel.groupby(["rune_core_icon","rune_core","rune_sub_icon","rune_sub"])
             .agg(games=("win_clean","count"), wins=("win_clean","sum"))
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
    if {"rune_core","rune_sub"}.issubset(dsel.columns):
        ru = (dsel.groupby(["rune_core","rune_sub"])
                 .agg(games=("win_clean","count"), wins=("win_clean","sum"))
                 .reset_index())
        ru["win_rate"] = (ru["wins"]/ru["games"]*100).round(2)
        ru = ru.sort_values(["games","win_rate"], ascending=[False,False]).head(10)
        st.dataframe(ru, use_container_width=True)
    else:
        st.info("룬 관련 컬럼이 없습니다.")

# ── 원본(선택 챔피언) ─────────────────────────────────────
with st.expander("Raw rows (selected champion)"):
    st.dataframe(dsel, use_container_width=True)
