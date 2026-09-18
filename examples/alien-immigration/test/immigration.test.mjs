import test, { after } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { ZenEngine } from '@gorules/zen-engine';
import { base, travelers, validate } from '../src/data.js';
const engine = new ZenEngine();
const model=JSON.parse(fs.readFileSync(new URL('../public/immigration.json',import.meta.url)));
const decision=engine.createDecision(model);
const evaluate=async changes=>(await decision.evaluate(validate({...base,...changes}),{trace:true}));
after(()=>engine.dispose());
test('the four arrivals produce distinct, explained outcomes',async()=>{
 for(const [i,expected] of ['tourist','denied','review','quarantine'].entries()){
  const r=await evaluate(travelers[i].case);assert.equal(r.result.visa.status,expected);assert.ok(r.trace.admission.traceData);assert.ok(r.result.checks.length);
 }
});
test('each troubled visitor can be cleared by fixing the manifest',async()=>{
 assert.equal((await evaluate({...travelers[1].case,cargo:'none'})).result.visa.status,'cultural');
 assert.equal((await evaluate({...travelers[2].case,consent:true})).result.visa.status,'diplomatic');
 assert.equal((await evaluate({...travelers[3].case,containment:true})).result.visa.status,'cultural');
});
test('black holes override every purpose, containment and environment',async()=>{
 for(const purpose of ['tourism','culture','diplomacy'])for(const atmosphere of ['oxygen','methane','vacuum'])for(const containment of [true,false]){
  const r=await evaluate({cargo:'blackHole',purpose,atmosphere,containment,suit:false});assert.equal(r.result.visa.status,'denied');
 }
});
test('all simultaneous hazards appear, but the first admission rule wins',async()=>{
 const r=await evaluate({cargo:'blackHole',atmosphere:'methane',suit:false,telepathy:true,consent:false,translator:false,days:90});
 assert.deepEqual(r.result.checks.map(x=>x.code),['singularity','atmosphere','telepathy','translation','duration','welcome']);
 assert.equal(r.result.visa.code,'no-black-holes');
});
test('biosecurity and atmosphere safety override diplomatic privileges',async()=>{
 assert.equal((await evaluate({purpose:'diplomacy',cargo:'spores',containment:false})).result.visa.status,'quarantine');
 assert.equal((await evaluate({purpose:'diplomacy',atmosphere:'vacuum',suit:false})).result.visa.status,'quarantine');
});
test('30 days is allowed; 31 days is reviewed',async()=>{
 assert.equal((await evaluate({days:30})).result.visa.status,'tourist');
 assert.equal((await evaluate({days:31})).result.visa.code,'shorten-trip');
});
test('no telepathy needs no pledge, but a translator is mandatory',async()=>{
 assert.equal((await evaluate({telepathy:false,consent:false})).result.visa.status,'tourist');
 assert.equal((await evaluate({translator:false})).result.visa.code,'bring-translator');
});
test('invalid manifests fail validation',()=>{
 for(const patch of [{days:0},{days:91},{days:1.5},{days:NaN},{translator:'true'},{cargo:'unknown'},{purpose:'work'}])assert.throws(()=>validate({...base,...patch}));
});
test('both languages have messages for every decision and finding',()=>{
 for(const node of model.nodes.filter(n=>n.content?.rules))for(const row of node.content.rules){assert.ok(JSON.parse(row.en));assert.match(JSON.parse(row.zh),/[\u4e00-\u9fff]/);}
});
