"""Phase V1: build dashboard/doom_scatter.html, a self-contained Plotly page (plotly.js, data and logos inlined;
no server). Inputs: dashboard/data/*.csv and dashboard/assets/logos/ (dashboard/fetch_logos.py). Decisions D102-D108.

URL hash sets the view (also used for screenshots): #league=NHL&season=2025&y=doom&team=seattle-kraken
Run: python dashboard/build_scatter.py"""
import base64, json, os
import numpy as np
import pandas as pd
from plotly.offline import get_plotlyjs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # ADAM-DATA
DASH = os.path.join(ROOT, "dashboard")
DATA = os.path.join(DASH, "data")
LOGOS = os.path.join(DASH, "assets", "logos")
OUT = os.path.join(DASH, "doom_scatter.html")


def clean(v):
    if isinstance(v, (float, np.floating)):
        return None if np.isnan(v) else round(float(v), 3)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    return v


def build_data():
    P = pd.read_csv(os.path.join(DATA, "doom_predictions.csv"))
    D = pd.read_csv(os.path.join(DATA, "doom_drivers_long.csv"))
    C = pd.read_csv(os.path.join(DATA, "comparables.csv"))
    M = pd.read_csv(os.path.join(DATA, "team_meta.csv"))
    key = lambda r: f"{r.league}|{r.season_start_year}|{r.franchise_id}"

    # drivers: baseline = prediction - sum of all contributions (the model intercept, D104)
    drv = {}
    for k, g in D.groupby(["league", "season_start_year", "franchise_id"]):
        drv["|".join(map(str, k))] = {"sum": float(g.contribution.sum()),
                                      "items": [[r.feature_label, round(float(r.contribution), 2)]
                                                for r in g.reindex(g.contribution.abs().sort_values(ascending=False).index)
                                                .itertuples() if abs(r.contribution) >= 0.05]}
    comps = {}
    for k, g in C.groupby(["league", "season_start_year", "franchise_id"]):
        comps["|".join(map(str, k))] = [{c: clean(v) for c, v in r.items()} for r in
                                        g.sort_values("comp_rank").drop(columns=["league", "season_start_year",
                                                                                 "franchise_id"]).to_dict("records")]
    rows = []
    keep = ["league", "season_start_year", "franchise_id", "team", "wins", "losses", "ot_losses", "games", "win_pct",
            "win_pct_percentile", "doom_pred", "doom_lo80", "doom_hi80", "interval_available", "p_doom75",
            "doom_band", "p_doomed", "b1_pred", "doom_vs_standing", "proj_pct_t1", "proj_pct_t2", "proj_pct_t3",
            "path_clipped", "pred_type", "actual_doom", "actual_pct_t1", "actual_pct_t2", "actual_pct_t3",
            "driver_note"]
    for r in P[keep].itertuples(index=False):
        d = {c: clean(v) for c, v in zip(keep, r)}
        k = key(r)
        d["key"] = k
        d["baseline"] = round(d["doom_pred"] - drv[k]["sum"], 2)
        d["drivers"] = drv[k]["items"]
        d["comps"] = comps.get(k, [])
        rows.append(d)

    logos, missing = {}, []
    for r in M.itertuples():
        f = os.path.join(LOGOS, f"{r.league}_{r.franchise_id}.svg")
        if os.path.exists(f):
            logos[f"{r.league}|{r.franchise_id}"] = "data:image/svg+xml;base64," + base64.b64encode(
                open(f, "rb").read()).decode()
        else:
            missing.append(f"{r.league} {r.franchise_id}")
    return {"rows": rows, "logos": logos}, missing


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Doom Score Scatter</title>
<style>
:root{--bg:#f7f7f5;--card:#ffffff;--ink:#1d2329;--muted:#5f6b76;--line:#d9dde1;--accent:#2f5d8a;
--low:#3f7d4e;--mod:#a07d12;--high:#c4621c;--vhigh:#b02a2a;--na:#8a939b;--up:#c4621c;--down:#2f6db0}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
header{padding:16px 20px 6px}
h1{font-size:22px;margin:0 0 2px}
.sub{color:var(--muted);margin:0;max-width:980px}
.controls{display:flex;flex-wrap:wrap;gap:16px;align-items:center;padding:10px 20px;border-bottom:1px solid var(--line)}
.controls label{font-weight:600;margin-right:6px}
select,button{font:inherit}
select{padding:4px 8px;border:1px solid var(--line);border-radius:6px;background:#fff}
.seg{display:inline-flex;border:1px solid var(--line);border-radius:6px;overflow:hidden}
.seg button{border:0;background:#fff;padding:5px 10px;cursor:pointer;color:var(--ink)}
.seg button[aria-pressed="true"]{background:var(--accent);color:#fff}
.season{display:flex;align-items:center;gap:8px}
.season input{width:220px}
.tag{display:inline-block;font-size:12px;padding:1px 8px;border-radius:10px;border:1px solid var(--line);color:var(--muted)}
main{display:grid;grid-template-columns:minmax(0,1fr) 270px;gap:12px;padding:12px 20px 20px}
main.open{grid-template-columns:minmax(0,1fr) 400px}
#chart{background:var(--card);border:1px solid var(--line);border-radius:10px;height:640px;min-width:0}
aside{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px;overflow:auto;max-height:640px}
.lists h2{font-size:14px;margin:4px 0 6px}
.lists ol{list-style:none;margin:0 0 14px;padding:0}
.lists li{display:flex;align-items:center;gap:8px;padding:5px 4px;border-radius:6px;cursor:pointer}
.lists li:hover,.lists li:focus{background:#eef2f6;outline:none}
.lists img{width:22px;height:22px;object-fit:contain}
.lists .nm{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.num{font-variant-numeric:tabular-nums;font-weight:600}
.chip{display:inline-block;font-size:11px;font-weight:600;color:#fff;padding:1px 7px;border-radius:9px;white-space:nowrap}
.b-Low{background:var(--low)}.b-Moderate{background:var(--mod)}.b-High{background:var(--high)}.b-Very-high{background:var(--vhigh)}.b-Not-available{background:var(--na)}
.bar{position:relative;height:10px;background:#eceff2;border-radius:5px;margin:4px 0 2px}
.bar .seg80{position:absolute;top:0;bottom:0;background:#9fb6cf;border-radius:5px}
.bar .pt{position:absolute;top:-3px;width:4px;height:16px;margin-left:-2px;background:var(--ink);border-radius:2px}
.barlbl{display:flex;justify-content:space-between;font-size:11px;color:var(--muted)}
.na{font-size:12px;color:var(--muted);font-style:italic}
#tip{position:fixed;pointer-events:none;z-index:10;background:#fff;border:1px solid var(--line);border-radius:8px;
box-shadow:0 4px 14px rgba(0,0,0,.12);padding:8px 10px;width:250px;display:none;font-size:13px}
#tip .t{font-weight:700}
#tip .m{color:var(--muted);font-size:12px}
aside.panel{max-height:none}
.panel h2{font-size:18px;margin:0}
.panel .hd{display:flex;align-items:center;gap:10px;margin-bottom:8px}
.panel .hd img{width:44px;height:44px;object-fit:contain}
.panel .x{margin-left:auto;border:1px solid var(--line);background:#fff;border-radius:6px;cursor:pointer;padding:2px 9px;font-size:16px}
.big{font-size:34px;font-weight:700;line-height:1}
.verdict{background:#f2f4f6;border-radius:8px;padding:8px 10px;margin:10px 0}
.panel h3{font-size:13px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);margin:14px 0 6px}
.drv{display:grid;grid-template-columns:1fr 150px 44px;gap:6px;align-items:center;font-size:12.5px;margin:3px 0}
.drv .track{position:relative;height:12px}
.drv .track:before{content:"";position:absolute;left:50%;top:-3px;bottom:-3px;border-left:1px solid #b7bec5}
.drv .fill{position:absolute;top:0;bottom:0}
.drv.base,.drv.total{font-weight:600}
.cmp{border-top:1px solid var(--line);padding:6px 0;font-size:13px}
.cmp:first-of-type{border-top:0}
button.diag{margin-top:14px;width:100%;padding:8px;border:1px dashed var(--line);background:#f4f5f6;color:var(--muted);border-radius:8px;cursor:not-allowed}
.note{font-size:12px;color:var(--muted)}
@media (max-width:900px){main,main.open{grid-template-columns:1fr}#chart{height:520px}}
</style>
</head>
<body>
<header>
  <h1>Doom Score: who is headed for the bottom of the league?</h1>
  <p class="sub">Doom = 100 minus a team's average league percentile over the next three seasons (0 = top of the league all three years, 100 = bottom all three). Each logo is one team; past seasons show out-of-sample backtest predictions.</p>
</header>
<div class="controls" role="toolbar" aria-label="Chart controls">
  <div><label for="league">League</label><select id="league"><option>MLB</option><option selected>NHL</option><option value="All">All</option></select></div>
  <div class="season"><label for="season">Season</label><input id="season" type="range" step="1"><span id="seasonLbl" class="num"></span> <span id="typeTag" class="tag"></span></div>
  <div><span style="font-weight:600;margin-right:6px" id="ylbl">Y-axis</span><span class="seg" role="group" aria-labelledby="ylbl">
    <button id="yDoom" aria-pressed="true">Doom score</button><button id="yDiff" aria-pressed="false">Doom vs. standing</button></span></div>
</div>
<main id="main">
  <div id="chart" role="img" aria-label="Scatter plot of current win percentage against predicted doom, one logo per team"></div>
  <aside id="side"></aside>
</main>
<div id="tip" role="tooltip"></div>
<script>__PLOTLY__</script>
<script>
const DATA = __DATA__;
const ROWS = DATA.rows, LOGOS = DATA.logos;
const BAND_ORDER = {"Low":0,"Moderate":1,"High":2,"Very high":3,"Not available":-1};
const state = {league:"NHL", season:null, y:"doom", sel:null};
const $ = id => document.getElementById(id);
const fmt = (v, d=0) => v==null ? "—" : Number(v).toFixed(d);
const pct = v => v==null ? "—" : Math.round(v*100) + "%";
const ord = n => {n=Math.round(n); const s=["th","st","nd","rd"], v=n%100; return n+(s[(v-20)%10]||s[v]||s[0]);};
const seasonsOf = lg => [...new Set(ROWS.filter(r => lg==="All" || r.league===lg).map(r => r.season_start_year))].sort((a,b)=>a-b);
const seasonText = (lg, y) => lg==="NHL" ? `${y}–${String(y+1).slice(2)}` : lg==="MLB" ? `${y}` : `${y} (NHL ${y}–${String(y+1).slice(2)})`;
const record = r => r.league==="NHL" ? `${r.wins}–${r.losses}–${r.ot_losses}` : `${r.wins}–${r.losses}`;
const wp = r => r.league==="NHL" ? `points % ${r.win_pct.toFixed(3).replace(/^0/,"")}` : `win % ${r.win_pct.toFixed(3).replace(/^0/,"")}`;
const chip = b => `<span class="chip b-${b.replace(/ /g,"-")}">${b}</span>`;
const logo = r => LOGOS[r.league+"|"+r.franchise_id];
function rangeBar(r){
  if(!r.interval_available) return `<div class="na">range not available</div>`;
  return `<div class="bar" aria-label="80% range ${fmt(r.doom_lo80)} to ${fmt(r.doom_hi80)}"><div class="seg80" style="left:${r.doom_lo80}%;width:${r.doom_hi80-r.doom_lo80}%"></div><div class="pt" style="left:${r.doom_pred}%"></div></div><div class="barlbl"><span>80% range ${fmt(r.doom_lo80)}–${fmt(r.doom_hi80)}</span><span>0–100</span></div>`;
}
function topDriver(r){
  if(r.league==="MLB") return "Based on current standing only";
  const d = r.drivers[0]; return d ? `Top driver: ${d[0]} (${d[1]>0?"+":""}${d[1].toFixed(1)})` : "";
}
function view(){
  const rows = ROWS.filter(r => (state.league==="All" || r.league===state.league) && r.season_start_year===state.season);
  return rows;
}
function xOf(r){ return state.league==="All" ? r.win_pct_percentile : r.win_pct; }
function yOf(r){ return state.y==="doom" ? r.doom_pred : r.doom_vs_standing; }
function median(a){ const s=[...a].sort((x,y)=>x-y), m=Math.floor(s.length/2); return s.length%2? s[m] : (s[m-1]+s[m])/2; }
function axisRanges(){
  const pool = ROWS.filter(r => state.league==="All" || r.league===state.league);
  let xr;
  if(state.league==="All") xr = [-6,106];
  else { const xs = pool.map(r=>r.win_pct); const lo=Math.min(...xs), hi=Math.max(...xs), p=(hi-lo)*0.05; xr=[lo-p,hi+p]; }
  let yr;
  if(state.y==="doom"){ const ys = pool.map(r=>r.doom_pred); yr=[Math.min(5, Math.min(...ys)-6), Math.max(95, Math.max(...ys)+6)]; yr=[Math.max(-2,yr[0]), Math.min(102,yr[1])]; }
  else { const m = Math.max(10, ...pool.map(r=>Math.abs(r.doom_vs_standing))) + 3; yr=[-m, m]; }
  return [xr, yr];
}
const MARGIN = {l:70, r:20, t:20, b:62};
function render(){
  const rows = view(), [xr, yr] = axisRanges(), el = $("chart");
  const willOpen = !!(state.sel && rows.find(r => r.key===state.sel));
  $("main").classList.toggle("open", willOpen);          // set the grid first so the chart gets its final width
  const W = el.clientWidth - MARGIN.l - MARGIN.r, H = el.clientHeight - MARGIN.t - MARGIN.b;
  const px = state.league==="All" ? 28 : 34;
  const dx = (xr[1]-xr[0]) * px / W, dy = (yr[1]-yr[0]) * px / H;
  const selKey = state.sel && rows.find(r => r.key===state.sel) ? state.sel : null;
  const op = r => !selKey || r.key===selKey ? 1 : 0.22;
  const noLogo = rows.filter(r => !logo(r));
  const trace = {type:"scatter", mode:"markers", x:rows.map(xOf), y:rows.map(yOf), customdata:rows.map(r=>r.key),
    hoverinfo:"none", marker:{size:px+8, color:"rgba(255,255,255,0.92)", line:{color:"#9aa3ad", width:1.2}, opacity:rows.map(op)}};
  const labels = {type:"scatter", mode:"text", x:noLogo.map(xOf), y:noLogo.map(yOf), text:noLogo.map(r=>r.team.split(" ").pop()),
    textposition:"middle center", textfont:{size:9}, hoverinfo:"skip"};
  const images = rows.filter(logo).map(r => ({source:logo(r), xref:"x", yref:"y", x:xOf(r), y:yOf(r), sizex:dx*0.94, sizey:dy*0.94,
    xanchor:"center", yanchor:"middle", sizing:"contain", layer:"above", opacity:op(r)}));
  const xm = state.league==="All" ? 50 : median(rows.map(r=>r.win_pct));
  const ym = state.y==="doom" ? 50 : 0;
  const shapes = [
    {type:"line", xref:"x", yref:"paper", x0:xm, x1:xm, y0:0, y1:1, line:{dash:"dash", color:"#a3abb3", width:1}},
    {type:"line", xref:"paper", yref:"y", x0:0, x1:1, y0:ym, y1:ym, line:{dash:"dash", color:"#a3abb3", width:1}}];
  if(selKey){ const r = rows.find(r=>r.key===selKey); const rx=dx*0.75, ry=dy*0.75;
    shapes.push({type:"circle", xref:"x", yref:"y", x0:xOf(r)-rx, x1:xOf(r)+rx, y0:yOf(r)-ry, y1:yOf(r)+ry, line:{color:"#1d2329", width:3}}); }
  const corner = (x, y, t, xa, ya) => ({xref:"paper", yref:"paper", x, y, text:t, showarrow:false, xanchor:xa, yanchor:ya,
    font:{size:13, color:"#9aa3ad"}});
  const ann = state.y==="doom" ? [corner(0.01,0.99,"Stuck<br><span style='font-size:11px'>bad now, high doom</span>","left","top"),
      corner(0.99,0.99,"Cliff ahead<br><span style='font-size:11px'>good now, high doom</span>","right","top"),
      corner(0.01,0.01,"Rising<br><span style='font-size:11px'>bad now, low doom</span>","left","bottom"),
      corner(0.99,0.01,"Contender<br><span style='font-size:11px'>good now, low doom</span>","right","bottom")]
    : [corner(0.5,0.99,"More doomed than current standing alone suggests","center","top"),
       corner(0.5,0.01,"Less doomed than current standing alone suggests","center","bottom")];
  if(state.y==="diff" && rows.some(r=>r.league==="MLB")) ann.push({xref:"paper", yref:"paper", x:0.5, y:0.08, showarrow:false,
      text:"MLB points sit at 0: the MLB score is the standing-only model", font:{size:12, color:"#5f6b76"}});
  const xt = state.league==="All" ? "Current standing (league percentile, 0 = worst, 100 = best)" :
    state.league==="NHL" ? "Points % this season (points ÷ (2 × games))" : "Win % this season";
  const yt = state.y==="doom" ? "Predicted doom (0–100, higher = more doomed)" : "Doom vs. standing (doom points above the standing-only prediction)";
  const layout = {width:el.clientWidth, height:el.clientHeight, margin:MARGIN, paper_bgcolor:"#ffffff", plot_bgcolor:"#ffffff", showlegend:false, images, shapes, annotations:ann,
    xaxis:{title:{text:xt}, range:xr, zeroline:false, gridcolor:"#eef0f2", tickformat: state.league==="All" ? "d" : ".3f", fixedrange:true},
    yaxis:{title:{text:yt}, range:yr, zeroline:false, gridcolor:"#eef0f2", fixedrange:true}, dragmode:false, hovermode:"closest"};
  Plotly.react(el, [trace, labels], layout, {displayModeBar:false, responsive:false});
  renderSide(rows);
  const r0 = rows[0]; $("seasonLbl").textContent = seasonText(state.league, state.season);
  const types = [...new Set(rows.map(r=>r.pred_type))];
  $("typeTag").textContent = types.includes("live") ? "Live prediction" : "Backtest (out-of-sample)";
  writeHash();
}
function listHTML(rows, title){
  return `<h2>${title}</h2><ol>` + rows.map(r => `<li tabindex="0" data-key="${r.key}" aria-label="${r.team}, doom ${fmt(r.doom_pred)}">
    ${logo(r)?`<img alt="" src="${logo(r)}">`:""}<span class="nm">${r.team}${state.league==="All"?` <span class="note">${r.league}</span>`:""}</span>
    <span class="num">${fmt(r.doom_pred)}</span>${chip(r.doom_band)}</li>`).join("") + `</ol>`;
}
function renderSide(rows){
  const main = $("main"), side = $("side");
  const r = state.sel && rows.find(x => x.key===state.sel);
  if(!r){ main.classList.remove("open");
    const s = [...rows].sort((a,b)=>b.doom_pred-a.doom_pred);
    side.className = "lists"; side.innerHTML = listHTML(s.slice(0,5), "Most doomed") + listHTML(s.slice(-5).reverse(), "Least doomed") +
      `<p class="note">Bands are the chance of ending at doom ≥ 75: Low &lt; 10%, Moderate 10–30%, High 30–50%, Very high ≥ 50%.</p>`;
    side.querySelectorAll("li").forEach(li => { li.onclick = () => select(li.dataset.key);
      li.onkeydown = e => { if(e.key==="Enter"||e.key===" "){ e.preventDefault(); select(li.dataset.key);} }; });
    return; }
  main.classList.add("open"); side.className = "panel"; side.innerHTML = panelHTML(r, rows);
  $("closeP").onclick = () => select(null);
}
function verdict(r, rows){
  const good = state.league==="All" ? r.win_pct_percentile>=50 : r.win_pct >= median(rows.map(x=>x.win_pct));
  const high = r.doom_pred >= 50;
  const q = good ? (high ? "Cliff ahead" : "Contender") : (high ? "Stuck" : "Rising");
  let t = `<b>${q}.</b> ${good?"Above":"Below"} the league median now (${ord(r.win_pct_percentile)} percentile); expected to average about the ${ord(100-r.doom_pred)} percentile over the next three seasons.`;
  if(r.p_doom75!=null) t += ` ${pct(r.p_doom75)} chance of a bottom-quarter three years (doom ≥ 75).`;
  return t;
}
function driversHTML(r){
  const items = r.drivers.slice(0,6), rest = r.drivers.slice(6).reduce((s,d)=>s+d[1],0) + (r.doom_pred - r.baseline - r.drivers.reduce((s,d)=>s+d[1],0));
  const all = items.concat(Math.abs(rest)>=0.05 ? [["Other factors", Math.round(rest*100)/100]] : []);
  const m = Math.max(5, ...all.map(d=>Math.abs(d[1])));
  const row = (lbl, v) => { const w = Math.abs(v)/m*50, left = v>=0 ? 50 : 50-w, col = v>=0 ? "var(--up)" : "var(--down)";
    return `<div class="drv"><span>${lbl}</span><span class="track"><span class="fill" style="left:${left}%;width:${w}%;background:${col}"></span></span><span class="num" style="text-align:right">${v>0?"+":""}${v.toFixed(1)}</span></div>`; };
  let h = `<div class="drv base"><span>League baseline</span><span></span><span class="num" style="text-align:right">${fmt(r.baseline,1)}</span></div>`;
  h += all.map(d => row(d[0], d[1])).join("");
  h += `<div class="drv total"><span>= Predicted doom</span><span></span><span class="num" style="text-align:right">${fmt(r.doom_pred,1)}</span></div>`;
  h += `<p class="note">Orange pushes doom up, blue pulls it down (doom points). The baseline is the model's starting point for an average team.</p>`;
  if(r.league==="MLB") h += `<p class="note">${r.driver_note}</p>`;
  return h;
}
function pathSVG(r){
  const W=360, H=150, L=34, R=24, T=12, B=26, xs=[0,1,2,3].map(i => L + i*(W-L-R)/3), y = v => T + (100-v)/100*(H-T-B);
  const proj = [r.win_pct_percentile, r.proj_pct_t1, r.proj_pct_t2, r.proj_pct_t3];
  const act = [r.win_pct_percentile, r.actual_pct_t1, r.actual_pct_t2, r.actual_pct_t3];
  const yr = i => r.league==="NHL" ? `${String(r.season_start_year+i).slice(2)}–${String(r.season_start_year+i+1).slice(2)}` : `${r.season_start_year+i}`;
  let s = `<svg width="100%" viewBox="0 0 ${W} ${H}" role="img" aria-label="Projected league percentile for the next three seasons">`;
  [0,25,50,75,100].forEach(v => s += `<line x1="${L}" x2="${W-R}" y1="${y(v)}" y2="${y(v)}" stroke="#eef0f2"/><text x="${L-6}" y="${y(v)+4}" font-size="10" text-anchor="end" fill="#5f6b76">${v}</text>`);
  xs.forEach((x,i) => s += `<text x="${x}" y="${H-8}" font-size="10" text-anchor="middle" fill="#5f6b76">${i===0?"now ":""}${yr(i)}</text>`);
  const line = (vals, dash, col) => { const pts = vals.map((v,i)=>v==null?null:[xs[i],y(v)]).filter(Boolean);
    return pts.length>1 ? `<polyline fill="none" stroke="${col}" stroke-width="2.2" ${dash?'stroke-dasharray="5 4"':""} points="${pts.map(p=>p.join(",")).join(" ")}"/>` + pts.map(p=>`<circle cx="${p[0]}" cy="${p[1]}" r="3.2" fill="${col}"/>`).join("") : ""; };
  s += line(proj, true, "#2f5d8a");
  if(act.slice(1).some(v=>v!=null)) s += line(act, false, "#1d2329");
  s += `</svg><p class="note">Dashed: projected percentile (100 = best). ${act.slice(1).some(v=>v!=null)?"Solid: what actually happened. ":""}${r.path_clipped?"Path clipped to 0–100.":""}</p>`;
  return s;
}
function compsHTML(r){
  if(!r.comps.length) return `<p class="note">No earlier comparable seasons.</p>`;
  return r.comps.map(c => { const lg=r.league; const yr = lg==="NHL" ? `${c.comp_season}–${String(c.comp_season+1).slice(2)}` : c.comp_season;
    const rec = c.comp_ot_losses!=null ? `${c.comp_wins}–${c.comp_losses}–${c.comp_ot_losses}` : `${c.comp_wins}–${c.comp_losses}`;
    return `<div class="cmp"><b>${c.comp_team} ${yr}</b> <span class="note">(${rec}, ${ord(c.comp_win_pct_percentile)} percentile)</span><br>
      Next three seasons: ${[c.comp_pct_t1,c.comp_pct_t2,c.comp_pct_t3].map(v=>ord(v)).join(" → ")} percentile · actual doom <b>${fmt(c.comp_actual_doom)}</b>
      <span class="note">· difference ${fmt(c.distance,1)} pts</span></div>`; }).join("") +
    `<p class="note">Most similar earlier team-seasons (outcome known at prediction time) on the team-profile percentiles; context, not model inputs.</p>`;
}
function panelHTML(r, rows){
  const sl = seasonText(r.league, r.season_start_year);
  return `<div class="hd">${logo(r)?`<img alt="" src="${logo(r)}">`:""}<div><h2>${r.team}</h2><div class="note">${r.league} ${sl} · ${record(r)} · ${wp(r)} · ${r.pred_type==="live"?"live":"backtest"}</div></div>
    <button class="x" id="closeP" aria-label="Close details">×</button></div>
    <div style="display:flex;align-items:baseline;gap:10px"><span class="big">${fmt(r.doom_pred)}</span><span>doom</span>${chip(r.doom_band)}
    ${r.p_doom75!=null?`<span class="note">${pct(r.p_doom75)} chance of doom ≥ 75</span>`:""}</div>${rangeBar(r)}
    <div class="verdict">${verdict(r, rows)}</div>
    <h3>What drives the score</h3>${driversHTML(r)}
    <h3>3-year path</h3>${pathSVG(r)}
    ${r.actual_doom!=null?`<p class="note">Actual doom: <b>${fmt(r.actual_doom)}</b></p>`:""}
    <h3>Comparable seasons</h3>${compsHTML(r)}
    <button class="diag" disabled aria-disabled="true">Full diagnostics (coming soon)</button>`;
}
function tipHTML(r){
  return `<div class="t">${r.team} <span class="m">${seasonText(r.league, r.season_start_year)}</span></div>
    <div>${record(r)} · ${wp(r)}</div>
    <div>Doom <b>${fmt(r.doom_pred)}</b> ${chip(r.doom_band)}</div>
    ${rangeBar(r)}
    <div class="m">${topDriver(r)}</div>
    <div class="m" style="margin-top:3px"><i>Click for details</i></div>`;
}
const BYKEY = Object.fromEntries(ROWS.map(r=>[r.key, r]));
function select(key){ state.sel = key; render(); }
function writeHash(){ const h = `league=${state.league}&season=${state.season}&y=${state.y}` + (state.sel?`&team=${state.sel.split("|")[2]}`:"");
  history.replaceState(null, "", "#"+h); }
function setSeasonSlider(keep){
  const ss = seasonsOf(state.league), s = $("season");
  s.min = ss[0]; s.max = ss[ss.length-1];
  if(!keep || !ss.includes(state.season)) state.season = ss[ss.length-1];
  s.value = state.season;
}
function init(){
  const h = Object.fromEntries(location.hash.slice(1).split("&").filter(Boolean).map(p=>p.split("=")));
  if(["MLB","NHL","All"].includes(h.league)) state.league = h.league;
  if(h.y==="diff") state.y = "diff";
  $("league").value = state.league;
  state.season = h.season ? +h.season : null;
  setSeasonSlider(!!h.season);
  if(h.team){ const lg = state.league==="All" ? null : state.league;
    const r = ROWS.find(r => r.franchise_id===h.team && r.season_start_year===state.season && (!lg || r.league===lg)); if(r) state.sel = r.key; }
  $("yDoom").setAttribute("aria-pressed", state.y==="doom"); $("yDiff").setAttribute("aria-pressed", state.y==="diff");
  $("league").onchange = e => { state.league = e.target.value; state.sel = null; setSeasonSlider(true); render(); };
  $("season").oninput = e => { state.season = +e.target.value; render(); };
  $("yDoom").onclick = () => { state.y="doom"; $("yDoom").setAttribute("aria-pressed","true"); $("yDiff").setAttribute("aria-pressed","false"); render(); };
  $("yDiff").onclick = () => { state.y="diff"; $("yDiff").setAttribute("aria-pressed","true"); $("yDoom").setAttribute("aria-pressed","false"); render(); };
  render();
  const el = $("chart"), tip = $("tip");
  if(h.tip){ // review aid: show the hover card for one team without a mouse (used for report screenshots)
    const r = view().find(r => r.franchise_id===h.tip); if(r){ const [xr, yr] = axisRanges(), b = el.getBoundingClientRect();
      const X = b.left + MARGIN.l + (xOf(r)-xr[0])/(xr[1]-xr[0])*(el.clientWidth-MARGIN.l-MARGIN.r);
      const Y = b.top + MARGIN.t + (yr[1]-yOf(r))/(yr[1]-yr[0])*(el.clientHeight-MARGIN.t-MARGIN.b);
      tip.innerHTML = tipHTML(r); tip.style.display = "block"; tip.style.left = (X+18)+"px"; tip.style.top = (Y+10)+"px"; } }
  el.on("plotly_hover", ev => { const p = ev.points[0]; if(p.curveNumber!==0) return; const r = BYKEY[p.customdata];
    tip.innerHTML = tipHTML(r); tip.style.display = "block";
    const x = ev.event.clientX + 14, y = ev.event.clientY + 14;
    tip.style.left = Math.min(x, window.innerWidth - 270) + "px"; tip.style.top = Math.min(y, window.innerHeight - tip.offsetHeight - 8) + "px"; });
  el.on("plotly_unhover", () => { tip.style.display = "none"; });
  el.on("plotly_click", ev => { const p = ev.points[0]; if(p.curveNumber!==0) return; tip.style.display="none"; select(p.customdata); });
  document.addEventListener("keydown", e => { if(e.key==="Escape" && state.sel) select(null); });
  let t; window.addEventListener("resize", () => { clearTimeout(t); t = setTimeout(render, 150); });
}
init();
</script>
</body>
</html>
"""


def main():
    data, missing = build_data()
    html = TEMPLATE.replace("__PLOTLY__", get_plotlyjs()).replace("__DATA__", json.dumps(data, separators=(",", ":")))
    open(OUT, "w", encoding="utf-8").write(html)
    print(f"{OUT}: {len(html) / 1e6:.1f} MB; rows {len(data['rows'])}; logos {len(data['logos'])}; missing logos {missing}")


if __name__ == "__main__":
    main()
