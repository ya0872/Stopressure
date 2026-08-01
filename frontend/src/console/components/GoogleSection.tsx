/**
 * Google OAuth クライアントの登録と連携操作。
 *
 * 取得するのは「量」だけで、予定のタイトル・メールの件名や本文は取得しない。
 * 要求する権限はすべて読み取り専用（docs/design.md §7.2）。
 */
import { useState } from 'react';
import { LOGIN_URL, REDIRECT_URI } from '../api';
import { useGoogleSettings } from '../hooks/useGoogleSettings';
import { CopyLine, Message, Row, Rows, SecretInput, Section } from './primitives';

/** ISO8601(UTC) を「2026-08-01 13:25:36 UTC」の形にする */
function formatLinkedAt(iso: string | null): string {
  if (!iso) return '—';
  return iso.replace('T', ' ').slice(0, 19) + ' UTC';
}

/** スコープURLは長いので、/auth/ より後ろだけを見せる */
function shortScope(scope: string): string {
  return scope.split('/auth/').pop() ?? scope;
}

export function GoogleSection() {
  const { status, unreachable, msg, setMsg, save, applyJson, verify, setUseContext, unlink } =
    useGoogleSettings();

  const [json, setJson] = useState('');
  const [clientId, setClientId] = useState('');
  const [clientSecret, setClientSecret] = useState('');
  const [reveal, setReveal] = useState(false);

  const configured = status?.configured ?? false;
  const linked = status?.linked ?? false;

  const onApplyJson = async () => {
    const result = await applyJson(json);
    if (result.ok) {
      // 貼り付けた内容も、そこから取り出したシークレットも残さない
      setJson('');
      setClientSecret('');
      setReveal(false);
      // 何を保存したかは見えるようにしておく（IDは平文で保存される値なので出してよい）
      if (result.clientId) setClientId(result.clientId);
    }
  };

  const onSave = async () => {
    const ok = await save(clientId.trim(), clientSecret.trim());
    if (ok) {
      setClientSecret('');
      setReveal(false);
    }
  };

  return (
    <Section title="Google 連携（カレンダー / ToDo / メール）">
      <Rows spaced>
        {unreachable ? (
          <Row label="バックエンド" value="未起動" tone="ng" />
        ) : !status ? (
          <Row label="状態" value="読み込んでいます…" tone="dim" />
        ) : (
          <>
            <Row
              label="OAuthクライアント"
              value={configured ? '登録済み' : '未登録'}
              tone={configured ? 'ok' : 'warn'}
            />
            <Row label="クライアントID" value={status.client_id ?? '—'} tone="dim" mono />
            <Row
              label="アカウント連携"
              value={linked ? '連携済み' : '未連携'}
              tone={linked ? 'ok' : 'warn'}
            />
            <Row label="連携した日時" value={formatLinkedAt(status.linked_at)} tone="dim" />
            <Row
              label="要求する権限"
              tone="dim"
              mono
              value={status.scopes.map((s) => (
                <span key={s}>
                  {shortScope(s)}
                  <br />
                </span>
              ))}
            />
          </>
        )}
      </Rows>

      <div className="field">
        <label htmlFor="gg-json">
          client_secret JSON を貼り付ける <span className="hint">— 手入力より確実です</span>
        </label>
        <textarea
          id="gg-json"
          rows={4}
          value={json}
          onChange={(e) => setJson(e.target.value)}
          spellCheck={false}
          autoComplete="off"
          placeholder={
            'Cloud Console でシークレットを追加したときにダウンロードできる JSON をそのまま貼り付けてください\n{"web":{"client_id":"...","client_secret":"...", ...}}'
          }
        />
        <div className="input-row" style={{ marginTop: '0.4rem' }}>
          <button type="button" className="primary" onClick={() => void onApplyJson()}>
            JSONから読み込んで保存・検証
          </button>
        </div>
        <div className="sub-hint">
          client_id とシークレットが必ず対になるため、組み合わせ違いが起きません。
          貼り付けた内容は保存後に消去され、どこにも残しません。
        </div>
      </div>

      <div className="field">
        <label htmlFor="gg-id">
          クライアントID <span className="hint">— 認可URLに載るため平文で保存されます</span>
        </label>
        <div className="input-row">
          <input
            id="gg-id"
            type="text"
            value={clientId}
            onChange={(e) => setClientId(e.target.value)}
            placeholder="000000000000-xxxxxxxx.apps.googleusercontent.com"
            autoComplete="off"
            spellCheck={false}
          />
        </div>
        <div className="sub-hint">
          Cloud Console の<strong>コピーボタン</strong>で取得してください。手入力すると空白や記号が混入し、
          Google が <code className="inline">401 invalid_client</code> を返します。
        </div>
      </div>

      <div className="field">
        <label htmlFor="gg-secret">
          クライアントシークレット <span className="hint">— 暗号化して保存されます</span>
        </label>
        <SecretInput
          id="gg-secret"
          value={clientSecret}
          onChange={setClientSecret}
          placeholder="GOCSPX-…"
          reveal={reveal}
          onToggleReveal={() => setReveal((v) => !v)}
        />
      </div>

      <div className="actions">
        <button type="button" className="primary" onClick={() => void onSave()}>
          保存する
        </button>
        <button type="button" onClick={() => void verify()} disabled={!configured}>
          ID と シークレットを検証
        </button>
        <button
          type="button"
          disabled={!configured}
          onClick={() => {
            // 認可画面へ遷移する。戻りはバックエンドのコールバックが受ける
            window.location.href = LOGIN_URL;
          }}
        >
          Googleと連携する
        </button>
        <button type="button" className="danger" onClick={() => void unlink()} disabled={!linked}>
          連携を解除
        </button>
      </div>
      <Message msg={msg} />

      <div className="field" style={{ marginTop: '1.2rem' }}>
        <label className="toggle">
          <input
            type="checkbox"
            checked={status?.use_context ?? false}
            onChange={(e) => void setUseContext(e.target.checked)}
          />
          予定・メール・ToDo を体力予算に反映する
        </label>
        <div className="sub-hint" style={{ marginLeft: '1.5rem' }}>
          外すと、連携を保ったまま反映だけを止めます。
        </div>
      </div>

      <div className="note">
        <strong style={{ color: 'var(--text-dim)' }}>Google Cloud Console 側の設定</strong>
        <ol>
          <li>プロジェクトを作成する</li>
          <li>
            「APIとサービス」→ ライブラリ で <code>Google Calendar API</code> /{' '}
            <code>Google Tasks API</code> / <code>Gmail API</code> を有効化する
          </li>
          <li>
            「認証情報」→ OAuth クライアント ID を作成（種別: <strong>ウェブ アプリケーション</strong>）
          </li>
          <li>承認済みのリダイレクト URI に、下の値を<strong>そのまま</strong>登録する</li>
          <li>
            OAuth 同意画面は「テスト」のままでよい（審査不要）。テストユーザーに自分のアカウントを追加する
          </li>
        </ol>
        <CopyLine value={REDIRECT_URI} onCopied={setMsg} />
        <div style={{ marginTop: '0.9rem' }}>
          取得するのは「拘束時間」「未読の重要メール件数」「期限が今日以前のToDo件数」だけです。
          予定のタイトル、メールの件名や本文は取得しません。要求する権限はすべて読み取り専用です。
        </div>
      </div>
    </Section>
  );
}
