import fs from 'node:fs/promises';
import path from 'node:path';
import { createRequire } from 'node:module';
const require=createRequire(import.meta.url);
const { chromium } = require('playwright');

const args = Object.fromEntries(process.argv.slice(2).map((v,i,a)=>v.startsWith('--')?[v.slice(2),a[i+1]]:null).filter(Boolean));
const start = args.url || 'http://127.0.0.1:8000/';
const out = args.out || 'capture_default';
const assetRoot=args['assets-dir']||'site';
const maxStates = Number(args['max-states'] || 80), maxDepth=Number(args['max-depth']||40);
const singlePath=args['single-path']==='true';
const ageIndex=Number.isInteger(Number(args['age-index']))?Number(args['age-index']):0;
let executablePath=args.chrome;
if(!executablePath&&process.platform==='win32'){
  const candidate='C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
  try{await fs.access(candidate);executablePath=candidate;}catch{}
}
const launchArgs=[];
if(args['map-host']&&/^[A-Za-z0-9.-]+$/.test(args['map-host']))launchArgs.push(`--host-resolver-rules=MAP ${args['map-host']} 127.0.0.1`);
const browser=await chromium.launch({headless:true,args:launchArgs,...(executablePath?{executablePath}:{})});
const context=await browser.newContext({viewport:{width:1280,height:900},acceptDownloads:false});
const requests=[], failures=[], consoleErrors=[];
const assetUrls={}, assetJobs=[];
if(args['block-tracking']==='true')await context.route('**/*',route=>{
  const host=new URL(route.request().url()).hostname;
  if(['connect.facebook.net','cdn.utmify.com.br','tracking.utmify.com.br','ingest.xquiz.com.br','api.ipify.org','api6.ipify.org'].includes(host))return route.abort();
  return route.continue();
});
context.on('page', p=>{
  p.on('request',r=>requests.push({type:r.resourceType(),method:r.method(),url:r.url()}));
  p.on('requestfailed',r=>failures.push({url:r.url(),error:r.failure()?.errorText}));
  p.on('console',m=>{if(m.type()==='error')consoleErrors.push({text:m.text(),url:m.location().url})});
  p.on('pageerror',e=>consoleErrors.push({text:String(e)}));
  p.on('response',r=>{
    const job=(async()=>{
      const u=new URL(r.url()), type=r.request().resourceType();
      if(r.status()<200||r.status()>=300||!['script','stylesheet','image','font'].includes(type))return;
      if(![new URL(start).host,'cdn.xquiz.co','fonts.bunny.net'].includes(u.host))return;
      let rel=(u.host===new URL(start).host?u.pathname.replace(/^\//,''):`_external/${u.host}/${u.pathname.replace(/^\//,'')}`)||'index.html';
      if(u.search)rel+='__q_'+u.search.slice(1).replace(/[^A-Za-z0-9._-]/g,'_').slice(0,100);
      if(rel.split('/').includes('..'))return;
      const dest=path.join(assetRoot,rel); await fs.mkdir(path.dirname(dest),{recursive:true});
      const body=await r.body(); await fs.writeFile(dest,body);
      assetUrls[u.href]={path:'/'+rel,type:r.headers()['content-type']||'application/octet-stream',bytes:body.length};
    })().catch(()=>{}); assetJobs.push(job);
  });
});
await fs.mkdir(out,{recursive:true});
const queue=[[]], seen=new Set(); let captured=0, reachedPurchase=false;
const normalize=s=>(s||'').replace(/\s+/g,' ').trim();
async function candidates(page){
 return await page.evaluate(()=>{
  const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.visibility!=='hidden'&&s.display!=='none'};
  const hasText=x=>(x||'').replace(/\s+/g,' ').trim().length>0;
  const tidy=items=>{items=items.filter(e=>visible(e)&&hasText(e.innerText||e.getAttribute('aria-label')));items=items.filter(e=>!items.some(p=>p!==e&&p.contains(e)));return [...new Set(items)];};
  const chains=['.steps > .step','[class*=option]','div[class*=grid] > *','button,[role=button],label'];
  let list=[];
  for(const sel of chains){list=tidy([...document.querySelectorAll(sel)]);if(list.length)break;}
  if(!list.length)list=tidy([...document.querySelectorAll('body *')].filter(e=>visible(e)&&getComputedStyle(e).cursor==='pointer'));
  // If one candidate wraps several answers, descend through single-child containers until there are siblings.
  if(list.length===1){let e=list[0];for(let i=0;i<8;i++){const kids=tidy([...e.children]);if(kids.length<2)break;e=kids[0];list=kids;}}
  // Include global fixed action bars even when the answer cards were found first.
  const ctas=[...document.querySelectorAll('button,[role=button]')].filter(e=>visible(e)&&/^(continuar|próximo|avançar|concluir)$/i.test((e.innerText||'').trim()));
  for(const e of ctas)if(!list.includes(e))list.push(e);
  list.forEach((e,i)=>e.setAttribute('data-crawl-i',String(i)));
  return list.map((e,i)=>({i,text:(e.innerText||e.getAttribute('aria-label')||'').trim().slice(0,240),tag:e.tagName,cls:String(e.className||'').slice(0,150)}));
 });
}
function normalizeText(x){return (x||'').replace(/\s+/g,' ').trim().length>0}
async function openPath(actions){
 const page=await context.newPage();
 await page.goto(start,{waitUntil:'domcontentloaded',timeout:45000}).catch(()=>{});
 await page.locator('main button').first().waitFor({state:'visible',timeout:15000}).catch(()=>{});
 await page.waitForTimeout(350);
 for(const action of actions){
   const opts=await candidates(page); const item=opts[action.i];
   if(!item){await page.close();return null;}
   const before=(await page.locator('body').innerText().catch(()=>'' )).replace(/\s+/g,' ').trim();
   const el=page.locator(`[data-crawl-i="${action.i}"]`).first();
   try { await el.click({timeout:6000}); } catch { await page.close(); return null; }
   await page.waitForTimeout(1100);
   const after=(await page.locator('body').innerText().catch(()=>'' )).replace(/\s+/g,' ').trim();
   if(before===after){
     const cta=page.getByRole('button',{name:/^(continuar|próximo|avançar|concluir)$/i}).last();
     if(await cta.count().catch(()=>0))await cta.click({timeout:6000}).catch(()=>{});
     await page.waitForTimeout(900);
   }
 }
 return page;
}
while(queue.length&&captured<maxStates){
 const actions=queue.shift();
 const key=JSON.stringify(actions);
 if(seen.has(key)||actions.length>maxDepth)continue; seen.add(key);
 const page=await openPath(actions);if(!page)continue;
 let body=await page.locator('body').innerText({timeout:10000}).catch(()=>''), url=page.url();
 let readyOptions=await candidates(page);
 if(!readyOptions.length&&/aguarde|preparando|calculando|gerando/i.test(body)){
   for(let i=0;i<32&&!readyOptions.length;i++){await page.waitForTimeout(1000);body=await page.locator('body').innerText().catch(()=>body);readyOptions=await candidates(page);}
 }
 const purchase=/\b(checkout|pagamento|finalizar compra|dados de pagamento|cart[aã]o de cr[eé]dito|compre agora|garantir minha vaga)\b/i.test(body)||/R\$\s?\d+[,.]\d{2}/i.test(body)||/pay\.cakto\.com\.br/i.test(url);
 const n=String(captured+1).padStart(3,'0'), dir=path.join(out,`${n}_${actions.map(a=>a.label).filter(Boolean).join('_').replace(/[^\p{L}\p{N}_-]+/gu,'-').slice(0,70)||'initial'}`);
 await fs.mkdir(dir,{recursive:true});
 await fs.writeFile(path.join(dir,'page.html'),await page.content(),'utf8');
 await fs.writeFile(path.join(dir,'text.txt'),body,'utf8');
 await fs.writeFile(path.join(dir,'options.json'),JSON.stringify({url,actions,options:readyOptions,purchase},null,2),'utf8');
 await page.screenshot({path:path.join(dir,'screen.png'),fullPage:true}).catch(()=>{});
 captured++;
 if(purchase){reachedPurchase=true;await page.close();break;}
 const opts=readyOptions.length?readyOptions:await candidates(page);
 const answers=opts.filter(o=>!/^\s*(?:cm|pol|in|kg|lb|continuar|pr[oó]ximo|avançar|voltar)\s*$/i.test(o.text));
 const branches=answers.length?answers:opts.filter(o=>/^\s*(?:continuar|pr[oó]ximo|avançar)\s*$/i.test(o.text));
 // Avoid clicking form submission or payment actions; record the first purchase surface and stop there.
 let chosen=branches;
 if(singlePath){
   const gender=branches.filter(o=>/\b(mulher|mulheres|homem|homens|feminino|masculino)\b/i.test(o.text));
   if(gender.length)chosen=gender; else if(actions.length===0)chosen=[branches[ageIndex]].filter(Boolean); else chosen=branches.slice(0,1);
 }
 for(const opt of chosen){
   if(/buy|purchase|checkout|pay|comprar|pagar|finalizar/i.test(opt.text))continue;
   const next=[...actions,{i:opt.i,label:opt.text.slice(0,70)}];
   const sig=JSON.stringify(next);if(!seen.has(sig))queue.push(next);
 }
 await page.close();
}
await fs.writeFile(path.join(out,'network.json'),JSON.stringify({requests,failures,consoleErrors,summary:{captured,queued:queue.length,reachedPurchase}},null,2),'utf8');
const byHost={}; for(const r of requests){const h=new URL(r.url).host;(byHost[h]??=new Set()).add(`${r.type}:${r.method}`)}
await fs.writeFile(path.join(out,'network_by_host.txt'),Object.entries(byHost).map(([h,v])=>`${h}: ${[...v].join(', ')}`).join('\n'),'utf8');
await Promise.allSettled(assetJobs);
let oldMimes={};try{oldMimes=JSON.parse(await fs.readFile(path.join(assetRoot,'_mime_types.json'),'utf8'));}catch{}
await fs.writeFile(path.join(assetRoot,'_mime_types.json'),JSON.stringify({...oldMimes,...Object.fromEntries(Object.values(assetUrls).map(x=>[x.path.replace(/^\//,''),x.type]))},null,2),'utf8').catch(()=>{});
await fs.writeFile(path.join(out,'asset_urls.json'),JSON.stringify(assetUrls,null,2),'utf8');
console.log(JSON.stringify({captured,queued:queue.length,reachedPurchase,requests:requests.length,failures:failures.length,consoleErrors:consoleErrors.length,out},null,2));
await browser.close();
