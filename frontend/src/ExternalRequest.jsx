import React, {useEffect, useMemo, useRef, useState} from 'react';
import {Copy, Download, LoaderCircle, RefreshCw, X} from 'lucide-react';
import {requestForDelivery, requestImages} from './external-request.js';

const modeLabels = {both: '화풍 + 캐릭터', style: '화풍만', character: '캐릭터만'};

export default function ExternalRequest({file, files, job, mode: initialMode, focus = '', language: initialLanguage = 'en', api, notify, onClose, onImport}) {
  const dialog = useRef(), manualInput = useRef();
  const [language, setLanguage] = useState(initialLanguage);
  const [mode, setMode] = useState(initialMode);
  const [delivery, setDelivery] = useState('embedded_data_url');
  const [request, setRequest] = useState(null), [error, setError] = useState('');
  const [retry, setRetry] = useState(0), [manual, setManual] = useState(false), [copying, setCopying] = useState(false);
  const [copied, setCopied] = useState(false);
  const [downloadURL, setDownloadURL] = useState('');
  useEffect(() => {
    const previous = document.activeElement, overflow = document.body.style.overflow;
    dialog.current.showModal();
    document.body.style.overflow = 'hidden';
    return () => {document.body.style.overflow = overflow; previous?.focus()};
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    setRequest(null); setError(''); setManual(false);
    let promise;
    if (job) {
      promise = api(`/jobs/${job.id}/export-request`, {method: 'POST', signal: controller.signal,
        body: JSON.stringify({mode, language, focus: mode === 'style' ? '' : focus})});
    } else {
      const body = new FormData();
      (files || [file]).forEach(image => body.append('files', image)); body.append('mode', mode); body.append('language', language);
      body.append('focus', mode === 'style' ? '' : focus);
      promise = api('/export-request', {method: 'POST', body, signal: controller.signal});
    }
    promise.then(data => {if (!controller.signal.aborted) setRequest(data)})
      .catch(e => {if (!controller.signal.aborted) setError(e.message)});
    return () => controller.abort();
  }, [file, files, job?.id, mode, language, focus, retry, api]);
  const output = useMemo(() => request ? JSON.stringify(requestForDelivery(request, delivery), null, 2) : '', [request, delivery]);
  const images = requestImages(request);
  useEffect(() => {
    if (!output) {setDownloadURL(''); return}
    const url = URL.createObjectURL(new Blob([output], {type: 'application/json;charset=utf-8'}));
    setDownloadURL(url);
    return () => URL.revokeObjectURL(url);
  }, [output]);
  useEffect(() => setCopied(false), [output]);
  useEffect(() => {if (manual) {manualInput.current?.focus(); manualInput.current?.select()}}, [manual, output]);
  async function copy() {
    setCopying(true);
    try {
      await navigator.clipboard.writeText(output);
      setManual(false); setCopied(true);
      notify('외부 도구용 JSON 요청문을 복사했습니다.');
    } catch {
      setManual(true);
    } finally {setCopying(false)}
  }
  return <dialog ref={dialog} className="export-dialog" aria-labelledby="export-title" onCancel={e => {e.preventDefault(); onClose()}}>
    <div className="export-heading"><div><h2 id="export-title">외부 도구용 JSON</h2><p>같은 추출 규칙을 이미지 분석이 가능한 도구에서 사용하세요.</p></div><button autoFocus className="icon-button" aria-label="JSON 내보내기 닫기" onClick={onClose}><X size={18}/></button></div>
    <div className="export-options"><select aria-label="외부 요청 분석 범위" value={mode} onChange={e => setMode(e.target.value)}>{Object.entries(modeLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select><select aria-label="외부 요청 프롬프트 언어" value={language} onChange={e => setLanguage(e.target.value)}><option value="en">English</option><option value="ko">한국어</option></select></div>
    <div className="export-delivery" role="radiogroup" aria-label="외부 도구에 이미지 전달 방식">{[['embedded_data_url', '이미지 포함'], ['separate_attachment', '이미지 별도 첨부']].map(([value, label]) => <button key={value} role="radio" aria-checked={delivery === value} className={delivery === value ? 'selected' : ''} onClick={() => {setDelivery(value); setManual(false)}}>{label}</button>)}</div>
    <p className="export-help">{delivery === 'embedded_data_url' ? '최적화한 모든 WebP를 Base64로 포함합니다. 대화창에서 이미지 데이터를 인식하지 못하면 ‘이미지 별도 첨부’를 사용하세요.' : 'JSON을 붙여 넣고 아래 이미지를 순서대로 모두 첨부하세요. 1번이 화풍의 기준이며, 이미지 데이터가 빠져 요청문이 짧아집니다.'}</p>
    {error ? <div role="alert" className="error-box">{error}<button className="button ghost" onClick={() => setRetry(v => v + 1)}><RefreshCw size={15}/>다시 준비</button></div> : !request ? <div className="export-loading" role="status"><LoaderCircle size={18} className="spin"/>이미지와 추출 규칙을 준비하고 있습니다.</div> : <>
      <div className="export-summary"><span>{images.length>1?`${images.length}장 · 1번 기준`: `${images[0].width} × ${images[0].height}`} · WebP</span><span>규칙 {request.style_ruleset} · JSON {(new Blob([output]).size / 1024).toFixed(0)} KB</span></div>
      <details className="export-instructions"><summary>추출 지침 확인</summary><pre>{request.instructions}</pre></details>
      {manual && <div className="export-manual"><p role="status">브라우저가 클립보드 복사를 허용하지 않았습니다. 선택된 요청문을 직접 복사하거나 JSON 파일로 받으세요.</p><textarea ref={manualInput} readOnly value={output} aria-label="직접 복사할 JSON 요청문"/></div>}
    </>}
    {delivery==='separate_attachment'&&images.length>1&&<div className="attachment-images" aria-label="첨부할 이미지">{images.map(image=><a key={image.filename} href={image.data_url} download={image.filename}><img src={image.data_url} alt={`${image.index}번 첨부 이미지`}/><span>{image.filename}</span><Download size={13}/></a>)}</div>}
    <div className="export-actions">{delivery === 'separate_attachment' && images.length===1 && <a className="button light" href={images[0].data_url} download={images[0].filename}><Download size={16}/>이미지 받기</a>}{output && downloadURL ? <a className="button light" href={downloadURL} download="artstyle-request.json"><Download size={16}/>JSON 받기</a> : <button className="button light" disabled><Download size={16}/>JSON 받기</button>}<button className="button" aria-live="polite" disabled={!output || copying} onClick={copy}>{copying ? <LoaderCircle size={16} className="spin"/> : <Copy size={16}/>} {copied ? '복사됨' : 'JSON 복사'}</button></div>
    <p className="export-footnote">Codex 연결 없이 준비되며 새 분석 기록을 만들지 않습니다. 여러 도구에서 읽을 수 있는 요청 명세로, 특정 서비스 API에 바로 보내는 형식은 아닙니다. 결과는 도구·모델에 따라 달라질 수 있습니다.</p>
    {onImport&&<button className="export-import-link" onClick={onImport}>챗봇의 응답을 받았나요? JSON 저장하기 →</button>}
  </dialog>;
}
