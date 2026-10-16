'use strict';
// Three operator-ordered uploads. No matching, reference import or inferred order.
const batchColumns=[
 {key:'portrait',count:7,title:'7 photos',platforms:'Instagram + YouTube',hint:'Portrait · 3:4',delivery:'Manual upload packages'},
 {key:'landscape',count:10,title:'10 photos',platforms:'Instagram + YouTube',hint:'Landscape · 4:3',delivery:'Instagram API queue · YouTube manual'},
 {key:'facebook',count:17,title:'17 photos',platforms:'Facebook',hint:'Your own order · mixed ratios',delivery:'Facebook API queue'}
];
$('social-batch').innerHTML=`
<article class="panel batch-simple-intro"><div class="section-head"><div><p class="eyebrow">UPLOAD · ARRANGE · PREPARE</p><h3>Your photos. Your order.</h3></div><span id="batch-count" class="badge"></span></div><p>Upload each column separately. Use the arrows or position selector to arrange photos; you can also drag within a column. Photo 1 is the cover. Your selected order is used exactly.</p><p class="hint">Instagram + YouTube share the same photos in each of the first two columns. Facebook has its own 17-photo order. No automatic matching or photo changes.</p></article>
<div class="batch-upload-columns">${batchColumns.map(c=>`<article class="panel batch-upload-column" data-column="${c.key}"><div class="batch-column-heading"><span class="batch-platform-icon" aria-hidden="true">${c.key==='facebook'?'f':'▧'}</span><div><h3>${c.title}</h3><b>${c.platforms}</b></div><span id="batch-count-${c.key}" class="badge"></span></div><p class="hint">${c.hint}</p><div class="inline"><label class="primary social-file-label">Upload photos<input id="batch-files-${c.key}" type="file" multiple accept="image/jpeg,image/png"></label><button id="batch-clear-${c.key}" type="button" class="text-button">Clear column</button></div><p id="batch-upload-${c.key}" class="hint" role="status"></p><div id="batch-${c.key}" class="batch-column-photos"></div><div class="batch-column-footer"><span class="badge">${c.delivery}</span><label class="field">Posting time (IST)<input id="batch-time-${c.key}" type="datetime-local"></label></div></article>`).join('')}</div>
<article class="panel batch-details"><div class="section-head"><h3>Caption for all five posts</h3><span id="batch-save-state" class="hint"></span></div><div class="batch-details-grid"><label class="field">Batch name<input id="batch-title" maxlength="65" placeholder="Daily darshan"></label><label class="field">Shared caption<textarea id="batch-caption" rows="3" maxlength="2200" placeholder="Write your caption…"></textarea></label></div><p class="hint">Facebook and supported Instagram landscape photos use the approved API queue. YouTube photo posts and Instagram 3:4 portraits still require manual upload from the ordered package. Their selected time is a handoff time, not automatic platform scheduling.</p></article>
<div class="panel batch-actions"><p id="batch-validation" class="hint" role="status"></p><div class="inline"><button id="batch-prepare" type="button" class="primary">Review & create five drafts</button><button id="batch-save" type="button" class="secondary">Save progress</button><button id="batch-reload" type="button" class="secondary">Reload saved batch</button><button id="batch-build" type="button" class="secondary">Create saved drafts</button></div><p class="hint">Review and approve each destination in Posting queue. Preparing drafts does not publish photos.</p></div>`;
let batchLoaded=false,batchDirty=false,batchRevision=0,batchSignature='',batchDrag=null;
let batchGroups=Object.fromEntries(batchColumns.map(c=>[c.key,Array(c.count).fill('')]));
function batchChanged(){batchDirty=true;batchSignature='';socialBatchRender();socialButtons();}
function batchLoad(){const p=socialState?.batch;if(!p||!('revision' in p))return;batchRevision=p.revision;batchGroups=structuredClone(p.groups||{portrait:p.slots.slice(0,7),landscape:p.slots.slice(7),facebook:socialState.structure.facebook_order.map(i=>p.slots[i])});$('batch-title').value=p.title;$('batch-caption').value=p.caption;let defaults=false;for(const c of batchColumns){$('batch-time-'+c.key).value=p.times[c.key]?p.times[c.key].slice(0,16):socialDate();if(!p.times[c.key])defaults=true;}batchLoaded=true;batchDirty=defaults;batchSignature='';}
function batchData(){return {action:'save',mode:'columns',revision:batchRevision,groups:structuredClone(batchGroups),title:$('batch-title').value,caption:$('batch-caption').value,times:Object.fromEntries(batchColumns.map(c=>[c.key,$('batch-time-'+c.key).value?$('batch-time-'+c.key).value+':00+05:30':'']))};}
function batchPhotoError(a,g){if(!a)return 'Photo missing';if(!a.type.startsWith('image/'))return 'Choose a photo';if(g==='facebook')return '';if(Math.abs(a.width/a.height-(g==='portrait'?.75:4/3))>.002)return 'Needs '+(g==='portrait'?'3:4':'4:3')+' ratio';if(g==='portrait'&&a.size>16*1024*1024)return 'Needs a photo under 16 MB';if(g==='landscape'&&(a.type!=='image/jpeg'||a.size>8*1024*1024||a.width<320||a.width>1440))return 'Instagram API: JPG, under 8 MB, width 320–1440px';return '';}
function batchValid(){return batchColumns.every(c=>batchGroups[c.key].length===c.count&&new Set(batchGroups[c.key]).size===c.count&&batchGroups[c.key].every(id=>id&&!batchPhotoError(socialState?.assets.find(a=>a.id===id),c.key)));}
function socialBatchButtons(blocked){$('batch-prepare').disabled=blocked||!batchLoaded||!batchValid();$('batch-build').disabled=blocked||batchDirty||!batchLoaded||!batchValid();for(const c of batchColumns)$('batch-clear-'+c.key).disabled=blocked||!batchGroups[c.key].some(Boolean);document.querySelectorAll('#social-batch [data-at-boundary="true"]').forEach(b=>b.disabled=true);}
function batchCanEdit(){return online&&!socialPending&&state?.role!=='viewer'&&!(state?.busy&&state?.mode!=='arm');}
function batchMove(group,from,to){if(!batchCanEdit()||from===to||to<0||to>=batchGroups[group].length)return;const ids=batchGroups[group],id=ids.splice(from,1)[0];ids.splice(to,0,id);batchChanged();}
function socialBatchEdited(slot,id){const [group,index]=typeof slot==='string'?slot.split(':'):[slot<7?'portrait':'landscape',slot<7?slot:slot-7];batchGroups[group][Number(index)]=id;batchDirty=true;batchSignature='';}
function socialBatchRemoved(ids,revision){for(const c of batchColumns)batchGroups[c.key]=batchGroups[c.key].map(id=>ids.includes(id)?'':id);if(revision!==undefined)batchRevision=revision;batchSignature='';socialBatchRender();}
for(const id of ['batch-title','batch-caption',...batchColumns.map(c=>'batch-time-'+c.key)])$(id).oninput=batchChanged;
function socialBatchRender(){
 if(!socialState)return;if(!batchLoaded)batchLoad();$('social-batch').hidden=socialTab!=='batch';
 if(state?.role==='viewer'){for(const c of batchColumns){$('batch-'+c.key).replaceChildren();$('batch-time-'+c.key).value='';}for(const id of ['batch-title','batch-caption'])$(id).value='';batchLoaded=false;$('batch-validation').textContent='Pair as an operator to upload photos.';return;}
 const assets=new Map(socialState.assets.map(a=>[a.id,a]));
 $('batch-count').textContent=batchColumns.reduce((n,c)=>n+batchGroups[c.key].filter(id=>assets.has(id)).length,0)+' / 34 positions';
 $('batch-save-state').textContent=batchDirty?'Unsaved changes':'Saved · revision '+batchRevision;
 $('batch-validation').textContent=batchValid()?'All three columns are ready. Review your order and prepare five drafts.':'Fill 7, 10 and 17 photo positions. Check any format warning shown under a photo.';
 const sig=JSON.stringify([socialState.assets,batchGroups]);if(sig===batchSignature)return;batchSignature=sig;
 for(const c of batchColumns){
  const host=$('batch-'+c.key);host.replaceChildren();$('batch-count-'+c.key).textContent=batchGroups[c.key].filter(id=>assets.has(id)).length+' / '+c.count;
  batchGroups[c.key].forEach((id,i)=>{
   const a=assets.get(id),card=el('article','batch-photo');card.dataset.index=i;card.dataset.group=c.key;
   const top=el('div','batch-photo-top');top.append(el('b','',String(i+1).padStart(2,'0')+(i===0?' · Cover':'')));card.append(top);
   if(a){const img=el('img');img.src='/api/social/media/'+id;img.alt=a.name;img.loading='lazy';img.draggable=false;card.append(img,el('small','batch-photo-name',a.name));
    const controls=el('div','batch-photo-controls');
    for(const [text,delta,label] of [['↑',-1,'Move up'],['↓',1,'Move down']]){const b=el('button','secondary',text);b.type='button';b.setAttribute('aria-label',label+' '+c.key+' photo '+(i+1));b.dataset.atBoundary=String(i+delta<0||i+delta>=c.count);b.onclick=()=>batchMove(c.key,i,i+delta);controls.append(b);}
    const position=el('select');position.setAttribute('aria-label',c.key+' photo '+(i+1)+' position');for(let n=0;n<c.count;n++){const o=el('option','',String(n+1));o.value=String(n);position.append(o);}position.value=String(i);position.onchange=()=>batchMove(c.key,i,Number(position.value));controls.append(position);card.append(controls);
    const actions=el('div','inline'),remove=el('button','text-button','Remove');remove.type='button';remove.setAttribute('aria-label','Remove '+c.key+' photo '+(i+1));remove.onclick=()=>{batchGroups[c.key].splice(i,1);batchGroups[c.key].push('');batchChanged();};
    const edit=el('button','text-button','Edit copy');edit.type='button';edit.onclick=()=>socialEdit(a,c.key+':'+i);actions.append(remove,edit);card.append(actions);
    const error=batchPhotoError(a,c.key);if(error)card.append(el('small','batch-crop-needed',error));
    card.draggable=true;card.ondragstart=e=>{if(!batchCanEdit()){e.preventDefault();return;}batchDrag={group:c.key,index:i};e.dataTransfer.setData('text/plain',c.key+':'+i);e.dataTransfer.effectAllowed='move';};card.ondragend=()=>batchDrag=null;
   }else card.append(el('div','batch-photo-empty','Upload photo '+(i+1)));
   card.ondragover=e=>{if(batchCanEdit()&&batchDrag?.group===c.key)e.preventDefault();};card.ondrop=e=>{e.preventDefault();if(batchDrag?.group===c.key)batchMove(c.key,batchDrag.index,i);batchDrag=null;};host.append(card);
  });
 }
}
for(const c of batchColumns){
 $('batch-clear-'+c.key).onclick=async()=>{if(!await confirmAction('Clear this photo column?',c.platforms+' · '+c.count+' photos. This clears its selections. Uploaded files and existing posts remain.'))return;batchGroups[c.key]=Array(c.count).fill('');batchChanged();};
 $('batch-files-'+c.key).onchange=async e=>{
  const files=[...e.target.files];e.target.value='';if(!files.length)return;if(files.length>c.count)return toast('Choose up to '+c.count+' photos for this column.');
  const free=batchGroups[c.key].filter(id=>!id).length;
  if(files.length>free){if(!await confirmAction('Replace this column?',c.platforms+' · replace the selected '+c.count+'-photo group with this upload? The other two columns stay in place.'))return;batchGroups[c.key]=Array(c.count).fill('');batchChanged();}
  socialPending=true;socialButtons();let done=0,duplicates=0;
  try{for(const file of files){const a=await socialImport(file);done++;if(batchGroups[c.key].includes(a.id)){duplicates++;continue;}const index=batchGroups[c.key].indexOf('');if(index<0)break;batchGroups[c.key][index]=a.id;batchDirty=true;$('batch-upload-'+c.key).textContent=done+' / '+files.length+' imported';}
   await socialRefresh(true);batchSignature='';socialBatchRender();$('batch-upload-'+c.key).textContent=done+' / '+files.length+' imported'+(duplicates?' · '+duplicates+' duplicates skipped':'')+'. Check the order shown.';
  }catch(err){await socialRefresh(true).catch(()=>{});batchSignature='';socialBatchRender();$('batch-upload-'+c.key).textContent=done+' / '+files.length+' imported · '+err.message+' Successfully imported photos are kept.';}
  finally{socialPending=false;socialButtons();}
 };
}
$('batch-save').onclick=async()=>{try{const p=await socialRequest('/api/social/batch',batchData());batchRevision=p.revision;batchDirty=false;socialBatchRender();socialButtons();toast('All three columns saved. No photos posted.');}catch(e){toast(e.message);}};
$('batch-reload').onclick=async()=>{if(batchDirty&&!await confirmAction('Reload saved photos?','Unsaved order, caption and times will be discarded.'))return;await socialRefresh(true);batchLoad();socialBatchRender();socialButtons();};
$('batch-build').onclick=async()=>{try{const r=await socialRequest('/api/social/batch',{action:'build',revision:batchRevision});toast(r.already_built?'These drafts already exist.':'Five drafts created in your selected order.');socialTabShow('queue');}catch(e){toast(e.message);}};
$('batch-prepare').onclick=async()=>{
 const data=batchData(),order=batchColumns.map(c=>c.title+' · '+c.platforms+'\n'+data.groups[c.key].map((id,i)=>(i+1)+'. '+(socialState.assets.find(a=>a.id===id)?.name||'Missing')).join('\n')).join('\n\n');
 if(!await confirmAction('Use this photo order?',order+'\n\nCaption: '+data.caption+'\n\nTimes (IST): '+Object.entries(data.times).map(([g,t])=>g+': '+t).join('\n')+'\n\nCreates five unapproved drafts. Facebook and Instagram landscape use the API queue; YouTube photos and Instagram portrait require manual upload.'))return;
 socialPending=true;socialButtons();try{const p=await api('/api/social/batch',data);batchRevision=p.revision;batchDirty=false;const r=await api('/api/social/batch',{action:'build',revision:batchRevision});await socialRefresh(true);socialTabShow('queue');toast(r.already_built?'These drafts already exist.':'Five drafts ready. Review and approve each destination.');}catch(e){toast(e.message);}finally{socialPending=false;socialButtons();}
};
