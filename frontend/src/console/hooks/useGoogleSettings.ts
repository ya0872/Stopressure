/**
 * Google OAuth クライアントの登録と連携状態を扱うフック。
 *
 * 設計上の要点（docs/design.md §7.2.3）:
 *   保存しただけでは client_id と client_secret の組み合わせの正否が分からない。
 *   誤りは「認可画面は出るのに最後のトークン交換で invalid_client」という形でしか
 *   表面化せず、原因の特定が難しい。そこで保存に成功したら続けて検証まで走らせる。
 */
import { useCallback, useEffect, useState } from 'react';
import * as api from '../api';
import type { ApiResult } from '../api';
import type { ClientSecretJson, GoogleStatus } from '../types';
import type { Msg } from '../components/primitives';

/**
 * client_id の形。バックエンドの _CLIENT_ID_RE（routers/settings.py）と同じ判定を
 * こちらでも行い、送信前に気づけるようにする。判定の正はバックエンド側。
 */
const CLIENT_ID_RE = /^\d+-[a-z0-9]+\.apps\.googleusercontent\.com$/;

function failure(r: ApiResult<unknown>): Msg {
  if (r.kind === 'unreachable') {
    return { text: 'バックエンドに接続できません。backend で uvicorn を起動してください。', tone: 'ng' };
  }
  return { text: r.kind === 'error' ? r.detail : '不明なエラー', tone: 'ng' };
}

/** 形式が不正な client_id について、どこが変なのかを言葉にする */
function explainBadClientId(id: string): string {
  const why: string[] = [];
  if (/\s/.test(id)) why.push('空白が入っています');
  const bad = [...new Set([...id].filter((c) => !/[a-zA-Z0-9.-]/.test(c)))];
  if (bad.length) why.push('使えない文字: ' + bad.join(' '));
  if (!id.endsWith('.apps.googleusercontent.com')) {
    why.push('末尾が .apps.googleusercontent.com ではありません');
  }
  return (
    'クライアントIDの形式が正しくありません' +
    (why.length ? `（${why.join(' / ')}）` : '') +
    '。Cloud Console のコピーボタンで取得して貼り付けてください。'
  );
}

