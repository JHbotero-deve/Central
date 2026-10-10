window.Shopr=(()=>{"use strict";
const API="/api/v1";
const GLOWS=[["Rojo Fuego","#ff3b1f"],["Naranja","#ff7a1a"],["Ámbar","#ffb300"],["Verde","#2ecc71"],["Azul","#3b82f6"],["Violeta","#8b5cf6"],["Blanco","#e9e9f0"],["Negro","#1c1c20"]];
const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const url=u=>/^https?:\/\//i.test(u||"")?String(u):"";
const imgOk=u=>/^(https?:\/\/|data:image\/|mongo:\/\/)/i.test(u||"")?String(u):"";
const imageSrc=u=>{const src=imgOk(u);return src.startsWith("mongo://")?API+"/media/image?url="+encodeURIComponent(src):src};
const nn=x=>(x==null||x===""||isNaN(Number(x)))?null:Number(x);
const money=(v,c)=>{if(nn(v)==null)return"—";const cur=String(c||"COP").toUpperCase();try{return new Intl.NumberFormat(cur==="COP"?"es-CO":"en-US",{style:"currency",currency:cur,maximumFractionDigits:cur==="COP"?0:2}).format(Number(v))}catch{return v+" "+cur}};
const enc=s=>{let o="";new TextEncoder().encode(s).forEach(x=>o+=String.fromCharCode(x));return btoa(o)};
const dec=s=>new TextDecoder().decode(Uint8Array.from(atob(s),c=>c.charCodeAt(0)));
const pack=(t,m)=>String(t||"").trim()+"\n\n[[central:"+enc(JSON.stringify(m))+"]]";
const unpack=d=>{d=String(d||"");const m=d.match(/\n*\[\[central:([A-Za-z0-9+\/=]+)\]\]\s*$/);if(!m)return{text:d.trim(),meta:{}};let meta={};try{meta=JSON.parse(dec(m[1]))}catch{}return{text:d.slice(0,m.index).trim(),meta}};
async function api(path,opt={}){
  const h={Accept:"application/json",...(opt.headers||{})};
  const r=await fetch(API+path,{cache:"no-store",credentials:"include",...opt,headers:h});let b=null;try{b=await r.json()}catch{}
  if(!r.ok){const d=b&&b.detail;const e=new Error(typeof d==="string"?d:(d?JSON.stringify(d):"HTTP "+r.status));e.status=r.status;throw e}
  return b}


function mkLinks(mt,plat,p,g){
  const L=Object.assign({},mt.links||{}),aff=g("affiliate_url")||g("product_url")||"";
  if(plat==="amazon"&&!L.amazon)L.amazon=aff;
  if((plat==="mercadolibre"||plat==="meli")&&!L.meli)L.meli=aff;
  return L}
function fromApi(p,detail){
  const d=detail?(detail.product||detail):p, g=k=>(d[k]!=null?d[k]:p[k]);
  const u=unpack(g("description")), mt=u.meta||{}, gal=Array.isArray(g("image_gallery"))?g("image_gallery"):[], seller=g("seller")||{};
  const res=i=>typeof i==="string"&&i.startsWith("g:")?(gal[+i.slice(2)]||""):(i||"");
  let variants=(mt.variants||[]).map(v=>({name:v.n||"",glow:v.g|0,img:res(v.i)})).filter(v=>v.img||v.name);
  if(!variants.length)variants=[{name:"",glow:0,img:g("image_url")||""}];
  const plat=String(p.platform||"").toLowerCase();
  return{id:p.id,raw:p,title:g("title")||"Producto",brand:mt.brand||(plat&&plat!=="personal"?plat.toUpperCase():""),tag:mt.tag||"",
    cat:String(g("category")||"otros").toLowerCase(),desc:u.text,price:nn(g("current_price")??g("price")),prev:nn(g("previous_price")),
    currency:g("currency")||"COP",rating:nn(g("rating"))??(nn(mt.rating)||0),reviews:nn(g("reviews_count"))??(nn(mt.reviews)||0),features:mt.features||[],variants,
    links:mkLinks(mt,plat,p,g),fallback:g("product_url")||"",platform:plat,score:nn(g("opportunity_score"))||0,
    sku:g("sku")||"",stock:nn(g("stock")),sellerName:seller.name||g("seller_name")||"",sellerReputation:seller.reputation||"",salesEstimate:nn(g("sales_estimate")),updatedAt:g("updated_at")||"",gallery:gal,
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
  const im=imageSrc(v.img)?`<img src="${esc(imageSrc(v.img))}" alt="${esc(m.title)}" referrerpolicy="no-referrer" onerror="this.hidden=true;this.nextElementSibling.hidden=false"><span class="sh-noimg" hidden>Imagen no disponible</span>`:'<span class="sh-noimg">Sin imagen</span>';
  const facts=[];if(m.sku)facts.push(["SKU",m.sku]);if(m.stock!=null)facts.push(["Disponibilidad",m.stock>0?String(m.stock)+" unidades":"Agotado"]);if(m.sellerName)facts.push(["Vendedor",m.sellerName]);if(m.sellerReputation)facts.push(["Reputación",typeof m.sellerReputation==="string"?m.sellerReputation:JSON.stringify(m.sellerReputation)]);if(m.salesEstimate!=null)facts.push(["Ventas estimadas",String(m.salesEstimate)]);if(m.reviews>0)facts.push(["Reseñas",String(m.reviews)]);if(m.updatedAt)facts.push(["Actualizado",String(m.updatedAt).slice(0,10)]);if(m.platform)facts.push(["Origen",m.platform==="mercadolibre"?"Mercado Libre":m.platform==="amazon"?"Amazon":m.platform]);
  const sw=m.variants.length>1?`<div class="sh-color">COLOR: <b>${esc(v.name||gl[0])}</b></div><div class="sh-sw">${m.variants.map((x,i)=>`<button type="button" data-vi="${i}" class="${i===vi?"on":""}" title="${esc(x.name||"")}" style="background:${(GLOWS[x.glow]||GLOWS[0])[1]}"></button>`).join("")}</div>`:"";
  return `<section class="sh-detail"><div class="sh-stage ${m.plate?"plate":""}">${im}</div><div class="sh-info">
    <div class="sh-meta">${m.brand?`<span class="sh-brand">${esc(m.brand)}</span>`:""}${m.tag?`<span class="sh-tag">${esc(m.tag)}</span>`:""}</div>
    <h2 class="sh-title">${esc(m.title)}</h2>
    ${m.rating?`<div class="sh-rate"><span class="sh-stars">${stars(m.rating)}</span><b>${m.rating}</b><span>(${Number(m.reviews||0).toLocaleString("es-CO")} reseñas)</span></div>`:""}
    ${m.desc?`<p class="sh-desc">${esc(m.desc)}</p>`:""}
    ${m.features.length?`<ul class="sh-feat">${m.features.map(f=>`<li>${esc(f)}</li>`).join("")}</ul>`:""}
    ${facts.length?`<dl class="sh-facts">${facts.map(([k,val])=>`<div><dt>${esc(k)}</dt><dd>${esc(val)}</dd></div>`).join("")}</dl>`:""}
    ${sw}
    <div class="sh-price"><b>${money(m.price,m.currency)}</b>${disc?`<span class="sh-old">${money(m.prev,m.currency)}</span><span class="sh-disc">-${disc}%</span>`:""}</div>
    <div class="sh-cta">${b.join("")}</div></div></section>`}
function mountDetail(root,m,vi=0){
  root.innerHTML=detailHtml(m,vi);
  const gl=(GLOWS[(m.variants[vi]||{}).glow]||GLOWS[0])[1];document.documentElement.style.setProperty("--glow",gl);
  root.querySelectorAll("[data-vi]").forEach(b=>b.addEventListener("click",()=>mountDetail(root,m,+b.dataset.vi)))}
function cardHtml(m){
  const v=m.variants[0]||{};
  const src=imageSrc(v.img),im=src?`<img src="${esc(src)}" alt="${esc(m.title)}" loading="lazy" referrerpolicy="no-referrer" onerror="this.hidden=true;this.nextElementSibling.hidden=false"><span class="sh-noimg" hidden>Imagen no disponible</span>`:'<span class="sh-noimg">Sin imagen</span>';
  return `<button type="button" class="sh-card" data-id="${esc(m.id)}"><div class="sh-cim ${m.plate?"plate":""}">${im}</div><div class="sh-cb"><span class="sh-cbrand">${esc(m.brand||m.cat)}</span><span class="sh-ctitle">${esc(m.title)}</span><span class="sh-cprice">${money(m.price,m.currency)}</span></div></button>`}

return{API,GLOWS,esc,url,imgOk,imageSrc,nn,money,pack,unpack,fromApi,detailHtml,mountDetail,cardHtml,api}
})();