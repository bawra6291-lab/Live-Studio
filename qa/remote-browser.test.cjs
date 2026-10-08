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
 page.on('dialog',dialog=>dialog.accept());await page.goto(info.origin);
 await page.locator('#code').fill(info.code);await page.locator('#login button').click();
 await page.locator('#desk').waitFor({state:'visible'});await page.locator('#phones p').filter({hasText:'This phone'}).waitFor();
 assert.equal((await context.cookies())[0].secure,true);assert.equal((await context.cookies())[0].httpOnly,true);
 await page.getByRole('button',{name:'Enable automation',exact:true}).click();
 await page.waitForFunction(()=>document.querySelector('#commands').textContent.includes('accepted'));
 await page.getByRole('button',{name:'Pause automation',exact:true}).click();
 await page.waitForFunction(()=>[...document.querySelectorAll('#commands p')].filter(p=>p.textContent.includes('accepted')).length>=2);
 const saved=await context.storageState();await context.close();
 const restored=await browser.newContext({ignoreHTTPSErrors:true,storageState:saved,viewport:{width:390,height:844}});const again=await restored.newPage();again.on('dialog',d=>d.accept());await again.goto(info.origin);
 await again.locator('#desk').waitFor({state:'visible'});assert.equal(await again.locator('#login').isVisible(),false);
 assert(await again.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 fs.mkdirSync('qa/results',{recursive:true});await again.screenshot({path:'qa/results/remote-connected.png'});
 await again.getByRole('button',{name:'Forget phone',exact:true}).click();await again.locator('#login').waitFor({state:'visible'});
 await again.screenshot({path:'qa/results/remote-pairing.png'});
 console.log('PASS HTTPS pairing, Secure/HttpOnly cookie, Enable/Pause acknowledgement, restored phone session, revocation and narrow layout');
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();fixture.kill();});
