import { useState, useRef, useEffect } from 'react';

interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
}

const CONTROLLER = 'http://127.0.0.1:8765';

function timestamp(): string {
  return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export default function ChatPanel() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome',
      role: 'system',
      content:
        'GHOST retrieval runs locally against your corpus. Enter a query to call POST /v1/retrieve ' +
        '(hybrid BM25 + dense). No data leaves your machine.',
      timestamp: timestamp(),
    },
  ]);
  const [input, setInput]       = useState('');
  const [loading, setLoading]   = useState(false);
  const [presetId, setPresetId] = useState<string | ''>('');
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const send = async () => {
    const text = input.trim();
    if (!text || loading) return;
    setInput('');

    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content: text,
      timestamp: timestamp(),
    };
    setMessages((m) => [...m, userMsg]);
    setLoading(true);

    try {
      const body: Record<string, string | number> = { query: text, limit: 8 };
      if (presetId) body.preset_id = presetId;
      const response = await fetch(`${CONTROLLER}/v1/retrieve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      if (!response.ok) {
        throw new Error(`API returned ${response.status}`);
      }

      const data = (await response.json()) as {
        decision_id?: string;
        chunks?: unknown[];
        explain?: Record<string, unknown>;
      };
      const result =
        JSON.stringify(
          {
            decision_id: data.decision_id,
            chunks: data.chunks,
            explain: data.explain,
          },
          null,
          2
        );

      const assistantMsg: Message = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: result,
        timestamp: timestamp(),
      };
      setMessages((m) => [...m, assistantMsg]);
    } catch (err) {
      const errMsg: Message = {
        id: crypto.randomUUID(),
        role: 'system',
        content:
          `Could not reach the GHOST API or retrieval failed. Is the engine running on 127.0.0.1:8765? ` +
          `Error: ${String(err)}`,
        timestamp: timestamp(),
      };
      setMessages((m) => [...m, errMsg]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="panel" style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div className="panel-header">
        <span className="panel-title">Retrieve</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>preset_id</span>
          <input
            value={presetId}
            onChange={(e) => setPresetId(e.target.value)}
            placeholder="optional"
            style={{
              background: 'var(--bg-tertiary)',
              border: '1px solid var(--border-dim)',
              color: 'var(--text-primary)',
              padding: '3px 6px',
              borderRadius: 4,
              fontSize: 11,
              fontFamily: 'var(--font-mono)',
              width: 120,
            }}
          />
        </div>
      </div>

      {/* Message thread */}
      <div style={{
        flex: 1,
        overflowY: 'auto',
        padding: '12px 16px',
        display: 'flex',
        flexDirection: 'column',
        gap: 12,
      }}>
        {messages.map((msg) => (
          <div
            key={msg.id}
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: msg.role === 'user' ? 'flex-end' : 'flex-start',
            }}
          >
            <div style={{
              maxWidth: '80%',
              padding: '8px 12px',
              borderRadius: 8,
              fontSize: 13,
              lineHeight: 1.6,
              background:
                msg.role === 'user'      ? 'var(--accent-blue)'  :
                msg.role === 'assistant' ? 'var(--bg-tertiary)'  :
                                           'var(--bg-secondary)',
              color:
                msg.role === 'user'      ? '#fff'                       :
                msg.role === 'assistant' ? 'var(--text-primary)'        :
                                           'var(--text-muted)',
              border: msg.role === 'system' ? '1px solid var(--border-dim)' : 'none',
              fontStyle: msg.role === 'system' ? 'italic' : 'normal',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
            }}>
              {msg.content}
            </div>
            <span style={{
              fontSize: 9,
              color: 'var(--text-muted)',
              marginTop: 3,
              fontFamily: 'var(--font-mono)',
            }}>
              {msg.role !== 'system' && (msg.role === 'user' ? 'you' : 'ghost')} {msg.timestamp}
            </span>
          </div>
        ))}

        {loading && (
          <div style={{ display: 'flex', alignItems: 'flex-start' }}>
            <div style={{
              padding: '8px 14px',
              borderRadius: 8,
              background: 'var(--bg-tertiary)',
              fontSize: 13,
              color: 'var(--text-muted)',
              fontStyle: 'italic',
            }}>
              Retrieving…
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input bar */}
      <div style={{
        padding: '10px 16px',
        borderTop: '1px solid var(--border-color)',
        display: 'flex',
        gap: 8,
      }}>
        <input
          type="text"
          placeholder="Search your corpus — hybrid retrieval via /v1/retrieve"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && send()}
          disabled={loading}
          style={{
            flex: 1,
            background: 'var(--bg-tertiary)',
            border: '1px solid var(--border-dim)',
            color: 'var(--text-primary)',
            padding: '8px 12px',
            borderRadius: 6,
            fontSize: 13,
            fontFamily: 'inherit',
            outline: 'none',
          }}
        />
        <button
          className="console-send-btn"
          onClick={send}
          disabled={loading || !input.trim()}
          style={{ padding: '8px 18px', fontSize: 12 }}
        >
          {loading ? '…' : 'Send'}
        </button>
      </div>
    </div>
  );
}

