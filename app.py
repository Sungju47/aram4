# app.py — ARAM PS Dashboard (Champion-centric) + 아이콘 표시
import os, glob, ast, requests
from typing import Optional, List, Dict, Any
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px

st.set_page_config(page_title="ARAM PS Dashboard", layout="wide")

# -------------------- 파일 탐색 --------------------
CANDIDATES = [
    "aram_participants_with_full_runes_merged_plus.csv",
    "aram_participants_with_full_runes_merged.csv",
    "aram_participants_with_full_runes.csv",
    "aram_participants_clean_preprocessed.csv",
    "aram_participants_clean_no_dupe_items.csv",
    "aram_participants_with_items.csv",
]
def discover_csv() -> Optional[str]:
    for name in CANDIDATES:
        if os.path.exists(name): return name
    hits = sorted(glob.glob("*.csv"))
    return hits[0] if hits else None

# -------------------- Data Dragon(아이콘/메타) --------------------
DD_BASE = "https://ddragon.leagueoflegends.com"
@st.cache_data(show_spinner=False)
def dd_versions() -> List[str]:
    r = requests.get(f"{DD_BASE}/api/versions.json", timeout=10)
    r.raise_for_status()
    return r.json()

@st.cache_data(show_spinner=False)
def dd_catalog() -> Dict[str, Any]:
    ver = dd_versions()[0]  # 최신 버전
    # items (name -> id)
    items = requests.get(f"{DD_BASE}/cdn/{ver}/data/ko_KR/item.json", timeout=10).json()["data"]
    item_by_name = {}
    for iid, meta in items.items():
        nm = str(meta.get("name","")).strip()
        if nm: item_by_name.setdefault(nm, str(iid))
    # spells (name -> image.full)
    spells = requests.get(f"{DD_BASE}/cdn/{ver}/data/ko_KR/summoner.json", timeout=10).json()["data"]
    spell_by_name = {}
    for key, meta in spells.items():
        nm = str(meta.get("name","")).strip()
        img = meta.get("image",{}).get("full","")
        if nm and img: spell_by_name.setdefault(nm, img)
    # champs(영문키 -> png), 영문명으로 파일명 매칭
    champs = requests.get(f"{DD_BASE}/cdn/{ver}/data/en_US/champion.json", timeout=10).json()["data"]
    champ_png = { key: f"{DD_BASE}/cdn/{ver}/img/champion/{key}.png" for key in champs.keys() }
    # runes (name -> icon path under /cdn/img/)
    runes = requests.get(f"{DD_BASE}/cdn/{ver}/data/ko_KR/runesReforged.json", timeout=10).json()
    rune_icon_by_name = {}
    def walk_runes(tree):
        name = tree.get("name")
        icon = tree.get("icon")  # e.g. "perk-images/Styles/Precision/Precision.png"
        if name and icon:
            rune_icon_by_name.setdefault(name, f"{DD_BASE}/cdn/img/{icon}")
        for s in tree.get("slots", []):
            for r in s.get("runes", []):
                rn, ic = r.get("name"), r.get("icon")
                if rn and ic:
                    rune_icon_by_name.setdefault(rn, f"{DD_BASE}/cdn/img/{ic}")
    for t in runes: walk_runes(t)
    return {"ver": ver, "item_by_name": item_by_name, "spell_by_name": spell_by_name,
            "champ_png": champ_png, "rune_icon_by_name": rune_icon_by_name}

def champ_icon_url(champ_en: str) -> Optional[str]:
    cat = dd_catalog()
    return cat["champ_png"].get(str(champ_en), None)

def item_icon_url(item_name: str) -> Optional[str]:
    if not item_name: return None
    cat = dd_catalog()
    iid = cat["item_by_name"].get(str(item_name).strip())
    if not iid: return None
    return f"{DD_BASE}/cdn/{dd_catalog()['ver']}/img/item/{iid}.png"

def spell_icon_url(spell_kor_name: str) -> Optional[str]:
    if not spell_kor_name: return None
    img = dd_catalog()["spell_by_name"].get(str(spell_kor_name).strip())
    return f"{DD_BASE}/cdn/{dd_catalog()['ver']}/img/spell/{img}" if img else None

