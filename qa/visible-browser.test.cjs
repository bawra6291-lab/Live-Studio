'use strict';
const {chromium}=require('playwright');
const fs=require('node:fs/promises');
const os=require('node:os');
const path=require('node:path');
const http=require('node:http');
const {spawn}=require('node:child_process');
let browser,server,profile;
(async()=>{
 profile=await fs.mkdtemp(path.join(os.tmpdir(),'live-visible-qa-'));
 server=http.createServer((req,res)=>{res.writeHead(200,{'Content-Type':'text/html'});res.end(`<!doctype html><html><body><button id="account">Test Temple</button><label>Title<input id="title"></label><input id="password" type="password"><button id="save">Save fixture</button><p id="result">Waiting</p><studio-fixture></studio-fixture><script>
 document.getElementById('save').onclick=e=>{window.trustedClick=e.isTrusted;window.savedTitle=document.getElementById('title').value;document.getElementById('result').textContent='Saved via real click';};
 const root=document.querySelector('studio-fixture').attachShadow({mode:'open'});
 root.innerHTML='<span id="channel-name">Test Temple</span><label>Event title<input id="shadow-title"></label><div id="editable-title" contenteditable="true" aria-label="Editable title"></div><input type="password" id="shadow-password"><button id="shadow-save"><span>Save shadow fixture</span></button><p id="shadow-result">Waiting</p>';
 root.querySelector('#shadow-save').onclick=e=>{window.shadowTrusted=e.isTrusted;window.shadowSaved=root.querySelector('#shadow-title').value;root.querySelector('#shadow-result').textContent='Shadow saved';};
 </script></body></html>`);});
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 browser=await chromium.launchPersistentContext(profile,{headless:true,channel:'chromium',args:['--remote-debugging-address=127.0.0.1','--remote-debugging-port=0']});
 const port=(await fs.readFile(path.join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0];
 const child=spawn(process.env.PYTHON||'python',[path.join(__dirname,'visible_fixture.py'),port,`http://127.0.0.1:${server.address().port}/`],{stdio:'inherit'});
 const code=await new Promise((resolve,reject)=>{child.on('error',reject);child.on('exit',resolve);});
 if(code!==0)throw new Error('Visible browser fixture failed: '+code);
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();if(server)await new Promise(resolve=>server.close(resolve));if(profile)await fs.rm(profile,{recursive:true,force:true});});
