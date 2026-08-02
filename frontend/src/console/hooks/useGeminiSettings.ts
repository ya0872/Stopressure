/**
 * Gemini APIキーとモデルの設定を扱うフック。
 *
 * 画面は「状態表示」と「操作の結果メッセージ」の2つを持つ。どちらもここで管理し、
 * コンポーネント側は表示と入力欄のクリアだけを担当する。
 */
import { useCallback, useEffect, useState } from 'react';
import * as api from '../api';
import type { ApiResult } from '../api';
import type { GeminiStatus } from '../types';
import type { Msg } from '../components/primitives';

/** バックエンド未起動と HTTP エラーで文言を変える。原因の切り分けが変わるため */
function failure(r: ApiResult<unknown>): Msg {
  if (r.kind === 'unreachable') {
    return { text: 'バックエンドに接続できません。backend で uvicorn を起動してください。', tone: 'ng' };
  }
  return { text: r.kind === 'error' ? r.detail : '不明なエラー', tone: 'ng' };
}

export function useGeminiSettings() {
  const [status, setStatus] = useState<GeminiStatus | null>(null);
  const [unreachable, setUnreachable] = useState(false);
  const [models, setModels] = useState<string[]>([]);
  const [msg, setMsg] = useState<Msg | null>(null);

  /** 取得結果を状態へ反映する。初回取得と手動リロードで共通に使う */
  const applyStatus = useCallback((r: ApiResult<GeminiStatus>) => {
    if (r.kind === 'ok') {
      setStatus(r.data);
      setUnreachable(false);
      // 現在のモデルは必ず選択肢に含める。一覧未取得でも選択欄が空にならないようにする
      setModels((prev) => (prev.includes(r.data.model) ? prev : [r.data.model, ...prev]));
      return;
    }
    setUnreachable(r.kind === 'unreachable');
    if (r.kind === 'unreachable') setMsg(failure(r));
  }, []);

  const reload = useCallback(async () => {
    applyStatus(await api.getGemini());
  }, [applyStatus]);

  // 初回取得。effect の本体では setState を呼ばず、反映は必ず then の中で行う
  // （同期的に呼ぶとカスケードレンダーになる: react-hooks/set-state-in-effect）。
  // あわせて、応答が返る前にアンマウントされた場合は結果を捨てる。
  useEffect(() => {
    let cancelled = false;
    void api.getGemini().then((r) => {
      if (!cancelled) applyStatus(r);
    });
    return () => {
      cancelled = true;
    };
  }, [applyStatus]);

  /** キーとモデルを保存する。成功したら true を返す（呼び出し側が入力欄を消すため） */
  const save = useCallback(
    async (apiKey: string, model: string): Promise<boolean> => {
      if (!apiKey && !model) {
        setMsg({ text: 'APIキーを入力してください。', tone: 'ng' });
        return false;
      }
      // バックエンドは保存前にその設定で1回生成して確かめるので、数秒かかることがある。
      // 「保存しています」だけだと固まったように見えるため、何をしているかを出す
      setMsg({ text: '設定を確認して保存しています…', tone: 'plain' });

      const body: { api_key?: string; model?: string } = {};
      if (apiKey) body.api_key = apiKey;
      if (model) body.model = model;

      const r = await api.putGemini(body);
      if (r.kind !== 'ok') {
        setMsg(failure(r));
        return false;
      }
      setStatus(r.data);
      setMsg({ text: '保存しました。', tone: 'ok' });
      return true;
    },
    [],
  );

  const refreshModels = useCallback(async () => {
    setMsg({ text: 'モデル一覧を取得しています…', tone: 'plain' });
    const r = await api.getGeminiModels();
    if (r.kind !== 'ok' || !r.data.length) {
      setMsg(r.kind === 'ok' ? { text: '利用できるモデルがありません。', tone: 'ng' } : failure(r));
      return;
    }
    // 一覧で置き換えず、保存済みのモデルは必ず選択肢に残す。一覧から外れると
    // <select> の value がどの <option> とも一致せず、ブラウザが先頭を表示するため
    // 「保存されている値」と「選択中に見える値」が食い違う
    const current = status?.model;
    setModels(current && !r.data.includes(current) ? [current, ...r.data] : r.data);
    setMsg({ text: `${r.data.length} 件のモデルが利用できます。`, tone: 'ok' });
  }, [status]);

  const test = useCallback(async () => {
    setMsg({ text: '接続を確認しています…', tone: 'plain' });
    const r = await api.testGemini();
    if (r.kind !== 'ok') {
      setMsg(failure(r));
      return;
    }
    setMsg({
      text: (r.data.ok ? '応答: ' : '') + r.data.message,
      tone: r.data.ok ? 'ok' : 'ng',
    });
  }, []);

  const remove = useCallback(async () => {
    setMsg({ text: '削除しています…', tone: 'plain' });
    const r = await api.deleteGemini();
    if (r.kind !== 'ok') {
      setMsg(failure(r));
      await reload();
      return;
    }
    setStatus(r.data);
    setMsg({ text: '保存済みのキーを削除しました。', tone: 'ok' });
  }, [reload]);

  return { status, unreachable, models, msg, setMsg, reload, save, refreshModels, test, remove };
}
