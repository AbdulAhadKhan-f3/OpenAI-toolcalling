import { useRef, useState } from "react";

// Runs in the browser's audio thread: resamples the microphone to 16 kHz and sends 16-bit PCM in 0.25 s pieces.
const WORKLET = `
class Pcm16Downsampler extends AudioWorkletProcessor {
  constructor() {
    super();
    this.ratio = sampleRate / 16000;
    this.pos = 0;
    this.carry = new Float32Array(0);
    this.buf = [];
  }
  process(inputs) {
    const ch = inputs[0][0];
    if (!ch) return true;
    const data = new Float32Array(this.carry.length + ch.length);
    data.set(this.carry);
    data.set(ch, this.carry.length);
    let pos = this.pos;
    while (pos + 1 < data.length) {
      const i = Math.floor(pos), frac = pos - i;
      this.buf.push(data[i] * (1 - frac) + data[i + 1] * frac);
      pos += this.ratio;
    }
    const keep = Math.floor(pos);
    this.carry = data.slice(keep);
    this.pos = pos - keep;
    if (this.buf.length >= 4000) {
      const pcm = new Int16Array(this.buf.length);
      for (let i = 0; i < pcm.length; i++) pcm[i] = Math.max(-1, Math.min(1, this.buf[i])) * 32767;
      this.port.postMessage(pcm.buffer, [pcm.buffer]);
      this.buf = [];
    }
    return true;
  }
}
registerProcessor("pcm16-downsampler", Pcm16Downsampler);
`;

