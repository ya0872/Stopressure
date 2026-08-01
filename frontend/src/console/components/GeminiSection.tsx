/**
 * Gemini APIキーとモデルの設定。
 *
 * キーは保存すると Fernet で暗号化され、画面にはマスク済み文字列しか返らない
 * （平文を返すAPIは用意されていない: docs/design.md §3.3）。
 */
import { useState } from 'react';
import { useGeminiSettings } from '../hooks/useGeminiSettings';
import { Message, Row, Rows, SecretInput, Section } from './primitives';

export function GeminiSection() {
  const { status, unreachable, models, msg, save, refreshModels, test, remove } =
    useGeminiSettings();

  const [apiKey, setApiKey] = useState('');
  const [reveal, setReveal] = useState(false);
  const [model, setModel] = useState('');

  // 未取得のうちは status.model を選択値として見せる
  const selectedModel = model || status?.model || '';

  const onSave = async () => {
    const ok = await save(apiKey.trim(), selectedModel);
    if (ok) {
      // 入力欄に平文を残さない
      setApiKey('');
      setReveal(false);
    }
  };

  return (
    <Section title="Gemini API">
      <Rows spaced>
        {unreachable ? (
          <Row label="バックエンド" value="未起動" tone="ng" />
        ) : !status ? (
          <Row label="状態" value="読み込んでいます…" tone="dim" />
        ) : (
          <>
            <Row
              label="APIキー"
              value={status.configured ? '登録済み' : '未登録'}
              tone={status.configured ? 'ok' : 'warn'}
            />
            <Row label="保存されている値" value={status.masked_key ?? '—'} tone="dim" mono />
            <Row
              label="取得元"
              value={
                status.source === 'env'
                  ? '環境変数'
                  : status.source === 'settings'
                    ? 'この画面で保存'
                    : '—'
              }
              tone="dim"
            />
            <Row label="使用するモデル" value={status.model} mono />
            <Row
              label="SDK (google-genai)"
              value={status.sdk_installed ? '利用可能' : '未インストール'}
              tone={status.sdk_installed ? 'ok' : 'ng'}
            />
          </>
        )}
      </Rows>

      <div className="field">
        <label htmlFor="gm-key">
          APIキー <span className="hint">— 保存すると暗号化され、以後は平文を取り出せません</span>
        </label>
        <SecretInput
          id="gm-key"
          value={apiKey}
          onChange={setApiKey}
          placeholder="AIza… で始まるキーを貼り付けてください"
          reveal={reveal}
          onToggleReveal={() => setReveal((v) => !v)}
        />
      </div>

      <div className="field">
        <label htmlFor="gm-model">モデル</label>
        <div className="input-row">
          <select id="gm-model" value={selectedModel} onChange={(e) => setModel(e.target.value)}>
            {models.length === 0 && <option value="">（未取得）</option>}
            {models.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
          <button type="button" onClick={() => void refreshModels()} disabled={!status?.configured}>
            一覧を取得
          </button>
        </div>
      </div>

      <div className="actions">
        <button type="button" className="primary" onClick={() => void onSave()}>
          保存する
        </button>
        <button type="button" onClick={() => void test()} disabled={!status?.configured}>
          疎通テスト
        </button>
        <button
          type="button"
          className="danger"
          onClick={() => void remove()}
          disabled={!status?.configured}
        >
          キーを削除
        </button>
      </div>
      <Message msg={msg} />

      <div className="note">
        キーは <code>backend/data/app.db</code> に Fernet で暗号化して保存されます。 復号鍵は{' '}
        <code>backend/.secret.key</code>（または環境変数 <code>TOKEN_ENCRYPTION_KEY</code>）です。
        画面に返るのはマスク済みの文字列だけで、平文を返すAPIは用意されていません。
      </div>
    </Section>
  );
}
