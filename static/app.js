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
async function refresh(){
  const responses=await Promise.all([fetch("/api/state",{cache:"no-store"}),fetch("/api/risk",{cache:"no-store"})]);
  if(responses.some(r=>!r.ok)) throw new Error("Portfolio and risk services are unavailable");
  const [state,risk]=await Promise.all(responses.map(r=>r.json()));
  if(state.mode!=="SIMULATION ONLY" || state.broker_connected!==false) throw new Error("Unexpected environment: trading controls disabled");
  updateUi(state,risk);
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
