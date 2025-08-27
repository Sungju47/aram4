# app.py — ARAM 챔피언 대시보드 (아이콘: 챔피언/스펠/룬/아이템)
import os, re
import pandas as pd
import streamlit as st

st.set_page_config(page_title="ARAM PS Dashboard", layout="wide")

# ===== 파일 경로 =====
PLAYERS_CSV   = "aram_participants_with_icons_superlight.csv"  # 참가자 행 데이터
ITEM_SUM_CSV  = "item_summary_with_icons.csv"                  # item, icon_url, total_picks, wins, win_rate
CHAMP_CSV     = "champion_icons.csv"                           # (이름, 아이콘URL) 2열 가능
RUNE_CSV      = "rune_icons.csv"                               # (이름, 아이콘URL) 2열 가능도 OK
SPELL_CSV     = "spell_icons.csv"                              # (이름, 아이콘URL) 2열 가능

# ===== 유틸 =====
def _exists(path:str)->bool:
    ok = os.path.exists(path)
    if not ok: st.warning(f"파일 없음: `{path}`")
    return ok

def _norm(x:str)->str:
    return re.sub(r"\s+","", str(x)).strip().lower()

# ===== 데이터 로더 =====
@st.cache_data
def load_players(path: str) -> pd.DataFrame:
    if not _exists(path): st.stop()
    df = pd.read_csv(path)
    # 승패 정리
    if "win_clean" not in df.columns:
        if "win" in df.columns:
            df["win_clean"] = df["win"].astype(str).str.lower().isin(["true","1","t","yes"]).astype(int)
        else:
            df["win_clean"] = 0
    # 아이템 이름 칼럼 정리
    for c in [c for c in df.columns if re.fullmatch(r"item[0-6]_name", c)]:
        df[c] = df[c].fillna("").astype(str).str.strip()
    # 기본 텍스트 컬럼 정리
    for c in ["spell1","spell2","spell1_name_fix","spell2_name_fix","rune_core","rune_sub","champion"]:
        if c in df.columns:
            df[c] = df[c].fillna("").astype(str).str.strip()
    return df

@st.cache_data
def load_item_summary(path: str) -> pd.DataFrame:
    if not _exists(path): return pd.DataFrame()
    g = pd.read_csv(path)
    need = {"item","icon_url","total_picks","wins","win_rate"}
    if not need.issubset(g.columns):
        st.warning(f"`{path}` 헤더 확인 필요 (기대: {sorted(need)}, 실제: {list(g.columns)})")
    if "item" in g.columns:
        g = g[g["item"].astype(str).str.strip()!=""]
    return g

@st.cache_data
def load_two_col_map(path: str) -> dict:
    """2열 CSV를 (이름 → 아이콘URL) dict로 읽음. 헤더명 자유."""
    if not _exists(path): return {}
    df = pd.read_csv(path)
    if df.shape[1] < 2: return {}
    name_col, icon_col = df.columns[:2]
    return { str(n).strip(): str(u).strip() for n,u in zip(df[name_col], df[icon_col]) if str(n).strip() }

# ===== 데이터 로드 =====
df        = load_players(PLAYERS_CSV)
item_sum  = load_item_summary(ITEM_SUM_CSV)
champ_map = load_two_col_map(CHAMP_CSV)          # champion -> icon
rune_map  = load_two_col_map(RUNE_CSV)           # rune_name -> icon
spell_map = load_two_col_map(SPELL_CSV)          # spell_name -> icon

# 아이템: 이름 -> 아이콘
ITEM_ICON_MAP = dict(zip(item_sum.get("item",[]), item_sum.get("icon_url",[])))

# ===== 사이드바 =====
st.sidebar.title("ARAM PS Controls")
champs = sorted(df["champion"].dropna().unique().tolist()) if "champion" in df.columns else []
selected = st.sidebar.selectbox("Champion", champs, index=0 if champs else None)

# ===== 상단 요약 =====
dsel = df[df["champion"]==selected].copy() if len(champs) else df.head(0).copy()
games = len(dsel)
match_cnt_all = df["matchId"].nunique() if "matchId" in df.columns else len(df)
match_cnt_sel = dsel["matchId"].nunique() if "matchId" in dsel.columns else games
winrate = round(dsel["win_clean"].mean()*100,2) if games else 0.0
pickrate = round((match_cnt_sel / match_cnt_all * 100),2) if match_cnt_all else 0.0

title_cols = st.columns([1,5])
with title_cols[0]:
    cicon = champ_map.get(selected, "") or champ_map.get(selected.capitalize(), "")
    if cicon:
        st.image(cicon, width=64)
with title_cols[1]:
    st.title(f"{selected}")

c1,c2,c3 = st.columns(3)
c1.metric("Games", f"{games}")
c2.metric("Win Rate", f"{winrate}%")
c3.metric("Pick Rate", f"{pickrate}%")

