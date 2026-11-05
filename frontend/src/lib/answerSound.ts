let audioContext: AudioContext | null = null;
let output: AudioNode | null = null;

function context() {
  const AudioContextClass = window.AudioContext;
  if (!AudioContextClass) return null;
  audioContext ??= new AudioContextClass();
  return audioContext;
}

/** A soft compressor keeps stacked notes from clipping on phone speakers. */
function destination(ctx: AudioContext) {
  if (!output) {
    const compressor = ctx.createDynamicsCompressor();
    compressor.threshold.setValueAtTime(-18, ctx.currentTime);
    compressor.ratio.setValueAtTime(4, ctx.currentTime);
    compressor.connect(ctx.destination);
    output = compressor;
  }
  return output;
}

interface Tone {
  frequency: number;
  startsAt: number;
  duration: number;
  gain: number;
  type?: OscillatorType;
  glideTo?: number;
  lowpass?: number;
}

function tone(ctx: AudioContext, { frequency, startsAt, duration, gain: level, type = "sine", glideTo, lowpass }: Tone) {
  const oscillator = ctx.createOscillator();
  const gain = ctx.createGain();
  oscillator.type = type;
  oscillator.frequency.setValueAtTime(frequency, startsAt);
  if (glideTo) oscillator.frequency.exponentialRampToValueAtTime(glideTo, startsAt + duration);
  gain.gain.setValueAtTime(0.0001, startsAt);
  gain.gain.exponentialRampToValueAtTime(level, startsAt + 0.012);
  gain.gain.exponentialRampToValueAtTime(0.0001, startsAt + duration);
  let source: AudioNode = oscillator;
  if (lowpass) {
    const filter = ctx.createBiquadFilter();
    filter.type = "lowpass";
    filter.frequency.setValueAtTime(lowpass, startsAt);
    oscillator.connect(filter);
    source = filter;
  }
  source.connect(gain);
  gain.connect(destination(ctx));
  oscillator.start(startsAt);
  oscillator.stop(startsAt + duration + 0.02);
}

/** A bell-like note: a warm fundamental with quieter overtones that fade first. */
function chime(ctx: AudioContext, frequency: number, startsAt: number, duration: number, gain: number) {
  tone(ctx, { frequency, startsAt, duration, gain, type: "triangle" });
  tone(ctx, { frequency: frequency * 2, startsAt, duration: duration * 0.6, gain: gain * 0.3 });
  tone(ctx, { frequency: frequency * 3.01, startsAt, duration: duration * 0.3, gain: gain * 0.1 });
}

function play(compose: (ctx: AudioContext, now: number) => void) {
  if (typeof window === "undefined") return;
  const ctx = context();
  if (!ctx) return;
  void ctx.resume().then(() => compose(ctx, ctx.currentTime)).catch(() => undefined);
}

export function playAnswerSound(correct: boolean) {
  play((ctx, now) => {
    if (correct) {
      // A quick rising sparkle that lands on the octave.
      [523.25, 659.25, 783.99].forEach((frequency, step) => chime(ctx, frequency, now + step * 0.06, 0.22, 0.07));
      chime(ctx, 1046.5, now + 0.18, 0.5, 0.09);
      return;
    }
    // A gentle, muffled "bwomp": noticeable without sounding like a buzzer.
    tone(ctx, { frequency: 330, startsAt: now, duration: 0.18, gain: 0.09, type: "triangle", glideTo: 300, lowpass: 900 });
    tone(ctx, { frequency: 262, startsAt: now + 0.14, duration: 0.34, gain: 0.1, type: "triangle", glideTo: 220, lowpass: 700 });
  });
}

/** The finish-screen jingle: a full fanfare for a perfect score, a warm chord otherwise. */
export function playFinishSound(perfect: boolean) {
  play((ctx, now) => {
    if (perfect) {
      [523.25, 659.25, 783.99, 1046.5].forEach((frequency, step) => chime(ctx, frequency, now + step * 0.1, 0.3, 0.07));
      [1046.5, 1318.51, 1567.98].forEach(frequency => chime(ctx, frequency, now + 0.46, 0.9, 0.05));
      return;
    }
    [392, 523.25, 659.25].forEach((frequency, step) => chime(ctx, frequency, now + step * 0.12, 0.5, 0.06));
    chime(ctx, 783.99, now + 0.36, 0.7, 0.05);
  });
}
