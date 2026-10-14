'use strict';
const assert=require('node:assert/strict');
const A=require('../app/web/social-arrange.js');
// Global assignment must not let one excellent candidate fill two positions.
assert.deepEqual(A.assignment([[1,2,9],[1,5,9]]),[1,0]);
assert.deepEqual(A.assignment([[.1,2,3],[2,.1,3],[2,3,.1]]),[0,1,2]);
assert.throws(()=>A.assignment([[1],[2]]));
function pixels(seed,brightness=1){let r=seed;const a=[];for(let i=0;i<1024;i++){r=(Math.imul(r,1664525)+1013904223)>>>0;const v=30+(r%150);a.push(v*brightness,v*brightness,v*brightness,255);}return a;}
const refs=Array.from({length:17},(_,i)=>A.describe(pixels(i+1)));
const photos=refs.map((_,i)=>({id:String(i),width:i<7?300:400,height:i<7?400:300,descriptor:A.describe(pixels(i+1,.85))})).reverse();
let result=A.arrange(refs,photos);assert.deepEqual(result.slots,refs.map((_,i)=>String(i)));assert.equal(result.unused.length,0);
result=A.arrange(refs,[...photos,photos[0]]);assert.equal(new Set(result.slots).size,17);
result=A.arrange(refs,photos.filter(a=>a.id!=='5'));assert.equal(result.slots[5],'');assert.equal(result.slots.filter(Boolean).length,16);
const blank={id:'blank',width:300,height:400,descriptor:A.describe(Array(1024).fill([127,127,127,255]).flat())};
result=A.arrange(refs,[blank]);assert.ok(result.slots.every(x=>!x));assert.deepEqual(result.unused,['blank']);
const wrong={...photos[0],id:'wrong',width:400,height:400};assert.ok(A.arrange(refs,[wrong]).slots.every(x=>!x));
console.log('PASS arrangement: global assignment, shuffled new names, brightness, duplicates, missing, flat and incorrect-ratio images');
