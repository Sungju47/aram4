# app.py — ARAM 챔피언 대시보드 (+ 아이템 0 전처리, 스펠 무순서 집계)
import os, re, json
import pandas as pd
import streamlit as st

st.set_page_config(page_title="ARAM PS Dashboard", layout="wide")

# ===== 파일 경로(리포 루트) =====
PLAYERS_CSV   = "aram_participants_with_icons_superlight.csv"  # 참가자 행 데이터
ITEM_SUM_CSV  = "item_summary.csv"                  # item, icon_url, total_picks, wins, win_rate,+@
CHAMP_CSV     = "champion_icons.csv"                           # champion, champion_icon (또는 icon/icon_url)
RUNE_CSV      = "rune_icons.csv"                               # rune_core, rune_core_icon, rune_sub, rune_sub_icon
SPELL_CSV     = "spell_icons.csv"                              # 스펠 이름 ↔ 아이콘 URL
DD_VERSION    = "15.16.1"                                      # Data Dragon 폴백 버전

# ===== 유틸 =====
def _exists(path: str) -> bool:
    ok = os.path.exists(path)
    if not ok:
        st.warning(f"파일 없음: `{path}`")
    return ok

def _norm(x: str) -> str:
    return re.sub(r"\s+", "", str(x)).strip().lower()

# ===== 로더 =====
@st.cache_data
def load_players(path: str) -> pd.DataFrame:
    if not _exists(path):
        st.stop()
    df = pd.read_csv(path)

    # 승패 정리
    if "win_clean" not in df.columns:
        if "win" in df.columns:
            df["win_clean"] = df["win"].astype(str).str.lower().isin(["true","1","t","yes"]).astype(int)
        else:
            df["win_clean"] = 0

    # 아이템 이름 정리 + "0" 전처리 (아이템 구매 전 종료 케이스 제외)
    for c in [c for c in df.columns if re.fullmatch(r"item[0-6]_name", c)]:
        df[c] = df[c].fillna("").astype(str).str.strip()
        df[c] = df[c].replace({"0": "", 0: ""})

    # 기본 텍스트 컬럼
    for c in ["spell1","spell2","spell1_name_fix","spell2_name_fix","rune_core","rune_sub","champion","matchId"]:
        if c in df.columns:
            df[c] = df[c].fillna("").astype(str).str.strip()
    return df

@st.cache_data
def load_item_summary(path: str) -> pd.DataFrame:
    if not _exists(path):
        return pd.DataFrame()
    g = pd.read_csv(path)
    need = {"item","icon_url","total_picks","wins","win_rate"}
    if not need.issubset(g.columns):
        st.warning(f"`{path}` 헤더 확인 필요 (기대: {sorted(need)}, 실제: {list(g.columns)})")
    if "item" in g.columns:
        g = g[g["item"].astype(str).str.strip() != ""]
        g = g[g["item"] != "0"]  # 혹시 요약 파일에도 0이 남아있다면 제거
    return g

@st.cache_data
def load_champion_icons(path: str) -> dict:
    if not _exists(path):
        return {}
    df = pd.read_csv(path)
    name_col = next((c for c in ["champion","Champion","championName"] if c in df.columns), None)
    icon_col = next((c for c in ["champion_icon","icon","icon_url"] if c in df.columns), None)
    if not name_col or not icon_col:
        return {}
    df[name_col] = df[name_col].astype(str).str.strip()
    return dict(zip(df[name_col], df[icon_col]))

@st.cache_data
def load_rune_icons(path: str) -> dict:
    if not _exists(path):
        return {"core": {}, "sub": {}, "shards": {}}
    df = pd.read_csv(path)
    core_map, sub_map, shard_map = {}, {}, {}
    if "rune_core" in df.columns:
        ic = "rune_core_icon" if "rune_core_icon" in df.columns else None
        if ic: core_map = dict(zip(df["rune_core"].astype(str), df[ic].astype(str)))
    if "rune_sub" in df.columns:
        ic = "rune_sub_icon" if "rune_sub_icon" in df.columns else None
        if ic: sub_map = dict(zip(df["rune_sub"].astype(str), df[ic].astype(str)))
    if "rune_shard" in df.columns:
        ic = "rune_shard_icon" if "rune_shard_icon" in df.columns else ("rune_shards_icons" if "rune_shards_icons" in df.columns else None)
        if ic: shard_map = dict(zip(df["rune_shard"].astype(str), df[ic].astype(str)))
    return {"core": core_map, "sub": sub_map, "shards": shard_map}

