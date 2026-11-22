"use strict";
// FLY dashboard: intentionally consumes only the local paper account + read-only quotes.
const $ = id => document.getElementById(id);
const money = cents => (cents / 100).toLocaleString("en-US", { style: "currency", currency: "USD" });
const usd = dollars => typeof dollars === "number" && Number.isFinite(dollars) ? dollars.toLocaleString("en-US",{style:"currency",currency:"USD"}) : "—";
const pct = n => (Number.isFinite(n) ? n.toFixed(1) : "0.0") + "%";
const palette = ["#4fd4b5","#769fff","#ebc37c","#bd93ed","#e38fa3","#70c8d1","#a7b4c8"];
let currentState = null;
let currentRisk = null;
let selectedShock = "mild";
let currentView = "overview";
const pages = {
  overview:["Overview","Portfolio overview","A unified view of positions, exposure, and decision support."],
  portfolio:["Portfolio","Portfolio inventory","Review positions and execute simulated orders."],
  risk:["Risk analytics","Risk analytics","Transparent exposure and deterministic what-if scenarios."],
  markets:["Market monitor","Market monitor","Read-only quotes and clear data provenance."],
  activity:["Audit trail","Activity & audit","Recorded paper orders, with no live brokerage activity."]
};
function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = String(text);
  if (className) element.className = className;
  return element;
}
function emptyRow(cols, text) {
  const tr = node("tr");
  const td = node("td", text, "empty");
  td.colSpan = cols;
  tr.append(td);
  return tr;
}
function changeView(name) {
  if (!pages[name]) return;
  currentView = name;
  for (const b of document.querySelectorAll(".nav-item")) b.classList.toggle("selected", b.dataset.view === name);
  for (const v of document.querySelectorAll(".view")) v.classList.toggle("active", v.id === "view-" + name);
  $("crumb").textContent = pages[name][0];
  $("pageTitle").textContent = pages[name][1];
  $("pageSubtitle").textContent = pages[name][2];
}
function updateClock() {
  const d = new Date();
  $("clock").textContent = new Intl.DateTimeFormat("en-US",{hour:"2-digit",minute:"2-digit",timeZoneName:"short"}).format(d);
}
function tableHoldings(target, state) {
  const tbody = $(target);
  tbody.replaceChildren();
  const sorted = [...state.positions].sort((a,b) => b.qty*b.last_cents-a.qty*a.last_cents);
  if (!sorted.length) { tbody.append(emptyRow(5,"No simulated holdings yet — create a paper order to begin.")); return; }
  for (const p of sorted) {
    const tr = node("tr");
    for (const item of [p.symbol, p.qty.toLocaleString("en-US"), money(p.last_cents),money(p.qty*p.last_cents),pct((p.qty*p.last_cents/state.equity_cents)*100)]) tr.append(node("td",item));
    tbody.append(tr);
  }
}
function setComposition(state, risk) {
  const parts = [{name:"Cash",amount:state.cash_cents,weight:risk.cash_weight_pct,color:palette[0]}];
  risk.weights.forEach((h,i) => parts.push({name:h.symbol,amount:h.market_value_cents,weight:h.portfolio_weight_pct,color:palette[(i+1)%palette.length]}));
  let start = 0;
  const segments = [];
  for (const part of parts) {
    const stop = Math.min(100,start + 100*part.amount/state.equity_cents);
    segments.push(part.color+" "+start.toFixed(4)+"% "+stop.toFixed(4)+"%");
    start = stop;
  }
  $("donut").style.background = "conic-gradient("+segments.join(",")+")";
  $("donutEquity").textContent = money(state.equity_cents);
  const list=$("allocationList"); list.replaceChildren();
  for(const part of parts.slice(0,7)){
    const item=node("div",undefined,"allocation-item");
    const name=node("div",undefined,"allocation-name");
    const swatch=node("span",undefined,"swatch");swatch.style.background=part.color;
    name.append(swatch,node("span",part.name));
    const val=node("div",pct(100*part.amount/state.equity_cents),"allocation-value");
    item.append(name,val);list.append(item);
  }
}
function setScenarios(state, risk) {
  const s=risk.scenarios.find(s=>s.id===selectedShock) || risk.scenarios[0];
  $("stressEquity").textContent=money(s.hypothetical_equity_cents);
  $("stressDelta").textContent=money(s.hypothetical_loss_cents)+" illustrative value change";
  $("stressBar").style.width=Math.max(0,Math.min(100,(s.hypothetical_equity_cents / state.equity_cents)*100))+"%";
  document.querySelectorAll(".shock").forEach(b=>b.classList.toggle("active",b.dataset.shock===selectedShock));
}
function setWeights(state,risk){
  const root=$("riskWeights");root.replaceChildren();
  const items=[{name:"Cash",weight:risk.cash_weight_pct,color:palette[0]},...risk.weights.map((w,i)=>({name:w.symbol,weight:w.portfolio_weight_pct,color:palette[(i+1)%palette.length]}))];
  for(const item of items){
    const wrap=node("div",undefined,"weight-item");
    const head=node("div");head.append(node("span",item.name),node("b",pct(item.weight)));
    const track=node("div",undefined,"weight-track");
    const fill=node("div",undefined,"weight-fill");
    fill.style.width=Math.max(0,Math.min(100,item.weight))+"%"; fill.style.background=item.color;
    track.append(fill);wrap.append(head,track);root.append(wrap);
  }
}
function setAudit(events) {
  const root=$("history");root.replaceChildren();
  if (!events.length) {root.append(emptyRow(6,"No simulator orders recorded."));return;}
  for(const evt of events){
    const p=evt.payload;
    const tr=node("tr");
    const cols=[evt.created+" UTC",p.side,p.symbol,p.qty,money(p.hypothetical_price_cents),money(p.notional_cents)];
    for(const c of cols) tr.append(node("td",c));
    root.append(tr);
  }
}
function updateUi(state,risk){
  currentState=state;currentRisk=risk;
  $("equity").textContent=money(state.equity_cents);
  $("cash").textContent=money(state.cash_cents);
  $("exposure").textContent=money(risk.gross_exposure_cents);
  $("cashPct").textContent=pct(risk.cash_weight_pct);
  $("investedPct").textContent=pct(risk.invested_weight_pct);
  $("concentration").textContent=pct(risk.largest_position_pct);
  $("positionsCount").textContent=String(risk.position_count);
  $("asof").textContent=new Intl.DateTimeFormat("en-US",{hour:"2-digit",minute:"2-digit",second:"2-digit"}).format(new Date());
  $("providerStatus").textContent=state.market_data_configured?"CONFIGURED (UNVERIFIED)":"NOT CONFIGURED";
  $("marketProvider").textContent=state.market_data_configured?"Credentials present; quote access not yet proven":"Not configured";
  $("navAlpaca").textContent=state.market_data_configured?"CONFIGURED":"NOT CONNECTED";
  $("navAlpaca").className=state.market_data_configured?"sys-ok":"sys-off";
  tableHoldings("holdingsOverview",state);
  tableHoldings("holdingsFull",state);
  setComposition(state,risk);
  setScenarios(state,risk);
  setWeights(state,risk);
  setAudit(state.events);
}
function renderPaperHistory(h){
  const root=$("paperChart");root.replaceChildren();
  const points=h.points || [];
  $("markCount").textContent=points.length+" OBSERVATION"+(points.length===1?"":"S");
  if(!points.length){$("chartEmpty").hidden=false;return;}
  $("markStart").textContent="BASELINE "+money(points[0].equity_cents);
  $("markEnd").textContent="LATEST "+money(points[points.length-1].equity_cents);
  $("markDelta").textContent="CHANGE "+money(h.equity_change_cents);
  $("chartEmpty").hidden=points.length>1;
  if(points.length<2)return;
  const values=points.map(p=>p.equity_cents);
  const min=Math.min(...values),max=Math.max(...values),range=Math.max(max-min,1);
  const xy=points.map((p,i)=>[20+i*960/(points.length-1),138-(p.equity_cents-min)*116/range]);
  const ns="http://www.w3.org/2000/svg";
  function svg(tag,attributes){
    const el=document.createElementNS(ns,tag);
    for(const [k,v] of Object.entries(attributes))el.setAttribute(k,String(v));
    return el;
  }
  for(const y of [22,80,138])root.append(svg("line",{x1:20,x2:980,y1:y,y2:y,stroke:"#25394d","stroke-width":1}));
  const line=xy.map((p,i)=>(i?"L":"M")+p[0].toFixed(2)+","+p[1].toFixed(2)).join(" ");
  const area=line+" L980,147 L20,147 Z";
  root.append(svg("path",{d:area,fill:"#4fd4b5","fill-opacity":"0.08"}));
  root.append(svg("path",{d:line,fill:"none",stroke:"#4fd4b5","stroke-width":2.8,"stroke-linecap":"round","stroke-linejoin":"round"}));
  for(const [x,y] of xy.slice(-25))root.append(svg("circle",{cx:x,cy:y,r:3,fill:"#4fd4b5"}));
}
async function refresh(){
  const responses=await Promise.all([fetch("/api/state",{cache:"no-store"}),fetch("/api/risk",{cache:"no-store"}),fetch("/api/performance",{cache:"no-store"})]);
  if(responses.some(r=>!r.ok)) throw new Error("Portfolio, risk, or observation history unavailable");
  const [state,risk,history]=await Promise.all(responses.map(r=>r.json()));
  if(state.mode!=="SIMULATION ONLY" || state.broker_connected!==false) throw new Error("Unexpected environment: trading controls disabled");
  updateUi(state,risk);
  renderPaperHistory(history);
}
async function doOrder(event){
  event.preventDefault();
  const msg=$("message");msg.className="form-message";msg.textContent="Validating simulated order…";
  const fd=new FormData(event.currentTarget);
  const payload={symbol:String(fd.get("symbol")).trim().toUpperCase(),side:String(fd.get("side")),qty:Number(fd.get("qty")),price:String(fd.get("price"))};
  try{
    if(!currentState || currentState.broker_connected !== false) throw new Error("Paper environment was not verified");
    if(!Number.isSafeInteger(payload.qty) || payload.qty < 1) throw new Error("Enter a valid number of whole shares");
    const response=await fetch("/api/paper-orders",{
      method:"POST",
      headers:{"Content-Type":"application/json","X-Fly-Token":document.querySelector('meta[name="fly-token"]').content},
      body:JSON.stringify(payload)
    });
    const result=await response.json();
    if(!response.ok) throw new Error(result.error || "Paper order rejected");
    msg.className="form-message ok";msg.textContent="Recorded in the simulated portfolio. No brokerage order was sent.";
    await refresh();
  }catch(err){msg.className="form-message err";msg.textContent=err.message;}
}
async function doQuotes(event){
  event.preventDefault();
  const message=$("quoteMessage");message.className="form-message";message.textContent="Fetching read-only quotes…";
  const symbols=$("quoteSymbols").value.toUpperCase().split(",").map(s=>s.trim()).filter(Boolean);
  if(!symbols.length||symbols.length>10||symbols.some(s=>!/^[A-Z][A-Z0-9.]{0,9}$/.test(s))){
    message.className="form-message err";message.textContent="Enter 1–10 valid ticker symbols.";return;
  }
  try{
    const resp=await fetch("/api/quotes?symbols="+encodeURIComponent(symbols.join(","))+"&feed=iex",{cache:"no-store"});
    const result=await resp.json();
    if(!resp.ok) throw new Error(result.error || "Provider not available");
    const root=$("quoteRows");root.replaceChildren();
    if(!result.quotes.length)root.append(emptyRow(4,"No quotes returned by Alpaca."));
    for(const q of result.quotes){
      const tr=node("tr");
      for(const v of [q.symbol,usd(q.bid),usd(q.ask),q.timestamp || "—"])tr.append(node("td",v));
      root.append(tr);
    }
    message.className="form-message ok";message.textContent="Alpaca "+String(result.source).toUpperCase()+" feed · requested "+result.requested_at+" · read-only.";
  }catch(err){message.className="form-message err";message.textContent=err.message;}
}
document.querySelectorAll(".nav-item").forEach(b=>b.addEventListener("click",()=>changeView(b.dataset.view)));
document.querySelectorAll("[data-jump]").forEach(b=>b.addEventListener("click",()=>changeView(b.dataset.jump)));
document.querySelectorAll(".shock").forEach(b=>b.addEventListener("click",()=>{selectedShock=b.dataset.shock;if(currentRisk&&currentState)setScenarios(currentState,currentRisk)}));
$("order").addEventListener("submit",doOrder);
$("quoteForm").addEventListener("submit",doQuotes);
$("refresh").addEventListener("click",()=>refresh().catch(e=>{const m=$("message");m.textContent=e.message;m.className="form-message err"}));
$("logout").addEventListener("click",async()=>{
  const token=document.querySelector('meta[name="fly-token"]').content;
  try{const res=await fetch("/api/auth/logout",{method:"POST",headers:{"Content-Type":"application/json","X-Fly-Token":token},body:"{}"});if(!res.ok)throw new Error("Sign out failed");location.replace("/auth")}
  catch(e){alert(e.message)}
});
document.addEventListener("keydown",e=>{if(e.metaKey&&!e.shiftKey&&!e.altKey){const index=Number(e.key);if(index>=1&&index<=5){e.preventDefault();changeView(Object.keys(pages)[index-1])}}});
updateClock();setInterval(updateClock,60000);
refresh().catch(e=>{const m=$("message");m.className="form-message err";m.textContent=e.message});
setInterval(()=>{if(document.visibilityState==="visible")refresh().catch(()=>{})},30000);

