# app.py — ARAM PS Dashboard with icons (ID/이름 모두 지원)
import os, glob, ast, requests
from typing import Optional, List, Dict, Any
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px

st.set_page_config(page_title="ARAM PS Dashboard", layout="wide")

CANDIDATES = [
    "aram_participants_with_full_runes_merged_plus.csv",
    "aram_participants_with_full_runes_merged.csv",
    "aram_participants_with_full_runes.csv",
    "aram_participants_clean_preprocessed.csv",
    "aram_participants_clean_no_dupe_items.csv",
    "aram_participants_with_items.csv",
]

def discover_csv() -> Optional[str]:
    for n in CANDIDATES:
        if os.path.exists(n): return n
    hits = sorted(glob.glob("*.csv"))
    return hits[0] if hits else None

# ---------------- Data Dragon ----------------
DD_BASE = "https://ddragon.leagueoflegends.com"

@st.cache_data(show_spinner=False)
def dd_versions() -> List[str]:
    r = requests.get(f"{DD_BASE}/api/versions.json", timeout=10)
    r.raise_for_status()
    return r.json()

@st.cache_data(show_spinner=False)
def dd_catalog() -> Dict[str, Any]:
    ver = dd_versions()[0]
    # 아이템: id->name / name->id
    items = requests.get(f"{DD_BASE}/cdn/{ver}/data/ko_KR/item.json", timeout=10).json()["data"]
    item_by_id, item_by_name = {}, {}
    for iid, meta in items.items():
        nm = str(meta.get("name","")).strip()
        item_by_id[str(iid)] = nm
        if nm: item_by_name.setdefault(nm, str(iid))
    # 스펠: name->file
    spells = requests.get(f"{DD_BASE}/cdn/{ver}/data/ko_KR/summoner.json", timeout=10).json()["data"]
    spell_file = { meta["name"]: meta["image"]["full"] for meta in spells.values() }
    # 챔프: eng key -> png
    champs = requests.get(f"{DD_BASE}/cdn/{ver}/data/en_US/champion.json", timeout=10).json()["data"]
    champ_png = { k: f"{DD_BASE}/cdn/{ver}/img/champion/{k}.png" for k in champs.keys() }
    # 룬: name -> icon path(/cdn/img/)
    runes = requests.get(f"{DD_BASE}/cdn/{ver}/data/ko_KR/runesReforged.json", timeout=10).json()
    rune_icon = {}
    def walk(t):
        if t.get("name") and t.get("icon"):
            rune_icon.setdefault(t["name"], f"{DD_BASE}/cdn/img/{t['icon']}")
        for s in t.get("slots", []):
            for r in s.get("runes", []):
                if r.get("name") and r.get("icon"):
                    rune_icon.setdefault(r["name"], f"{DD_BASE}/cdn/img/{r['icon']}")
    for tree in runes: walk(tree)
    return {"ver": ver, "item_by_id": item_by_id, "item_by_name": item_by_name,
            "spell_file": spell_file, "champ_png": champ_png, "rune_icon": rune_icon}

def item_name_any(v) -> str:
    """숫자ID/문자ID/한글이름 다 받아 사람이 읽는 이름 반환"""
    if v is None: return ""
    s = str(v).strip()
    if not s or s == "0" or s.lower() in ("nan","none"): return ""
    cat = dd_catalog()
    # 숫자/문자 ID -> 이름
    if s.isdigit() or s in cat["item_by_id"]:
        return cat["item_by_id"].get(s, "")
    # 이미 이름이면 그대로
    return s

def item_icon_any(v) -> Optional[str]:
    s = item_name_any(v)
    if not s: return None
    iid = dd_catalog()["item_by_name"].get(s)
    return f"{DD_BASE}/cdn/{dd_catalog()['ver']}/img/item/{iid}.png" if iid else None

def spell_icon_url(name_kor: str) -> Optional[str]:
    if not name_kor: return None
    f = dd_catalog()["spell_file"].get(name_kor.strip())
    return f"{DD_BASE}/cdn/{dd_catalog()['ver']}/img/spell/{f}" if f else None

def champ_icon_url(champ_en: str) -> Optional[str]:
    return dd_catalog()["champ_png"].get(str(champ_en))

def rune_icon_url(rune_name: str) -> Optional[str]:
    return dd_catalog()["rune_icon"].get(str(rune_name))

# ---------------- utils ----------------
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
    if "|" in s: return [t.strip() for t in s.split("|") if t.strip()]
    if "," in s: return [t.strip() for t in s.split(",") if t.strip()]
    return [s]

