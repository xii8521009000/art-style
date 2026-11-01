import test from 'node:test';
import assert from 'node:assert/strict';
import {requestForDelivery, requestImages} from './external-request.js';

test('separate attachment removes image data without mutating embedded request or rules', () => {
  const request = {task: 'Analyze.', instructions: 'Shared rules.', output_schema: {type: 'object'}, input: {
    mode: 'style', image: {delivery: 'embedded_data_url', filename: 'reference.webp', data_url: 'data:image/webp;base64,abc', width: 12},
  }};
  const attached = requestForDelivery(request, 'separate_attachment');
  assert.equal(attached.input.image.data_url, undefined);
  assert.equal(attached.input.image.delivery, 'separate_attachment');
  assert.match(attached.task, /reference.webp/);
  assert.match(attached.task, /do not guess/);
  assert.equal(attached.instructions, request.instructions);
  assert.deepEqual(attached.output_schema, request.output_schema);
  assert.equal(attached.input.mode, 'style');
  assert.ok(request.input.image.data_url);
  assert.equal(requestForDelivery(request, 'embedded_data_url'), request);
  assert.deepEqual(JSON.parse(JSON.stringify(attached)), attached);
});

test('all multiple attachments preserve order/metadata while removing every image payload', () => {
  const request = {task:'Analyze all.',instructions:'Common rules.',input:{primary_image:1,images:[
    {index:1,filename:'reference-01.webp',data_url:'data:one',width:20},
    {index:2,filename:'reference-02.webp',data_url:'data:two',width:30},
  ]}};
  const attached=requestForDelivery(request,'separate_attachment');
  assert.deepEqual(requestImages(attached).map(image=>[image.index,image.filename,image.width,image.delivery]),[
    [1,'reference-01.webp',20,'separate_attachment'],[2,'reference-02.webp',30,'separate_attachment'],
  ]);
  assert.ok(attached.input.images.every(image=>!('data_url' in image)));
  assert.ok(request.input.images.every(image=>image.data_url));
  assert.equal(attached.input.primary_image,1);
  assert.match(attached.task,/ALL source images/);
});