const currency=v=>Number.isFinite(v)?v.toLocaleString("en-US",{style:"currency",currency:"USD"}):"—";
function renderMarketLine(bars){
  const root=$("marketChart");root.replaceChildren();
  $("marketEmpty").hidden=bars.length>1;
  if(!bars.length)return;
  $("marketFirst").textContent="FIRST "+currency(bars[0].close);
  $("marketLatest").textContent="LATEST "+currency(bars[bars.length-1].close);
  const change=(bars[bars.length-1].close/bars[0].close-1)*100;
  $("marketChange").textContent="CHANGE "+change.toFixed(2)+"% (raw)";
  if(bars.length<2)return;
  const values=bars.map(b=>b.close),min=Math.min(...values),max=Math.max(...values),range=Math.max(max-min,.000001);
  const coords=bars.map((b,i)=>[20+960*i/(bars.length-1),138-(b.close-min)*116/range]);
  const ns="http://www.w3.org/2000/svg";
  const svg=(name,attrs)=>{const el=document.createElementNS(ns,name);for(const [k,v] of Object.entries(attrs))el.setAttribute(k,String(v));return el};
  for(const y of [22,80,138])root.append(svg("line",{x1:20,x2:980,y1:y,y2:y,stroke:"#25394d"}));
  const d=coords.map((p,i)=>(i?"L":"M")+p[0].toFixed(2)+","+p[1].toFixed(2)).join(" ");
  root.append(svg("path",{d:d+" L980,145 L20,145 Z",fill:"#769fff","fill-opacity":".08"}));
  root.append(svg("path",{d,fill:"none",stroke:"#769fff","stroke-width":2.8,"stroke-linejoin":"round","stroke-linecap":"round"}));
}
function displayResearch(r){
  const box=$("researchMetrics");box.replaceChildren();
  const lines=[
    ["DATA","Alpaca "+r.feed.toUpperCase()+" · "+r.observations+" daily bars"],
    ["CLOSE",r.latest_close===undefined?"Not enough data":currency(r.latest_close)],
    ["OBSERVED CHANGE",r.observed_change_pct===undefined?"—":r.observed_change_pct.toFixed(2)+"% (unadjusted)"],
    ["20-DAY AVERAGE",r.sma20===null||r.sma20===undefined?"Insufficient history":currency(r.sma20)],
    ["50-DAY AVERAGE",r.sma50===null||r.sma50===undefined?"Insufficient history":currency(r.sma50)],
    ["ANNUALIZED VOLATILITY",r.sample_annualized_volatility_pct===undefined||r.sample_annualized_volatility_pct===null?"Insufficient history":r.sample_annualized_volatility_pct.toFixed(2)+"% · sample only"],
    ["MODEL", "Deterministic descriptive stats · no AI or forecasts"],
  ];
  for(const [label,value] of lines){const line=document.createElement("div");line.append(node("b",label),node("span",value));box.append(line)}
}
async function historicalLookup(e){
  e.preventDefault();
  const target=$("historicalMessage"),symbol=$("historySymbol").value.trim().toUpperCase(),days=Number($("historyDays").value);
  if(!/^[A-Z][A-Z0-9.]{0,9}$/.test(symbol)||![30,90,180,365].includes(days)){
    target.textContent="Enter a valid stock symbol and period.";target.className="form-message err";return;
  }
  target.textContent="Requesting read-only Alpaca daily bars…";target.className="form-message";
  try{
    const qs="?symbol="+encodeURIComponent(symbol)+"&days="+days+"&feed=iex";
    const [barsResponse,metricsResponse]=await Promise.all([
      fetch("/api/historical"+qs,{cache:"no-store"}),
      fetch("/api/research"+qs,{cache:"no-store"})
    ]);
    const [bars,metrics]=await Promise.all([barsResponse.json(),metricsResponse.json()]);
    if(!barsResponse.ok||!metricsResponse.ok)throw new Error(bars.error||metrics.error||"Historical feed unavailable");
    renderMarketLine(bars.bars);
    displayResearch(metrics);
    target.textContent=bars.bars.length+" Alpaca IEX daily bars · raw, unadjusted · information only, no trading.";
    target.className="form-message ok";
  }catch(err){target.textContent=err.message;target.className="form-message err"}
}
$("historicalForm").addEventListener("submit",historicalLookup);


