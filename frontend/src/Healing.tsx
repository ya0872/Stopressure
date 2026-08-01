/**
 * 全肯定ヒーリング・ダイアログ
 *
 * ユーザーの入力テキストをバックエンド POST /api/v1/reflection へ送り、
 * Gemini（gemini.py）で生成された全肯定の応答を表示する。
 * バックエンド側は既存の reflection.py → gemini.generate() をそのまま使う。
 */
import { useCallback, useState } from 'react';

const API_BASE = import.meta.env.VITE_API_BASE;

/** 生成に失敗したときの定型文（バックエンド側と同じ） */
const FALLBACK_REPLY =
    '無事に一日を終えられただけで満点です。気圧がこれだけ動いた日に、それ以上は誰にもできません。';

interface Message {
    role: 'user' | 'assistant';
    text: string;
}

export const Healing = () => {
    const [messages, setMessages] = useState<Message[]>([]);
    const [inputText, setInputText] = useState('');
    const [isSending, setIsSending] = useState(false);

    const sendMessage = useCallback(async (userText: string) => {
        if (!userText.trim() || isSending) return;

        // ユーザーの発言を追加
        setMessages((prev) => [...prev, { role: 'user', text: userText }]);
        setIsSending(true);

        try {
            const res = await fetch(`${API_BASE}/reflection`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: userText }),
            });

            let reply: string;
            if (res.ok) {
                const json = await res.json();
                reply = json.reply;
            } else {
                reply = FALLBACK_REPLY;
            }

            setMessages((prev) => [...prev, { role: 'assistant', text: reply }]);
        } catch {
            setMessages((prev) => [...prev, { role: 'assistant', text: FALLBACK_REPLY }]);
        } finally {
            setIsSending(false);
        }
    }, [isSending]);

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        if (!inputText.trim()) return;
        sendMessage(inputText.trim());
        setInputText('');
    };

    return (
        <section>
            <div className="sec-title">今日、うまくいかなかったことを話してください</div>

            <p className="widget-note" style={{ marginBottom: '1.25rem' }}>
                テキストで話しかけてください。全肯定で受け止めます。
                <br />
                入力内容は Gemini へ送信されます。
            </p>

            {/* メッセージ一覧 */}
            <div className="healing-messages">
                {messages.length === 0 && (
                    <div className="healing-empty">
                        まだ何も話されていません。
                        <br />
                        下の入力欄からどうぞ。
                    </div>
                )}
                {messages.map((msg, i) => (
                    <div key={i} className={`healing-bubble ${msg.role}`}>
                        <div className="healing-bubble-text">{msg.text}</div>
                    </div>
                ))}
            </div>

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
        </section>
    );
};