# ===== 아이템 추천 =====
st.subheader("Recommended Items")
if games and any(re.fullmatch(r"item[0-6]_name", c) for c in dsel.columns):
    stacks=[]
    for c in [c for c in dsel.columns if re.fullmatch(r"item[0-6]_name", c)]:
        stacks.append(dsel[[c,"win_clean"]].rename(columns={c:"item"}))
    union = pd.concat(stacks, ignore_index=True)
    union = union[union["item"].astype(str).str.strip()!=""]
    top_items = (union.groupby("item")
                        .agg(total_picks=("item","count"), wins=("win_clean","sum"))
                        .reset_index())
    top_items["win_rate"] = (top_items["wins"]/top_items["total_picks"]*100).round(2)
    top_items["icon_url"] = top_items["item"].map(ITEM_ICON_MAP)
    top_items = top_items.sort_values(["total_picks","win_rate"], ascending=[False,False]).head(20)

    st.dataframe(
        top_items[["icon_url","item","total_picks","wins","win_rate"]],
        use_container_width=True,
        column_config={
            "icon_url": st.column_config.ImageColumn("아이콘", width="small"),
            "item":"아이템","total_picks":"픽수","wins":"승수","win_rate":"승률(%)"
        }
    )
else:
    st.info("아이템 이름 컬럼(item0_name~item6_name)이 없어 챔피언별 아이템 추천 집계를 만들 수 없습니다.")

# ===== 스펠 추천 (아이콘 매핑: spell_icons.csv) =====
st.subheader("Recommended Spell Combos")

def _pick_spell_cols(df_):
    """우선순위: spell1_name_fix/spell2_name_fix → spell1/spell2 → 'spell' 포함 임의 2개"""
    if {"spell1_name_fix","spell2_name_fix"}.issubset(df_.columns):
        return "spell1_name_fix","spell2_name_fix"
    if {"spell1","spell2"}.issubset(df_.columns):
        return "spell1","spell2"
    cands = [c for c in df_.columns if "spell" in c.lower()]
    if len(cands) >= 2:
        return cands[0], cands[1]
    return None, None

def _spell_icon(name:str)->str:
    if not name: return ""
    # 공백/대소문자 차이 흡수
    return spell_map.get(name, "") or spell_map.get(name.capitalize(), "") or spell_map.get(name.upper(), "") or spell_map.get(name.lower(), "") or spell_map.get(re.sub(r"\s+","",str(name)).lower(), "")

s1, s2 = _pick_spell_cols(dsel)

if games and s1 and s2:
    sp = (dsel.groupby([s1, s2])
              .agg(games=("win_clean","count"), wins=("win_clean","sum"))
              .reset_index())
    sp["win_rate"] = (sp["wins"]/sp["games"]*100).round(2)
    sp = sp.sort_values(["games","win_rate"], ascending=[False,False]).head(10)
    sp["spell1_icon"] = sp[s1].apply(_spell_icon)
    sp["spell2_icon"] = sp[s2].apply(_spell_icon)

    st.dataframe(
        sp[["spell1_icon", s1, "spell2_icon", s2, "games", "wins", "win_rate"]],
        use_container_width=True,
        column_config={
            "spell1_icon": st.column_config.ImageColumn("스펠1", width="small"),
            "spell2_icon": st.column_config.ImageColumn("스펠2", width="small"),
            s1:"스펠1 이름", s2:"스펠2 이름",
            "games":"게임수","wins":"승수","win_rate":"승률(%)"
        }
    )
else:
    st.info("스펠 컬럼을 찾지 못했습니다. (spell1_name_fix/spell2_name_fix 또는 spell1/spell2 필요)")

# ===== 룬 추천 (아이콘 매핑: rune_icons.csv) =====
st.subheader("Recommended Rune Combos")

def _rune_icon(name:str)->str:
    if not name: return ""
    return rune_map.get(name, "") or rune_map.get(name.capitalize(), "") or rune_map.get(name.lower(), "") or rune_map.get(_norm(name), "")

if games and {"rune_core","rune_sub"}.issubset(dsel.columns):
    ru = (dsel.groupby(["rune_core","rune_sub"])
              .agg(games=("win_clean","count"), wins=("win_clean","sum"))
              .reset_index())
    ru["win_rate"] = (ru["wins"]/ru["games"]*100).round(2)
    ru = ru.sort_values(["games","win_rate"], ascending=[False,False]).head(10)
    ru["rune_core_icon"] = ru["rune_core"].apply(_rune_icon)
    ru["rune_sub_icon"]  = ru["rune_sub"].apply(_rune_icon)

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
    st.info("룬 컬럼(rune_core, rune_sub)이 없습니다.")

# ===== 원본 행 보기 =====
with st.expander("Raw rows (selected champion)"):
    st.dataframe(dsel, use_container_width=True)
