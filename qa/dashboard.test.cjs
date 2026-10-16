'use strict';
// Real HTML/JS and HTTP controller, with an isolated fake service backend.
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {once}=require('node:events');
const fs=require('node:fs/promises');
const path=require('node:path');
const {chromium}=require('playwright');
const output=path.join(__dirname,'results');
const report={tests:[],errors:[]};
let server,browser,desktop,mobile;
async function test(name,fn){await fn();report.tests.push({name,status:'passed'});console.log('PASS '+name);}
async function pair(page,url){await page.goto(url);await page.locator('#pair-code').fill('qa-pairing');await page.locator('#pair-form button').click();await page.locator('#app').waitFor({state:'visible'});}
async function view(page,name){await page.locator('[data-view="'+name+'"]').click();await page.locator('#view-'+name).waitFor({state:'visible'});}
async function state(page){return await page.evaluate(()=>fetch('/api/state').then(r=>r.json()));}
async function saveSettings(page){const response=page.waitForResponse(r=>r.url().endsWith('/api/settings')&&r.request().method()==='POST');await page.locator('#save-settings').click();return await response;}
async function confirm(page){await page.locator('#confirm-dialog').waitFor({state:'visible'});await page.locator('#confirm-ok').click();await page.locator('#confirm-dialog').waitFor({state:'hidden'});}
async function saveSchedule(page){await page.locator('#save-schedule').click();const response=page.waitForResponse(r=>r.url().endsWith('/api/schedule'));await confirm(page);assert.equal((await response).status(),200);await page.waitForFunction(()=>!document.getElementById('save-schedule').disabled);}
async function programTab(page,tab='timings',index=0){const p=page.locator('.schedule-program').nth(index);if(!await p.evaluate(n=>n.open))await p.locator('.program-summary').click();await p.locator('[role="tab"][data-tab="'+tab+'"]').click();return p;}
async function noOverflow(page){assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'page must fit viewport');}
(async()=>{
 await fs.mkdir(output,{recursive:true});
 server=spawn(process.env.PYTHON||'python',[path.join(__dirname,'server.py')],{stdio:['pipe','pipe','inherit']});
 const endpoints=await new Promise((resolve,reject)=>{let text='';const timer=setTimeout(()=>reject(new Error('QA server startup timed out')),15000);server.on('error',reject);server.on('exit',code=>reject(new Error('QA server exited '+code)));server.stdout.on('data',chunk=>{text+=chunk;if(text.includes('\n')){clearTimeout(timer);try{resolve(JSON.parse(text.split('\n')[0]));}catch(e){reject(e);}}});});
 browser=await chromium.launch({headless:true,channel:'chromium'});
 const context=await browser.newContext({viewport:{width:1440,height:1000}});
 await context.route('**/*',route=>route.request().url().startsWith('http://127.0.0.1:')?route.continue():route.abort());
 context.on('page',p=>p.on('pageerror',e=>report.errors.push(e.message)));
 desktop=await context.newPage();
 await test('Pairing and clean first installation',async()=>{await desktop.goto(endpoints.desktop);await desktop.locator('#pair-code').fill('wrong');await desktop.locator('#pair-form button').click();await desktop.locator('#pair-error').filter({hasText:'Incorrect pairing code'}).waitFor();await pair(desktop,endpoints.desktop);assert.equal((await state(desktop)).schedule.length,0);await desktop.locator('#countdown').filter({hasText:'Add and enable a program'}).waitFor();});
 await test('Integrated PC controls report completion and preserve background host across browser close',async()=>{
  await view(desktop,'pc');await desktop.locator('#pc-obs').click();
  await desktop.locator('#pc-action-status').filter({hasText:'QA PC action finished: obs'}).waitFor();
  await desktop.locator('#pc-quit').click();await desktop.locator('#confirm-cancel').click();
  assert.ok(!(await state(desktop)).logs.some(r=>r.message==='QA PC action: quit'));
  await view(desktop,'mobile');await desktop.locator('#pc-ip').selectOption('192.168.1.42');
  await desktop.locator('#pc-mobile-toggle').click();await desktop.waitForFunction(()=>document.getElementById('pc-mobile-toggle').textContent.startsWith('Disable'));
  assert.deepEqual((await state(desktop)).mobile_urls,['http://192.168.1.42:8866']);
  await desktop.locator('#pc-mobile-toggle').click();await desktop.locator('#confirm-cancel').click();assert.equal((await state(desktop)).mobile_enabled,true);
  await desktop.locator('#pc-mobile-toggle').click();await confirm(desktop);await desktop.waitForFunction(()=>document.getElementById('pc-mobile-toggle').textContent.startsWith('Enable'));
  await view(desktop,'pc');await desktop.screenshot({path:path.join(output,'pc-controls-desktop.png'),fullPage:true});await noOverflow(desktop);
  await desktop.setViewportSize({width:650,height:850});await noOverflow(desktop);await desktop.screenshot({path:path.join(output,'pc-controls-narrow.png'),fullPage:true});
  const started=(await state(desktop)).started_at;await desktop.close();desktop=await context.newPage();await desktop.goto(endpoints.desktop);await desktop.locator('#app').waitFor({state:'visible'});assert.equal((await state(desktop)).started_at,started);await desktop.setViewportSize({width:1440,height:1000});
 });
 await test('Setup saves destinations, preserves blank secret, and rejects invalid channel',async()=>{
  await view(desktop,'connections');await desktop.locator('#field-workspace_name').fill('Temple Test Desk');await desktop.locator('#field-youtube_channel_id').fill('invalid');assert.equal((await saveSettings(desktop)).status(),409);assert.equal((await state(desktop)).workspace_name,'My Live Desk');
  await desktop.locator('#field-youtube_channel_id').fill('UC'+'a'.repeat(22));await desktop.locator('#field-facebook_page_id').fill('123456789');await desktop.locator('#field-youtube_stream_title').fill('YouTube Official Livestream');await desktop.locator('#field-obs_collection').fill('Test Collection');assert.equal((await saveSettings(desktop)).status(),200);
  const s=await state(desktop);assert.equal(s.workspace_name,'Temple Test Desk');assert.equal(s.destinations.youtube_stream_title,'YouTube Official Livestream');assert.ok(!JSON.stringify(s).includes('qa-only-secret'));assert.equal(await desktop.locator('#field-facebook_page_token').inputValue(),'');await desktop.screenshot({path:path.join(output,'desktop-setup.png'),fullPage:true});await noOverflow(desktop);
 });
 await test('Supplied DARSHANFLOW replaces social page without changing its document',async()=>{
  const crypto=require('node:crypto'),response=await context.request.get(endpoints.desktop+'/darshanflow.html');
  assert.equal(response.status(),200);assert.equal(crypto.createHash('sha256').update(await response.body()).digest('hex'),'662e41b5b4b8a03922446dc4fbe731a2ea52676f9670a9d6fabd3b03885aabcb');
  assert.ok(response.headers()['content-security-policy'].includes("script-src 'unsafe-inline'"));
  assert.ok(!(await context.request.get(endpoints.desktop+'/')).headers()['content-security-policy'].includes('unsafe-inline'));
  await view(desktop,'social');const frame=desktop.frameLocator('#darshanflow-frame');await frame.locator('#mainGrid .deity-col').first().waitFor();
  assert.equal(await desktop.locator('#social-compose').count(),0);assert.equal(await desktop.getByRole('button',{name:'Social Media',exact:true}).count(),0);
  assert.equal(await frame.locator('#mainGrid .deity-col').count(),7);
  await frame.locator('html[data-live-desk-theme="ready"]').waitFor();
  assert.deepEqual(await frame.locator('body').evaluate(n=>({ink:getComputedStyle(n).color,bg:getComputedStyle(n).backgroundColor})),await desktop.locator('html').evaluate(n=>({ink:getComputedStyle(n).color,bg:getComputedStyle(n).backgroundColor})));
  assert.equal(await frame.locator('.sf-primary').first().evaluate(n=>getComputedStyle(n).backgroundColor),await desktop.locator('html').evaluate(n=>getComputedStyle(n).getPropertyValue('--orange').trim()).then(hex=>{const rgb=hex.match(/\w\w/g).map(x=>parseInt(x,16));return `rgb(${rgb.join(', ')})`;}));
  await frame.getByRole('button',{name:'Post 2 · Landscape (1→10)',exact:true}).click();assert.equal(await frame.locator('#mainGrid .deity-col').count(),10);
  await frame.getByRole('button',{name:'Facebook · Mixed (1→17)',exact:true}).click();assert.equal(await frame.locator('#mainGrid .deity-col').count(),17);
  await frame.getByRole('button',{name:'Post 1 · Portrait (1→7)',exact:true}).click();
  await frame.getByRole('button',{name:'Publish',exact:true}).click();await frame.locator('#sf-publish').waitFor({state:'visible'});
  await frame.locator('#captionTitle').fill('Unchanged studio test caption');await frame.locator('#sf-save-caption').click();await frame.locator('#sf-message').filter({hasText:'Caption saved'}).waitFor();
  await view(desktop,'overview');await desktop.waitForResponse(r=>r.url().endsWith('/api/state'));await view(desktop,'social');assert.equal(await frame.locator('#captionTitle').inputValue(),'Unchanged studio test caption');
  const nonce=await frame.locator('body').evaluate(n=>{n.dataset.qaInstance='retained';return n.dataset.qaInstance;});
  await desktop.waitForResponse(r=>r.url().endsWith('/api/state'));assert.equal(await frame.locator('body').getAttribute('data-qa-instance'),nonce);
  await desktop.reload();await desktop.locator('#app').waitFor({state:'visible'});await view(desktop,'social');await frame.locator('html[data-live-desk-theme="ready"]').waitFor();assert.equal(await frame.locator('#captionTitle').inputValue(),'Unchanged studio test caption');
  await frame.getByRole('button',{name:'Photos',exact:true}).click();
  for(const width of [1440,390,320]){await desktop.setViewportSize({width,height:1000});await noOverflow(desktop);await desktop.locator('#darshanflow-frame').screenshot({path:path.join(output,'darshanflow-'+width+'.png')});}
  await desktop.setViewportSize({width:1440,height:1000});
 });
 await test('DARSHANFLOW upload and swap remain inside the preserved document',async()=>{
  const frame=desktop.frameLocator('#darshanflow-frame');
  const png=Buffer.from(await desktop.evaluate(()=>{const c=document.createElement('canvas');c.width=300;c.height=400;const ctx=c.getContext('2d');ctx.fillStyle='#1f7765';ctx.fillRect(0,0,300,400);return c.toDataURL('image/png').split(',')[1];}),'base64');
  await frame.locator('#bulkInput').setInputFiles({name:'qa-original-photo.png',mimeType:'image/png',buffer:png});
  await frame.locator('#mainGrid .seq-num-pill').filter({hasText:'✓'}).first().waitFor();
  const assigned=await frame.locator('body').evaluate(()=>Object.entries(assignedSlots).filter(([,v])=>v).map(([id,v])=>({id,dataUrl:v.dataUrl})));
  assert.equal(assigned.length,1);assert.equal(assigned[0].dataUrl,'data:image/png;base64,'+png.toString('base64'));
  const first=assigned[0].id,next=first==='P1'?'P2':'P1';
  await frame.locator('#mainGrid .deity-col').nth(Number(first.slice(1))-1).locator('select').selectOption(next);
  await frame.locator('#mainGrid .deity-col').nth(Number(next.slice(1))-1).locator('.seq-num-pill').filter({hasText:'✓'}).waitFor();
  assert.equal(await frame.locator('body').evaluate((node,id)=>!!assignedSlots[id],next),true);
  await view(desktop,'activity');await view(desktop,'social');assert.equal(await frame.locator('body').evaluate((node,id)=>!!assignedSlots[id],next),true);
  assert.equal((await desktop.evaluate(()=>fetch('/api/social/state').then(r=>r.json()))).jobs.length,0);
 });
 await test('DARSHANFLOW separates connections, blocks reference posting and tracks nine manual shares',async()=>{
  const frame=desktop.frameLocator('#darshanflow-frame');
  await frame.getByRole('button',{name:'Publish',exact:true}).click();await frame.locator('[data-prepare="facebook"]').click();await frame.locator('#sf-message').filter({hasText:'Upload all 17 photos'}).waitFor();
  await frame.locator('[data-prepare="telegram"]').click();await frame.locator('#sf-message').filter({hasText:'Upload all 17 photos'}).waitFor();
  await frame.getByRole('button',{name:'Connections',exact:true}).click();assert.equal(await frame.locator('#sf-ig-token').getAttribute('type'),'password');await frame.getByText('How to connect Instagram without Facebook linking',{exact:true}).click();
  await desktop.locator('#darshanflow-frame').screenshot({path:path.join(output,'darshanflow-connections.png')});
  await frame.getByRole('button',{name:'WhatsApp',exact:true}).click();assert.equal(await frame.locator('.sf-target').count(),9);
  await frame.locator('#sf-programs [data-key="youtube"]').first().fill('https://www.youtube.com/live/abcdefghijk');await frame.locator('#sf-save-share').click();await frame.locator('#sf-message').filter({hasText:'Sharing setup saved'}).waitFor();
  await frame.locator('#sf-targets [data-done]').first().click();await frame.locator('#sf-shared-count').filter({hasText:'1 / 9 confirmed'}).waitFor();assert.ok((await frame.locator('#sf-share-preview').textContent()).includes('Mangal Arati Darshan'));
  await frame.locator('#sf-targets [data-done]').first().click();await frame.locator('#sf-shared-count').filter({hasText:'0 / 9 confirmed'}).waitFor();
  for(const width of [1440,390,320]){await desktop.setViewportSize({width,height:1000});await noOverflow(desktop);assert.ok(await frame.locator('body').evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));await desktop.locator('#darshanflow-frame').screenshot({path:path.join(output,'darshanflow-sharing-'+width+'.png')});}
  await desktop.setViewportSize({width:1440,height:1000});
 });
 await test('YouTube photo handoff saves exact sequence and requires an explicit published link',async()=>{
  const frame=desktop.frameLocator('#darshanflow-frame');await frame.getByRole('button',{name:'Photos',exact:true}).click();
  await frame.locator('body').evaluate(()=>{for(let i=1;i<=7;i++){const c=document.createElement('canvas');c.width=300;c.height=400;const x=c.getContext('2d');x.fillStyle='rgb('+i*25+',100,80)';x.fillRect(0,0,300,400);assignedSlots['P'+i]={dataUrl:c.toDataURL('image/png'),fileName:'qa-'+i+'.png'};}renderGrid();});
  await frame.getByRole('button',{name:'Publish',exact:true}).click();await frame.locator('[data-prepare="youtube"]').click();await frame.locator('#sf-review').waitFor({state:'visible'});assert.equal(await frame.locator('#sf-review-photos img').count(),7);
  await frame.locator('#sf-send').click();await frame.locator('#sf-export').waitFor({state:'visible'});assert.match(await frame.locator('#sf-youtube-open').getAttribute('href'),/youtube.com\/channel\/UC/);
  const result=await context.request.get(endpoints.desktop+await frame.locator('#sf-export').getAttribute('href'));assert.equal(result.status(),200);assert.equal((await result.body()).slice(0,2).toString(),'PK');
  await frame.locator('#sf-youtube-url').fill('https://www.youtube.com/post/qa-fixture');await frame.locator('#sf-youtube-done').click();await frame.locator('#sf-message').filter({hasText:'YouTube link saved as confirmed by you'}).waitFor();
  await frame.getByRole('button',{name:'WhatsApp',exact:true}).click();await frame.locator('#sf-use-links').click();assert.ok((await frame.locator('#sf-share-preview').textContent()).includes('/post/qa-fixture'));
  await desktop.reload();await desktop.locator('#app').waitFor({state:'visible'});await view(desktop,'social');await frame.locator('html[data-live-desk-theme="ready"]').waitFor();await frame.getByRole('button',{name:'Publish',exact:true}).click();await frame.locator('#sf-history').filter({hasText:'manual done'}).waitFor();
 });
 await test('Telegram restores saved connection and publishes two reviewed fixture albums',async()=>{
  const frame=desktop.frameLocator('#darshanflow-frame');await frame.getByRole('button',{name:'Connections',exact:true}).click();
  assert.equal(await frame.locator('#sf-tg-token').getAttribute('type'),'password');
  await frame.locator('body').evaluate(()=>{localStorage.setItem('df_pure_tgToken','123456789:'+'q'.repeat(35));localStorage.setItem('df_pure_tgChatId','@qa_darshan');});
  await frame.locator('#sf-import-telegram').click();await frame.locator('#sf-status-telegram').filter({hasText:'Verified'}).waitFor();
  assert.match(await frame.locator('#sf-account-telegram').textContent(),/QA Telegram channel/);
  assert.equal(await frame.locator('#sf-tg-token').inputValue(),'');assert.equal(await frame.locator('#sf-tg-channel').inputValue(),'@qa_darshan');
  assert.equal(await frame.locator('body').evaluate(()=>localStorage.getItem('df_pure_tgToken')),null);
  assert.ok(!JSON.stringify(await desktop.evaluate(()=>fetch('/api/studio/state').then(r=>r.json()))).includes('q'.repeat(35)));
  for(const width of [1440,390,320]){await desktop.setViewportSize({width,height:1000});await noOverflow(desktop);assert.ok(await frame.locator('body').evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));await desktop.locator('#darshanflow-frame').screenshot({path:path.join(output,'telegram-connections-'+width+'.png')});}
  await desktop.setViewportSize({width:1440,height:1000});
  await frame.getByRole('button',{name:'Photos',exact:true}).click();
  await frame.locator('body').evaluate(()=>{for(const [prefix,count,w,h] of [['P',7,300,400],['L',10,400,300]])for(let i=1;i<=count;i++){const c=document.createElement('canvas');c.width=w;c.height=h;const x=c.getContext('2d');x.fillStyle='rgb('+i*20+','+(prefix==='P'?80:140)+',100)';x.fillRect(0,0,w,h);assignedSlots[prefix+i]={dataUrl:c.toDataURL('image/png'),fileName:'qa-'+prefix+i+'.png'};}renderGrid();});
  await frame.getByRole('button',{name:'Publish',exact:true}).click();await frame.locator('#captionTitle').fill('QA Telegram darshan');await frame.locator('#captionBody').fill('Fixture caption only');await frame.locator('#captionTags').fill('#fixture');
  assert.equal(await frame.locator('#sf-mode-telegram').inputValue(),'TG');await frame.locator('[data-prepare="telegram"]').click();await frame.locator('#sf-review').waitFor({state:'visible'});
  assert.equal(await frame.locator('#sf-review-photos img').count(),17);assert.match(await frame.locator('#sf-review-note').textContent(),/7 portrait, then 10 landscape/);
  await desktop.locator('#darshanflow-frame').screenshot({path:path.join(output,'telegram-preview.png')});
  await frame.locator('#sf-send').click();await frame.locator('#sf-history').filter({hasText:'telegram · published'}).waitFor();
  assert.equal(await frame.locator('#sf-history a').filter({hasText:/Open album/}).count(),2);
  const saved=await desktop.evaluate(()=>fetch('/api/studio/state').then(r=>r.json()));const job=saved.jobs.find(j=>j.platforms[0]==='telegram');
  assert.equal(job.status,'published');assert.deepEqual(job.results.telegram.albums.map(a=>a.count),[7,10]);
  assert.equal((await desktop.evaluate(()=>fetch('/api/social/state').then(r=>r.json()))).enabled,false);
  await desktop.reload();await desktop.locator('#app').waitFor({state:'visible'});await view(desktop,'social');await frame.locator('html[data-live-desk-theme="ready"]').waitFor();await frame.getByRole('button',{name:'Connections',exact:true}).click();assert.equal(await frame.locator('#sf-tg-channel').inputValue(),'@qa_darshan');
 });
 await test('New section controls retain references, replace photos, add IST date and export selected sets',async()=>{
  const frame=desktop.frameLocator('#darshanflow-frame');await frame.getByRole('button',{name:'Photos',exact:true}).click();
  await frame.locator('body').evaluate(()=>{for(const [prefix,count,w,h] of [['P',7,300,400],['L',10,400,300]])for(let i=1;i<=count;i++){const c=document.createElement('canvas');c.width=w;c.height=h;const x=c.getContext('2d');x.fillStyle='rgb('+i*20+','+(prefix==='P'?90:150)+',110)';x.fillRect(0,0,w,h);assignedSlots[prefix+i]={dataUrl:c.toDataURL('image/png'),fileName:'qa-new-'+prefix+i+'.png'};}renderGrid();});
  const replace=frame.getByRole('button',{name:'Replace photo P1',exact:true});const reference=await replace.locator('img').first().getAttribute('src');
  const png=Buffer.from(await desktop.evaluate(()=>{const c=document.createElement('canvas');c.width=300;c.height=400;const x=c.getContext('2d');x.fillStyle='#cf803b';x.fillRect(0,0,300,400);return c.toDataURL('image/png').split(',')[1];}),'base64');
  await replace.click();await frame.locator('#sf-replace-photo').setInputFiles({name:'manual-photo.png',mimeType:'image/png',buffer:png});await frame.locator('#sf-message').filter({hasText:'Photo replaced in P1'}).waitFor();
  assert.equal(await frame.getByRole('button',{name:'Replace photo P1',exact:true}).locator('img').first().getAttribute('src'),reference);
  assert.equal(await frame.getByRole('button',{name:'Replace photo P1',exact:true}).locator('img').last().getAttribute('src'),'data:image/png;base64,'+png.toString('base64'));
  assert.equal(await frame.locator('#mainGrid select').first().locator('option').count(),17);
  await frame.getByRole('button',{name:'Publish',exact:true}).click();await frame.locator('#captionTitle').fill('Evening Darshan');await frame.locator('#captionBody').fill('Keep this exact description');await frame.locator('#captionTags').fill('#unchanged');await frame.locator('#sf-caption-date').fill('2026-10-16');
  for(let i=0;i<2;i++){const saved=desktop.waitForResponse(r=>r.url().endsWith('/api/studio/save'));await frame.locator('#sf-auto-date').click();await saved;await frame.locator('#sf-message').filter({hasText:'Date added to your title'}).waitFor();}
  assert.equal(await frame.locator('#captionTitle').inputValue(),'Evening Darshan · 16 Oct 2026');assert.equal(await frame.locator('#captionBody').inputValue(),'Keep this exact description');assert.equal(await frame.locator('#captionTags').inputValue(),'#unchanged');
  await frame.locator('[data-section="P1"]').click();assert.equal(await frame.locator('#sf-mode-facebook').inputValue(),'P1');
  const before=(await desktop.evaluate(()=>fetch('/api/studio/state').then(r=>r.json()))).jobs.length;
  const downloaded=desktop.waitForEvent('download');await frame.locator('#sf-download-section').click();await downloaded;await frame.locator('#sf-photo-package').waitFor({state:'visible'});assert.equal(await frame.locator('#sf-package-thumbs img').count(),7);
  const pack=await context.request.get(endpoints.desktop+await frame.locator('#sf-package-download').getAttribute('href'));assert.equal(pack.status(),200);assert.equal((await pack.body()).slice(0,2).toString(),'PK');
  assert.equal((await desktop.evaluate(()=>fetch('/api/studio/state').then(r=>r.json()))).jobs.length,before);
  await frame.locator('[data-section="BOTH"]').click();await frame.locator('#sf-whatsapp-photos').click();await frame.locator('#sf-package-note').filter({hasText:'separate 7-portrait and 10-landscape folders'}).waitFor();assert.equal(await frame.locator('#sf-package-thumbs img').count(),17);
  await frame.locator('body').evaluate(()=>Object.defineProperty(navigator,'canShare',{configurable:true,value:()=>false}));await frame.locator('#sf-package-native').click();await frame.locator('#sf-message').filter({hasText:'cannot share this photo set directly'}).waitFor();
  await desktop.locator('#darshanflow-frame').screenshot({path:path.join(output,'studio-selected-package.png')});
 });
 await test('All connected review dispatches fixture Telegram once and prepares two manual YouTube posts',async()=>{
  const frame=desktop.frameLocator('#darshanflow-frame');await frame.locator('[data-section="BOTH"]').click();await frame.locator('#sf-all-connected').click();await frame.locator('#sf-batch-review').waitFor({state:'visible'});
  assert.equal(await frame.locator('.sf-batch-job').count(),3);assert.deepEqual(await frame.locator('.sf-batch-job').evaluateAll(nodes=>nodes.map(n=>n.querySelectorAll('img').length)),[17,7,10]);
  const snapshot=await desktop.evaluate(()=>fetch('/api/studio/state').then(r=>r.json())),batch=snapshot.batches.at(-1);
  assert.ok(batch.jobs.every(id=>snapshot.jobs.find(j=>j.id===id).status==='draft'));
  await desktop.locator('#darshanflow-frame').screenshot({path:path.join(output,'studio-connected-review.png')});
  await frame.locator('#sf-send-batch').click();await frame.locator('#sf-batch-summary').filter({hasText:'YouTube handoff ready'}).waitFor();
  const after=await desktop.evaluate(()=>fetch('/api/studio/state').then(r=>r.json()));assert.deepEqual(batch.jobs.map(id=>after.jobs.find(j=>j.id===id).status),['published','manual_ready','manual_ready']);assert.equal(await frame.locator('#sf-send-batch').isVisible(),false);
  for(const width of [1440,390,320]){await desktop.setViewportSize({width,height:1000});await noOverflow(desktop);assert.ok(await frame.locator('body').evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));await desktop.locator('#darshanflow-frame').screenshot({path:path.join(output,'studio-batch-'+width+'.png')});}
  await desktop.setViewportSize({width:1440,height:1000});await desktop.reload();await desktop.locator('#app').waitFor({state:'visible'});await view(desktop,'social');await frame.locator('html[data-live-desk-theme="ready"]').waitFor();await frame.getByRole('button',{name:'Publish',exact:true}).click();await frame.locator('#sf-saved-batches button').first().click();await frame.locator('#sf-batch-summary').filter({hasText:'YouTube handoff ready'}).waitFor();assert.equal(await frame.locator('#sf-send-batch').isVisible(),false);
 });
 await test('Custom schedule, end time and camera action survive save/reload',async()=>{
  await view(desktop,'schedule');await desktop.locator('#add-program').click();const p=desktop.locator('.schedule-program');await p.locator('[data-field="name"]').fill('Evening Service');await programTab(desktop,'content');await p.locator('[data-field="reference"]').fill('abcdefghijk');await programTab(desktop);await p.locator('[data-field="at"]').fill('18:00');await p.locator('[data-field="end_at"]').fill('18:30');await p.locator('[data-field="enabled"]').check();await programTab(desktop,'camera');await p.locator('.add-action').click();await p.locator('[data-field="kind"]').selectOption('preset');await p.locator('[data-field="number"]').fill('3');await saveSchedule(desktop);
  await desktop.reload();await desktop.locator('.schedule-program').waitFor();assert.equal(await desktop.locator('[data-field="name"]').inputValue(),'Evening Service');const saved=(await state(desktop)).schedule[0];assert.equal(saved.end_at,'18:30');assert.equal(saved.camera_actions[0].number,3);assert.equal(saved.camera_actions[0].kind,'preset');assert.equal(saved.camera_actions[0].only_if_live,true);await desktop.screenshot({path:path.join(output,'desktop-schedule.png'),fullPage:true});
 });
 await test('Progress, readiness, program content and inline update controls',async()=>{
  await view(desktop,'overview');await desktop.locator('#readiness').getByRole('heading',{name:'Ready for automation?'}).waitFor();await desktop.locator('#live-monitor').getByRole('heading',{name:'Observed live status'}).waitFor();await noOverflow(desktop);
  await view(desktop,'content');await desktop.locator('#content-title').fill('{date} | {program} | Darshan');await desktop.locator('#content-mode').selectOption('custom');await desktop.locator('#content-description').fill('The same saved description for each run.');
  const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAIAAAABCAIAAAB7QOjdAAAAD0lEQVR4nGN4sKBAxtYIAAsnAnyYPiW8AAAAAElFTkSuQmCC','base64');await desktop.getByLabel('Upload thumbnail for day 9',{exact:true}).setInputFiles({name:'thumbnail.png',mimeType:'image/png',buffer:png});await desktop.locator('#toast').filter({hasText:'Thumbnail uploaded'}).waitFor();
  await desktop.locator('#content-save').click();const response=desktop.waitForResponse(r=>r.url().endsWith('/api/schedule'));await confirm(desktop);assert.equal((await response).status(),200);await desktop.waitForFunction(()=>!document.getElementById('content-save').disabled);
  const saved=(await state(desktop)).schedule[0];assert.equal(saved.description,'The same saved description for each run.');assert.ok(saved.thumbnail_days['9']);assert.equal((await state(desktop)).destinations.youtube_stream_title,'YouTube Official Livestream');await desktop.screenshot({path:path.join(output,'program-content-desktop.png'),fullPage:true});await noOverflow(desktop);
  await view(desktop,'schedule');await saveSchedule(desktop);assert.equal((await state(desktop)).schedule[0].thumbnail_days['9'],saved.thumbnail_days['9']);
  await view(desktop,'updates');await desktop.locator('#dashboard-update').waitFor();assert.equal(await desktop.locator('#update-install').isDisabled(),true);await desktop.screenshot({path:path.join(output,'updates-dashboard.png'),fullPage:true});await noOverflow(desktop);await view(desktop,'schedule');
 });
 await test('Calendar recurrence, preview and credential-free backup round trip',async()=>{
  await programTab(desktop);await desktop.locator('[data-field="repeat"]').selectOption('weekdays');await desktop.locator('[data-field="weekdays"]').fill('1,3,5');await desktop.locator('[data-field="prepare_minutes"]').fill('20');await saveSchedule(desktop);
  const s=await state(desktop);assert.deepEqual(s.schedule[0].weekdays,[0,2,4]);assert.equal(s.schedule[0].prepare_minutes,20);assert.ok(s.upcoming.length>0);assert.equal((Date.parse(s.upcoming[0].due)-Date.parse(s.upcoming[0].prepare_at))/60000,20);
  await view(desktop,'recovery');const download=desktop.waitForEvent('download');await desktop.locator('#backup-export').click();const backup=JSON.parse(await fs.readFile(await (await download).path(),'utf8'));assert.equal(backup.format,'live-desk-settings');assert.ok(!JSON.stringify(backup).includes('qa-only-secret'));assert.equal(backup.settings.obs_exe,undefined);
  await desktop.locator('#backup-file').setInputFiles({name:'backup.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(backup))});await desktop.locator('#backup-restore').click();const response=desktop.waitForResponse(r=>r.url().endsWith('/api/restore'));await confirm(desktop);assert.equal((await response).status(),200);await desktop.waitForFunction(()=>!document.getElementById('backup-restore').disabled);await noOverflow(desktop);await desktop.screenshot({path:path.join(output,'recovery-desktop.png'),fullPage:true});await view(desktop,'schedule');
 });
 await test('Polling preserves unsaved edits; cancelled save/removal keeps saved plan',async()=>{
  await programTab(desktop);await desktop.locator('[data-field="name"]').fill('Unsaved Edit');await desktop.waitForResponse(r=>r.url().endsWith('/api/state'));assert.equal(await desktop.locator('[data-field="name"]').inputValue(),'Unsaved Edit');await desktop.locator('#save-schedule').click();await desktop.locator('#confirm-cancel').click();assert.equal((await state(desktop)).schedule[0].name,'Evening Service');await desktop.getByRole('button',{name:'Remove program',exact:true}).click();await desktop.locator('#confirm-cancel').click();assert.equal(await desktop.locator('.schedule-program').count(),1);await desktop.locator('#reload-schedule').click();await confirm(desktop);assert.equal(await desktop.locator('[data-field="name"]').inputValue(),'Evening Service');
 });
 await test('Mobile viewport and remote credential restrictions',async()=>{
  const phone=await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true});phone.on('page',p=>p.on('pageerror',e=>report.errors.push(e.message)));mobile=await phone.newPage();await pair(mobile,endpoints.mobile);assert.equal(await mobile.locator('#pc-nav').isVisible(),false);assert.equal(await mobile.locator('#pc-lan-tools').isVisible(),false);assert.equal((await state(mobile)).local,false);assert.equal((await state(mobile)).settings,null);await view(mobile,'connections');assert.equal(await mobile.locator('#settings-form').isVisible(),false);await mobile.locator('#remote-settings').waitFor({state:'visible'});
  const result=await mobile.evaluate(async()=>{const s=await fetch('/api/state').then(r=>r.json());return (await fetch('/api/settings',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':s.csrf},body:JSON.stringify({workspace_name:'Remote change'})})).status;});assert.equal(result,403);await noOverflow(mobile);await mobile.screenshot({path:path.join(output,'mobile-setup.png'),fullPage:true});
  await view(mobile,'schedule');await programTab(mobile);await mobile.getByLabel('Live start (IST)',{exact:true}).fill('18:05');await saveSchedule(mobile);assert.equal((await state(desktop)).schedule[0].at,'18:05');await noOverflow(mobile);await mobile.screenshot({path:path.join(output,'mobile-schedule.png'),fullPage:true});await mobile.setViewportSize({width:320,height:740});await noOverflow(mobile);
 });
 await test('Connection loss disables controls and recovers without a new login',async()=>{
  await desktop.route('**/api/state',route=>route.abort());await desktop.locator('#offline').waitFor({state:'visible'});assert.equal(await desktop.locator('#save-schedule').isDisabled(),true);assert.equal(await desktop.locator('#arm').isDisabled(),true);await desktop.unroute('**/api/state');await desktop.locator('#offline').waitFor({state:'hidden'});assert.equal(await desktop.locator('#save-schedule').isDisabled(),false);
 });
 await test('Compact schedule preserves drafts across programs, tabs and polling',async()=>{
  await desktop.reload();await desktop.locator('.schedule-program').waitFor();
  assert.equal(await desktop.locator('.schedule-program[open]').count(),0);
  const saved=(await state(desktop)).schedule[0];
  await desktop.locator('#add-program').click();await desktop.locator('.schedule-program').nth(1).locator('[data-field="name"]').fill('Draft second program');
  await programTab(desktop,'timings',0);assert.equal(await desktop.locator('.schedule-program[open]').count(),1);
  await programTab(desktop,'content',0);await desktop.locator('.schedule-program').nth(0).locator('[data-field="title_template"]').fill('{date} | Draft title');
  await programTab(desktop,'timings',1);assert.equal(await desktop.locator('.schedule-program').nth(1).locator('[data-field="name"]').inputValue(),'Draft second program');
  await desktop.waitForResponse(r=>r.url().endsWith('/api/state'));
  assert.equal(await desktop.locator('.schedule-program[open]').count(),1);
  await desktop.locator('#schedule-dirty').filter({hasText:'Unsaved changes'}).waitFor();
  await desktop.locator('#reload-schedule').click();await confirm(desktop);
  assert.equal(await desktop.locator('.schedule-program').count(),1);assert.equal((await state(desktop)).schedule[0].title_template,saved.title_template);
  // Four program summaries must fit without the old multi-page form stack.
  for(const [name,at,end] of [['Mangal Arati Darshan','04:30','05:25'],['Darshan Arati','07:30','08:00'],['Rajbhog Arati','12:00','12:40']]){
   await desktop.locator('#add-program').click();const p=desktop.locator('.schedule-program').last();await p.locator('[data-field="name"]').fill(name);await p.locator('[data-field="at"]').fill(at);await p.locator('[data-field="end_at"]').fill(end);await p.locator('[data-field="enabled"]').check();await p.locator('.program-summary').click();
  }
  assert.equal(await desktop.locator('.schedule-program[open]').count(),0);
  assert.ok((await desktop.locator('#schedule-editor').boundingBox()).height<420,'Four collapsed programs should occupy less than 420 pixels');
  await desktop.screenshot({path:path.join(output,'schedule-four-programs.png'),fullPage:true});
  await programTab(desktop,'camera',0);
  for(let i=0;i<7;i++)await desktop.locator('.schedule-program').first().locator('.add-action').click();
  assert.equal(await desktop.locator('.schedule-program').first().locator('.camera-editor-row').count(),8);
  assert.equal(await desktop.locator('.camera-editor-row[open]').count(),1);
  const draft=await desktop.evaluate(()=>readEditor());await programTab(desktop,'content',0);await programTab(desktop,'camera',0);assert.deepEqual(await desktop.evaluate(()=>readEditor()),draft);
  await desktop.screenshot({path:path.join(output,'schedule-eight-camera-steps.png'),fullPage:true});
  await desktop.locator('#reload-schedule').click();await confirm(desktop);
  // The fake backend is unchanged; compact navigation performs no schedule writes.
  for(const width of [1440,980,390,320]){await desktop.setViewportSize({width,height:900});await noOverflow(desktop);await programTab(desktop,'camera');await noOverflow(desktop);await desktop.screenshot({path:path.join(output,'compact-schedule-'+width+'.png'),fullPage:true});}
  await desktop.setViewportSize({width:1440,height:1000});
 });
 await test('Saved program removal and empty schedule persist',async()=>{
  await desktop.reload();await desktop.locator('.schedule-program').waitFor();await programTab(desktop);await desktop.getByRole('button',{name:'Remove program',exact:true}).click();await confirm(desktop);await saveSchedule(desktop);assert.equal((await state(desktop)).schedule.length,0);await desktop.reload();await desktop.locator('#app').waitFor({state:'visible'});assert.equal(await desktop.locator('.schedule-program').count(),0);
 });
 await test('Visible mode controls are local, default API and retain unsaved values',async()=>{
  await view(desktop,'visible');await desktop.locator('#visible-local').waitFor({state:'visible'});assert.equal(await desktop.locator('#visible-mode').inputValue(),'api');await desktop.locator('#visible-identity-text').fill('Unsaved identity');await desktop.waitForResponse(r=>r.url().endsWith('/api/state'));assert.equal(await desktop.locator('#visible-identity-text').inputValue(),'Unsaved identity');await noOverflow(desktop);await desktop.screenshot({path:path.join(output,'visible-desktop.png'),fullPage:true});
  // The owner's setup controls must remain readable on narrow windows too,
  // not just in the remote status-only mobile view.
  for(const width of [980,390,320]){
   await desktop.setViewportSize({width,height:1000});await noOverflow(desktop);
   await desktop.locator('.visible-setup-grid').screenshot({path:path.join(output,'visible-owner-'+width+'.png')});
  }
  await desktop.setViewportSize({width:1440,height:1000});
  assert.equal(await desktop.locator('#visible-connect-chrome').isDisabled(),true);
  await desktop.locator('#visible-browser-source').selectOption('running_chrome');
  await desktop.waitForResponse(r=>r.url().endsWith('/api/state'));
  assert.equal(await desktop.locator('#visible-browser-source').inputValue(),'running_chrome');
  await desktop.locator('#visible-chrome-status').filter({hasText:'Browser choice has not been saved'}).waitFor();
  // Saving only the browser must not commit an unsaved execution-mode choice.
  await desktop.locator('#visible-mode').selectOption('visible');
  const savedBrowser=desktop.waitForResponse(r=>r.url().endsWith('/api/visible/save'));await desktop.locator('#visible-save-browser').click();assert.equal((await savedBrowser).status(),200);
  await desktop.waitForFunction(()=>!document.getElementById('visible-connect-chrome').disabled);
  assert.equal((await state(desktop)).visible.browser_source,'running_chrome');
  assert.equal((await state(desktop)).visible.chrome_connected,false);
  assert.equal((await state(desktop)).visible.mode,'api');
  await desktop.reload();await desktop.locator('#app').waitFor({state:'visible'});await view(desktop,'visible');
  assert.equal(await desktop.locator('#visible-browser-source').inputValue(),'running_chrome');
  await view(mobile,'visible');await mobile.locator('#visible-remote').waitFor({state:'visible'});assert.equal(await mobile.locator('#visible-local').isVisible(),false);const status=await mobile.evaluate(async()=>{const s=await fetch('/api/state').then(r=>r.json());return (await fetch('/api/visible/save',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':s.csrf},body:JSON.stringify({mode:'visible'})})).status;});assert.equal(status,403);assert.equal((await state(mobile)).visible.recipes,undefined);await noOverflow(mobile);await mobile.screenshot({path:path.join(output,'visible-mobile.png'),fullPage:true});
  const connectionStatus=await mobile.evaluate(async()=>{const s=await fetch('/api/state').then(r=>r.json());return (await fetch('/api/visible/browser',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':s.csrf},body:JSON.stringify({action:'connect'})})).status;});
  assert.equal(connectionStatus,403);assert.equal((await state(mobile)).visible.browser_source,undefined);
 });
 await test('Existing live preview, cancellation, explicit takeover, mobile layout and pause',async()=>{
  const before=await state(desktop), now=Date.parse(before.now);
  const ist=ms=>new Date(ms).toLocaleString('sv-SE',{timeZone:'Asia/Kolkata'});
  const start=ist(now-10*60000),end=ist(now+10*60000),camera=ist(now+3*60000);
  const slot={id:'qa-takeover',name:'QA existing live',reference:'P8-DKvGQLDs',title_template:'{date} | {program}',enabled:true,at:start.slice(11,16),end_at:end.slice(11,16),end_next_day:end.slice(0,10)!==start.slice(0,10),repeat:'once',on_date:start.slice(0,10),camera_actions:[{kind:'patrol_start',number:8,timing:'after_live',delay_seconds:120,at:'',next_day:false,only_if_live:true},{kind:'preset',number:2,timing:'clock',delay_seconds:0,at:camera.slice(11,16),next_day:camera.slice(0,10)!==start.slice(0,10),only_if_live:true}]};
  const saved=await desktop.evaluate(async schedule=>{const st=await fetch('/api/state').then(r=>r.json());return (await fetch('/api/schedule',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':st.csrf},body:JSON.stringify({schedule,grace_minutes:2,confirmed:true})})).status;},[slot]);assert.equal(saved,200);
  await desktop.reload();await desktop.locator('#app').waitFor({state:'visible'});await view(desktop,'overview');
  await desktop.locator('#takeover-panel summary').click();await desktop.locator('#takeover-date').fill(start.slice(0,10));
  await desktop.locator('#takeover-inspect').click();await desktop.waitForFunction(()=>!document.getElementById('takeover-confirm').hidden&&!document.getElementById('takeover-confirm').disabled);
  assert.match(await desktop.locator('#takeover-preview').innerText(),/QA existing YouTube live/);
  assert.match(await desktop.locator('#takeover-preview').innerText(),/Skipped · before control began/);
  assert.equal((await state(desktop)).armed,false);assert.equal((await state(desktop)).runs.length,0);
  await desktop.locator('#takeover-confirm').click();await desktop.locator('#confirm-cancel').click();assert.equal((await state(desktop)).runs.length,0);
  for(const width of [1440,390,320]){await desktop.setViewportSize({width,height:1000});await noOverflow(desktop);await desktop.locator('#takeover-panel').screenshot({path:path.join(output,'takeover-'+width+'.png')});}
  await desktop.setViewportSize({width:1440,height:1000});await desktop.locator('#takeover-confirm').click();await confirm(desktop);
  await desktop.waitForFunction(()=>document.getElementById('arm-badge').textContent==='Automation enabled');
  const active=await state(desktop);assert.equal(active.takeover.status,'active');assert.equal(active.runs.length,1);assert.equal(active.progress.origin,'manual_takeover');assert.equal(active.progress.started_by_app,false);assert.ok(!JSON.stringify(active).includes('qa-not-a-secret'));
  await desktop.locator('#pause').click();await desktop.waitForFunction(()=>!document.getElementById('takeover-inspect').disabled);assert.equal((await state(desktop)).armed,false);assert.equal((await state(desktop)).takeover.status,'paused');
 });
 assert.deepEqual(report.errors,[],'no uncaught browser errors');report.status='passed';
})().catch(async error=>{report.status='failed';report.failure=error.stack;console.error(error);if(desktop)await desktop.screenshot({path:path.join(output,'failure.png'),fullPage:true}).catch(()=>{});process.exitCode=1;}).finally(async()=>{
 if(browser)await browser.close();if(server&&server.exitCode===null){const exit=once(server,'exit');server.stdin.end();const timer=setTimeout(()=>server.kill(),5000);await exit.catch(()=>{});clearTimeout(timer);}await fs.mkdir(output,{recursive:true});await fs.writeFile(path.join(output,'report.json'),JSON.stringify(report,null,2));
});

