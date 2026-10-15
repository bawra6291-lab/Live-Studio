'use strict';
// The uploaded document is served unchanged. Keep its DOM, styles and state isolated.
function renderDarshanFlow(){
 if(!state)return;
 const frame=$('darshanflow-frame'),viewer=state.role==='viewer';
 $('darshanflow-viewer').hidden=!viewer;
 frame.hidden=viewer;
 if(viewer){if(frame.hasAttribute('src'))frame.removeAttribute('src');return;}
 if(!$('view-social').hidden&&!frame.hasAttribute('src'))frame.src='/darshanflow.html';
}