# ---------------- load ----------------
@st.cache_data(show_spinner=False)
def load_df(src) -> pd.DataFrame:
    df = pd.read_csv(src)
    df["win_clean"] = df["win"].apply(_yes) if "win" in df.columns else 0
    s1 = "spell1_name" if "spell1_name" in df.columns else ("spell1" if "spell1" in df.columns else None)
    s2 = "spell2_name" if "spell2_name" in df.columns else ("spell2" if "spell2" in df.columns else None)
    df["spell1_final"] = df[s1].astype(str) if s1 else ""
    df["spell2_final"] = df[s2].astype(str) if s2 else ""
    df["spell_combo"] = (df["spell1_final"] + " + " + df["spell2_final"]).str.strip()
    # 아이템 컬럼 정리(숫자/이름 혼재 지원)
    for c in [c for c in df.columns if c.startswith("item")]:
        df[c] = df[c].apply(item_name_any)  # ← 여기서 전부 “이름”으로 정규화
    # 리스트 문자열 컬럼
    for col in ("team_champs","enemy_champs"):
        if col in df.columns: df[col] = df[col].apply(_as_list)
    # 시간/지표
    df["duration_min"] = (pd.to_numeric(df.get("game_end_min", np.nan), errors="coerce")
                          .fillna(18.0).clip(lower=6.0, upper=40.0))
    if "damage_total" in df.columns:
        df["dpm"] = df["damage_total"]/df["duration_min"].replace(0,np.nan)
    else:
        df["dpm"] = np.nan
    for c in ("kills","deaths","assists"):
        if c not in df.columns: df[c] = 0
    df["kda"] = (df["kills"]+df["assists"])/df["deaths"].replace(0,np.nan)
    df["kda"] = df["kda"].fillna(df["kills"]+df["assists"])
    # 코어템 이름 컬럼도 정규화
    for cc in ("first_core_item_name","second_core_item_name"):
        if cc in df.columns: df[cc] = df[cc].apply(item_name_any)
    return df

# ---------------- UI ----------------
st.sidebar.title("데이터")
auto = discover_csv()
st.sidebar.write("🔎 자동 검색:", auto if auto else "없음")
uploaded = st.sidebar.file_uploader("CSV 업로드(선택)", type=["csv"])
df = load_df(uploaded if uploaded is not None else auto) if (uploaded or auto) else None
if df is None:
    st.error("CSV를 찾을 수 없습니다."); st.stop()

st.sidebar.markdown("---")
if "champion" not in df.columns:
    st.error("'champion' 컬럼이 없습니다."); st.stop()
champs = sorted(df["champion"].dropna().unique().tolist())
sel = st.sidebar.selectbox("챔피언 선택", champs)

# ---------------- header ----------------
sub = df[df["champion"]==sel].copy()
total_matches = df["matchId"].nunique() if "matchId" in df.columns else len(df)
games = len(sub)
winrate = round(sub["win_clean"].mean()*100,2) if games else 0.0
pickrate = round(games/max(1,total_matches)*100,2)
avg_k = round(sub["kills"].mean(),2); avg_d = round(sub["deaths"].mean(),2); avg_a = round(sub["assists"].mean(),2)
avg_dpm = round(sub["dpm"].mean(),1)

left, mid = st.columns([1,5])
with left:
    url = champ_icon_url(sel)
    if url: st.image(url, width=88)
with mid:
    st.title(f"ARAM Dashboard — {sel}")
    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("게임 수", games)
    c2.metric("승률(%)", winrate)
    c3.metric("픽률(%)", pickrate)
    c4.metric("평균 K/D/A", f"{avg_k}/{avg_d}/{avg_a}")
    c5.metric("평균 DPM", avg_dpm)

# ---------------- timeline ----------------
tl = ["first_blood_min","blue_first_tower_min","red_first_tower_min","game_end_min","gold_spike_min"]
if any(c in sub.columns for c in tl):
    st.subheader("타임라인 요약")
    t1,t2,t3 = st.columns(3)
    if "first_blood_min" in sub and sub["first_blood_min"].notna().any():
        t1.metric("퍼블 평균(분)", round(sub["first_blood_min"].mean(),2))
    if ("blue_first_tower_min" in sub) or ("red_first_tower_min" in sub):
        bt = round(sub.get("blue_first_tower_min", pd.Series([])).dropna().mean(),2) if "blue_first_tower_min" in sub else np.nan
        rt = round(sub.get("red_first_tower_min", pd.Series([])).dropna().mean(),2) if "red_first_tower_min" in sub else np.nan
        t2.metric("첫 포탑 평균(블루/레드)", f"{bt} / {rt}")
    if "game_end_min" in sub and sub["game_end_min"].notna().any():
        t3.metric("평균 게임시간(분)", round(sub["game_end_min"].mean(),2))
    if "gold_spike_min" in sub and sub["gold_spike_min"].notna().any():
        st.plotly_chart(px.histogram(sub, x="gold_spike_min", nbins=20, title="골드 스파이크 분포"), use_container_width=True)

