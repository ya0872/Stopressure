/**
 * 全肯定ヒーリング・ダイアログ
 *
 * ユーザーの入力テキストをバックエンド POST /api/v1/reflection へ送り、
 * Gemini（gemini.py）で生成された全肯定の応答を表示する。
 * バックエンド側は既存の reflection.py → gemini.generate() をそのまま使う。
 */
import { useCallback, useState } from 'react';
import './healing.css';

const API_BASE = import.meta.env.VITE_API_BASE;

/** 生成に失敗したときの定型文（バックエンド側と同じ） */
const FALLBACK_REPLY =
    '無事に一日を終えられただけで満点です。気圧がこれだけ動いた日に、それ以上は誰にもできません。';

export const Healing = () => {
    const [reply, setReply] = useState<string | null>(null);
    const [inputText, setInputText] = useState('');
    const [isSending, setIsSending] = useState(false);

    const sendMessage = useCallback(async (userText: string) => {
        if (!userText.trim() || isSending) return;

        setIsSending(true);
        setReply(null); // 通信中は前の応答を消す

        try {
            const res = await fetch(`${API_BASE}/reflection`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: userText }),
            });

            let responseText: string;
            if (res.ok) {
                const json = await res.json();
                responseText = json.reply;
            } else {
                responseText = FALLBACK_REPLY;
            }

            setReply(responseText);
        } catch {
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
