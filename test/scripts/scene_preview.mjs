// Test asynchronous preview ordering without a browser/network timing lottery.
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const source=readFileSync('examples/scene-renderer/preview.html','utf8').split('<script>')[1].split('</script>')[0];
const elements=new Map();
const el=id=>{if(!elements.has(id))elements.set(id,{value:0,textContent:'',replaceChildren(){}});return elements.get(id)};
const requests=[];
const context=vm.createContext({document:{getElementById:el,createElement:()=>({})},
  Image:class{set src(v){this.url=v;requests.push(this)}get src(){return this.url}},
  fetch:()=>new Promise(()=>{}),performance:{now:()=>0},requestAnimationFrame(){},setInterval(){},addEventListener(){},console});
vm.runInContext(source,context);
const run=s=>vm.runInContext(s,context);
run("manifest={revision:'a',frames:360,fps:[30,1],duration:12};request(0);request(40);request(90)");
assert.equal(requests.length,1,'only one image admitted');
requests.shift().onload();
assert.equal(el('frame').src,undefined,'stale frame never published');
assert.equal(requests[0].url,'a/90.png','pending scrubs coalesced');
requests.shift().onload();assert.equal(el('frame').src,'a/90.png');
run("request(100);manifest={revision:'b',frames:360,fps:[30,1],duration:12};request(110)");
requests.shift().onload();assert.equal(el('frame').src,'a/90.png','old revision cannot replace last valid image');
requests.shift().onerror();assert.equal(el('frame').src,'a/90.png','failure retains last valid frame');
run('request(120)');requests.shift().onload();assert.equal(el('frame').src,'b/120.png');
console.log('preview: bounded queue, coalescing, stale revision suppression and failure retention passed');