# ---------------- core items ----------------
core_cols = [c for c in ["first_core_item_min","first_core_item_name","second_core_item_min","second_core_item_name"] if c in sub.columns]
if core_cols:
    st.subheader("코어 아이템 구매 타이밍")
    a,b = st.columns(2)
    if "first_core_item_min" in sub and sub["first_core_item_min"].notna().any():
        a.metric("1코어 평균(분)", round(sub["first_core_item_min"].mean(),2))
        st.plotly_chart(px.histogram(sub.dropna(subset=["first_core_item_min"]),
                                     x="first_core_item_min", nbins=24, title="1코어 시각 분포"), use_container_width=True)
    if "second_core_item_min" in sub and sub["second_core_item_min"].notna().any():
        b.metric("2코어 평균(분)", round(sub["second_core_item_min"].mean(),2))
        st.plotly_chart(px.histogram(sub.dropna(subset=["second_core_item_min"]),
                                     x="second_core_item_min", nbins=24, title="2코어 시각 분포"), use_container_width=True)

    rows = []
    if "first_core_item_name" in sub:
        rows.append(sub[["matchId","win_clean","first_core_item_name"]].rename(columns={"first_core_item_name":"core_item"}))
    if "second_core_item_name" in sub:
        rows.append(sub[["matchId","win_clean","second_core_item_name"]].rename(columns={"second_core_item_name":"core_item"}))
    if rows:
        u = pd.concat(rows, ignore_index=True)
        u["core_item"] = u["core_item"].apply(item_name_any)
        u = u[u["core_item"]!=""]
        g = (u.groupby("core_item").agg(games=("matchId","count"), wins=("win_clean","sum")).reset_index())
        g["win_rate"] = (g["wins"]/g["games"]*100).round(2)
        g["item_icon"] = g["core_item"].apply(item_icon_any)
        st.dataframe(
            g.sort_values(["games","win_rate"], ascending=[False,False]).head(20)[["item_icon","core_item","games","wins","win_rate"]],
            use_container_width=True,
            column_config={"item_icon": st.column_config.ImageColumn("아이콘")}
        )

# ---------------- items (all slots) ----------------
st.subheader("아이템 성과(슬롯 무시)")
def item_stats(subdf: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in subdf.columns if c.startswith("item")]
    rec = []
    for c in cols:
        rec.append(subdf[["matchId","win_clean",c]].rename(columns={c:"item"}))
    u = pd.concat(rec, ignore_index=True)
    u["item"] = u["item"].apply(item_name_any)
    u = u[(u["item"]!="")]
    g = (u.groupby("item").agg(total_picks=("matchId","count"), wins=("win_clean","sum")).reset_index())
    g["win_rate"] = (g["wins"]/g["total_picks"]*100).round(2)
    g["item_icon"] = g["item"].apply(item_icon_any)
    return g.sort_values(["total_picks","win_rate"], ascending=[False,False])

g_items = item_stats(sub)
st.dataframe(
    g_items[["item_icon","item","total_picks","wins","win_rate"]].head(25),
    use_container_width=True,
    column_config={"item_icon": st.column_config.ImageColumn("아이콘")}
)

# ---------------- spells / runes ----------------
c1, c2 = st.columns(2)
with c1:
    st.subheader("스펠 조합")
    if "spell_combo" in sub and sub["spell_combo"].str.strip().any():
        sp = (sub.groupby(["spell1_final","spell2_final"])
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
    if ("rune_core" in sub.columns) and ("rune_sub" in sub.columns):
        rn = (sub.groupby(["rune_core","rune_sub"])
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

# ---------------- raw ----------------
st.subheader("원본 데이터 (필터 적용)")
hide = [c for c in sub.columns if c in ("team_champs","enemy_champs")]
st.dataframe(sub[[c for c in sub.columns if c not in hide]], use_container_width=True)

st.markdown("---")
st.caption(f"아이콘/이름 매핑: Riot Data Dragon ({dd_catalog()['ver']}) · 아이템 ID/이름 모두 지원")
