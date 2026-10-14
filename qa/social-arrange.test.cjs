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
// A shifted camera frame must match by shape, not by the filename or dress colour.
function shifted(seed){const src=pixels(seed),out=[];for(let y=0;y<32;y++)for(let x=0;x<32;x++){
  const sx=Math.max(0,Math.min(31,x+3)),sy=Math.max(0,Math.min(31,y-3));
  const value=src[(sy*32+sx)*4]*.8;out.push(value,value,value,255);
}return out;}
const moved=photos.map(p=>({...p,id:'shifted-'+p.id,descriptor:A.describe(shifted(Number(p.id)+1))}));
result=A.arrange(refs,moved);assert.deepEqual(result.slots,refs.map((_,i)=>'shifted-'+i));
assert.deepEqual(A.arrange(refs,[...moved].reverse()).slots,result.slots);
result=A.arrange(refs,moved.filter(p=>p.id!=='shifted-3'));assert.equal(result.slots[3],'');
const unrelated={id:'unrelated',width:300,height:400,descriptor:A.describe(pixels(90210))};
assert.ok(A.arrange(refs,[unrelated]).slots.every(x=>!x));
console.log('PASS arrangement: global assignment, shuffled new names, brightness, duplicates, missing, flat and incorrect-ratio images');
console.log('PASS framing: camera shift, exposure, input-order independence, missing and unrelated photos');
