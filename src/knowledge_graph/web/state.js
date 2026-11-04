export class ViewCache {
  constructor(limit=10) { this.limit=limit; this.values=new Map(); }
  get(key) { const value=this.values.get(key); if(value){this.values.delete(key);this.values.set(key,value);} return value; }
  set(key,value) { this.values.delete(key);this.values.set(key,value);while(this.values.size>this.limit)this.values.delete(this.values.keys().next().value); }
}
export class LatestRequest {
  constructor(){this.id=0;}
  next(){return ++this.id;}
  current(id){return id===this.id;}
}
export function positions(nodes,focus) {
  const ids=nodes.filter(n=>n.id!==focus).map(n=>n.id).sort();
  const result={[focus]:{x:0,y:0}};
  ids.forEach((id,index)=>{
    if(ids.length<=12){const angle=ids.length===2?-3*Math.PI/4+index*Math.PI/2:-Math.PI/2+index*2*Math.PI/ids.length;const radius=Math.max(180,ids.length*26);result[id]={x:Math.cos(angle)*radius,y:Math.sin(angle)*radius};}
    else result[id]={x:(index%8-3.5)*150,y:(Math.floor(index/8)+1)*130};
  });return result;
}