@st.cache_data
def load_spell_icons(path: str) -> dict:
    """스펠명(여러 형태) -> 아이콘 URL"""
    if not _exists(path):
        return {}
    df = pd.read_csv(path)
    cand_name = [c for c in df.columns if _norm(c) in {"spell","spellname","name","spell1_name_fix","spell2_name_fix","스펠","스펠명"}]
    cand_icon = [c for c in df.columns if _norm(c) in {"icon","icon_url","spelli con","spell_icon"} or "icon" in c.lower()]
    m = {}
    if cand_name and cand_icon:
        name_col, icon_col = cand_name[0], cand_icon[0]
        for n, i in zip(df[name_col].astype(str), df[icon_col].astype(str)):
            m[_norm(n)] = i
            m[str(n).strip()] = i
    else:
        if df.shape[1] >= 2:
            for n, i in zip(df.iloc[:,0].astype(str), df.iloc[:,1].astype(str)):
                m[_norm(n)] = i
                m[str(n).strip()] = i
    return m

# ===== 데이터 로드 =====
df        = load_players(PLAYERS_CSV)
item_sum  = load_item_summary(ITEM_SUM_CSV)
champ_map = load_champion_icons(CHAMP_CSV)
rune_maps = load_rune_icons(RUNE_CSV)
spell_map = load_spell_icons(SPELL_CSV)

ITEM_ICON_MAP = dict(zip(item_sum.get("item", []), item_sum.get("icon_url", [])))

# ===== 사이드바 =====
st.sidebar.title("ARAM PS Controls")
champs = sorted(df["champion"].dropna().unique().tolist()) if "champion" in df.columns else []
selected = st.sidebar.selectbox("Champion", champs, index=0 if champs else None)

# ===== 상단 요약 =====
dsel = df[df["champion"] == selected].copy() if len(champs) else df.head(0).copy()
games = len(dsel)
match_cnt_all = df["matchId"].nunique() if "matchId" in df.columns else len(df)
match_cnt_sel = dsel["matchId"].nunique() if "matchId" in dsel.columns else games
winrate = round(dsel["win_clean"].mean()*100, 2) if games else 0.0
pickrate = round((match_cnt_sel / match_cnt_all * 100), 2) if match_cnt_all else 0.0

c0, ctitle = st.columns([1, 5])
with c0:
    cicon = champ_map.get(selected, "")
    if cicon:
        st.image(cicon, width=64)
with ctitle:
    st.title(f"{selected}")

c1, c2, c3 = st.columns(3)
c1.metric("Games", f"{games}")
c2.metric("Win Rate", f"{winrate}%")
c3.metric("Pick Rate", f"{pickrate}%")

# ===== 코어템 3개 조합 추천 =====
st.subheader("3코어 조합 통계")

# dsel: 선택 챔피언 데이터 (이미 필터링된 DataFrame)
# df_items: item_summary CSV (item, is_core, is_boots 컬럼 포함)
df_items = pd.read_csv(ITEM_SUM_CSV)

item_cols = [c for c in dsel.columns if re.fullmatch(r"item[0-6]_name", c)]

def is_core_item(item_name: str) -> bool:
    """CSV 기준: 코어템인지, 부츠인지 판단. 없으면 False 처리"""
    if not item_name or item_name == "포로 간식":
        return False
    sub = df_items[df_items["item"] == item_name]
    if sub.empty:
        return False
    is_core = str(sub["is_core"].iloc[0]).strip().lower() in ["true","1","yes"]
    is_boots = str(sub["is_boots"].iloc[0]).strip().lower() in ["true","1","yes"]
    return is_core and not is_boots
