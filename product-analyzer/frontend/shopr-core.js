window.Shopr=(()=>{"use strict";
const API="/api/v1",KEY="central_admin_token";
const GLOWS=[["Rojo Fuego","#ff3b1f"],["Naranja","#ff7a1a"],["Ámbar","#ffb300"],["Verde","#2ecc71"],["Azul","#3b82f6"],["Violeta","#8b5cf6"],["Blanco","#e9e9f0"],["Negro","#1c1c20"]];
const THEMES=[["Negro","#0a0a0a"],["Pizarra","#10151c"],["Marino","#0a1226"],["Violeta","#150b26"],["Bosque","#0a1a12"],["Carbón","#171717"],["Vino","#1f0a12"]];
const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const url=u=>/^https?:\/\//i.test(u||"")?String(u):"";
const imgOk=u=>/^(https?:\/\/|data:image\/)/i.test(u||"")?String(u):"";
const nn=x=>(x==null||x===""||isNaN(Number(x)))?null:Number(x);
const money=(v,c)=>{if(nn(v)==null)return"—";const cur=String(c||"COP").toUpperCase();try{return new Intl.NumberFormat(cur==="COP"?"es-CO":"en-US",{style:"currency",currency:cur,maximumFractionDigits:cur==="COP"?0:2}).format(Number(v))}catch{return v+" "+cur}};
const enc=s=>{let o="";new TextEncoder().encode(s).forEach(x=>o+=String.fromCharCode(x));return btoa(o)};
const dec=s=>new TextDecoder().decode(Uint8Array.from(atob(s),c=>c.charCodeAt(0)));
const pack=(t,m)=>String(t||"").trim()+"\n\n[[central:"+enc(JSON.stringify(m))+"]]";
const unpack=d=>{d=String(d||"");const m=d.match(/\n*\[\[central:([A-Za-z0-9+\/=]+)\]\]\s*$/);if(!m)return{text:d.trim(),meta:{}};let meta={};try{meta=JSON.parse(dec(m[1]))}catch{}return{text:d.slice(0,m.index).trim(),meta}};
const theme=()=>{try{return JSON.parse(localStorage.getItem("central_theme"))||THEMES[0]}catch{return THEMES[0]}};
const setTheme=t=>{localStorage.setItem("central_theme",JSON.stringify(t));applyTheme()};
const applyTheme=()=>document.documentElement.style.setProperty("--bg",theme()[1]);
const tok=()=>localStorage.getItem(KEY)||"";
const setTok=t=>t?localStorage.setItem(KEY,t):localStorage.removeItem(KEY);

async function api(path,opt={}){
  const h={Accept:"application/json",...(opt.headers||{})};if(tok())h.Authorization="Bearer "+tok();
  const r=await fetch(API+path,{cache:"no-store",...opt,headers:h});let b=null;try{b=await r.json()}catch{}
  if(!r.ok){const d=b&&b.detail;const e=new Error(typeof d==="string"?d:(d?JSON.stringify(d):"HTTP "+r.status));e.status=r.status;throw e}
  return b}
async function login(u,p){
  const tries=[{t:"application/json",b:JSON.stringify({username:u,password:p})},
    {t:"application/x-www-form-urlencoded",b:new URLSearchParams({username:u,password:p}).toString()},
    {t:"application/json",b:JSON.stringify({email:u,password:p})}];
  let last="Credenciales invalidas";
  for(const x of tries){
    const r=await fetch(API+"/auth/login",{method:"POST",headers:{"Content-Type":x.t,Accept:"application/json"},body:x.b});
    const j=await r.json().catch(()=>({}));
    if(r.ok){const k=j.access_token||j.token;if(!k)throw new Error("La respuesta no trae token");return k}
    if(typeof j.detail==="string")last=j.detail;
    if(r.status!==422&&r.status!==400)break}
  throw new Error(last)}

function mkLinks(mt,plat,p,g){
  const L=Object.assign({},mt.links||{}),aff=g("affiliate_url")||g("product_url")||"";
  if(plat==="amazon"&&!L.amazon)L.amazon=aff;
  if((plat==="mercadolibre"||plat==="meli")&&!L.meli)L.meli=aff;
  return L}
function fromApi(p,detail){
  const d=detail?(detail.product||detail):p, g=k=>(d[k]!=null?d[k]:p[k]);
  const u=unpack(g("description")), mt=u.meta||{}, gal=Array.isArray(g("image_gallery"))?g("image_gallery"):[];
  const res=i=>typeof i==="string"&&i.startsWith("g:")?(gal[+i.slice(2)]||""):(i||"");
  let variants=(mt.variants||[]).map(v=>({name:v.n||"",glow:v.g|0,img:res(v.i)})).filter(v=>v.img||v.name);
  if(!variants.length)variants=[{name:"",glow:0,img:g("image_url")||""}];
  const plat=String(p.platform||"").toLowerCase();
  return{id:p.id,raw:p,title:g("title")||"Producto",brand:mt.brand||(plat&&plat!=="personal"?plat.toUpperCase():""),tag:mt.tag||"",
    cat:String(g("category")||"otros").toLowerCase(),desc:u.text,price:nn(g("current_price")??g("price")),prev:nn(g("previous_price")),
    currency:g("currency")||"COP",rating:nn(mt.rating)||0,reviews:nn(mt.reviews)||0,features:mt.features||[],variants,
    links:mkLinks(mt,plat,p,g),fallback:g("product_url")||"",platform:plat,score:nn(g("opportunity_score"))||0,
    plate:mt.plate!==undefined?!!mt.plate:plat!=="personal"}}

const stars=r=>{const n=Math.max(0,Math.min(5,Math.round(r)));return"★".repeat(n)+"☆".repeat(5-n)};
function detailHtml(m,vi){
  const v=m.variants[vi]||m.variants[0]||{}, gl=GLOWS[v.glow]||GLOWS[0], L=m.links||{}, b=[];
  const disc=m.prev&&m.price&&m.prev>m.price?Math.round((1-m.price/m.prev)*100):0;
  const a=(c,href,html)=>`<a class="sh-btn ${c}" href="${esc(href)}" target="_blank" rel="noopener noreferrer">${html} ↗</a>`;
  if(url(L.amazon))b.push(a("sh-amz",L.amazon,"Ver en <b>Amazon</b>"));
  if(url(L.meli))b.push(a("sh-meli",L.meli,"Ver en <b>Mercado Libre</b>"));
  if(url(L.wompi))b.push(a("sh-wmp",L.wompi,"Pagar con <b>Wompi</b>"));
  if(!b.length&&url(m.fallback))b.push(a("sh-amz",m.fallback,"Ver <b>producto</b>"));
  if(!b.length&&m.platform==="personal")b.push('<a class="sh-btn sh-wmp" href="/tienda">Comprar en <b>Central</b></a>');
  const im=imgOk(v.img)?`<img src="${esc(imgOk(v.img))}" alt="${esc(m.title)}" referrerpolicy="no-referrer">`:'<span class="sh-noimg">Sin imagen</span>';
  const sw=m.variants.length>1?`<div class="sh-color">COLOR: <b>${esc(v.name||gl[0])}</b></div><div class="sh-sw">${m.variants.map((x,i)=>`<button type="button" data-vi="${i}" class="${i===vi?"on":""}" title="${esc(x.name||"")}" style="background:${(GLOWS[x.glow]||GLOWS[0])[1]}"></button>`).join("")}</div>`:"";
  return `<section class="sh-detail"><div class="sh-stage ${m.plate?"plate":""}">${im}</div><div class="sh-info">
    <div class="sh-meta">${m.brand?`<span class="sh-brand">${esc(m.brand)}</span>`:""}${m.tag?`<span class="sh-tag">${esc(m.tag)}</span>`:""}</div>
    <h2 class="sh-title">${esc(m.title)}</h2>
    ${m.rating?`<div class="sh-rate"><span class="sh-stars">${stars(m.rating)}</span><b>${m.rating}</b><span>(${Number(m.reviews||0).toLocaleString("es-CO")} reseñas)</span></div>`:""}
    ${m.desc?`<p class="sh-desc">${esc(m.desc)}</p>`:""}
    ${m.features.length?`<ul class="sh-feat">${m.features.map(f=>`<li>${esc(f)}</li>`).join("")}</ul>`:""}
    ${sw}
    <div class="sh-price"><b>${money(m.price,m.currency)}</b>${disc?`<span class="sh-old">${money(m.prev,m.currency)}</span><span class="sh-disc">-${disc}%</span>`:""}</div>
    <div class="sh-cta">${b.join("")}</div></div></section>`}
function mountDetail(root,m,vi=0){
  root.innerHTML=detailHtml(m,vi);
  const gl=(GLOWS[(m.variants[vi]||{}).glow]||GLOWS[0])[1];document.documentElement.style.setProperty("--glow",gl);
  root.querySelectorAll("[data-vi]").forEach(b=>b.addEventListener("click",()=>mountDetail(root,m,+b.dataset.vi)))}
function cardHtml(m){
  const v=m.variants[0]||{};
  const im=imgOk(v.img)?`<img src="${esc(imgOk(v.img))}" alt="${esc(m.title)}" loading="lazy" referrerpolicy="no-referrer">`:'<span class="sh-noimg">Sin imagen</span>';
  return `<button type="button" class="sh-card" data-id="${esc(m.id)}"><div class="sh-cim ${m.plate?"plate":""}">${im}</div><div class="sh-cb"><span class="sh-cbrand">${esc(m.brand||m.cat)}</span><span class="sh-ctitle">${esc(m.title)}</span><span class="sh-cprice">${money(m.price,m.currency)}</span></div></button>`}

return{API,GLOWS,THEMES,esc,url,imgOk,nn,money,pack,unpack,fromApi,detailHtml,mountDetail,cardHtml,api,login,tok,setTok,theme,setTheme,applyTheme,KEY}
})();