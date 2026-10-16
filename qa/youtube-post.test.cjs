'use strict';
// Actual production CDP commands, DOM inspection, file selection and mouse clicks.
// All pages and photos belong to this local fixture; no YouTube account is contacted.
const assert=require('node:assert/strict'),http=require('node:http'),net=require('node:net');
const fs=require('node:fs/promises'),os=require('node:os'),path=require('node:path');
const {spawn}=require('node:child_process'),{chromium}=require('playwright');
let current='happy7',publishes=0,uploads=[],accountVisits=0;
let channel='UC'+'a'.repeat(22),caption='Darshan fixture\n\nHare Krishna 🙏\n#daily';
function accountHtml(){
 const id=(current==='wrong-account'||(current==='account-switch'&&accountVisits>1))?'UC'+'b'.repeat(22):channel;
 if(current==='happy-sibling')return '<section><span id="channel-id">Channel ID</span><div><input readonly value="'+id+'"></div></section>';
 if(current==='happy-labelled')return '<label id="label">Channel ID</label><input aria-labelledby="label" readonly value="'+id+'">';
 if(current==='happy-shadow')return '<div id="host"></div><script>document.getElementById("host").attachShadow({mode:"open"}).innerHTML='+JSON.stringify('<section><label>Channel ID</label><input readonly value="'+id+'"></section>')+';</script>';
 if(current==='happy-decoy')return '<input id="channel-id" readonly value="'+id+'"><a href="/channel/UCbbbbbbbbbbbbbbbbbbbbbb">UCbbbbbbbbbbbbbbbbbbbbbb</a>';
 if(current==='missing-identity')return '<p>Channel ID</p><a href="/channel/'+id+'">Recommended channel '+id+'</a>';
 if(current==='conflicting-identity')return '<input id="channel-id" value="'+id+'"><input aria-label="Channel ID" value="UCbbbbbbbbbbbbbbbbbbbbbb">';
 if(current==='hidden-identity')return '<input id="channel-id" style="display:none" value="'+id+'">';
 if(current==='happy-hyphen')return '<input id="channel-id" readonly value="UCaaaaaaaaaaaaaaaaaaaaa-">';
 return '<input id="channel-id" readonly value="'+id+'">';
}
function html(account){return `<!doctype html><meta charset="utf-8"><style>body{font:16px Arial}button{padding:15px}#contenteditable-root{white-space:pre-wrap;min-height:80px;border:1px solid}img{width:80px;height:80px}ytd-backstage-post-creation-box-renderer,ytd-backstage-post-renderer{display:block;padding:20px}</style>${account?accountHtml():`<button id="create">Create</button><div id="feed"></div><script>
const caption=${JSON.stringify(caption)},mode=${JSON.stringify(current)};window.selected=[];window.published=0;window.imageActivated=false;
function receipt(id){const n=document.createElement('ytd-backstage-post-renderer');n.innerHTML='<a id="author-text" href="/@qa_fixture">Author</a><a id="published-time-text" href="/post/'+id+'">Just now</a><div id="content-text"></div>';n.data={postId:id,authorEndpoint:{browseEndpoint:{browseId:'${channel}'}},contentText:{runs:[{text:caption}]}};if(id==='UgNewFixturePost'&&mode!=='text-only-receipt')n.data.backstageAttachment={postMultiImageRenderer:{images:Array.from({length:mode==='short-receipt'?1:window.selected.length},()=>({backstageImageRenderer:mode==='empty-receipt'?{}:{image:{thumbnails:[{url:location.origin+'/fixture-photo.jpg'}]}}}))}};n.querySelector('#content-text').textContent=caption;document.getElementById('feed').prepend(n);}
receipt('UgExistingManualPost');
function composer(){const root=document.createElement('ytd-backstage-post-creation-box-renderer');root.innerHTML='<div id="contenteditable-root" contenteditable="true"></div><input type="file" accept="image/jpeg" multiple hidden><div id="attachments"></div><button id="image-button">Image</button><button id="publish">Post</button>';document.body.append(root);if(mode==='existing-draft')root.querySelector('[contenteditable]').innerText='Another draft, keep this';
root.querySelector('[contenteditable]').addEventListener('input',e=>{if(mode==='changed-caption')e.target.innerText='Changed by operator';});
root.querySelector('#image-button').onclick=()=>{window.imageActivated=true;};
root.querySelector('input').onchange=async e=>{let files=Array.from(e.target.files);if(mode==='wrong-order'){const dt=new DataTransfer();files.reverse().forEach(f=>dt.items.add(f));e.target.files=dt.files;files=Array.from(e.target.files);}if(!window.imageActivated)throw new Error('Image flow must be activated before file selection');window.selected=await Promise.all(files.map(async f=>({name:f.name,size:f.size,bytes:Array.from(new Uint8Array(await f.arrayBuffer()))})));root.querySelector('#attachments').replaceChildren();if(mode==='no-previews')return;for(const f of files){const img=new Image();img.src=URL.createObjectURL(f);root.querySelector('#attachments').append(img);}if(mode==='happy10'||mode==='modal-drop'){const modal=document.createElement('ytd-backstage-image-upload-renderer');modal.style.display='block';modal.append(root.querySelector('#attachments'));const done=document.createElement('button');done.textContent='Done';done.onclick=()=>{if(mode==='modal-drop')modal.querySelector('#attachments').replaceChildren();root.append(modal.querySelector('#attachments'));root.style.visibility='visible';modal.remove();};modal.append(done);document.body.append(modal);root.style.visibility='hidden';}};
root.querySelector('#publish').onclick=async()=>{window.published++;await fetch('/publish',{method:'POST'});if(mode!=='uncertain'){receipt('UgNewFixturePost');root.remove();}};
if(mode==='ambiguous'){const clone=root.querySelector('#publish').cloneNode(true);root.append(clone);}}
document.getElementById('create').onclick=()=>{const b=document.createElement('button');b.textContent='Create post';b.onclick=()=>{b.remove();composer();};document.body.append(b);};
</script>`}`;}
(async()=>{
 const server=http.createServer((req,res)=>{if(req.url==='/publish'){publishes++;res.end('ok');return;}if(req.url.startsWith('/account_advanced'))accountVisits++;if(current==='redirect-account'&&req.url.startsWith('/account_advanced')){res.writeHead(302,{Location:'/account'});res.end();return;}if(current==='signin-redirect'&&req.url.startsWith('/account_advanced')){res.writeHead(302,{Location:'/signin'});res.end();return;}res.setHeader('Content-Type','text/html');res.end(html(req.url.startsWith('/account_advanced')));});
 await new Promise(r=>server.listen(0,'127.0.0.1',r));const site='http://127.0.0.1:'+server.address().port;
 const temp=await fs.mkdtemp(path.join(os.tmpdir(),'youtube-photo-cdp-'));let context;
 try{
  const reserve=net.createServer();await new Promise(r=>reserve.listen(0,'127.0.0.1',r));const port=reserve.address().port;await new Promise(r=>reserve.close(r));
  context=await chromium.launchPersistentContext(path.join(temp,'chrome'),{headless:true,args:['--remote-debugging-port='+port],viewport:{width:1280,height:1000}});
  const address=(await(await fetch('http://127.0.0.1:'+port+'/json/version')).json()).webSocketDebuggerUrl;
  const page=context.pages()[0];const photos=await page.evaluate(()=>Array.from({length:10},(_,i)=>{const c=document.createElement('canvas');c.width=128;c.height=128;const x=c.getContext('2d');x.fillStyle='rgb('+i*20+',100,180)';x.fillRect(0,0,128,128);return c.toDataURL('image/jpeg').split(',')[1];}));
  const cases=[];
  for(const name of ['happy7','happy10','happy-sibling','happy-labelled','happy-shadow','happy-decoy','happy-hyphen','missing-identity','conflicting-identity','hidden-identity','redirect-account','signin-redirect','account-switch','wrong-account','existing-draft','changed-caption','wrong-order','ambiguous','uncertain','no-previews','modal-drop','text-only-receipt','short-receipt','empty-receipt','corrupt']){
   current=name;channel=name==='happy-hyphen'?'UC'+'a'.repeat(21)+'-':'UC'+'a'.repeat(22);publishes=0;uploads=[];accountVisits=0;for(const p of context.pages())if(p!==page)await p.close();
   const file=path.join(temp,'input.json'),count=name==='happy10'?10:7;await fs.writeFile(file,JSON.stringify({photos:photos.slice(0,count),caption,channel}));
   const child=spawn(process.env.PYTHON||'python',[path.join(__dirname,'youtube_post_worker.py'),address,site,name,file]);let out='',err='';child.stdout.on('data',b=>out+=b);child.stderr.on('data',b=>err+=b);
   const code=await new Promise(r=>child.on('close',r));assert.equal(code,0,err);const result=JSON.parse(out.trim());const tab=context.pages().find(p=>p.url().includes('/channel/'));
   if(name.startsWith('happy')){
    if(result.error)console.error('Fixture caption diagnostic',await tab.locator('[contenteditable]').evaluate(n=>({html:n.innerHTML,text:n.innerText,expected:caption})).catch(()=>null));
    assert.equal(result.error,'');assert.equal(result.result.status,'published');assert.match(result.result.url,/\/post\/UgNewFixturePost$/);assert.equal(result.result.photos,count);assert.equal(publishes,1);assert.equal(await tab.evaluate(()=>window.imageActivated),true);
    const selected=await tab.evaluate(()=>window.selected);assert.deepEqual(selected.map(f=>f.name),Array.from({length:count},(_,i)=>String(i+1).padStart(2,'0')+'.jpg'));
    selected.forEach((f,i)=>assert.deepEqual(Buffer.from(f.bytes),Buffer.from(photos[i],'base64')));
   }else{
    assert.ok(result.error,name+' must stop');assert.notEqual(result.result.status,'published');assert.equal(publishes,['uncertain','text-only-receipt','short-receipt','empty-receipt'].includes(name)?1:0);
    if(['missing-identity','hidden-identity'].includes(name))assert.match(result.error,/could not read the Channel ID/);
    if(name==='redirect-account')assert.match(result.error,/Advanced settings did not open/);
    if(name==='signin-redirect')assert.match(result.error,/sign-in or consent/);
    if(['uncertain','text-only-receipt','short-receipt','empty-receipt'].includes(name))assert.equal(result.result.write_dispatched,true);
    if(name==='no-previews')assert.match(result.error,/did not display all selected photo previews/);
    if(name==='modal-drop')assert.match(result.error,/avoid a text-only post/);
    if(name==='existing-draft')assert.equal(await tab.locator('[contenteditable]').innerText(),'Another draft, keep this');
   }
   cases.push({name,status:'passed',publishClicks:publishes});console.log('PASS YouTube browser '+name);
  }
  await fs.mkdir(path.join(__dirname,'results'),{recursive:true});await fs.writeFile(path.join(__dirname,'results','youtube-post-browser.json'),JSON.stringify({cases,realPlatformsContacted:false},null,2));
 }finally{await context?.close();await fs.rm(temp,{recursive:true,force:true});await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);process.exit(1);});
