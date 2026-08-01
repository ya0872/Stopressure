/**
 * Google連携の実データ表示。
 *
 * 値が null のときは「—（未取得）」と出す。0 と混同させないため。
 * 0 は「計測して負荷がなかった」、null は「そもそも測れていない」を意味する。
 */
import { LOGIN_URL, unlinkGoogle } from '../api';
import type { ContextResponse, GoogleStatus } from '../types';
import { Row, Rows, Section } from './primitives';

const yesNo = (b: boolean) => (b ? 'はい' : 'いいえ');

/** null（未取得）と 0（負荷なし）を区別して表示する */
function amount(v: number | null, unit: string): string {
  return v === null || v === undefined ? '—（未取得）' : `${v}${unit}`;
}

export function LiveGoogle({
  status,
  context,
  onReload,
  onOpenSettings,
}: {
  status: GoogleStatus | null;
  context: ContextResponse | null;
  onReload: () => void;
  onOpenSettings: () => void;
}) {
  const unlink = async () => {
    await unlinkGoogle();
    onReload();
  };

  return (
    <Section title="Google連携（カレンダー / ToDo / メール）">
      {!status || !context ? (
        <div className="empty">—</div>
      ) : (
        <>
          <Rows>
            <Row label="OAuthクライアント登録" value={yesNo(status.configured)} />
            <Row label="アカウント連携" value={yesNo(status.linked)} />
            <Row label="予算への反映" value={yesNo(status.use_context)} />
            <Row label="拘束時間" value={amount(context.busy_hours, ' 時間')} />
            <Row label="要対応メール" value={amount(context.actionable_mail_count, ' 件')} />
            <Row
              label="ToDo（期限が今日以前）"
              value={amount(context.open_task_count, ' 件')}
            />
            {context.warnings.map((w) => (
              <Row key={w} label="警告" value={w} tone="dim" />
            ))}
          </Rows>

          <div className="scopes">
            要求する権限（すべて読み取り専用）
            {status.scopes.map((s) => (
              <code key={s}>{s.split('/auth/').pop()}</code>
            ))}
          </div>

          <div className="actions">
            <button
              type="button"
              className="slim"
              disabled={!status.configured}
              onClick={() => {
                window.location.href = LOGIN_URL;
              }}
            >
              Googleと連携する
            </button>
            <button
              type="button"
              className="slim"
              disabled={!status.linked}
              onClick={() => void unlink()}
            >
              連携を解除
            </button>
            <button type="button" className="slim" onClick={onOpenSettings}>
              設定を開く
            </button>
          </div>
        </>
      )}

      <div className="note">
        取得するのは「拘束時間」「未読の重要メール件数」「期限が今日以前のToDo件数」だけです。
        予定のタイトル、メールの件名や本文は取得しません。
        <br />
        期限が設定されていないToDoは件数に入りません（「いつかやる」は今日の負荷ではないため:
        docs/design.md §7.2.1）。
      </div>
    </Section>
  );
}
