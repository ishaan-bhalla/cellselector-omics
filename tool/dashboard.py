# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import re
from functools import reduce

st.set_page_config(page_title="CellLineFinder", page_icon="🧬", layout="centered")
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@500&display=swap');
#MainMenu,footer,header{visibility:hidden;}
.stApp{background:#F1F5F9;}
.block-container{padding-top:2rem;max-width:880px;}
*{font-family:'Inter',sans-serif;}
.head{display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #E2E8F0;padding-bottom:1.3rem;margin-bottom:0.4rem;}
.brand{display:flex;align-items:center;gap:0.7rem;}
.mark{width:38px;height:38px;border-radius:9px;background:linear-gradient(135deg,#0D9488,#0F766E);display:flex;align-items:center;justify-content:center;color:#fff;font-weight:800;font-size:1.1rem;}
.bt h1{font-size:1.35rem;font-weight:700;color:#0F172A;letter-spacing:-0.3px;margin:0;}
.bt p{font-size:0.82rem;color:#64748B;font-weight:400;margin:1px 0 0 0;}
.headstats{display:flex;gap:1.8rem;}
.hs{text-align:right;}
.hs .n{font-size:1.1rem;font-weight:700;color:#0F172A;font-family:'IBM Plex Mono';}
.hs .l{font-size:0.66rem;color:#94A3B8;text-transform:uppercase;letter-spacing:0.6px;}
.stTextInput input{background:#fff !important;border:1px solid #CBD5E1 !important;border-radius:9px !important;padding:0.85rem 1.1rem !important;font-size:1rem !important;color:#0F172A !important;font-family:'IBM Plex Mono' !important;}
.stTextInput input:focus{border-color:#0D9488 !important;box-shadow:0 0 0 3px rgba(13,148,136,0.12) !important;}
.stButton button{background:#0F172A !important;color:#fff !important;border:none !important;border-radius:9px !important;padding:0.85rem 0 !important;font-weight:600 !important;}
.stButton button:hover{background:#1E293B !important;}
.parsed{font-size:0.82rem;color:#64748B;margin:0.6rem 0 0 0;font-family:'IBM Plex Mono';}
.parsed b{color:#0D9488;}
.resbar{font-size:0.85rem;color:#64748B;margin:1.4rem 0 1rem 0;font-weight:500;}
.resbar b{color:#0F172A;}
.card{background:#fff;border:1px solid #E2E8F0;border-radius:12px;padding:1.2rem 1.4rem;margin-bottom:0.8rem;transition:all .15s;}
.card:hover{border-color:#0D9488;box-shadow:0 4px 16px rgba(15,23,42,0.06);}
.card.top{border-left:3px solid #0D9488;}
.crow{display:flex;align-items:center;gap:1rem;}
.rank{font-family:'IBM Plex Mono';font-weight:600;font-size:0.9rem;color:#94A3B8;min-width:30px;}
.rank.hi{color:#0D9488;}
.name{font-size:1.2rem;font-weight:700;color:#0F172A;}
.cid{font-family:'IBM Plex Mono';font-size:0.75rem;color:#94A3B8;}
.score{margin-left:auto;text-align:right;}
.score .n{font-size:1.5rem;font-weight:800;color:#0F172A;font-family:'IBM Plex Mono';line-height:1;}
.score .l{font-size:0.64rem;color:#94A3B8;text-transform:uppercase;letter-spacing:0.6px;margin-top:3px;}
.metrics{display:flex;margin-top:1rem;border:1px solid #EEF2F6;border-radius:8px;overflow:hidden;}
.m{flex:1;padding:0.6rem 0.9rem;border-right:1px solid #EEF2F6;background:#FAFBFC;}
.m:last-child{border-right:none;}
.m .v{font-family:'IBM Plex Mono';font-weight:600;font-size:0.98rem;color:#0F172A;}
.m .k{font-size:0.64rem;color:#94A3B8;text-transform:uppercase;letter-spacing:0.5px;margin-top:1px;}
.m .v.teal{color:#0D9488;}
.srcs{display:flex;gap:5px;margin-top:0.85rem;flex-wrap:wrap;}
.sq{font-family:'IBM Plex Mono';font-size:0.7rem;padding:3px 9px;border-radius:5px;font-weight:500;}
.sq.on{background:#E6F5F3;color:#0F766E;}
.sq.off{background:#F1F5F9;color:#B8C2CE;}
.ev{margin-top:0.85rem;padding-top:0.85rem;border-top:1px solid #EEF2F6;font-size:0.85rem;color:#64748B;line-height:1.5;}
.ev b{color:#334155;font-weight:600;}
.ev .d{color:#0D9488;font-weight:600;}
.chip{display:inline-block;font-size:0.7rem;font-weight:600;padding:2px 9px;border-radius:20px;margin-left:6px;}
.chip.mut{background:#FEF2F2;color:#B91C1C;}.chip.fus{background:#F5F3FF;color:#6D28D9;}.chip.comp{background:#E6F5F3;color:#0F766E;}
</style>
""", unsafe_allow_html=True)

DISEASE_WORDS=["lung","breast","colon","colorectal","ovarian","prostate","pancreatic","leukemia","leukaemia","lymphoma","melanoma","glioma","glioblastoma","liver","kidney","gastric","stomach","bladder","cervical","brain","neuroblastoma","sarcoma","carcinoma","skin","blood","bone","esophageal","thyroid"]
PQ="outputs/parquet/"

@st.cache_data
def load_data():
    lk = pd.read_parquet("outputs/cell_line_lookup.parquet")
    hpa = dict(zip(lk["hpa_name"].dropna(), lk.loc[lk["hpa_name"].notna(),"cellosaurus_id"]))
    meta = lk.set_index("cellosaurus_id")[["disease","lineage"]].to_dict("index")
    samp = pd.read_csv("data/nomenclature/9_DepMap_sample_info.csv", low_memory=False)
    ach = dict(zip(samp["DepMap_ID"], samp["RRID"]))
    geo = pd.read_csv("data/nomenclature/10_GEOInfo.txt", sep="\t", low_memory=False)
    gsm = dict(zip(geo["Geo_accession"], geo["Cellosaurus_ID"]))
    m = pd.read_parquet("outputs/master_with_confidence.parquet")
    for c in ["has_mutations","has_fusions"]:
        if c not in m: m[c]=False
    keep=[k for k in ["cellosaurus_id","official_name","confidence","evidence_count","has_mutations","has_fusions"] if k in m.columns]
    return hpa, ach, gsm, m[keep].drop_duplicates("cellosaurus_id"), meta

@st.cache_data
def load_gene_set():
    g=pd.read_parquet(PQ+"gene_expr_hpa_preprocessed.parquet", columns=["gene_symbol"])
    return set(g["gene_symbol"].dropna().unique())

hpa_to_id, ach_to_id, gsm_to_id, CONF, META = load_data()
GENES = load_gene_set()

def parse_query(text):
    dl=text.lower()
    disease=next((w for w in DISEASE_WORDS if w in dl), None)
    gene=None
    for tok in re.findall(r"[A-Za-z0-9\-]+", text):
        if tok.upper() in GENES:
            gene=tok.upper(); break
    return gene, disease

@st.cache_data
def score_source(path, gene, which):
    idmap={"hpa":hpa_to_id,"depmap":None,"geo":gsm_to_id,"prot":ach_to_id}[which]
    col="cellosaurus_id" if which=="depmap" else "original_id"
    df=pd.read_parquet(path, columns=[col,"gene_symbol","expression_value"])
    rows=df[df["gene_symbol"]==gene]
    if len(rows)==0: return None
    per=rows.groupby(col)["expression_value"].mean().reset_index()
    per["score"]=per["expression_value"]/per["expression_value"].max()
    per["cellosaurus_id"]=per[col].map(idmap) if idmap is not None else per[col]
    per=per.dropna(subset=["cellosaurus_id"])
    return per.groupby("cellosaurus_id")["score"].max().reset_index()

def recommend(gene, disease_filter=None, top_n=10):
    parts={}
    for path,which in [(PQ+"gene_expr_hpa_preprocessed.parquet","hpa"),(PQ+"gene_expr_depmap_preprocessed.parquet","depmap"),(PQ+"gene_expr_geo_preprocessed.parquet","geo"),(PQ+"gene_expr_ccle_proteomics_preprocessed.parquet","prot")]:
        s=score_source(path,gene,which)
        if s is not None: parts[which]=s.rename(columns={"score":which})
    if not parts: return None,0
    c=reduce(lambda a,b:a.merge(b,on="cellosaurus_id",how="outer"),parts.values())
    for w in ["hpa","depmap","geo","prot"]:
        if w not in c: c[w]=float("nan")
    c["expr_score"]=c[["hpa","depmap","geo","prot"]].mean(axis=1,skipna=True)
    c["n_sources"]=c[["hpa","depmap","geo","prot"]].notna().sum(axis=1)
    r=c.merge(CONF,on="cellosaurus_id",how="left")
    r["disease"]=r["cellosaurus_id"].map(lambda x:(META.get(x) or {}).get("disease",""))
    r["lineage"]=r["cellosaurus_id"].map(lambda x:(META.get(x) or {}).get("lineage",""))
    if disease_filter:
        mask=r["disease"].fillna("").str.lower().str.contains(disease_filter.lower())|r["lineage"].fillna("").str.lower().str.contains(disease_filter.lower())
        r=r[mask]
    r["final_score"]=r["expr_score"]*r["confidence"]
    return r.sort_values("final_score",ascending=False).head(top_n), len(r)

st.markdown('<div class="head"><div class="brand"><div class="bt"><h1>CellLineFinder</h1><p>Multi-omics cell line recommendation</p></div></div><div class="headstats"><div class="hs"><div class="n">2,076</div><div class="l">cell lines</div></div><div class="hs"><div class="n">4</div><div class="l">datasets</div></div><div class="hs"><div class="n">4/5</div><div class="l">validated</div></div></div></div>', unsafe_allow_html=True)
st.write("")
c1,c2=st.columns([4,1])
query=c1.text_input("q",value="show me EGFR lung cancer lines",label_visibility="collapsed",placeholder="Enter a gene or ask in plain English").strip()
go=c2.button("Search",use_container_width=True)

if query:
    gene, disease = parse_query(query)
    if gene is None:
        st.warning("No recognised gene found in your query. Try including a gene symbol such as EGFR or TP53.")
    else:
        st.markdown(f'<p class="parsed">Detected gene <b>{gene}</b>' + (f' &middot; tissue <b>{disease}</b>' if disease else '') + '</p>', unsafe_allow_html=True)
        with st.spinner(f"Ranking cell lines for {gene}"):
            r,total=recommend(gene, disease)
        if r is None or len(r)==0:
            st.warning(f"No results for {gene}" + (f" in {disease}" if disease else "") + ".")
        else:
            ctx=f" in <b>{disease}</b>" if disease else ""
            st.markdown(f'<div class="resbar">Showing top {len(r)} of <b>{total}</b> cell lines for {gene}{ctx}</div>', unsafe_allow_html=True)
            for i,(_,row) in enumerate(r.iterrows(),1):
                strength="strongly" if row["expr_score"]>=0.5 else "moderately"
                has_mut=bool(row.get("has_mutations",False)); has_fus=bool(row.get("has_fusions",False))
                def sq(n,w): return f'<span class="sq {"on" if pd.notna(row.get(w)) else "off"}">{n}</span>'
                srcs=sq("HPA RNA","hpa")+sq("DepMap","depmap")+sq("GEO","geo")+sq("Proteomics","prot")
                chips=('<span class="chip comp">complete model</span>' if (has_mut and has_fus) else '')
                evc=int(row["evidence_count"]) if "evidence_count" in row and pd.notna(row["evidence_count"]) else 0
                dis=row.get("disease") or ""; lin=row.get("lineage") or ""
                dis=dis if isinstance(dis,str) and dis and dis!="nan" else ""
                lin=lin if isinstance(lin,str) and lin and lin!="nan" else ""
                evp=[]
                if dis: evp.append(f'<span class="d">{dis}</span>')
                if lin: evp.append(f'{lin} lineage')
                evp.append(f'expresses {gene} {strength} across {int(row["n_sources"])} of 4 datasets')
                if has_mut: evp.append("mutation reported")
                if has_fus: evp.append("fusion reported")
                ev=f'<div class="ev"><b>Evidence:</b> ' + " &middot; ".join(evp) + f'. Backed by {evc} of 3 nomenclature sources.{chips}</div>'
                cc="card top" if i<=3 else "card"; rc="rank hi" if i<=3 else "rank"
                st.markdown(f"""<div class="{cc}"><div class="crow"><span class="{rc}">{i:02d}</span><div><span class="name">{row['official_name']}</span> <span class="cid">{row['cellosaurus_id']}</span></div><div class="score"><div class="n">{row['final_score']:.2f}</div><div class="l">Fit score</div></div></div><div class="metrics"><div class="m"><div class="v teal">{row['expr_score']:.2f}</div><div class="k">Expression</div></div><div class="m"><div class="v">{row['confidence']:.0%}</div><div class="k">Confidence</div></div><div class="m"><div class="v">{int(row['n_sources'])}/4</div><div class="k">Sources</div></div><div class="m"><div class="v">{evc}/3</div><div class="k">Evidence</div></div></div><div class="srcs">{srcs}</div>{ev}</div>""", unsafe_allow_html=True)
