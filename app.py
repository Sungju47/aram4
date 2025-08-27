# app.py — ARAM PS Dashboard (icons for items / spells / runes / champion)
# ------------------------------------------------------------------------
import os
import re
import pandas as pd
import streamlit as st

st.set_page_config(page_title="ARAM PS Dashboard", layout="wide")

# ---------- File paths (repo root) ----------
PLAYERS_CSV = "aram_participants_with_icons_superlight.csv"  # participants with names (items/spells/runes), some icons ok
ITEM_SUM_CSV = "item_summary_with_icons.csv"                  # item, icon_url, total_picks, wins, win_rate

CHAMP_ICON_CSV = "champion_icons.csv"   # 2 cols: name, icon_url (header 자유)
RUNE_ICON_CSV  = "rune_icons.csv"       # 2 cols: name, icon_url (header 자유)
SPELL_ICON_CSV = "spell_icons.csv"      # 2 cols: name, icon_url (header 자유)

# ---------- Small helpers ----------
def _norm(s: str) -> str:
    """normalize korean/english labels for mapping"""
    if pd.isna(s):
        return ""
    return re.sub(r"\s+", "", str(s)).lower()

@st.cache_data
def _load_any_two_col_csv(path: str) -> dict:
    """
    Read CSV and return { normalized_name : icon_url }.
    Works even if header names differ; uses first 2 columns.
    """
    if not os.path.exists(path):
        return {}
    df = pd.read_csv(path)
    if df.shape[1] < 2:
        return {}
    name_col = df.columns[0]
    icon_col = df.columns[1]
    df[name_col] = df[name_col].astype(str)
    return { _norm(n): u for n, u in zip(df[name_col], df[icon_col]) if str(n).strip() }

