import React, {useEffect, useRef, useState} from 'react';
import {ImagePlus, Plus, X, CheckCircle2} from 'lucide-react';
import {addImageFiles} from './image-selection.js';

const bytes = n => n < 1048576 ? `${(n/1024).toFixed(1)} KB` : `${(n/1048576).toFixed(1)} MB`;

export default function ImageSelection({files, onChange, onError, disabled}) {
  const input = useRef();
  const [previews, setPreviews] = useState([]), [drag, setDrag] = useState(false);
  useEffect(() => {
    const urls = files.map(file => URL.createObjectURL(file));
    setPreviews(urls);
    return () => urls.forEach(url => URL.revokeObjectURL(url));
  }, [files]);
  function add(incoming) {
    if (disabled) return;
    try {onChange(addImageFiles(files, Array.from(incoming))); onError('')}
    catch (error) {onError(error.message)}
  }
  return <section className="upload-card" onDragOver={e => {e.preventDefault(); setDrag(true)}} onDragLeave={() => setDrag(false)} onDrop={e => {e.preventDefault(); setDrag(false); add(e.dataTransfer.files)}}>
    <div className="card-top"><h2>레퍼런스 이미지</h2>{files.length > 0 && <span className="selection-count">{files.length} / 8</span>}</div>
    <input ref={input} className="sr-only" type="file" multiple accept="image/*" aria-label="레퍼런스 이미지 선택" disabled={disabled} onChange={e => {add(e.target.files); e.target.value = ''}}/>
    {files.length ? <div className={`selected-images ${drag ? 'drag' : ''}`}>{files.map((file,index) => <div className={`selected-image ${index === 0 ? 'primary' : ''}`} key={file.name + file.size + file.lastModified}>
      <div className="selected-preview"><img src={previews[index]} alt={`${index+1}번 ${file.name}`}/><span className="image-number">{index+1}{index===0?' · 기준':''}</span><button className="icon-button light" aria-label={`${index+1}번 이미지 제거`} disabled={disabled} onClick={() => onChange(files.filter((_,i) => i!==index))}><X size={14}/></button></div>
      <div className="selected-caption"><span title={file.name}>{file.name}</span>{index>0 && <button disabled={disabled} onClick={() => onChange([file,...files.filter((_,i) => i!==index)])}>기준으로</button>}</div>
    </div>)}</div> : <div className={`dropzone ${drag?'drag':''}`}><button className="drop-trigger" disabled={disabled} onClick={() => input.current.click()}><div className="upload-symbol"><ImagePlus size={29} strokeWidth={1.25}/><span>+</span></div><strong>이미지를 끌어다 놓으세요</strong><span>여러 장을 함께 선택할 수 있습니다</span><small>JPG, PNG, WebP 등 · 최대 8장 · 합계 30MB</small></button></div>}
    {files.length>0 && <><div className="selection-toolbar"><button className="button light" disabled={disabled||files.length>=8} onClick={() => input.current.click()}><Plus size={15}/>이미지 추가</button><span>{bytes(files.reduce((sum,file)=>sum+file.size,0))} / 30 MB</span></div><p className="selection-help">첫 이미지를 기준으로 공통 화풍을 찾습니다. 다른 화풍이 섞이면 차이를 따로 표시합니다.</p></>}
    <div className="compression-note"><CheckCircle2 size={14}/><span>각 이미지를 최적화해 보관합니다. 원본은 서버에 남기지 않습니다.</span></div>
  </section>;
}

export function SavedReferences({job}) {
  const [index, setIndex] = useState(0);
  useEffect(()=>setIndex(0),[job.id]);
  const images = job.images?.length ? job.images : [job], current = images[index] || images[0];
  return <>
    <div className="reference-image"><img src={`/api/jobs/${job.id}/image?index=${index}`} alt={`${index+1}번 ${current.filename}`}/></div>
    {images.length>1 && <div className="reference-thumbnails" aria-label="등록 이미지">{images.map((image,i)=><button key={image.id} className={index===i?'selected':''} aria-label={`${i+1}번 이미지${i===0?' · 기준':''}`} aria-pressed={index===i} onClick={()=>setIndex(i)}><img src={`/api/jobs/${job.id}/image?index=${i}`} alt=""/><span>{i+1}{i===0?' · 기준':''}</span></button>)}</div>}
    <div className="reference-meta"><strong>{current.filename}</strong><div><span>{current.width} × {current.height}</span><span>{bytes(current.stored_bytes)}</span></div><div className="storage-bar"><i style={{width:Math.min(100,current.stored_bytes/current.original_bytes*100)+'%'}}/></div><p>{bytes(current.original_bytes)} → {bytes(current.stored_bytes)}</p>{images.length>1 && <small>{images.length}장 · 최적화 합계 {bytes(job.total_stored_bytes)}</small>}<a className="image-download" href={`/api/jobs/${job.id}/image?index=${index}&download=true`}>이미지 받기 ↓</a></div>
  </>;
}

export function ReferenceSummary({summary, mode}) {
  if (!summary) return null;
  const status = {consistent:mode==='character'?'외형이 일치합니다':'공통 화풍을 확인했습니다',mixed:'서로 다른 특징이 있습니다',insufficient:'비교 근거가 부족합니다'}[summary.consistency];
  return <details className="reference-summary" open={summary.consistency!=='consistent'}><summary>이미지 비교 · {status}</summary>{[['common_traits','공통점'],['differences','차이와 변형'],['conflicts','주의할 차이']].map(([field,label])=>summary[field]?.length>0&&<div key={field}><strong>{label}</strong><ul>{summary[field].map((text,i)=><li key={i}>{text}</li>)}</ul></div>)}</details>;
}