if games and item_cols:
    core_builds = []

    for _, row in dsel.iterrows():
        items = [row[c] for c in item_cols if row[c]]  # 비어있는 값 제거
        # CSV 기준 코어템만, 부츠 제외, 순서 유지
        items = [i for i in items if is_core_item(i)]
        core = items[:3]  # 첫 3개만
        if len(core) == 3:
            core_builds.append((tuple(core), row["win_clean"]))

    if core_builds:
        core_df = pd.DataFrame(core_builds, columns=["core","win_clean"])
        core_df["core1"] = core_df["core"].apply(lambda x: x[0])
        core_df["core2"] = core_df["core"].apply(lambda x: x[1])
        core_df["core3"] = core_df["core"].apply(lambda x: x[2])

        # 조합별 통계
        builds = (
            core_df.groupby(["core1","core2","core3"])
            .agg(games=("win_clean","count"), wins=("win_clean","sum"))
            .reset_index()
        )
        builds["pick_rate"] = (builds["games"]/games*100).round(2)
        builds["win_rate"] = (builds["wins"]/builds["games"]*100).round(2)

        # 아이콘 매핑
        builds["core1_icon"] = builds["core1"].map(ITEM_ICON_MAP)
        builds["core2_icon"] = builds["core2"].map(ITEM_ICON_MAP)
        builds["core3_icon"] = builds["core3"].map(ITEM_ICON_MAP)

        # 정렬: 픽률 내림차순 → 승률 내림차순, 상위 3개
        builds = builds.sort_values(["pick_rate","win_rate"], ascending=[False, False]).head(3)

        st.dataframe(
            builds.reset_index(drop=True)[[
                "core1_icon","core1","core2_icon","core2","core3_icon","core3",
                "pick_rate","win_rate","games",
            ]].to_dict("records"),
            use_container_width=True,
            column_config={
                "core1_icon": st.column_config.ImageColumn("코어1", width="small"),
                "core2_icon": st.column_config.ImageColumn("코어2", width="small"),
                "core3_icon": st.column_config.ImageColumn("코어3", width="small"),
                "core1":"아이템1","core2":"아이템2","core3":"아이템3",
                "pick_rate":"픽률(%)","win_rate":"승률(%)","games":"게임수",
            }
        )
    else:
        st.info("3개 코어템을 완성한 게임이 없습니다.")
        
# ===== 코어템 통계 =====
st.subheader("코어템 통계")

# CSV 불러오기
df_items = pd.read_csv(ITEM_SUM_CSV)

# 문자열/숫자 모두 처리 가능하게 bool 변환
def to_bool(x):
    return str(x).strip().lower() in ["true","1","yes"]

df_items["is_core"]  = df_items["is_core"].apply(to_bool)
df_items["is_boots"] = df_items["is_boots"].apply(to_bool)

# 아이템 이름 정규화
def norm_item(x):
    return str(x).strip().lower()

df_items["item_norm"] = df_items["item"].apply(norm_item)

# dsel 아이템 컬럼 정규화
item_cols = [c for c in dsel.columns if re.fullmatch(r"item[0-6]_name", c)]
for c in item_cols:
    dsel[c+"_norm"] = dsel[c].apply(norm_item)

# CSV 기준 코어템 + 부츠 제외
core_items_set = set(df_items.loc[df_items["is_core"] & (~df_items["is_boots"]), "item_norm"])

# dsel_long으로 아이템 컬럼 합치기
dsel_long = pd.melt(
    dsel,
    id_vars=["win_clean"],
    value_vars=[c+"_norm" for c in item_cols],
    value_name="item_norm"
)[["item_norm","win_clean"]]

# 포로 간식, 부츠 제외, 코어템만 필터링
dsel_core = dsel_long[
    dsel_long["item_norm"].isin(core_items_set) &
    (~dsel_long["item_norm"].isin(["포로 간식","물약","수당"]))
]

if not dsel_core.empty:
    # 집계
    top_items = (
        dsel_core.groupby("item_norm", as_index=False)
        .agg(games=("win_clean","count"), wins=("win_clean","sum"))
    )
    top_items["win_rate"] = (top_items["wins"]/top_items["games"]*100).round(2)
    top_items["pick_rate"] = (top_items["games"]/games*100).round(2)

    # 아이콘 매핑 (원래 이름 기준)
    item_map = dict(zip(df_items["item_norm"], df_items["icon_url"]))
    top_items["icon_url"] = top_items["item_norm"].map(item_map)

    # 상위 20개
    top_items = top_items.sort_values(["games","win_rate"], ascending=[False,False]).head(20)

    # Streamlit 출력 (픽률, 승률, 게임수 순)
    st.dataframe(
        top_items.reset_index(drop=True)[["icon_url","item_norm","pick_rate","win_rate","games"]].to_dict("records"),
        use_container_width=True,
        column_config={
            "icon_url": st.column_config.ImageColumn("아이콘", width="small"),
            "item_norm": "아이템",
            "pick_rate": "픽률(%)",
            "win_rate": "승률(%)",
            "games": "게임수"
        }
    )