export function useGoogleSettings() {
  const [status, setStatus] = useState<GoogleStatus | null>(null);
  const [unreachable, setUnreachable] = useState(false);
  const [msg, setMsg] = useState<Msg | null>(null);

  /** 取得結果を状態へ反映する。初回取得と手動リロードで共通に使う */
  const applyStatus = useCallback((r: ApiResult<GoogleStatus>) => {
    if (r.kind === 'ok') {
      setStatus(r.data);
      setUnreachable(false);
      return;
    }
    setUnreachable(r.kind === 'unreachable');
    if (r.kind === 'unreachable') setMsg(failure(r));
  }, []);

  const reload = useCallback(async () => {
    applyStatus(await api.getGoogle());
  }, [applyStatus]);

  // 初回取得。effect の本体では setState を呼ばず、反映は then の中で行う
  // （react-hooks/set-state-in-effect）。アンマウント後の反映も防ぐ。
  useEffect(() => {
    let cancelled = false;
    void api.getGoogle().then((r) => {
      if (!cancelled) applyStatus(r);
    });
    return () => {
      cancelled = true;
    };
  }, [applyStatus]);

  /**
   * 認可画面を通さずに ID とシークレットの組み合わせだけを確かめる。
   * 仕組みは routers/settings.py の /settings/google/test を参照。
   */
  const verify = useCallback(async (prefix = '') => {
    setMsg({ text: prefix + 'Googleに問い合わせています…', tone: 'plain' });
    const r = await api.testGoogle();
    if (r.kind !== 'ok') {
      setMsg(failure(r));
      return;
    }
    setMsg({ text: prefix + r.data.message, tone: r.data.ok ? 'ok' : 'ng' });
  }, []);

  /** 手入力の ID / シークレットを保存する。成功したら true（呼び出し側が入力欄を消す） */
  const save = useCallback(
    async (clientId: string, clientSecret: string): Promise<boolean> => {
      if (!clientId && !clientSecret) {
        setMsg({ text: 'クライアントIDとシークレットを入力してください。', tone: 'ng' });
        return false;
      }
      if (clientId && !CLIENT_ID_RE.test(clientId)) {
        setMsg({ text: explainBadClientId(clientId), tone: 'ng' });
        return false;
      }

      setMsg({ text: '保存しています…', tone: 'plain' });
      const body: { client_id?: string; client_secret?: string } = {};
      if (clientId) body.client_id = clientId;
      if (clientSecret) body.client_secret = clientSecret;

      const r = await api.putGoogle(body);
      if (r.kind !== 'ok') {
        setMsg(failure(r));
        return false;
      }
      setStatus(r.data);
      await verify('保存しました。');
      return true;
    },
    [verify],
  );

  /**
   * client_secret.json をそのまま取り込む。
   *
   * 2つの値を手で運ぶのをやめれば、組み合わせ違いも転記ミスも起きない。
   * 成功したら取り込んだ client_id を返す（入力欄に反映して、何を保存したか見せるため）。
   */
  const applyJson = useCallback(
    async (raw: string): Promise<{ ok: boolean; clientId?: string }> => {
      if (!raw.trim()) {
        setMsg({ text: 'JSONを貼り付けてください。', tone: 'ng' });
        return { ok: false };
      }

      let parsed: ClientSecretJson;
      try {
        parsed = JSON.parse(raw) as ClientSecretJson;
      } catch {
        setMsg({
          text: 'JSONとして読めませんでした。ファイルの中身をそのまま貼り付けてください。',
          tone: 'ng',
        });
        return { ok: false };
      }

      // ウェブアプリは "web"、デスクトップは "installed" の下に入る
      if (parsed.installed && !parsed.web) {
        setMsg({
          text: 'これはデスクトップ用クライアントのJSONです。ウェブ アプリケーション用を使ってください。',
          tone: 'ng',
        });
        return { ok: false };
      }

      const c = parsed.web ?? parsed.installed ?? parsed;
      const id = (c.client_id ?? '').trim();
      const secret = (c.client_secret ?? '').trim();
      if (!id || !secret) {
        setMsg({ text: 'JSONに client_id または client_secret が見つかりません。', tone: 'ng' });
        return { ok: false };
      }

      setMsg({ text: '保存しています…', tone: 'plain' });
      const r = await api.putGoogle({ client_id: id, client_secret: secret });
      if (r.kind !== 'ok') {
        setMsg(failure(r));
        return { ok: false };
      }
      setStatus(r.data);
      await verify('保存しました。');
      return { ok: true, clientId: id };
    },
    [verify],
  );

  /** 連携を保ったまま、体力予算への反映だけを切り替える */
  const setUseContext = useCallback(async (enabled: boolean) => {
    const r = await api.putGoogle({ use_context: enabled });
    if (r.kind !== 'ok') {
      setMsg(failure(r));
      await reload();
      return;
    }
    setStatus(r.data);
    setMsg({
      text: enabled ? '体力予算に反映します。' : '反映を止めました。',
      tone: 'ok',
    });
  }, [reload]);

  const unlink = useCallback(async () => {
    setMsg({ text: '解除しています…', tone: 'plain' });
    const r = await api.unlinkGoogle();
    if (r.kind !== 'ok') {
      setMsg(failure(r));
      await reload();
      return;
    }
    setStatus(r.data);
    setMsg({
      text: '連携を解除しました。Google側の許可も取り消す場合は myaccount.google.com/permissions から削除してください。',
      tone: 'ok',
    });
  }, [reload]);

  return { status, unreachable, msg, setMsg, reload, save, applyJson, verify, setUseContext, unlink };
}
