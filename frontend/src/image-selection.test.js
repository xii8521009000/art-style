import test from 'node:test';
import assert from 'node:assert/strict';
import {addImageFiles} from './image-selection.js';
const file=(name,size=100)=>({name,size,type:'image/png',lastModified:1});
test('adding image batches retains chosen anchor and order, removes duplicate selections',()=>{
  const first=file('anchor.png'),second=file('view.png');
  assert.deepEqual(addImageFiles([first],[first,second]),[first,second]);
  assert.deepEqual(addImageFiles([second,first],[file('third.png')]).map(image=>image.name),['view.png','anchor.png','third.png']);
});
test('batch validation rejects excess count/total bytes and non-images',()=>{
  assert.throws(()=>addImageFiles([],Array.from({length:9},(_,i)=>file(`${i}.png`))),/8장/);
  assert.throws(()=>addImageFiles([file('one',20*1048576)],[file('two',11*1048576)]),/합계/);
  assert.throws(()=>addImageFiles([],[{...file('bad'),type:'text/plain'}]),/이미지/);
});