else:
    st.info("선택 챔피언의 코어템 데이터가 없습니다.")


# ===== 스펠 통계 (아이콘만 표시) =====
st.subheader("스펠 통계")

SPELL_ALIASES = {
    "점멸":"점멸","표식":"표식","눈덩이":"표식","유체화":"유체화","회복":"회복","점화":"점화",
    "정화":"정화","탈진":"탈진","방어막":"방어막","총명":"총명","순간이동":"순간이동",
    "flash":"점멸","mark":"표식","snowball":"표식","ghost":"유체화","haste":"유체화",
    "heal":"회복","ignite":"점화","cleanse":"정화","exhaust":"탈진","barrier":"방어막",
    "clarity":"총명","teleport":"순간이동",
}
KOR_TO_DDRAGON = {
    "점멸":"SummonerFlash","표식":"SummonerSnowball","유체화":"SummonerHaste","회복":"SummonerHeal",
    "점화":"SummonerDot","정화":"SummonerBoost","탈진":"SummonerExhaust","방어막":"SummonerBarrier",
    "총명":"SummonerMana","순간이동":"SummonerTeleport",
}

def standard_korean_spell(s: str) -> str:
    return SPELL_ALIASES.get(str(s).strip(), str(s).strip())

def ddragon_spell_icon(s: str) -> str:
    kor = standard_korean_spell(s)
    key = KOR_TO_DDRAGON.get(kor)
    if not key: return ""
    return f"https://ddragon.leagueoflegends.com/cdn/{DD_VERSION}/img/spell/{key}.png"

def canonical_pair(a: str, b: str):
    a_std = standard_korean_spell(a or "")
    b_std = standard_korean_spell(b or "")
    if a_std <= b_std:
        return a_std, b_std
    return b_std, a_std

# 스펠 컬럼 선택
def pick_spell_cols(df_):
    if {"spell1_name_fix","spell2_name_fix"}.issubset(df_.columns):
        return "spell1_name_fix", "spell2_name_fix"
    if {"spell1","spell2"}.issubset(df_.columns):
        return "spell1", "spell2"
    cands = [c for c in df_.columns if "spell" in c.lower()]
    return (cands[0], cands[1]) if len(cands) >= 2 else (None, None)

s1, s2 = pick_spell_cols(dsel)

if games and s1 and s2:
    tmp = dsel[[s1, s2, "win_clean"]].copy()
    tmp["s1_std"], tmp["s2_std"] = zip(*tmp.apply(lambda r: canonical_pair(r[s1], r[s2]), axis=1))
    
    sp = (
        tmp.groupby(["s1_std","s2_std"], as_index=False)
           .agg(games=("win_clean","count"), wins=("win_clean","sum"))
    )
    sp["win_rate"] = (sp["wins"]/sp["games"]*100).round(2)
    sp = sp.sort_values(["games","win_rate"], ascending=[False,False]).head(10)
    
    sp["spell1_icon"] = sp["s1_std"].apply(ddragon_spell_icon)
    sp["spell2_icon"] = sp["s2_std"].apply(ddragon_spell_icon)

    st.dataframe(
        sp[["spell1_icon","spell2_icon","win_rate","games"]].to_dict("records"),
        use_container_width=True,
        column_config={
            "spell1_icon": st.column_config.ImageColumn("스펠1", width="small"),
            "spell2_icon": st.column_config.ImageColumn("스펠2", width="small"),
            "win_rate":"승률(%)",
            "games":"게임수"
        }
    )
else:
    st.info("스펠 컬럼을 찾지 못했습니다.")



# ===== 룬 추천 =====
st.subheader("룬 통계")
core_map = rune_maps.get("core", {})
sub_map  = rune_maps.get("sub", {})

def _rune_core_icon(name: str) -> str: return core_map.get(name, "")
def _rune_sub_icon(name: str)  -> str: return sub_map.get(name, "")

