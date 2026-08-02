/**
 * 全肯定ヒーリング・ダイアログ
 *
 * ユーザーの入力テキストをバックエンド POST /api/v1/reflection へ送り、
 * Gemini（gemini.py）で生成された全肯定の応答を表示する。
 * バックエンド側は既存の reflection.py → gemini.generate() をそのまま使う。
 *
 * 通信は api/client.ts に寄せてある。ここで fetch を直接書かないこと
 * （client.ts 冒頭の方針。以前はここに独自の API_BASE があり、client.ts の
 *   既定値フォールバックが効かない状態になっていた）。
 */
import { useCallback, useState } from 'react';
import './healing.css';
import { postReflection, ApiError } from './api/client';

/** 生成に失敗したときの定型文（バックエンド側と同じ） */
const FALLBACK_REPLY =
    '無事に一日を終えられただけで満点です。気圧がこれだけ動いた日に、それ以上は誰にもできません。';

/**
 * 入力欄は決して塞がないこと。
 *
 * 上限に達していても /reflection は 200 で受け取り、内容を保存したうえで定型の肯定を返す
 * （docs/design.md §4.7 / §4.8）。「書くことはいつでもできる」がこの機能の前提であり、
 * 入力自体を disabled にすると、バックエンドが避けている「吐き出したのに無視された」
 * 体験をフロント側で作り直してしまう。
 * 2026-08-02 に一度 disabled にして実際に書けなくなったため、その記録として残す。
 */
export const Healing = () => {
    const [reply, setReply] = useState<string | null>(null);
    const [inputText, setInputText] = useState('');
    const [isSending, setIsSending] = useState(false);

    const sendMessage = useCallback(async (userText: string) => {
        if (!userText.trim() || isSending) return;

        setIsSending(true);
        setReply(null); // 通信中は前の応答を消す

        try {
            const res = await postReflection(userText);
            setReply(res.reply);

            // fallback=true は Gemini を通していない。理由は2つあり、対処が正反対:
            //   limit -> 仕様どおり。次のフェーズ（0/6/12/18時）まで待てば戻る。直すものは無い
            //   error -> 設定か通信の異常。uvicorn のログに原因が出ている
            // 利用者向けの文言は変えず、切り分けのためにログにだけ残す。
            // 画面に「上限」と出してはいけない（§1.2 / §4.8）
            if (res.fallback) {
                console.warn(
                    res.reason === 'limit'
                        ? '[reflection] このフェーズの対話回数に達しているためGeminiを呼んでいません（仕様どおり。次のフェーズまで待てば戻ります）'
                        : '[reflection] Gemini生成に失敗しました。uvicorn のログに原因が出ています',
                    { reason: res.reason, model: res.model },
                );
            }
        } catch (e) {
            // 409(キー未設定) / 502(Gemini障害) / ネットワーク断 を同じ見た目にしない。
            // 画面の文言は据え置き、原因だけログへ出す
            if (e instanceof ApiError) {
                console.warn('[reflection] HTTPエラー', e.status, e.message);
            } else {
                console.warn('[reflection] 通信に失敗しました', e);
            }
            setReply(FALLBACK_REPLY);
        } finally {
            setIsSending(false);
        }
    }, [isSending]);

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        if (!inputText.trim()) return;
        sendMessage(inputText.trim());
        setInputText(''); // 送信時にテキストをクリア
    };

    return (
        <div className="widget-box" style={{ borderRadius: '20px' }}>
            <div className="widget-header">
                <h3 className="widget-title">夜の吐き出し</h3>
                <span className="pill">ヒーリング</span>
            </div>

            <p className="widget-note" style={{ marginBottom: '1.25rem' }}>
                今日うまくいかなかったことを、テキストで話しかけてください。全肯定で受け止めます。
                <br />
                入力内容は Gemini へ送信されます。
            </p>

            {/* 返答エリア（応答がある時だけ表示） */}
            {reply && (
                <div className="healing-messages" style={{ maxHeight: 'none', padding: '0 0 1rem' }}>
                    <div className="healing-bubble assistant">
                        <div className="healing-bubble-text">{reply}</div>
                    </div>
                </div>
            )}

            {/* 入力フォーム */}
            <form className="healing-input-form" onSubmit={handleSubmit}>
                <input
                    type="text"
                    className="healing-input"
                    placeholder="ここに気持ちを書いてください…"
                    value={inputText}
                    onChange={(e) => setInputText(e.target.value)}
                    disabled={isSending}
                />
                <button
                    type="submit"
                    className="healing-send"
                    disabled={isSending || !inputText.trim()}
                >
                    {isSending ? '…' : '送信'}
                </button>
            </form>
        </div>
    );
};
