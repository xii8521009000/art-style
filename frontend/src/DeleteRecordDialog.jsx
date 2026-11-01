import React, {useEffect, useRef, useState} from 'react';
import {LoaderCircle, Trash2} from 'lucide-react';

export default function DeleteRecordDialog({job, api, onClose, onDeleted}) {
  const dialog = useRef(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  useEffect(() => {
    const element = dialog.current;
    element.showModal();
    return () => element.close();
  }, []);

  function cancel() {
    dialog.current.close();onClose();
  }

  async function remove(event) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);setError('');
    try {
      await api('/jobs/' + job.id, {method:'DELETE'});
      onDeleted(job);
    } catch (exception) {
      setError(exception.message);setBusy(false);
    }
  }

  return <dialog ref={dialog} className="delete-dialog" role="alertdialog" aria-labelledby="delete-title" aria-describedby="delete-description" onCancel={event => {event.preventDefault();if (!busy) cancel();}}>
    <form onSubmit={remove}>
      <Trash2 size={27}/><h2 id="delete-title">라이브러리에서 삭제할까요?</h2>
      <p className="delete-record-title">{job.title}</p>
      <p id="delete-description">이 기록의 프롬프트·JSON과 연결된 이미지를 삭제합니다. 다른 기록에서 사용하는 이미지는 유지됩니다. 삭제 후 복구할 수 없습니다.</p>
      {error && <p className="error-box" role="alert">{error}</p>}
      <div className="delete-dialog-actions">
        <button type="button" className="button light" disabled={busy} onClick={cancel} autoFocus>취소</button>
        <button type="submit" className="button danger" disabled={busy}>{busy && <LoaderCircle size={16} className="spin"/>}{busy?'삭제 중…':'삭제'}</button>
      </div>
    </form>
  </dialog>;
}
