'use strict';
// Local visual similarity, NOT a semantic deity recognizer. Every proposed order
// stays a draft and must be reviewed. No photo bytes leave the existing PC host.
const DarshanArrange=(()=>{
  const N=32;
  function describe(rgba){
    const gray=[],colour=[];
    for(let i=0;i<N*N;i++){const j=i*4,r=rgba[j]/255,g=rgba[j+1]/255,b=rgba[j+2]/255;gray.push(.299*r+.587*g+.114*b);colour.push(r,g,b);}
    const mean=gray.reduce((a,b)=>a+b,0)/gray.length;
    const sd=Math.sqrt(gray.reduce((s,v)=>s+(v-mean)**2,0)/gray.length);
    const luminance=gray.map(v=>(v-mean)/Math.max(sd,.035));
    const edge=[];
    for(let y=0;y<N;y++)for(let x=0;x<N;x++){const i=y*N+x;edge.push((luminance[y*N+Math.min(N-1,x+1)]-luminance[y*N+Math.max(0,x-1)])/2,(luminance[Math.min(N-1,y+1)*N+x]-luminance[Math.max(0,y-1)*N+x])/2);}
    return {luminance,edge,colour,sd};
  }
  function distance(a,b){
    function mse(x,y){return x.reduce((s,v,i)=>s+(v-y[i])**2,0)/x.length;}
    return .65*mse(a.luminance,b.luminance)+.25*mse(a.edge,b.edge)+.10*mse(a.colour,b.colour);
  }
  // Minimum-cost one-to-one assignment; rectangular matrices accept extra photos.
  // Dummy columns leave genuinely missing/unrelated slots empty.
  function assignment(costs){
    const n=costs.length;if(!n)return [];
    const m=costs[0].length;if(m<n)throw new Error('Not enough assignment columns.');
    const u=Array(n+1).fill(0),v=Array(m+1).fill(0),p=Array(m+1).fill(0),way=Array(m+1).fill(0);
    for(let i=1;i<=n;i++){p[0]=i;let j0=0;const min=Array(m+1).fill(Infinity),used=Array(m+1).fill(false);
      do{used[j0]=true;const i0=p[j0];let delta=Infinity,j1=0;
        for(let j=1;j<=m;j++)if(!used[j]){const cur=costs[i0-1][j-1]-u[i0]-v[j];if(cur<min[j]){min[j]=cur;way[j]=j0;}if(min[j]<delta){delta=min[j];j1=j;}}
        for(let j=0;j<=m;j++)if(used[j]){u[p[j]]+=delta;v[j]-=delta;}else min[j]-=delta;j0=j1;
      }while(p[j0]!==0);
      do{const j1=way[j0];p[j0]=p[j1];j0=j1;}while(j0);
    }
    const result=Array(n).fill(-1);for(let j=1;j<=m;j++)if(p[j])result[p[j]-1]=j-1;return result;
  }
  function arrange(references,photos){
    const unique=[...new Map(photos.map(a=>[a.id,a])).values()];
    const slots=Array(17).fill(''),notes=Array(17).fill('No similar photo found'),unused=[];
    for(const portrait of [true,false]){
      const indices=Array.from({length:portrait?7:10},(_,i)=>i+(portrait?0:7));
      const candidates=unique.filter(a=>a.descriptor&&a.descriptor.sd>.035&&Math.abs(a.width/a.height-(portrait?.75:4/3))<=.002);
      const costs=indices.map(i=>candidates.map(a=>distance(references[i],a.descriptor)));
      const padded=costs.map(row=>[...row,...indices.map(()=>.85)]);
      const selected=assignment(padded);
      selected.forEach((col,row)=>{if(col>=candidates.length)return;const i=indices[row],score=costs[row][col];if(score>=.85)return;
        slots[i]=candidates[col].id;
        const alternative=Math.min(...costs[row].filter((_,j)=>j!==col));
        notes[i]=score>.35||alternative-score<.10?'Check subject / angle':'Suggested visual match';
      });
    }
    for(const a of unique)if(!slots.includes(a.id))unused.push(a.id);
    return {slots,notes,unused};
  }
  async function fromImage(src){
    const im=new Image();await new Promise((resolve,reject)=>{const timer=setTimeout(()=>{im.src='';reject(new Error('Photo decoding timed out.'));},15000);im.onload=()=>{clearTimeout(timer);resolve();};im.onerror=()=>{clearTimeout(timer);reject(new Error('Photo could not be decoded.'));};im.src=src;});
    const c=document.createElement('canvas');c.width=N;c.height=N;const ctx=c.getContext('2d',{willReadFrequently:true});ctx.fillStyle='#fff';ctx.fillRect(0,0,N,N);ctx.drawImage(im,0,0,N,N);return describe(ctx.getImageData(0,0,N,N).data);
  }
  return {describe,distance,assignment,arrange,fromImage};
})();
if(typeof module!=='undefined')module.exports=DarshanArrange;