async function runRiskLab(){
  const box=$("analyticsMetrics"),button=$("runAnalytics");
  button.disabled=true;
  box.replaceChildren(node("div","Loading aligned daily history…"));
  try{
    const days=Number($("analyticsDays").value);
    const response=await fetch("/api/analytics?days="+days,{cache:"no-store"});
    const result=await response.json();
    if(!response.ok)throw new Error(result.error||"Risk analytics unavailable");
    const entries=[
      ["STATUS",result.status],
      ["BENCHMARK",result.benchmark],
      ["ALIGNED DAILY RETURNS",String(result.aligned_observations)],
      ["PERIOD",result.first_date+" → "+result.last_date],
      ["PROXY BETA",result.beta_vs_benchmark===null?"—":String(result.beta_vs_benchmark)],
      ["MAX DRAWDOWN",result.max_drawdown_pct+"%"],
      ["PROXY VOLATILITY",result.proxy_portfolio.sample_daily_volatility_pct===undefined?"—":result.proxy_portfolio.sample_daily_volatility_pct+"% daily"],
      ["BENCHMARK VOLATILITY",result.benchmark_stats.sample_daily_volatility_pct===undefined?"—":result.benchmark_stats.sample_daily_volatility_pct+"% daily"],
      ["CORRELATION",JSON.stringify(result.correlation_to_benchmark)],
      ["SECTOR EXPOSURE","UNCLASSIFIED"]
    ];
    box.replaceChildren();
    for(const [label,value] of entries){const row=document.createElement("div");row.append(node("b",label),node("span",String(value)));box.append(row)}
  }catch(error){box.replaceChildren(node("div",error.message))}
  finally{button.disabled=false}
}
$("runAnalytics").addEventListener("click",runRiskLab);