def rune_icon_url(rune_name_kor: str) -> Optional[str]:
    if not rune_name_kor: return None
    return dd_catalog()["rune_icon_by_name"].get(str(rune_name_kor).strip())

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

# -------------------- 로딩 --------------------
@st.cache_data(show_spinner=False)
def load_df(src) -> pd.DataFrame:
    df = pd.read_csv(src)
    df["win_clean"] = df["win"].apply(_yes) if "win" in df.columns else 0
    s1 = "spell1_name" if "spell1_name" in df.columns else ("spell1" if "spell1" in df.columns else None)
    s2 = "spell2_name" if "spell2_name" in df.columns else ("spell2" if "spell2" in df.columns else None)
    df["spell1_final"] = df[s1].astype(str) if s1 else ""
    df["spell2_final"] = df[s2].astype(str) if s2 else ""
    df["spell_combo"]  = (df["spell1_final"] + " + " + df["spell2_final"]).str.strip()
    for c in [c for c in df.columns if c.startswith("item")]:
        df[c] = df[c].fillna("").astype(str).str.strip()
    for col in ("team_champs","enemy_champs"):
        if col in df.columns: df[col] = df[col].apply(_as_list)
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
    return df

# -------------------- 파일 선택 UI --------------------
st.sidebar.title("데이터")
auto_path = discover_csv()
st.sidebar.write("🔎 자동 검색:", auto_path if auto_path else "없음")
uploaded = st.sidebar.file_uploader("CSV 업로드(선택)", type=["csv"])
if uploaded is not None: df = load_df(uploaded)
elif auto_path is not None: df = load_df(auto_path)
else:
    st.error("CSV를 찾지 못했습니다. 레포 루트에 파일을 넣거나 업로드하세요.")
    st.stop()

# -------------------- 필터 --------------------
st.sidebar.markdown("---")
if "champion" not in df.columns:
    st.error("CSV에 'champion' 컬럼이 없습니다."); st.stop()
champions = sorted(df["champion"].dropna().unique().tolist())
sel_champ = st.sidebar.selectbox("챔피언 선택", champions)

# -------------------- 상단 지표 + 챔피언 아이콘 --------------------
dfc = df[df["champion"]==sel_champ].copy()
total_matches = df["matchId"].nunique() if "matchId" in df.columns else len(dfc)
games = len(dfc)
winrate = round(dfc["win_clean"].mean()*100,2) if games else 0.0
pickrate = round(games / max(1,total_matches) * 100, 2)
avg_k = round(dfc["kills"].mean(),2) if "kills" in dfc else 0
avg_d = round(dfc["deaths"].mean(),2) if "deaths" in dfc else 0
avg_a = round(dfc["assists"].mean(),2) if "assists" in dfc else 0
avg_kda = round(dfc["kda"].mean(),2) if "kda" in dfc else 0
avg_dpm = round(dfc["dpm"].mean(),1) if "dpm" in dfc else 0

icon_url = champ_icon_url(sel_champ)
left, mid = st.columns([1,5])
with left:
    if icon_url:
        st.image(icon_url, width=88)
with mid:
    st.title(f"ARAM Dashboard — {sel_champ}")
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("게임 수", games)
    m2.metric("승률(%)", winrate)
    m3.metric("픽률(%)", pickrate)
    m4.metric("평균 K/D/A", f"{avg_k}/{avg_d}/{avg_a}")
    m5.metric("평균 DPM", avg_dpm)

# -------------------- 타임라인(있으면) --------------------
tl_cols = ["first_blood_min","blue_first_tower_min","red_first_tower_min","game_end_min","gold_spike_min"]
if any(c in dfc.columns for c in tl_cols):
    st.subheader("타임라인 요약")
    t1, t2, t3 = st.columns(3)
    if "first_blood_min" in dfc and dfc["first_blood_min"].notna().any():
        t1.metric("퍼블 평균(분)", round(dfc["first_blood_min"].mean(),2))
    if ("blue_first_tower_min" in dfc) or ("red_first_tower_min" in dfc):
        bt = round(dfc["blue_first_tower_min"].dropna().mean(),2) if "blue_first_tower_min" in dfc else np.nan
        rt = round(dfc["red_first_tower_min"].dropna().mean(),2) if "red_first_tower_min" in dfc else np.nan
        t2.metric("첫 포탑 평균(블루/레드)", f"{bt} / {rt}")
    if "game_end_min" in dfc and dfc["game_end_min"].notna().any():
        t3.metric("평균 게임시간(분)", round(dfc["game_end_min"].mean(),2))
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

        # 아이템 아이콘 칼럼 추가
        g["item_icon"] = g["core_item"].apply(item_icon_url)
        st.dataframe(
            g[["item_icon","core_item","games","wins","win_rate"]],
            use_container_width=True,
            column_config={"item_icon": st.column_config.ImageColumn("아이콘", help="Data Dragon")}
        )