# ---------- Loaders ----------
@st.cache_data
def load_players(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        st.error(f"`{path}` 파일이 리포지토리 루트에 없습니다.")
        st.stop()
    df = pd.read_csv(path)

    # unify win flag
    if "win_clean" not in df.columns:
        if "win" in df.columns:
            df["win_clean"] = df["win"].astype(str).str.lower().isin(["true","1","t","yes"]).astype(int)
        else:
            df["win_clean"] = 0

    # tidy item name columns
    for c in [c for c in df.columns if re.fullmatch(r"item[0-6]_name", c)]:
        df[c] = df[c].fillna("").astype(str).str.strip()

    # optional spell/rune text columns
    for c in ["spell1","spell2","spell1_name_fix","spell2_name_fix","rune_core","rune_sub"]:
        if c in df.columns:
            df[c] = df[c].fillna("").astype(str).str.strip()

    return df

@st.cache_data
def load_item_summary(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame()
    g = pd.read_csv(path)
    # expected: item, icon_url, total_picks, wins, win_rate (header can be slightly different but we try to map)
    cols = {c.lower(): c for c in g.columns}
    need = ["item","icon_url","total_picks","wins","win_rate"]
    if not all(n in cols for n in need):
        # try to guess
        rename = {}
        for c in g.columns:
            lc = c.lower()
            if "item" == lc:
                rename[c] = "item"
            elif "icon" in lc:
                rename[c] = "icon_url"
            elif "pick" in lc:
                rename[c] = "total_picks"
            elif lc in ("wins","win","승수"):
                rename[c] = "wins"
            elif "rate" in lc or "승률" in lc:
                rename[c] = "win_rate"
        if rename:
            g = g.rename(columns=rename)
    return g

# ---------- Data load ----------
df = load_players(PLAYERS_CSV)
item_sum = load_item_summary(ITEM_SUM_CSV)

# icon dicts
champ_icon_map = _load_any_two_col_csv(CHAMP_ICON_CSV)
rune_icon_map  = _load_any_two_col_csv(RUNE_ICON_CSV)
spell_icon_map = _load_any_two_col_csv(SPELL_ICON_CSV)

# item icon mapping from item summary
ITEM_ICON_MAP = {}
if not item_sum.empty and {"item","icon_url"}.issubset(item_sum.columns):
    ITEM_ICON_MAP = dict(zip(item_sum["item"], item_sum["icon_url"]))

# ---------- Sidebar ----------
st.sidebar.title("ARAM PS Controls")
champions = sorted(df["champion"].dropna().unique().tolist()) if "champion" in df.columns else []
if not champions:
    st.error("참가자 CSV에 `champion` 컬럼이 없습니다.")
    st.stop()

selected = st.sidebar.selectbox("Champion", champions, index=0)

# ---------- Header & summary ----------
dsel = df[df["champion"] == selected].copy()
games = len(dsel)
match_cnt = dsel["matchId"].nunique() if "matchId" in dsel.columns else games
all_matches = df["matchId"].nunique() if "matchId" in df.columns else len(df)

winrate = round(dsel["win_clean"].mean()*100, 2) if games else 0.0
pickrate = round(match_cnt / all_matches * 100, 2) if all_matches else 0.0

# title with champion icon if present
st.title(f"{selected}")
ch_icon = champ_icon_map.get(_norm(selected), "")
if ch_icon:
    st.image(ch_icon, width=48)
c1, c2, c3 = st.columns(3)
c1.metric("Games", f"{games}")
c2.metric("Win Rate", f"{winrate}%")
c3.metric("Pick Rate", f"{pickrate}%")

# ---------- Recommended Items (per selected champion) ----------
st.subheader("Recommended Items")
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
    top_items["icon_url"] = top_items["item"].map(ITEM_ICON_MAP)
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
else:
    st.info("아이템 이름 컬럼(item0_name ~ item6_name)이 없어 챔피언별 집계를 표시할 수 없습니다.")

# ---------- Recommended Spell Combos (flexible column names + icons) ----------
st.subheader("Recommended Spell Combos")

def pick_spell_cols(df_):
    if {"spell1","spell2"}.issubset(df_.columns):
        return "spell1","spell2","스펠1 이름","스펠2 이름"
    if {"spell1_name_fix","spell2_name_fix"}.issubset(df_.columns):
        return "spell1_name_fix","spell2_name_fix","스펠1 이름","스펠2 이름"
    cands = [c for c in df_.columns if "spell" in c.lower()]
    s1 = next((c for c in cands if "1" in c), None)
    s2 = next((c for c in cands if "2" in c), None)
    return s1, s2, s1 or "스펠1", s2 or "스펠2"

scol1, scol2, s1_label, s2_label = pick_spell_cols(dsel)

def _spell_icon(name: str) -> str:
    if not name: return ""
    return spell_icon_map.get(_norm(name), "")

if games and scol1 and scol2:
    sp = (dsel.groupby([scol1, scol2])
              .agg(games=("win_clean","count"), wins=("win_clean","sum"))
              .reset_index())
    sp["win_rate"] = (sp["wins"]/sp["games"]*100).round(2)
    sp = sp.sort_values(["games","win_rate"], ascending=[False, False]).head(10)
    sp["spell1_icon"] = sp[scol1].apply(_spell_icon)
    sp["spell2_icon"] = sp[scol2].apply(_spell_icon)

    st.dataframe(
        sp[["spell1_icon", scol1, "spell2_icon", scol2, "games", "wins", "win_rate"]],
        use_container_width=True,
        column_config={
            "spell1_icon": st.column_config.ImageColumn("스펠1", width="small"),
            "spell2_icon": st.column_config.ImageColumn("스펠2", width="small"),
            scol1: s1_label, scol2: s2_label,
            "games":"게임수","wins":"승수","win_rate":"승률(%)"
        }
    )
else:
    st.info("스펠 컬럼을 찾을 수 없습니다. (예: spell1/spell2 또는 spell1_name_fix/spell2_name_fix)")

# ---------- Recommended Rune Combos (icons) ----------
st.subheader("Recommended Rune Combos")

def _rune_icon(name: str) -> str:
    if not name: return ""
    return rune_icon_map.get(_norm(name), "")

if {"rune_core","rune_sub"}.issubset(dsel.columns):
    ru = (dsel.groupby(["rune_core","rune_sub"])
             .agg(games=("win_clean","count"), wins=("win_clean","sum"))
             .reset_index())
    ru["win_rate"] = (ru["wins"]/ru["games"]*100).round(2)
    ru = ru.sort_values(["games","win_rate"], ascending=[False, False]).head(10)
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
    st.info("룬 관련 컬럼(rune_core, rune_sub)이 없습니다.")

# ---------- Raw table ----------
with st.expander("Raw rows (selected champion)"):
    st.dataframe(dsel, use_container_width=True)
