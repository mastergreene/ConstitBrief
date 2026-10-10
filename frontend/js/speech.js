// Dictation via the Web Speech API (Chrome/Edge/Android, Safari 14.1+). Australian English.
export function createDictation({ onText, onState }) {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) return null;
  const rec = new SR();
  rec.lang = 'en-AU';
  rec.continuous = true;
  rec.interimResults = false;
  let active = false;
  rec.onresult = (e) => {
    for (let i = e.resultIndex; i < e.results.length; i += 1) {
      if (e.results[i].isFinal) onText(e.results[i][0].transcript.trim());
    }
  };
  rec.onend = () => {
    if (active) { try { rec.start(); return; } catch { /* fall through */ } }
    active = false; onState(false);
  };
  rec.onerror = (e) => {
    if (e.error === 'not-allowed' || e.error === 'service-not-allowed') { active = false; onState(false, 'Microphone permission denied'); }
  };
  return {
    toggle() {
      if (active) { active = false; rec.stop(); onState(false); return; }
      try { rec.start(); active = true; onState(true); } catch { /* already started */ }
    },
    stop() { if (active) { active = false; rec.stop(); onState(false); } },
  };
}
