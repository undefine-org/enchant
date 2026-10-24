// Deterministic latest-intent and bounded client checks without a timing lottery.
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const source=readFileSync('examples/scene-renderer/studio.html','utf8').split('<script>')[1].split('</script>')[0];
const elements=new Map();
function element(){return {value:'',textContent:'',children:[],setAttribute(){},replaceChildren(...v){this.children=v},append(...v){this.children.push(...v)}}}
const get=id=>{if(!elements.has(id))elements.set(id,element());return elements.get(id)};
const requests=[];
const ctx=vm.createContext({document:{getElementById:get,createElement:element,createElementNS:element},
  Image:class{decode(){return Promise.resolve()}},
  fetch:(path,opts)=>path==='/api/config'?new Promise(()=>{}):new Promise(resolve=>requests.push({opts,resolve})),
  requestAnimationFrame(){},performance:{now:()=>0},setTimeout(){},clearTimeout(){},addEventListener(){},console});
vm.runInContext(source,ctx);
const run=s=>vm.runInContext(s,ctx),flush=()=>new Promise(r=>setImmediate(r));
run("config={cards:[]};seek(20);seek(30);seek(40)");
assert.equal(requests.length,1);
assert.equal(JSON.parse(requests[0].opts.body).frame,20);
requests[0].resolve({json:async()=>({ok:true,image:'old',objects:{},revision:'old',frame:20,time:20/24})});
await flush();assert.equal(get('frame').src,undefined,'stale result must not replace desired newer frame');
assert.equal(requests.length,2);assert.equal(JSON.parse(requests[1].opts.body).frame,40,'pending seeks coalesce');
requests[1].resolve({json:async()=>({ok:true,image:'new',objects:{},revision:'new',frame:40,time:40/24})});
await flush();assert.equal(get('frame').src,'new');
run('seek(50)');requests[2].resolve({json:async()=>({ok:false,diagnostic:'invalid caption'})});
await flush();assert.equal(get('frame').src,'new','invalid edit retains valid pixels');
assert.equal(get('status').textContent,'invalid caption');
run("config.title='unpreviewed edit';$('export').onclick()");
assert.equal(requests.length,3,'an unpreviewed edit cannot silently export the old picture');
run("config=JSON.parse(JSON.stringify(accepted.config));$('export').onclick()");
assert.equal(requests.length,4);
assert.equal(JSON.parse(requests[3].opts.body).revision,'new');
requests[3].resolve({json:async()=>({ok:true,job:{revision:'new',state:'ready',url:'/api/export/video?revision=new'}})});
await flush();assert.equal(get('download').href,'/api/export/video?revision=new');
assert.equal(get('download').hidden,false);
console.log('Studio client: bounded latest intent, failure retention, exact accepted export, and download passed');