if games and {"rune_core","rune_sub"}.issubset(dsel.columns):
    ru = (
        dsel.groupby(["rune_core","rune_sub"])
        .agg(games=("win_clean","count"), wins=("win_clean","sum"))
        .reset_index()
    )
    ru["win_rate"] = (ru["wins"]/ru["games"]*100).round(2)
    ru = ru.sort_values(["games","win_rate"], ascending=[False,False]).head(10)
    ru["rune_core_icon"] = ru["rune_core"].apply(_rune_core_icon)
    ru["rune_sub_icon"]  = ru["rune_sub"].apply(_rune_sub_icon)

    st.dataframe(
        ru[["rune_core_icon","rune_core","rune_sub_icon","rune_sub","games","wins","win_rate"]].to_dict("records"),
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

# ===== (선택) 한 패널: 5v5 평균 승률 vs 평균 승률 + GPT 전략 =====
st.header("5v5 평균 승률 비교 & 전략 (단일 패널)")
with st.container():
    st.markdown(
        "- **챔피언 10명**을 입력하세요: **앞 5명=팀 A(아군)**, **뒤 5명=팀 B(적군)**. (쉼표 또는 공백 구분)\n"
        "- 모델 학습 전이므로 **챔피언별 베이스라인 승률의 단순 평균**을 비교합니다."
    )

    @st.cache_data
    def champion_baseline(df_all: pd.DataFrame) -> pd.DataFrame:
        if "champion" not in df_all.columns:
            return pd.DataFrame(columns=["champion","games","wins","winrate"])
        g = (df_all.groupby("champion", as_index=False)
                    .agg(games=("win_clean","count"), wins=("win_clean","sum")))
        g["winrate"] = (g["wins"] / g["games"] * 100).round(2)
        return g.sort_values("champion")

    base_tbl = champion_baseline(df)
    base_map = dict(zip(base_tbl["champion"], base_tbl["winrate"]))

    raw = st.text_area(
        "챔피언 10명 입력 (예: Lux Ziggs Sona Seraphine Ashe, Darius Garen Katarina Yasuo Aatrox)",
        placeholder="Lux Ziggs Sona Seraphine Ashe, Darius Garen Katarina Yasuo Aatrox"
    )
    api_key = st.text_input("OpenAI API 키 (선택: 전략 생성용)", type="password", placeholder="sk-...")

    def avg_winrate(lst):
        vals = [base_map.get(x, None) for x in lst]
        known = [v for v in vals if v is not None]
        return round(sum(known)/len(known), 2) if known else None, [x for x,v in zip(lst, vals) if v is None]

    if raw.strip():
        toks = re.split(r"[,\s]+", raw.strip())
        toks = [t for t in toks if t]
        if len(toks) >= 10:
            ally, enemy = toks[:5], toks[5:10]
            a_avg, a_missing = avg_winrate(ally)
            b_avg, b_missing = avg_winrate(enemy)

            c1, c2 = st.columns(2)
            with c1:
                st.metric("Team A 평균 승률", f"{a_avg if a_avg is not None else 'N/A'}%")
                st.caption("A: " + ", ".join(ally))
                if a_missing: st.error("A 데이터 없음: " + ", ".join(a_missing))
            with c2:
                st.metric("Team B 평균 승률", f"{b_avg if b_avg is not None else 'N/A'}%")
                st.caption("B: " + ", ".join(enemy))
                if b_missing: st.error("B 데이터 없음: " + ", ".join(b_missing))

            st.divider()
            st.subheader("전략 코멘트 (선택)")
            if api_key:
                try:
                    import openai
                    openai.api_key = api_key
                    a_show = f"{a_avg}%" if a_avg is not None else "N/A"
                    b_show = f"{b_avg}%" if b_avg is not None else "N/A"
                    prompt = f"""
너는 LoL ARAM 코치다. 아래 정보를 바탕으로 3~5줄 전략을 제시하라.

Team A: {', '.join(ally)} (avg {a_show})
Team B: {', '.join(enemy)} (avg {b_show})

조건:
- 단순 평균 승률 기반임을 전제(시너지/상성 미반영)
- 초반/중반/후반 전략 중 핵심 1~2개
- 과도한 확신/허풍 금지, 간결하게
""".strip()
                    resp = openai.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role":"user","content":prompt}],
                        temperature=0.6,
                        max_tokens=220,
                    )
                    st.write(resp.choices[0].message.content.strip())
                except Exception as e:
                    st.error(f"전략 생성 실패: {e}")
            else:
                st.info("전략 코멘트를 보려면 OpenAI API 키를 입력하세요.")
        else:
            st.warning("챔피언 10명을 입력해야 합니다 (앞5=팀 A, 뒤5=팀 B).")

# ===== 원본(선택 챔피언) =====
with st.expander("Raw rows (selected champion)"):
    st.dataframe(dsel, use_container_width=True)
