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
 await test('Setup saves destinations, preserves blank secret, and rejects invalid channel',async()=>{
  await view(desktop,'connections');await desktop.locator('#field-workspace_name').fill('Temple Test Desk');await desktop.locator('#field-youtube_channel_id').fill('invalid');assert.equal((await saveSettings(desktop)).status(),409);assert.equal((await state(desktop)).workspace_name,'My Live Desk');
  await desktop.locator('#field-youtube_channel_id').fill('UC'+'a'.repeat(22));await desktop.locator('#field-facebook_page_id').fill('123456789');await desktop.locator('#field-youtube_stream_title').fill('YouTube Official Livestream');await desktop.locator('#field-obs_collection').fill('Test Collection');assert.equal((await saveSettings(desktop)).status(),200);
  const s=await state(desktop);assert.equal(s.workspace_name,'Temple Test Desk');assert.equal(s.destinations.youtube_stream_title,'YouTube Official Livestream');assert.ok(!JSON.stringify(s).includes('qa-only-secret'));assert.equal(await desktop.locator('#field-facebook_page_token').inputValue(),'');await desktop.screenshot({path:path.join(output,'desktop-setup.png'),fullPage:true});await noOverflow(desktop);
 });
 await test('Custom schedule, end time and camera action survive save/reload',async()=>{
  await view(desktop,'schedule');await desktop.locator('#add-program').click();const p=desktop.locator('.schedule-program');await p.locator('[data-field="name"]').fill('Evening Service');await p.locator('[data-field="reference"]').fill('abcdefghijk');await p.locator('[data-field="at"]').fill('18:00');await p.locator('[data-field="end_at"]').fill('18:30');await p.locator('[data-field="enabled"]').check();await p.locator('.add-action').click();await p.locator('[data-field="kind"]').selectOption('preset');await p.locator('[data-field="number"]').fill('3');await saveSchedule(desktop);
  await desktop.reload();await desktop.locator('.schedule-program').waitFor();assert.equal(await desktop.locator('[data-field="name"]').inputValue(),'Evening Service');const saved=(await state(desktop)).schedule[0];assert.equal(saved.end_at,'18:30');assert.equal(saved.camera_actions[0].number,3);assert.equal(saved.camera_actions[0].kind,'preset');assert.equal(saved.camera_actions[0].only_if_live,true);await desktop.screenshot({path:path.join(output,'desktop-schedule.png'),fullPage:true});
 });
 await test('Calendar recurrence, preview and credential-free backup round trip',async()=>{
  await desktop.locator('[data-field="repeat"]').selectOption('weekdays');await desktop.locator('[data-field="weekdays"]').fill('1,3,5');await desktop.locator('[data-field="prepare_minutes"]').fill('20');await saveSchedule(desktop);
  const s=await state(desktop);assert.deepEqual(s.schedule[0].weekdays,[0,2,4]);assert.equal(s.schedule[0].prepare_minutes,20);assert.ok(s.upcoming.length>0);assert.equal((Date.parse(s.upcoming[0].due)-Date.parse(s.upcoming[0].prepare_at))/60000,20);
  await view(desktop,'recovery');const download=desktop.waitForEvent('download');await desktop.locator('#backup-export').click();const backup=JSON.parse(await fs.readFile(await (await download).path(),'utf8'));assert.equal(backup.format,'live-desk-settings');assert.ok(!JSON.stringify(backup).includes('qa-only-secret'));assert.equal(backup.settings.obs_exe,undefined);
  await desktop.locator('#backup-file').setInputFiles({name:'backup.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(backup))});await desktop.locator('#backup-restore').click();const response=desktop.waitForResponse(r=>r.url().endsWith('/api/restore'));await confirm(desktop);assert.equal((await response).status(),200);await desktop.waitForFunction(()=>!document.getElementById('backup-restore').disabled);await noOverflow(desktop);await desktop.screenshot({path:path.join(output,'recovery-desktop.png'),fullPage:true});await view(desktop,'schedule');
 });
 await test('Polling preserves unsaved edits; cancelled save/removal keeps saved plan',async()=>{
  await desktop.locator('[data-field="name"]').fill('Unsaved Edit');await desktop.waitForResponse(r=>r.url().endsWith('/api/state'));assert.equal(await desktop.locator('[data-field="name"]').inputValue(),'Unsaved Edit');await desktop.locator('#save-schedule').click();await desktop.locator('#confirm-cancel').click();assert.equal((await state(desktop)).schedule[0].name,'Evening Service');await desktop.getByRole('button',{name:'Remove program',exact:true}).click();await desktop.locator('#confirm-cancel').click();assert.equal(await desktop.locator('.schedule-program').count(),1);await desktop.locator('#reload-schedule').click();await confirm(desktop);assert.equal(await desktop.locator('[data-field="name"]').inputValue(),'Evening Service');
 });
 await test('Mobile viewport and remote credential restrictions',async()=>{
  const phone=await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true});phone.on('page',p=>p.on('pageerror',e=>report.errors.push(e.message)));mobile=await phone.newPage();await pair(mobile,endpoints.mobile);assert.equal((await state(mobile)).local,false);assert.equal((await state(mobile)).settings,null);await view(mobile,'connections');assert.equal(await mobile.locator('#settings-form').isVisible(),false);await mobile.locator('#remote-settings').waitFor({state:'visible'});
  const result=await mobile.evaluate(async()=>{const s=await fetch('/api/state').then(r=>r.json());return (await fetch('/api/settings',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':s.csrf},body:JSON.stringify({workspace_name:'Remote change'})})).status;});assert.equal(result,403);await noOverflow(mobile);await mobile.screenshot({path:path.join(output,'mobile-setup.png'),fullPage:true});
  await view(mobile,'schedule');await mobile.getByLabel('Live start (IST)',{exact:true}).fill('18:05');await saveSchedule(mobile);assert.equal((await state(desktop)).schedule[0].at,'18:05');await noOverflow(mobile);await mobile.screenshot({path:path.join(output,'mobile-schedule.png'),fullPage:true});await mobile.setViewportSize({width:320,height:740});await noOverflow(mobile);
 });
 await test('Connection loss disables controls and recovers without a new login',async()=>{
  await desktop.route('**/api/state',route=>route.abort());await desktop.locator('#offline').waitFor({state:'visible'});assert.equal(await desktop.locator('#save-schedule').isDisabled(),true);assert.equal(await desktop.locator('#arm').isDisabled(),true);await desktop.unroute('**/api/state');await desktop.locator('#offline').waitFor({state:'hidden'});assert.equal(await desktop.locator('#save-schedule').isDisabled(),false);
 });
 await test('Saved program removal and empty schedule persist',async()=>{
  await desktop.reload();await desktop.locator('.schedule-program').waitFor();await desktop.getByRole('button',{name:'Remove program',exact:true}).click();await confirm(desktop);await saveSchedule(desktop);assert.equal((await state(desktop)).schedule.length,0);await desktop.reload();await desktop.locator('#app').waitFor({state:'visible'});assert.equal(await desktop.locator('.schedule-program').count(),0);
 });
 await test('Visible mode controls are local, default API and retain unsaved values',async()=>{
  await view(desktop,'visible');await desktop.locator('#visible-local').waitFor({state:'visible'});assert.equal(await desktop.locator('#visible-mode').inputValue(),'api');await desktop.locator('#visible-identity-text').fill('Unsaved identity');await desktop.waitForResponse(r=>r.url().endsWith('/api/state'));assert.equal(await desktop.locator('#visible-identity-text').inputValue(),'Unsaved identity');await noOverflow(desktop);await desktop.screenshot({path:path.join(output,'visible-desktop.png'),fullPage:true});
  await view(mobile,'visible');await mobile.locator('#visible-remote').waitFor({state:'visible'});assert.equal(await mobile.locator('#visible-local').isVisible(),false);const status=await mobile.evaluate(async()=>{const s=await fetch('/api/state').then(r=>r.json());return (await fetch('/api/visible/save',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':s.csrf},body:JSON.stringify({mode:'visible'})})).status;});assert.equal(status,403);assert.equal((await state(mobile)).visible.recipes,undefined);await noOverflow(mobile);await mobile.screenshot({path:path.join(output,'visible-mobile.png'),fullPage:true});
 });
 assert.deepEqual(report.errors,[],'no uncaught browser errors');report.status='passed';
})().catch(async error=>{report.status='failed';report.failure=error.stack;console.error(error);if(desktop)await desktop.screenshot({path:path.join(output,'failure.png'),fullPage:true}).catch(()=>{});process.exitCode=1;}).finally(async()=>{
 if(browser)await browser.close();if(server&&server.exitCode===null){const exit=once(server,'exit');server.stdin.end();const timer=setTimeout(()=>server.kill(),5000);await exit.catch(()=>{});clearTimeout(timer);}await fs.mkdir(output,{recursive:true});await fs.writeFile(path.join(output,'report.json'),JSON.stringify(report,null,2));
});
