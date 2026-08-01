/**
 * コンソール共通の小さな部品。
 *
 * 設定タブと接続状態タブで同じ見た目の要素（状態行・ピル・メッセージ）が繰り返し出るため、
 * ここに集約する。ロジックは持たせず、見た目と入力の受け渡しだけを担う。
 */
import { useState } from 'react';
import type { ReactNode } from 'react';

/** 状態の色。色だけに情報を持たせないため、呼び出し側は必ず文字も渡すこと（§8.2） */
export type Tone = 'ok' | 'warn' | 'ng' | 'dim' | 'plain';

function toneClass(tone: Tone): string {
  return tone === 'plain' ? '' : ` ${tone}`;
}

/** 上部バーの状態ピル */
export function Pill({ text, tone = 'plain' }: { text: string; tone?: Tone }) {
  return <span className={'pill' + toneClass(tone)}>{text}</span>;
}

/** key-value の1行 */
export function Row({
  label,
  value,
  tone = 'plain',
  mono = false,
}: {
  label: string;
  value: ReactNode;
  tone?: Tone;
  mono?: boolean;
}) {
  return (
    <div className="row">
      <span>{label}</span>
      <span className={'val' + toneClass(tone) + (mono ? ' mono' : '')}>{value}</span>
    </div>
  );
}

/** Row をまとめる箱。spaced は下に余白を足す（入力欄が続くとき用） */
export function Rows({ children, spaced = false }: { children: ReactNode; spaced?: boolean }) {
  return <div className={'rows' + (spaced ? ' spaced' : '')}>{children}</div>;
}

/** カード1枚 */
export function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <div className="sec-title">{title}</div>
      {children}
    </section>
  );
}

/** 操作結果の表示。文言と色を1箇所で持つ */
export interface Msg {
  text: string;
  tone: 'ok' | 'ng' | 'plain';
}

export function Message({ msg }: { msg: Msg | null }) {
  if (!msg) return <div className="msg" />;
  return <div className={'msg' + (msg.tone === 'plain' ? '' : ` ${msg.tone}`)}>{msg.text}</div>;
}

/**
 * 秘密情報の入力欄。
 *
 * 既定は伏せ字で、ボタンで一時的に表示できる。保存後は呼び出し側が value を空にし、
 * あわせて reveal も戻す（入力欄に秘密を残さないため）。
 */
export function SecretInput({
  id,
  value,
  onChange,
  placeholder,
  reveal,
  onToggleReveal,
}: {
  id: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  reveal: boolean;
  onToggleReveal: () => void;
}) {
  return (
    <div className="input-row">
      <input
        id={id}
        type={reveal ? 'text' : 'password'}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        autoComplete="off"
        spellCheck={false}
      />
      <button type="button" onClick={onToggleReveal}>
        {reveal ? '隠す' : '表示'}
      </button>
    </div>
  );
}

/**
 * クリップボードへコピーするボタン付きの読み取り専用欄。
 *
 * navigator.clipboard は安全なコンテキスト（https か localhost）でしか使えないので、
 * 失敗したら選択状態にして手動コピーに委ねる。
 */
export function CopyLine({ value, onCopied }: { value: string; onCopied: (msg: Msg) => void }) {
  const [el, setEl] = useState<HTMLInputElement | null>(null);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      onCopied({ text: 'リダイレクトURIをコピーしました。', tone: 'ok' });
    } catch {
      el?.select();
      onCopied({ text: '選択しました。Ctrl+C でコピーしてください。', tone: 'plain' });
    }
  };

  return (
    <div className="copyline">
      <input ref={setEl} type="text" readOnly value={value} />
      <button type="button" onClick={copy}>
        コピー
      </button>
    </div>
  );
}

/**
 * 免責事項（docs/design.md §1.4）。
 * 任意のコピーではなく実装必須のUI要素なので、全画面の末尾に必ず置く。
 */
export function Disclaimer() {
  return (
    <div className="disclaimer">
      気象データと体調の関連は、体感を説明するための目安として扱っています。医学的な診断・治療の代替ではありません。
      体調不良が続く場合は医療機関を受診してください。
    </div>
  );
}
