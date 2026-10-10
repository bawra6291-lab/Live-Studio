/* HTTPS remote screen with an isolated relay; no real PC or platforms. */
const {chromium}=require('playwright');
const {spawn,execFileSync}=require('node:child_process');
const fs=require('node:fs');const path=require('node:path');const os=require('node:os');const assert=require('node:assert/strict');
const root=fs.mkdtempSync(path.join(os.tmpdir(),'livedesk-relay-browser-'));
execFileSync('openssl',['req','-x509','-newkey','rsa:2048','-nodes','-days','1','-keyout',root+'/key.pem','-out',root+'/cert.pem','-subj','/CN=localhost'],{stdio:'ignore'});
const fixture=spawn('python',['qa/remote_browser_server.py',root],{stdio:['ignore','pipe','inherit']});
let browser;
(async()=>{
 const info=await new Promise((resolve,reject)=>{let output='';fixture.stdout.on('data',d=>{output+=d;try{resolve(JSON.parse(output.trim()));}catch{}});fixture.on('exit',code=>reject(Error('fixture exit '+code)));setTimeout(()=>reject(Error('fixture timeout')),15000).unref();});
 browser=await chromium.launch({headless:true});
 // Only this local fixture uses a disposable certificate. Production app never ignores TLS errors.
 const context=await browser.newContext({ignoreHTTPSErrors:true,viewport:{width:390,height:844}});const page=await context.newPage();
 // Installed Android WebView has no native JS-dialog handler. Simulate that
 // suppression; every control must still show its own explicit confirmation.
 await context.addInitScript(()=>{window.nativeConfirmCalls=0;window.confirm=()=>{window.nativeConfirmCalls++;return false;};});
 page.on('dialog',dialog=>dialog.dismiss());await page.goto(info.origin);
 await page.locator('#code').fill(info.code);await page.locator('#login button').click();
 await page.locator('#desk').waitFor({state:'visible'});await page.locator('#phones p').filter({hasText:'This phone'}).waitFor();
 assert.equal((await context.cookies())[0].secure,true);assert.equal((await context.cookies())[0].httpOnly,true);
 const count=()=>page.evaluate(async()=>{const r=await fetch('/api/state');return (await r.json()).commands.length;});
 await page.getByRole('button',{name:'Check connections',exact:true}).click();
 const dialog=page.getByRole('dialog');await dialog.waitFor({state:'visible'});
 assert.equal(await count(),0);await page.waitForTimeout(4500);
 assert.equal(await dialog.isVisible(),true); // status polling must not dismiss it
 await dialog.getByRole('button',{name:'Cancel',exact:true}).click();
 assert.equal(await count(),0);assert.match(await page.locator('#command-message').textContent(),/cancelled/);
 await page.getByRole('button',{name:'Check connections',exact:true}).click();
 await dialog.getByRole('button',{name:'Confirm',exact:true}).click();
 await page.waitForFunction(()=>document.querySelector('#commands').textContent.includes('accepted'));
 assert.equal(await count(),1);
 // A rejected command must remain visible across automatic status refreshes.
 const reject=route=>route.fulfill({status:409,contentType:'application/json',body:JSON.stringify({error:'QA PC restarted; refresh before issuing a command.'})});
 await page.route('**/api/command',reject);
 await page.getByRole('button',{name:'Enable automation',exact:true}).click();
 await dialog.getByRole('button',{name:'Confirm',exact:true}).click();
 await page.waitForFunction(()=>document.querySelector('#command-message').textContent.includes('QA PC restarted'));
 await page.waitForTimeout(4500);assert.match(await page.locator('#command-message').textContent(),/QA PC restarted/);
 assert.equal(await count(),1);await page.unroute('**/api/command',reject);
 await page.getByRole('button',{name:'Enable automation',exact:true}).click();
 await dialog.getByRole('button',{name:'Cancel',exact:true}).click();assert.equal(await count(),1);
 await page.getByRole('button',{name:'Enable automation',exact:true}).click();
 await dialog.getByRole('button',{name:'Confirm',exact:true}).click();
 await page.waitForFunction(()=>[...document.querySelectorAll('#commands p')].filter(p=>p.textContent.includes('accepted')).length>=2);
 assert.equal(await count(),2);
 await page.waitForFunction(()=>document.querySelector('#commands').textContent.includes('accepted'));
 await page.getByRole('button',{name:'Pause automation',exact:true}).click();
 await dialog.getByRole('button',{name:'Confirm',exact:true}).click();
 await page.waitForFunction(()=>[...document.querySelectorAll('#commands p')].filter(p=>p.textContent.includes('accepted')).length>=3);
 assert.equal(await count(),3);assert.equal(await page.evaluate(()=>window.nativeConfirmCalls),0);
 const saved=await context.storageState();await context.close();
 const restored=await browser.newContext({ignoreHTTPSErrors:true,storageState:saved,viewport:{width:390,height:844}});await restored.addInitScript(()=>{window.confirm=()=>false;});const again=await restored.newPage();again.on('dialog',d=>d.dismiss());await again.goto(info.origin);
 await again.locator('#desk').waitFor({state:'visible'});assert.equal(await again.locator('#login').isVisible(),false);
 assert(await again.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 fs.mkdirSync('qa/results',{recursive:true});await again.screenshot({path:'qa/results/remote-connected.png'});
 await again.getByRole('button',{name:'Forget phone',exact:true}).click();
 await again.getByRole('dialog').getByRole('button',{name:'Cancel',exact:true}).click();assert.equal(await again.locator('#login').isVisible(),false);
 await again.getByRole('button',{name:'Forget phone',exact:true}).click();
 await again.getByRole('dialog').getByRole('button',{name:'Confirm',exact:true}).click();await again.locator('#login').waitFor({state:'visible'});
 await again.screenshot({path:'qa/results/remote-pairing.png'});
 console.log('PASS HTTPS pairing, Secure/HttpOnly cookie, WebView-safe Check/Enable/Pause confirmation/cancel, no unconfirmed commands, visible errors after polling, restored phone session, revocation and narrow layout');
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();fixture.kill();});