async function loadIntelligence(){
 const box=$("intelligenceMetrics"),button=$("loadIntelligence");button.disabled=true;
 try{
  const response=await fetch("/api/intelligence",{cache:"no-store"}),data=await response.json();
  if(!response.ok)throw new Error(data.error||"Report unavailable");
  const rows=[
   ["SECTOR CLASSIFICATION",data.sector_exposure.status],
   ...data.sector_exposure.sectors.map(x=>["SECTOR · "+x.sector,x.weight_pct+"%"]),
   ["UNCLASSIFIED SYMBOLS",data.sector_exposure.unclassified.map(x=>x.symbol).join(", ")||"None"],
   ["TRANSACTION ATTRIBUTION",data.attribution.status],
   ["REALIZED P&L",data.attribution.realized_pnl_cents===undefined?"Unavailable":"$"+(data.attribution.realized_pnl_cents/100).toFixed(2)],
   ["UNREALIZED P&L",data.attribution.unrealized_pnl_cents===undefined?"Unavailable":"$"+(data.attribution.unrealized_pnl_cents/100).toFixed(2)],
   ...data.stress_testing.scenarios.map(x=>["STRESS · "+x.label,"$"+(x.hypothetical_pnl_cents/100).toFixed(2)])
  ];
  box.replaceChildren();
  for(const [label,value] of rows){const row=document.createElement("div");row.append(node("b",label),node("span",String(value)));box.append(row)}
 }catch(e){box.replaceChildren(node("div",e.message))}
 finally{button.disabled=false}
}
$("loadIntelligence").addEventListener("click",loadIntelligence);

