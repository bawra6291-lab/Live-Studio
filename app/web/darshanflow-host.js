'use strict';
// Keep the supplied document and posting state intact; apply only a host colour theme.
function themeDarshanFlow(frame){
 const doc=frame.contentDocument;
 if(!doc||doc.getElementById('live-desk-colours'))return;
 const link=doc.createElement('link');
 link.id='live-desk-colours';link.rel='stylesheet';link.href='/darshanflow-theme.css';
 link.addEventListener('load',()=>{
  const style=doc.createElement('link');style.rel='stylesheet';style.href='/darshanflow-studio.css';doc.head.appendChild(style);
  style.addEventListener('load',()=>{
   const script=doc.createElement('script');script.src='/darshanflow-studio.js';
   script.addEventListener('load',()=>{doc.documentElement.dataset.liveDeskTheme='ready';});doc.head.appendChild(script);
  });
 });
 doc.head.appendChild(link);
}
function renderDarshanFlow(){
 if(!state)return;
 const frame=$('darshanflow-frame'),viewer=state.role==='viewer';
 $('darshanflow-viewer').hidden=!viewer;
 frame.hidden=viewer;
 if(viewer){if(frame.hasAttribute('src'))frame.removeAttribute('src');return;}
 if(!frame.dataset.themeBound){frame.addEventListener('load',()=>themeDarshanFlow(frame));frame.dataset.themeBound='true';}
 if(!$('view-social').hidden&&!frame.hasAttribute('src'))frame.src='/darshanflow.html';
}
