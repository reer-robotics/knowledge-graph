import {test} from 'node:test';
import assert from 'node:assert/strict';
import {ViewCache,LatestRequest,positions} from '../src/knowledge_graph/web/state.js';
test('view cache evicts old layouts and does not grow indefinitely',()=>{const c=new ViewCache(2);c.set('a',1);c.set('b',2);c.get('a');c.set('c',3);assert.equal(c.get('b'),undefined);assert.equal(c.values.size,2);});
test('old view requests are discarded',()=>{const r=new LatestRequest();const old=r.next();const current=r.next();assert.equal(r.current(old),false);assert.equal(r.current(current),true);});
test('layout is deterministic independent of source ordering',()=>{const nodes=[{id:'root'},{id:'a'},{id:'b'}];assert.deepEqual(positions(nodes,'root'),positions(nodes.toReversed(),'root'));});
