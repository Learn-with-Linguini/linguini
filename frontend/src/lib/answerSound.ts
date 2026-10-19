let audioContext: AudioContext | null = null;

function context() {
  const AudioContextClass = window.AudioContext;
  if (!AudioContextClass) return null;
  audioContext ??= new AudioContextClass();
  return audioContext;
}

function note(ctx: AudioContext, frequency: number, startsAt: number, duration: number, gainValue: number) {
  const oscillator = ctx.createOscillator();
  const gain = ctx.createGain();
  oscillator.type = "sine";
  oscillator.frequency.setValueAtTime(frequency, startsAt);
  gain.gain.setValueAtTime(0.0001, startsAt);
  gain.gain.exponentialRampToValueAtTime(gainValue, startsAt + 0.015);
  gain.gain.exponentialRampToValueAtTime(0.0001, startsAt + duration);
  oscillator.connect(gain);
  gain.connect(ctx.destination);
  oscillator.start(startsAt);
  oscillator.stop(startsAt + duration);
}

export function playAnswerSound(correct: boolean) {
  if (typeof window === "undefined") return;
  const ctx = context();
  if (!ctx) return;
  void ctx.resume().then(() => {
    const now = ctx.currentTime;
    if (correct) {
      note(ctx, 523.25, now, 0.16, 0.08);
      note(ctx, 659.25, now + 0.12, 0.2, 0.09);
      return;
    }
    note(ctx, 246.94, now, 0.18, 0.07);
    note(ctx, 196, now + 0.11, 0.24, 0.075);
  }).catch(() => undefined);
}