async function runSimulation(){const box=$("intelligenceMetrics"),button=$("runSimulation");button.disabled=true;try{const response=await fetch("/api/simulation",{cache:"no-store"}),data=await response.json();if(!response.ok)throw new Error(data.error||"Replay unavailable");const rows=[["SIMULATION REPLAY",data.status],["BASELINE UTC",data.baseline_utc||"—"],["OBSERVATIONS",String(data.observations||0)],["BASELINE EQUITY",data.baseline_equity_cents===undefined?"—":"$"+(data.baseline_equity_cents/100).toFixed(2)],["CURRENT REPLAY EQUITY",data.current_equity_cents===undefined?"—":"$"+(data.current_equity_cents/100).toFixed(2)],["CHANGE",data.equity_change_pct===undefined?"Not published":""+data.equity_change_pct+"%"],["METHOD",data.method||data.message||"—"]];box.replaceChildren();for(const [k,v] of rows){const row=document.createElement("div");row.append(node("b",k),node("span",v));box.append(row)}}catch(e){box.replaceChildren(node("div",e.message))}finally{button.disabled=false}}
$("runSimulation").addEventListener("click",runSimulation);

async function runMarketSimulation(){const box=$("intelligenceMetrics"),button=$("runMarketSimulation");button.disabled=true;box.replaceChildren(node("div","Loading aligned daily Alpaca bars and replaying paper transactions…"));try{const response=await fetch("/api/simulation/market",{cache:"no-store"}),data=await response.json();if(!response.ok)throw new Error(data.error||data.status||"Market replay unavailable");const rows=[["MARKET REPLAY",data.status],["OBSERVATIONS",String(data.observations||0)],["PERIOD",(data.first_date||"—")+" → "+(data.last_date||"—")],["DAILY TIME-WEIGHTED RETURN",data.daily_time_weighted_return_pct===undefined?"Not published":data.daily_time_weighted_return_pct+"%"],["MAX DRAWDOWN",data.max_drawdown_pct===undefined?"Not published":data.max_drawdown_pct+"%"],["METHOD",data.method||data.message||"—"],["LIMITATIONS",data.limitations||"—"]];box.replaceChildren();for(const [k,v] of rows){const row=document.createElement("div");row.append(node("b",k),node("span",String(v)));box.append(row)}}catch(e){box.replaceChildren(node("div",e.message))}finally{button.disabled=false}}


