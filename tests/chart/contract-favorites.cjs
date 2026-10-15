const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),{randomUUID}=require('node:crypto');
const source=fs.readFileSync('frontend/static/js/contract-favorites.js','utf8');
const context={window:{},crypto:{randomUUID}};vm.runInNewContext(source,context);
const factory=context.window.WheelContractFavorites;
const storage=seed=>{const values=new Map(Object.entries(seed||{}));return {getItem:k=>values.get(k)??null,setItem:(k,v)=>values.set(k,v)}};
(async()=>{
 let revision=0,rows=new Map(),posts=0,failAfterWrite=false;const errors=[];
 const api=async(path,body)=>{
  assert.equal(path,'chart-favorites');const conflicts=[];
  if(body){posts++;for(const op of body.operations){const old=rows.get(op.id);if(op.kind==='import'&&old)continue;if(old&&old.rev>op.base){conflicts.push({id:op.id,reason:'changed'});continue;}rows.set(op.id,{rev:++revision,value:op.kind==='delete'?null:op.value});}
   if(failAfterWrite)throw Error('Lost reply');}
  return {revision,favorites:[...rows.values()].flatMap(x=>x.value?[x.value]:[]),conflicts};
 };
 const legacy=JSON.stringify([{id:7,label:'QQQ 20261120 600 CALL'}]);const webStorage=storage({'wheel.web.favorite-contracts':legacy});
 const web=factory({api,storage:webStorage,onChange:()=>{},onError:e=>errors.push(e)});
 const phone=factory({api,storage:storage(),onChange:()=>{},onError:e=>errors.push(e)});
 await web.refresh();await phone.refresh();assert.equal(phone.items[0].id,7);assert.equal(webStorage.getItem('wheel.web.favorite-contracts'),legacy);
 await phone.toggle({id:8,label:'QQQ'});await web.refresh();assert.equal(web.items.length,2);
 await web.toggle({id:7,label:'QQQ 20261120 600 CALL'});await phone.refresh();assert.deepEqual([...phone.items].map(x=>x.id),[8]);
 const oldBrowser=factory({api,storage:storage({'wheel.web.favorite-contracts':legacy}),onChange:()=>{},onError:e=>errors.push(e)});
 await oldBrowser.refresh();assert.deepEqual([...oldBrowser.items].map(x=>x.id),[8]);
 failAfterWrite=true;await web.toggle({id:9,label:'MESZ6'});const count=posts;assert.equal(web.ready,false);
 failAfterWrite=false;await web.refresh();assert.equal(posts,count);assert.ok(web.items.some(x=>x.id===9));
 assert.ok(errors.some(x=>x.includes('could not be confirmed')));
 console.log('PASS shared favorites: import union, exact ID, deletion, old-device migration, unknown-response read reconciliation');
})().catch(e=>{console.error(e);process.exit(1)});
