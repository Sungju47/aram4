# app.py — ARAM 챔피언 대시보드 (아이콘: 챔피언/스펠/룬/아이템)
import os, re
import pandas as pd
import streamlit as st
st.set_page_config(page_title="ARAM PS Dashboard", layout="wide")
# ===== 파일 경로 =====
PLAYERS_CSV   = "aram_participants_with_icons_superlight.csv"  # 참가자 행 데이터(아이템 이름 등)
ITEM_SUM_CSV  = "item_summary_with_icons.csv"                  # 아이템 요약(item, icon_url, total_picks, wins, win_rate)
CHAMP_CSV     = "champion_icons.csv"                           # 최소: champion, champion_icon
RUNE_CSV      = "rune_icons.csv"                               # 예: rune_core, rune_core_icon, rune_sub, rune_sub_icon, (옵션: rune_shards_icons)
SPELL_CSV     = "spell_icons.csv"                              # 예: spell(또는 spell_name), icon_url  형태(유연 매핑)
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
    for c in ["spell1","spell2","rune_core","rune_sub","champion"]:
        if c in df.columns:
            df[c] = df[c].fillna("").astype(str).str.strip()
    return df
@st.cache_data
def load_item_summary(path: str) -> pd.DataFrame:
    if not _exists(path): return pd.DataFrame()
    g = pd.read_csv(path)
    # 기대 헤더
    need = {"item","icon_url","total_picks","wins","win_rate"}
    if not need.issubset(g.columns):
        st.warning(f"`{path}` 헤더 확인 필요 (기대: {sorted(need)}, 실제: {list(g.columns)})")
    if "item" in g.columns:
        g = g[g["item"].astype(str).str.strip()!=""]
    return g
@st.cache_data
def load_champion_icons(path: str) -> dict:
    """champion -> champion_icon"""
    if not _exists(path): return {}
    df = pd.read_csv(path)
    # 가능한 헤더 후보
    name_col = None
    for c in ["champion","Champion","championName"]:
        if c in df.columns: name_col = c; break
    icon_col = None
    for c in ["champion_icon","icon","icon_url"]:
        if c in df.columns: icon_col = c; break
    if not name_col or not icon_col: return {}
    df[name_col] = df[name_col].astype(str).str.strip()
    return dict(zip(df[name_col], df[icon_col]))
@st.cache_data
def load_rune_icons(path: str) -> dict:
    """반환: {'core':{name:icon}, 'sub':{name:icon}, 'shards':{name:icon}(옵션)}"""
    if not _exists(path): return {"core":{}, "sub":{}, "shards":{}}
    df = pd.read_csv(path)
    core_map, sub_map, shard_map = {}, {}, {}
    # core
    if "rune_core" in df.columns:
        icon_col = "rune_core_icon" if "rune_core_icon" in df.columns else None
        if icon_col:
            core_map = dict(zip(df["rune_core"].astype(str), df[icon_col].astype(str)))
    # sub
    if "rune_sub" in df.columns:
        icon_col = "rune_sub_icon" if "rune_sub_icon" in df.columns else None
        if icon_col:
            sub_map = dict(zip(df["rune_sub"].astype(str), df[icon_col].astype(str)))
    # shards(있을 수도/없을 수도)
    if "rune_shard" in df.columns:
        icon_col = "rune_shard_icon" if "rune_shard_icon" in df.columns else "rune_shards_icons" if "rune_shards_icons" in df.columns else None
        if icon_col:
            shard_map = dict(zip(df["rune_shard"].astype(str), df[icon_col].astype(str)))
    return {"core": core_map, "sub": sub_map, "shards": shard_map}
@st.cache_data
def load_spell_icons(path: str) -> dict:
    """스펠명 -> 아이콘 URL (대소문자/공백 무시)"""
    if not _exists(path): return {}
    df = pd.read_csv(path)
    # 가능한 헤더 자동 추론
    cand_name = [c for c in df.columns if _norm(c) in {"spell","spellname","name","spell1_name_fix","spell2_name_fix"}]
    cand_icon = [c for c in df.columns if _norm(c) in {"icon","icon_url","spell_icon"}]
    m = {}
    if cand_name and cand_icon:
        name_col, icon_col = cand_name[0], cand_icon[0]
        for n,i in zip(df[name_col].astype(str), df[icon_col].astype(str)):
            m[_norm(n)] = i
    else:
        # 2열짜리일 수도 있으니 첫 2열로 시도
        if df.shape[1] >= 2:
            m = { _norm(n):i for n,i in zip(df.iloc[:,0].astype(str), df.iloc[:,1].astype(str)) }
    return m
# ===== 데이터 로드 =====
df        = load_players(PLAYERS_CSV)
item_sum  = load_item_summary(ITEM_SUM_CSV)
champ_map = load_champion_icons(CHAMP_CSV)
rune_maps = load_rune_icons(RUNE_CSV)          # {'core':..., 'sub':..., 'shards':...}
spell_map = load_spell_icons(SPELL_CSV)         # norm(name) -> icon_url
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
    # 챔피언 아이콘
    cicon = champ_map.get(selected, "")
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
def _spell_icon(name:str)->str:
    if not name: return ""
    return spell_map.get(_norm(name), "")
if games and {"spell1","spell2"}.issubset(dsel.columns):
    sp = (dsel.groupby(["spell1","spell2"])
              .agg(games=("win_clean","count"), wins=("win_clean","sum"))
              .reset_index())
    sp["win_rate"] = (sp["wins"]/sp["games"]*100).round(2)
    sp = sp.sort_values(["games","win_rate"], ascending=[False,False]).head(10)
    sp["spell1_icon"] = sp["spell1"].apply(_spell_icon)
    sp["spell2_icon"] = sp["spell2"].apply(_spell_icon)
    st.dataframe(
        sp[["spell1_icon","spell1","spell2_icon","spell2","games","wins","win_rate"]],
        use_container_width=True,
        column_config={
            "spell1_icon": st.column_config.ImageColumn("스펠1", width="small"),
            "spell2_icon": st.column_config.ImageColumn("스펠2", width="small"),
            "spell1":"스펠1 이름","spell2":"스펠2 이름",
            "games":"게임수","wins":"승수","win_rate":"승률(%)"
        }
    )
else:
    st.info("스펠 컬럼(spell1, spell2)이 없습니다.")
# ===== 룬 추천 (아이콘 매핑: rune_icons.csv) =====
st.subheader("Recommended Rune Combos")
core_map = rune_maps.get("core",{})
sub_map  = rune_maps.get("sub",{})
def _rune_core_icon(name:str)->str: return core_map.get(name,"")
def _rune_sub_icon(name:str)->str:  return sub_map.get(name,"")
if games and {"rune_core","rune_sub"}.issubset(dsel.columns):
    ru = (dsel.groupby(["rune_core","rune_sub"])
              .agg(games=("win_clean","count"), wins=("win_clean","sum"))
              .reset_index())
    ru["win_rate"] = (ru["wins"]/ru["games"]*100).round(2)
    ru = ru.sort_values(["games","win_rate"], ascending=[False,False]).head(10)
    ru["rune_core_icon"] = ru["rune_core"].apply(_rune_core_icon)
    ru["rune_sub_icon"]  = ru["rune_sub"].apply(_rune_sub_icon)
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