async function renderExtendedPerformance(){
 const box=$("intelligenceMetrics"),button=$("runMarketSimulation");button.disabled=true;
 box.replaceChildren(node("div","Loading portfolio and SPY history…"));
 try{
  const response=await fetch("/api/simulation/market",{cache:"no-store"}),data=await response.json();
  if(!response.ok)throw new Error(data.error||data.status||"Performance unavailable");
  if(data.status!=="DAILY_MARKET_REPLAY")throw new Error(data.message||data.status||"No reconciled performance series");
  extendedPerformance=data;renderBenchmarkChart();renderTearSheet(data);
  box.replaceChildren();
  const add=(label,value)=>{const row=node("div");row.append(node("b",label),node("span",String(value)));box.append(row)};
  add("PORTFOLIO TWR",data.daily_time_weighted_return_pct+"%");
  add("SPY TWR",data.benchmark_time_weighted_return_pct+"%");
  add("ACTIVE RETURN",data.active_return_pct+"%");
  add("MAX DRAWDOWN",data.max_drawdown_pct+"%");
  add("SAMPLE",data.first_date+" → "+data.last_date+" · "+data.observations+" sessions");
  add("MONTHLY RETURNS",data.monthly_returns.map(x=>x.period+": "+x.portfolio_return_pct+"% / SPY "+x.benchmark_return_pct+"%").join(" · ")||"None");
  add("QUARTERLY RETURNS",data.quarterly_returns.map(x=>x.period+": "+x.portfolio_return_pct+"% / SPY "+x.benchmark_return_pct+"%").join(" · ")||"None");
  add("CONTRIBUTION",data.contribution_attribution.map(x=>x.symbol+": "+x.contribution_pct_equity+"%").join(" · ")||"None");
  const sc=data.scenario_comparison;
  add("BEST 20-SESSION WINDOW",sc.best?sc.best.start+" → "+sc.best.end+" · "+sc.best.portfolio_return_pct+"% / SPY "+sc.best.benchmark_return_pct+"%":"Insufficient observations");
  add("WORST 20-SESSION WINDOW",sc.worst?sc.worst.start+" → "+sc.worst.end+" · "+sc.worst.portfolio_return_pct+"% / SPY "+sc.worst.benchmark_return_pct+"%":"Insufficient observations");
 }catch(e){box.replaceChildren(node("div",e.message))}
 finally{button.disabled=false}
}
$("runMarketSimulation").addEventListener("click",renderExtendedPerformance);

