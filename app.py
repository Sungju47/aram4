# app.py — ARAM PS Dashboard (items + runes + spells with icons)
import os, re
import pandas as pd
import streamlit as st

st.set_page_config(page_title="ARAM PS Dashboard", layout="wide")

PLAYERS_CSV = "aram_participants_with_icons_superlight.csv"
ITEM_SUM_CSV = "item_summary_with_icons.csv"
CHAMP_ICON_CSV = "champion_icons.csv"
RUNE_ICON_CSV  = "rune_icons.csv"
SPELL_ICON_CSV = "spell_icons.csv"

# ---------- helpers ----------
def _norm(x:str)->str:
    if pd.isna(x): return ""
    return re.sub(r"\s+","",str(x)).lower()

@st.cache_data
def _load_two_col_map(path:str)->dict:
    """CSV의 앞 2개 컬럼을 (name, icon_url)로 보고 dict 반환. 파일없으면 {}"""
    if not os.path.exists(path):
        return {}
    df = pd.read_csv(path)
    if df.shape[1] < 2: return {}
    name_col, icon_col = df.columns[:2]
    return { _norm(n): u for n, u in zip(df[name_col].astype(str), df[icon_col]) if str(n).strip() }

# ---------- loaders ----------
@st.cache_data
def load_players(path:str)->pd.DataFrame:
    if not os.path.exists(path):
        st.error(f"`{path}` 가 없습니다.")
        st.stop()
    df = pd.read_csv(path)

    # win flag
    if "win_clean" not in df.columns:
        if "win" in df.columns:
            df["win_clean"] = df["win"].astype(str).str.lower().isin(["true","1","t","yes"]).astype(int)
        else:
            df["win_clean"] = 0

    # tidy item name columns
    for c in [c for c in df.columns if re.fullmatch(r"item[0-6]_name", c)]:
        df[c] = df[c].fillna("").astype(str).str.strip()

    # spell/rune text columns (있으면 정리)
    for c in ["spell1","spell2","spell1_name_fix","spell2_name_fix","rune_core","rune_sub"]:
        if c in df.columns: df[c] = df[c].fillna("").astype(str).str.strip()

    return df

@st.cache_data
def load_item_summary(path:str)->pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame()
    g = pd.read_csv(path)
    # 관용적 헤더 매핑
    rename = {}
    for c in g.columns:
        lc = c.lower()
        if lc == "item": rename[c] = "item"
        elif "icon" in lc: rename[c] = "icon_url"
        elif "pick" in lc: rename[c] = "total_picks"
        elif lc in ("wins","win","승수"): rename[c] = "wins"
        elif "rate" in lc or "승률" in lc: rename[c] = "win_rate"
    g = g.rename(columns=rename)
    return g

# ---------- load data ----------
df = load_players(PLAYERS_CSV)
item_sum = load_item_summary(ITEM_SUM_CSV)

champ_icon_map = _load_two_col_map(CHAMP_ICON_CSV)
rune_icon_map  = _load_two_col_map(RUNE_ICON_CSV)
spell_icon_map = _load_two_col_map(SPELL_ICON_CSV)

ITEM_ICON_MAP = {}
if not item_sum.empty and {"item","icon_url"}.issubset(item_sum.columns):
    ITEM_ICON_MAP = dict(zip(item_sum["item"], item_sum["icon_url"]))

# ---------- sidebar ----------
st.sidebar.title("ARAM PS Controls")
if "champion" not in df.columns:
    st.error("참가자 CSV에 `champion` 컬럼이 없습니다.")
    st.stop()
champions = sorted(df["champion"].dropna().unique().tolist())
selected = st.sidebar.selectbox("Champion", champions, index=0)

# ---------- summary ----------
dsel = df[df["champion"]==selected].copy()
games = len(dsel)
match_cnt   = dsel["matchId"].nunique() if "matchId" in dsel.columns else games
all_matches = df["matchId"].nunique()   if "matchId" in df.columns else len(df)
winrate  = round(dsel["win_clean"].mean()*100,2) if games else 0.0
pickrate = round(match_cnt / all_matches * 100,2) if all_matches else 0.0

st.title(selected)
ch_icon = champ_icon_map.get(_norm(selected), "")
if ch_icon: st.image(ch_icon, width=48)
c1,c2,c3 = st.columns(3)
c1.metric("Games", games)
c2.metric("Win Rate", f"{winrate}%")
c3.metric("Pick Rate", f"{pickrate}%")