export function LiveRecorder({ onTranscript, onStreamUpdate, onStatusChange }) {
  const [status, setStatus] = useState("idle"); // idle | loading | recording | finishing
  const [lines, setLines] = useState([]);
  const [swapped, setSwapped] = useState(false);
  const [error, setError] = useState("");
  const wsRef = useRef(null);
  const micRef = useRef(null);
  const statusRef = useRef("idle");
  const linesRef = useRef([]);

  const getSpeakerLabel = (speaker, isSwapped) => {
    if (isSwapped) {
      if (speaker === "Doctor") return "Patient";
      if (speaker === "Patient") return "Doctor";
    }
    return speaker || "Doctor";
  };

  const formatLinesToText = (linesArr, isSwapped) =>
    linesArr
      .filter((l) => l && l.text)
      .map((l) => `${getSpeakerLabel(l.speaker, isSwapped)}: ${l.text}`)
      .join("\n");

  const label = (l) => getSpeakerLabel(l.speaker, swapped);
  const asText = () => formatLinesToText(linesRef.current, swapped);

  const updateStatus = (newStatus) => {
    statusRef.current = newStatus;
    setStatus(newStatus);
    onStatusChange?.(newStatus);
  };

  function stopMic() {
    micRef.current?.stream.getTracks().forEach((t) => t.stop());
    micRef.current?.ctx.close().catch(() => { });
    micRef.current = null;
  }

  function fail(message) {
    setError(message);
    stopMic();
    wsRef.current?.close();
    updateStatus("idle");
  }

  async function startMic(ws) {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
    });
    const ctx = new AudioContext();
    await ctx.audioWorklet.addModule(URL.createObjectURL(new Blob([WORKLET], { type: "application/javascript" })));
    const node = new AudioWorkletNode(ctx, "pcm16-downsampler");
    node.port.onmessage = (e) => ws.readyState === WebSocket.OPEN && ws.send(e.data);
    ctx.createMediaStreamSource(stream).connect(node);
    micRef.current = { stream, ctx };
    updateStatus("recording");
  }

  function start() {
    setError("");
    setLines([]);
    setSwapped(false);
    linesRef.current = [];
    updateStatus("loading");

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.hostname || "127.0.0.1";
    const port = window.location.port;
    const urls = [];
    if (port && port !== "8000") {
      urls.push(`${protocol}//${window.location.host}/ws/transcribe`);
    }
    urls.push(`${protocol}//${host}:8000/ws/transcribe`);
    if (host === "localhost") {
      urls.push(`${protocol}//127.0.0.1:8000/ws/transcribe`);
    }

    let urlIndex = 0;
    let ws = null;
    let opened = false;

    function connect() {
      if (urlIndex >= urls.length) {
        fail("Could not reach the live transcription server. Is the backend running on port 8000?");
        return;
      }

      const currentUrl = urls[urlIndex];
      ws = new WebSocket(currentUrl);
      wsRef.current = ws;
      opened = false;

      ws.onopen = () => {
        opened = true;
      };

      ws.onmessage = async (event) => {
        const msg = JSON.parse(event.data);
        if (msg.type === "ready") {
          try {
            await startMic(ws);
          } catch (e) {
            fail(`Microphone problem: ${e.message}`);
          }
        } else if (msg.type === "line") {
          setLines((prev) => {
            const next = [...prev];
            next[msg.index] = msg;
            linesRef.current = next;
            const liveText = formatLinesToText(next, swapped);
            onStreamUpdate?.(liveText);
            return next;
          });
        } else if (msg.type === "final") {
          setLines(msg.lines);
          linesRef.current = msg.lines;
          updateStatus("idle");
          ws.close();
          const finalText = formatLinesToText(msg.lines, swapped);
          onStreamUpdate?.(finalText);
          onTranscript?.(finalText);
        } else if (msg.type === "error") {
          fail(msg.message);
        }
      };

      ws.onerror = () => {
        if (!opened && urlIndex + 1 < urls.length) {
          urlIndex++;
          connect();
          return;
        }
        fail("Could not reach the live transcription server. Is the backend running on port 8000?");
      };

      ws.onclose = () => {
        if (statusRef.current === "finishing") {
          updateStatus("idle");
        }
      };
    }

    connect();
  }

  function stop() {
    updateStatus("finishing");
    stopMic();
    // Send stop message and ensure WebSocket is closed after a timeout
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send("stop");
      // Safety timeout: if the server doesn't respond, force state reset
      setTimeout(() => {
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
          wsRef.current.close();
        }
      }, 5000);
    } else {
      updateStatus("idle");
    }
  }

  function handleSwap() {
    const nextSwapped = !swapped;
    setSwapped(nextSwapped);
    const updated = formatLinesToText(linesRef.current, nextSwapped);
    onStreamUpdate?.(updated);
    onTranscript?.(updated);
  }

  return (
    <div className="live-recorder">
      <div className="live-recorder-inner">
        <div className="live-recorder-info">
          <div className="live-recorder-icon">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
              <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
              <line x1="12" y1="19" x2="12" y2="23"/>
              <line x1="8" y1="23" x2="16" y2="23"/>
            </svg>
          </div>
          <div>
            <div className="live-recorder-label">Live Recording</div>
            <div className="live-recorder-sub">Stream mic audio directly to transcript</div>
          </div>
        </div>

        <div className="live-recorder-controls">
          {status === "idle" && (
            <button className="btn-record-start" onClick={start}>
              <span className="record-dot" />
              Start Recording
            </button>
          )}
          {status === "loading" && (
            <span className="live-status-chip loading">
              <span className="spinner-dot" /> Loading models…
            </span>
          )}
          {status === "recording" && (
            <button className="btn-record-stop" onClick={stop}>
              <span className="record-square" />
              Stop Recording
            </button>
          )}
          {status === "finishing" && (
            <span className="live-status-chip loading">
              <span className="spinner-dot" /> Finishing…
            </span>
          )}
        </div>
      </div>

      {error && <div className="status-toast error">{error}</div>}

      {lines.length > 0 && (
        <div className="quick-actions-bar" style={{ marginTop: 8 }}>
          <button className="btn-secondary" onClick={handleSwap}>⇄ Swap Doctor / Patient</button>
          <button className="btn-secondary" onClick={() => onTranscript?.(asText())}>Sync to Transcript</button>
        </div>
      )}
    </div>
  );
}