let extendedPerformance=null,selectedPerformanceRange="all";
function renderBenchmarkChart(){
 const root=$("benchmarkChart"),empty=$("benchmarkEmpty");root.replaceChildren();
 if(!extendedPerformance||!extendedPerformance.points.length){empty.hidden=false;return}
 let rows=extendedPerformance.points;
 if(selectedPerformanceRange!=="all")rows=rows.slice(-Number(selectedPerformanceRange));
 empty.hidden=true;
 let pg=1,bg=1;
 const series=rows.map(x=>{pg*=1+x.daily_return_pct/100;bg*=1+x.benchmark_return_pct/100;return {date:x.date,p:pg,b:bg}});
 const vals=series.flatMap(x=>[x.p,x.b]),lo=Math.min(...vals),hi=Math.max(...vals),span=Math.max(hi-lo,0.0001);
 const xy=(v,i)=>[24+i*952/Math.max(series.length-1,1),196-(v-lo)*168/span];
 const ns="http://www.w3.org/2000/svg";
 const el=(tag,attrs={})=>{const n=document.createElementNS(ns,tag);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,String(v));return n};
 for(const y of [28,112,196])root.append(el("line",{x1:24,x2:976,y1:y,y2:y,stroke:"#25394d","stroke-width":1}));
 for(const [key,color] of [["p","#4fd4b5"],["b","#769fff"]]){
  const d=series.map((x,i)=>{const [a,b]=xy(x[key],i);return (i?"L":"M")+a.toFixed(2)+","+b.toFixed(2)}).join(" ");
  root.append(el("path",{d,fill:"none",stroke:color,"stroke-width":3,"stroke-linecap":"round","stroke-linejoin":"round"}));
  series.forEach((x,i)=>{if(i%Math.max(1,Math.floor(series.length/16))!==0&&i!==series.length-1)return;const [cx,cy]=xy(x[key],i),dot=el("circle",{cx,cy,r:4,fill:color});const title=el("title");title.textContent=x.date+" · "+(key==="p"?"Portfolio ":"SPY ")+((x[key]-1)*100).toFixed(3)+"%";dot.append(title);root.append(dot)});
 }
 const first=series[0],last=series[series.length-1];
 $("chartPortfolioLabel").textContent="PORTFOLIO "+((last.p-1)*100).toFixed(2)+"%";
 $("chartBenchmarkLabel").textContent="SPY "+((last.b-1)*100).toFixed(2)+"%";
 $("chartPeriodLabel").textContent=first.date+" → "+last.date;
}
function renderTearSheet(data){
 const t=data.tear_sheet||{},risk=data.risk_metrics||{},root=$("tearSheetMetrics"),rolling=$("rollingRiskMetrics");
 root.replaceChildren();rolling.replaceChildren();
 const add=(target,label,value)=>{const row=node("div");row.append(node("b",label),node("span",value===null||value===undefined?"Insufficient observations":String(value)));target.append(row)};
 add(root,"PERIOD",t.period_start+" → "+t.period_end);
 add(root,"PORTFOLIO / SPY TWR",t.portfolio_twr_pct+"% / "+t.benchmark_twr_pct+"%");
 add(root,"ACTIVE RETURN",t.active_return_pct+"%");
 add(root,"MAX DRAWDOWN",t.max_drawdown_pct+"%");
 add(root,"OPENING / ENDING EQUITY",money(t.opening_equity_cents)+" / "+money(t.ending_equity_cents));
 add(root,"ENDING CASH / INVESTED",money(t.ending_cash_cents)+" / "+money(t.ending_market_value_cents));
 add(root,"OPEN POSITIONS",String(t.position_count));
 add(rolling,"PORTFOLIO ANNUALIZED VOLATILITY",risk.portfolio_annualized_volatility_pct+"%");
 add(rolling,"SPY ANNUALIZED VOLATILITY",risk.benchmark_annualized_volatility_pct+"%");
 add(rolling,"ANNUALIZED TRACKING ERROR",risk.annualized_tracking_error_pct+"%");
 add(rolling,"INFORMATION RATIO",risk.information_ratio);
 const last=data.points[data.points.length-1];
 add(rolling,"LATEST 20-SESSION ROLLING VOLATILITY",last.rolling_20d_volatility_pct===null?null:last.rolling_20d_volatility_pct+"%");
 add(rolling,"LATEST SPY ROLLING VOLATILITY",last.benchmark_rolling_20d_volatility_pct===null?null:last.benchmark_rolling_20d_volatility_pct+"%");
}
document.querySelectorAll("#performanceRanges [data-range]").forEach(button=>button.addEventListener("click",()=>{
 selectedPerformanceRange=button.dataset.range;
 document.querySelectorAll("#performanceRanges [data-range]").forEach(b=>b.classList.toggle("active",b===button));
 renderBenchmarkChart();
}));
