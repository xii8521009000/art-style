import React, {useState} from 'react';
import {Check, ClipboardPaste, LoaderCircle, Save} from 'lucide-react';
import ImageSelection from './ImageSelection.jsx';

export default function ImportLibrary({initialFiles = [], api, notify, onOpen}) {
  const [files,setFiles]=useState(initialFiles),[text,setText]=useState(''),[language,setLanguage]=useState('en');
  const [preview,setPreview]=useState(null),[title,setTitle]=useState(''),[busy,setBusy]=useState(''),[error,setError]=useState('');
  async function validate() {
    setBusy('preview');setError('');
    try {
      const result=await api('/library/preview',{method:'POST',body:JSON.stringify({response:text,language})});
      setPreview(result);setTitle(result.title);
    } catch(e) {setPreview(null);setError(e.message)}
    finally {setBusy('')}
  }
  async function save() {
    setBusy('save');setError('');
    try {
      const body=new FormData(); files.forEach(file=>body.append('files',file));
      body.append('response',text);body.append('language',language);body.append('title',title);
      const result=await api('/library/import',{method:'POST',body});
      notify('이미지와 JSON 응답을 라이브러리에 저장했습니다.');onOpen(result);
    } catch(e) {setError(e.message)}
    finally {setBusy('')}
  }
  function changeText(value) {setText(value);setPreview(null);setError('')}
  return <><div className="page-heading"><div><h1>챗봇 응답을 라이브러리로.</h1><p>분석한 이미지와 JSON 응답을 함께 저장합니다. Codex 연결 없이 사용할 수 있습니다.</p></div></div>
    <div className="new-grid"><ImageSelection files={files} onChange={setFiles} onError={setError} disabled={!!busy}/>
      <section className="options-card import-card"><label htmlFor="external-response">분석 결과 JSON</label><p className="import-help">외부 챗봇이 돌려준 응답 전체를 붙여 넣으세요. json 코드 블록도 인식합니다.</p>
        <textarea id="external-response" className="import-response" value={text} maxLength={1024*1024} spellCheck={false} placeholder={'{\n  "title": "나의 화풍",\n  "style_prompt": "...",\n  "character_prompt": null\n}'} onChange={e=>changeText(e.target.value)}/>
        <label className="import-language">프롬프트 언어<select value={language} onChange={e=>{setLanguage(e.target.value);setPreview(null)}}><option value="en">English</option><option value="ko">한국어</option></select></label>
        {error&&<div className="error-box" role="alert">{error}</div>}
        {!preview?<button className="button full" disabled={!text.trim()||!!busy} onClick={validate}>{busy?<LoaderCircle size={17} className="spin"/>:<ClipboardPaste size={17}/>}응답 확인</button>:<>
          <div className="import-preview"><p><Check size={16}/>{preview.mode==='both'?'화풍 + 캐릭터':preview.mode==='style'?'화풍':'캐릭터'} 프롬프트를 확인했습니다.</p><label>기록 제목<input value={title} maxLength={200} onChange={e=>setTitle(e.target.value)}/></label><small>{preview.style_prompt?.length||0}자 화풍 · {preview.character_prompt?.length||0}자 캐릭터</small></div>
          <button className="button full" disabled={!files.length||!!busy||!title.trim()} onClick={save}>{busy==='save'?<LoaderCircle size={17} className="spin"/>:<Save size={17}/>}이미지와 JSON 저장</button>
        </>}
        <p className="sub-note">원래 응답 JSON도 보관하며, 저장 즉시 분석 기록에서 다시 볼 수 있습니다.</p>
      </section></div>
  </>;
}