# -------------------- 아이템 성과(슬롯 무시) --------------------
st.subheader("아이템 성과(슬롯 무시)")
def item_stats(sub: pd.DataFrame) -> pd.DataFrame:
    item_cols = [c for c in sub.columns if c.startswith("item")]
    rec = []
    for c in item_cols:
        rec.append(sub[["matchId","win_clean",c]].rename(columns={c:"item"}))
    u = pd.concat(rec, ignore_index=True)
    u = u[u["item"].astype(str)!=""]
    g = (u.groupby("item").agg(total_picks=("matchId","count"), wins=("win_clean","sum")).reset_index())
    g["win_rate"] = (g["wins"]/g["total_picks"]*100).round(2)
    g = g.sort_values(["total_picks","win_rate"], ascending=[False,False])
    g["item_icon"] = g["item"].apply(item_icon_url)
    return g

g_items = item_stats(dfc)
st.dataframe(
    g_items[["item_icon","item","total_picks","wins","win_rate"]].head(25),
    use_container_width=True,
    column_config={"item_icon": st.column_config.ImageColumn("아이콘")}
)

# -------------------- 스펠/룬 (아이콘) --------------------
c1, c2 = st.columns(2)
with c1:
    st.subheader("스펠 조합")
    if "spell_combo" in dfc and dfc["spell_combo"].str.strip().any():
        sp = (dfc.groupby(["spell1_final","spell2_final"])
              .agg(games=("matchId","count"), wins=("win_clean","sum")).reset_index())
        sp["win_rate"] = (sp["wins"]/sp["games"]*100).round(2)
        sp = sp.sort_values(["games","win_rate"], ascending=[False,False]).head(10)
        sp["spell1_icon"] = sp["spell1_final"].apply(spell_icon_url)
        sp["spell2_icon"] = sp["spell2_final"].apply(spell_icon_url)
        st.dataframe(
            sp[["spell1_icon","spell2_icon","spell1_final","spell2_final","games","wins","win_rate"]],
            use_container_width=True,
            column_config={
                "spell1_icon": st.column_config.ImageColumn("스펠1"),
                "spell2_icon": st.column_config.ImageColumn("스펠2"),
            }
        )
    else:
        st.info("스펠 정보가 부족합니다.")

with c2:
    st.subheader("룬 조합(메인/보조)")
    if ("rune_core" in dfc.columns) and ("rune_sub" in dfc.columns):
        rn = (dfc.groupby(["rune_core","rune_sub"])
              .agg(games=("matchId","count"), wins=("win_clean","sum")).reset_index())
        rn["win_rate"] = (rn["wins"]/rn["games"]*100).round(2)
        rn = rn.sort_values(["games","win_rate"], ascending=[False,False]).head(10)
        rn["core_icon"] = rn["rune_core"].apply(rune_icon_url)
        rn["sub_icon"]  = rn["rune_sub"].apply(rune_icon_url)
        st.dataframe(
            rn[["core_icon","sub_icon","rune_core","rune_sub","games","wins","win_rate"]],
            use_container_width=True,
            column_config={
                "core_icon": st.column_config.ImageColumn("메인"),
                "sub_icon":  st.column_config.ImageColumn("보조"),
            }
        )
    else:
        st.info("룬 정보가 부족합니다.")

# -------------------- 원본 --------------------
st.subheader("원본 데이터 (필터 적용)")
show_cols = [c for c in dfc.columns if c not in ("team_champs","enemy_champs")]
st.dataframe(dfc[show_cols], use_container_width=True)

st.markdown("---")
ver = dd_catalog()["ver"]
st.caption(f"아이콘: Riot Data Dragon (ver {ver}) · 파일명 자동탐색/업로드 지원")
