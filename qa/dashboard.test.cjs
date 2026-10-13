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
 await test('Social media imports, photo editing, exact approval, cancelled edits and mobile layout',async()=>{
  await view(desktop,'social');await desktop.locator('#social-compose').waitFor({state:'visible'});
  await desktop.locator('[data-social-tab="accounts"]').click();await desktop.locator('#social-detect').click();await desktop.locator('#social-account-list').filter({hasText:'fixture_instagram'}).waitFor();await desktop.locator('#social-use-linked').click();await desktop.locator('#social-save-account').click();
  await desktop.locator('[data-social-tab="compose"]').click();const png=Buffer.from(await desktop.evaluate(async()=>{const canvas=document.createElement('canvas');canvas.width=720;canvas.height=900;const ctx=canvas.getContext('2d');ctx.fillStyle='#e7eee2';ctx.fillRect(0,0,720,900);const image=new Image();await new Promise((resolve,reject)=>{image.onload=resolve;image.onerror=reject;image.src='/icon.svg';});ctx.drawImage(image,190,270,340,340);return canvas.toDataURL('image/png').split(',')[1];}),'base64');
  await desktop.locator('#social-files').setInputFiles({name:'darshan.png',mimeType:'image/png',buffer:png});await desktop.locator('#social-upload-status').filter({hasText:'1 files imported'}).waitFor();
  await desktop.getByRole('checkbox',{name:'Select darshan.png',exact:true}).check();await desktop.locator('#social-title').fill('Evening darshan');await desktop.locator('#social-caption').fill('Reviewed devotional caption.');
  await desktop.locator('#social-media-picker').getByRole('button',{name:'Edit photo'}).click();await desktop.locator('#social-edit-dialog').waitFor({state:'visible'});await desktop.locator('#social-crop').selectOption('1');await desktop.locator('#social-watermark').check();await desktop.locator('#social-edit-dialog').screenshot({path:path.join(output,'social-photo-editor.png')});await desktop.locator('#social-edit-save').click();await desktop.locator('#social-edit-dialog').waitFor({state:'hidden'});await desktop.getByRole('checkbox',{name:'Select darshan-edited.jpg',exact:true}).waitFor();
  assert.equal(await desktop.getByRole('checkbox',{name:'Select darshan-edited.jpg',exact:true}).isChecked(),true);
  const response=desktop.waitForResponse(r=>r.url().endsWith('/api/social/draft'));await desktop.locator('#social-save').click();assert.equal((await response).status(),200);await desktop.locator('#social-approve').waitFor();
  await desktop.locator('#social-caption').fill('Unapproved edit');assert.equal(await desktop.locator('#social-approve').isDisabled(),true);await desktop.waitForResponse(r=>r.url().endsWith('/api/social/state'));assert.equal(await desktop.locator('#social-caption').inputValue(),'Unapproved edit');
  await desktop.locator('#social-save').click();await desktop.waitForFunction(()=>!document.getElementById('social-approve').disabled);await desktop.locator('#social-approve').click();await desktop.locator('#confirm-cancel').click();
  let social=await desktop.evaluate(()=>fetch('/api/social/state').then(r=>r.json()));assert.equal(social.jobs[0].status,'draft');assert.equal(social.enabled,false);
  await desktop.locator('#social-approve').click();const approved=desktop.waitForResponse(r=>r.url().endsWith('/api/social/action'));await confirm(desktop);assert.equal((await approved).status(),200);await desktop.locator('#social-queue').waitFor({state:'visible'});social=await desktop.evaluate(()=>fetch('/api/social/state').then(r=>r.json()));assert.equal(social.jobs[0].status,'queued');assert.equal(social.jobs[0].caption,'Unapproved edit');assert.equal(social.jobs[0].targets.facebook,'123456789');assert.ok(!JSON.stringify(social).includes('qa-only-secret'));assert.equal(social.enabled,false);
  for(const width of [1440,980,390,320]){await desktop.setViewportSize({width,height:1000});await noOverflow(desktop);await desktop.screenshot({path:path.join(output,'social-queue-'+width+'.png'),fullPage:true});await desktop.locator('[data-social-tab="compose"]').click();await noOverflow(desktop);await desktop.screenshot({path:path.join(output,'social-compose-'+width+'.png'),fullPage:true});await desktop.locator('[data-social-tab="queue"]').click();}
  await desktop.setViewportSize({width:1440,height:1000});await desktop.locator('#social-job-list').getByRole('button',{name:'Cancel',exact:true}).click();await confirm(desktop);await desktop.locator('#social-job-list').filter({hasText:'Cancelled'}).waitFor();
  await desktop.locator('#social-job-list').getByRole('button',{name:'Edit draft'}).click();await desktop.locator('#social-save').click();await desktop.waitForFunction(()=>!document.getElementById('social-approve').disabled);social=await desktop.evaluate(()=>fetch('/api/social/state').then(r=>r.json()));assert.equal(social.jobs[0].status,'draft');assert.deepEqual(social.jobs[0].targets,{});
  await desktop.locator('#social-enable').click();await desktop.locator('#confirm-cancel').click();assert.equal((await desktop.evaluate(()=>fetch('/api/social/state').then(r=>r.json()))).enabled,false);
 });
 await test('Darshan structure creates exact five drafts and manual photo package without API posting',async()=>{
  await desktop.locator('[data-social-tab="batch"]').click();await desktop.locator('#batch-portrait select').first().waitFor();
  const structure=await desktop.evaluate(()=>fetch('/api/social/state').then(r=>r.json()).then(s=>s.structure));
  const files=[];for(const slot of structure.slots){const encoded=await desktop.evaluate(slot=>{const c=document.createElement('canvas');c.width=slot.index<7?300:400;c.height=slot.index<7?400:300;const ctx=c.getContext('2d');ctx.fillStyle=`hsl(${slot.index*21},35%,65%)`;ctx.fillRect(0,0,c.width,c.height);ctx.fillStyle='#193b2b';ctx.font='24px sans-serif';ctx.fillText(slot.reference,20,80);return c.toDataURL('image/jpeg',.92).split(',')[1];},slot);files.push({name:slot.reference+'.jpg',mimeType:'image/jpeg',buffer:Buffer.from(encoded,'base64')});}
  await desktop.locator('#batch-files').setInputFiles(files);await desktop.locator('#batch-upload-status').filter({hasText:'17 / 17 imported'}).waitFor();await desktop.waitForFunction(()=>!document.getElementById('batch-match').disabled);
  await desktop.locator('#batch-match').click();await desktop.locator('#batch-count').filter({hasText:'17 / 17'}).waitFor();
  await desktop.locator('#batch-title').fill('Test darshan');await desktop.locator('#batch-caption').fill('Same caption for all five posts.');
  await desktop.waitForResponse(r=>r.url().endsWith('/api/social/state'));assert.equal(await desktop.locator('#batch-caption').inputValue(),'Same caption for all five posts.');
  // Editing a batch photo preselects the PPT crop and retains its slot.
  await desktop.locator('#batch-portrait .batch-slot').first().getByRole('button',{name:'Edit crop'}).click();await desktop.locator('#social-edit-dialog').waitFor({state:'visible'});assert.equal(await desktop.locator('#social-crop').inputValue(),'0.75');await desktop.locator('#social-edit-save').click();await desktop.locator('#social-edit-dialog').waitFor({state:'hidden'});
  const save=desktop.waitForResponse(r=>r.url().endsWith('/api/social/batch'));await desktop.locator('#batch-save').click();assert.equal((await save).status(),200);await desktop.waitForFunction(()=>!document.getElementById('batch-build').disabled);
  for(const width of [1440,390,320]){await desktop.setViewportSize({width,height:1000});await noOverflow(desktop);await desktop.screenshot({path:path.join(output,'darshan-batch-'+width+'.png'),fullPage:true});}await desktop.setViewportSize({width:1440,height:1000});
  const build=desktop.waitForResponse(r=>r.url().endsWith('/api/social/batch'));await desktop.locator('#batch-build').click();assert.equal((await build).status(),200);await desktop.locator('#social-queue').waitFor({state:'visible'});
  let s=await desktop.evaluate(()=>fetch('/api/social/state').then(r=>r.json()));const jobs=s.batch.jobs.map(id=>s.jobs.find(j=>j.id===id));assert.deepEqual(jobs.map(j=>j.media.length),[7,10,7,10,17]);assert.ok(jobs.every(j=>j.status==='draft'));assert.equal(s.enabled,false);assert.deepEqual(jobs[4].media,structure.facebook_order.map(i=>s.batch.slots[i]));
  await desktop.locator('[data-social-tab="batch"]').click();await desktop.locator('#batch-build').click();await desktop.locator('#social-queue').waitFor({state:'visible'});s=await desktop.evaluate(()=>fetch('/api/social/state').then(r=>r.json()));assert.equal(s.jobs.length,6);
  const job=jobs[2],card=desktop.locator('#social-job-list .social-job').filter({has:desktop.getByRole('heading',{name:job.title,exact:true})});await card.getByRole('button',{name:'Preview & approve'}).click();await desktop.locator('#confirm-text').filter({hasText:'Enabling posting will NOT send'}).waitFor();await confirm(desktop);await card.filter({hasText:'Ready · manual upload'}).waitFor();
  const download=desktop.waitForEvent('download');await card.getByRole('link',{name:'Download ordered photos'}).click();const file=await download;const raw=await fs.readFile(await file.path());assert.ok(raw.subarray(0,2).equals(Buffer.from('PK')));assert.ok(raw.includes(Buffer.from('Same caption for all five posts.')));assert.ok(raw.includes(Buffer.from('01_DSC03639')));
  await card.getByRole('button',{name:'Mark completed'}).click();await desktop.locator('#confirm-cancel').click();assert.equal((await desktop.evaluate(()=>fetch('/api/social/state').then(r=>r.json()))).jobs.find(j=>j.id===job.id).status,'manual_ready');
  await desktop.locator('[data-social-tab="batch"]').click();await desktop.reload();await desktop.locator('#app').waitFor({state:'visible'});await view(desktop,'social');await desktop.locator('[data-social-tab="batch"]').click();await desktop.locator('#batch-count').filter({hasText:'17 / 17'}).waitFor();assert.equal(await desktop.locator('#batch-caption').inputValue(),'Same caption for all five posts.');
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
 assert.deepEqual(report.errors,[],'no uncaught browser errors');report.status='passed';
})().catch(async error=>{report.status='failed';report.failure=error.stack;console.error(error);if(desktop)await desktop.screenshot({path:path.join(output,'failure.png'),fullPage:true}).catch(()=>{});process.exitCode=1;}).finally(async()=>{
 if(browser)await browser.close();if(server&&server.exitCode===null){const exit=once(server,'exit');server.stdin.end();const timer=setTimeout(()=>server.kill(),5000);await exit.catch(()=>{});clearTimeout(timer);}await fs.mkdir(output,{recursive:true});await fs.writeFile(path.join(output,'report.json'),JSON.stringify(report,null,2));
});