# ---------- items ----------
st.subheader("Recommended Items")
item_cols = [c for c in dsel.columns if re.fullmatch(r"item[0-6]_name", c)]
if item_cols:
    stacks = []
    for c in item_cols:
        stacks.append(dsel[[c,"win_clean"]].rename(columns={c:"item"}))
    iu = pd.concat(stacks, ignore_index=True)
    iu = iu[iu["item"].astype(str).str.strip()!=""]
    top_items = (iu.groupby("item")
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
            "item":"아이템","total_picks":"픽수","wins":"승수","win_rate":"승률(%)",
        }
    )
else:
    st.info("아이템 이름 컬럼(item0_name ~ item6_name)이 없습니다.")

# ---------- spells (icons from spell_icons.csv) ----------
st.subheader("Recommended Spell Combos")

def choose_spell_cols(df_):
    if {"spell1_name_fix","spell2_name_fix"}.issubset(df_.columns):
        return "spell1_name_fix","spell2_name_fix"
    if {"spell1","spell2"}.issubset(df_.columns):
        return "spell1","spell2"
    # 마지막 fallback: 'spell'이름 포함된 아무 두 컬럼
    cands = [c for c in df_.columns if "spell" in c.lower()]
    if len(cands)>=2: return cands[0], cands[1]
    return None, None

s1_col, s2_col = choose_spell_cols(dsel)

def spell_icon(name:str)->str:
    return spell_icon_map.get(_norm(name), "") if name else ""

if games and s1_col and s2_col:
    sp = (dsel.groupby([s1_col, s2_col])
              .agg(games=("win_clean","count"), wins=("win_clean","sum"))
              .reset_index())
    sp["win_rate"] = (sp["wins"]/sp["games"]*100).round(2)
    sp = sp.sort_values(["games","win_rate"], ascending=[False,False]).head(10)
    sp["spell1_icon"] = sp[s1_col].apply(spell_icon)
    sp["spell2_icon"] = sp[s2_col].apply(spell_icon)
    st.dataframe(
        sp[["spell1_icon", s1_col, "spell2_icon", s2_col, "games", "wins", "win_rate"]],
        use_container_width=True,
        column_config={
            "spell1_icon": st.column_config.ImageColumn("스펠1", width="small"),
            "spell2_icon": st.column_config.ImageColumn("스펠2", width="small"),
            s1_col:"스펠1 이름", s2_col:"스펠2 이름",
            "games":"게임수","wins":"승수","win_rate":"승률(%)",
        }
    )
else:
    st.info("스펠 컬럼을 찾을 수 없어 텍스트 집계를 생략했습니다.")

# ---------- runes (always computed, with icons) ----------
st.subheader("Recommended Rune Combos")

def rune_icon(name:str)->str:
    return rune_icon_map.get(_norm(name), "") if name else ""

if {"rune_core","rune_sub"}.issubset(dsel.columns):
    ru = (dsel.groupby(["rune_core","rune_sub"])
             .agg(games=("win_clean","count"), wins=("win_clean","sum"))
             .reset_index())
    ru["win_rate"] = (ru["wins"]/ru["games"]*100).round(2)
    ru = ru.sort_values(["games","win_rate"], ascending=[False,False]).head(10)
    ru["rune_core_icon"] = ru["rune_core"].apply(rune_icon)
    ru["rune_sub_icon"]  = ru["rune_sub"].apply(rune_icon)
    st.dataframe(
        ru[["rune_core_icon","rune_core","rune_sub_icon","rune_sub","games","wins","win_rate"]],
        use_container_width=True,
        column_config={
            "rune_core_icon": st.column_config.ImageColumn("핵심룬", width="small"),
            "rune_sub_icon":  st.column_config.ImageColumn("보조트리", width="small"),
            "rune_core":"핵심룬 이름","rune_sub":"보조트리 이름",
            "games":"게임수","wins":"승수","win_rate":"승률(%)",
        }
    )
else:
    st.info("룬 컬럼(rune_core, rune_sub)이 없어 룬 집계를 표시하지 못했습니다.")

# ---------- raw ----------
with st.expander("Raw rows (selected champion)"):
    st.dataframe(dsel, use_container_width=True)
