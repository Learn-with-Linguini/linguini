"""The edit decision list. Writes timeline.json for the score, tracker and overlay.

Shot lengths follow the music: three beats, then two, one, and a half beat, so
the cuts accelerate with the piano. `box` is the object at the in-point as
fractions of the source frame (x0, y0, x1, y1); `track` follows it with OpenCV, or is
a second box the frame eases to when the object moves in a way a tracker loses.
"""
import json

BPM = 100
BEAT = 60 / BPM

# (section, beats, mixkit id, in-point s, word, gloss, box, track[, zoom, focus])
# Every clip is under the Mixkit Stock Video *Free* License (commercial use,
# ads and YouTube allowed). Restricted-licence clips must not be used here.
SHOTS = [
    ("act1", 3, 4992, 1.0, "el café", "coffee", (0.379, 0.222, 0.667, 0.73), True),
    ("act1", 3, 2846, 5.5, "la lluvia", "rain", (0.25, 0.3, 0.5, 0.8), False),
    ("act1", 3, 1552, 5.1, "el perro", "dog", (0.25, 0.04, 0.74, 0.86), True),
    ("act1", 3, 4348, 9.2, "la bicicleta", "bicycle", (0.1, 0.44, 0.5, 0.95), False),
    ("act1", 3, 995, 5.3, "el pan", "bread", (0.46, 0.09, 0.75, 0.56), True),
    ("act2a", 2, 42945, 6.1, "la lima", "lime", (0.39, 0.36, 0.74, 0.97), True),
    ("act2a", 2, 22732, 2.3, "el gato", "cat", (0.23, 0.17, 0.53, 0.67), True),
    ("act2a", 2, 1724, 3.2, "el libro", "book", (0.125, 0.28, 0.84, 0.85), True),
    ("act2a", 2, 4477, 4.4, "el sol", "sun", (0.444, 0.14, 0.61, 0.4), True),
    ("act2b", 1, 52407, 4.3, "el vino", "wine", (0.34, 0.03, 0.67, 0.97), True),
    ("act2b", 1, 4305, 15.9, "la luna", "moon", (0.277, 0.36, 0.423, 0.64), True, 2.1, (0.35, 0.47)),
    ("act2b", 1, 28897, 2.4, "el reloj", "clock", (0.327, 0.21, 0.66, 0.8), True),
    ("act2b", 1, 3461, 3.2, "la vela", "candle", (0.5, 0.52, 0.74, 0.82), True, 1.25, (0.6, 0.55)),
    ("act2b", 1, 2560, 4.3, "el pájaro", "bird", (0.344, 0.23, 0.583, 0.8), True),
    ("act2b", 1, 44161, 3.3, "la guitarra", "guitar", (0.22, 0.34, 0.46, 0.83), True),
    ("act2c", 0.5, 41859, 3.3, "le café", "coffee", (0.22, 0.24, 0.74, 0.83), True),
    ("act2c", 0.5, 10435, 1.0, "l’orange", "orange", (0.375, 0.22, 0.72, 0.83), True),
    ("act2c", 0.5, 4742, 2.5, "les fleurs", "flowers", (0.22, 0.35, 0.56, 0.74), False),
    ("act2c", 0.5, 40672, 3.5, "le métro", "metro", (0.2, 0.12, 0.8, 0.82), False),
    ("act2c", 0.5, 43922, 18.3, "la tartine", "toast", (0.2, 0.05, 0.58, 0.72), True),
    ("act2c", 0.5, 4600, 2.8, "la rue", "street", (0.4, 0.35, 0.62, 0.95), False),
    ("act2c", 0.5, 1711, 4.2, "le téléphone", "phone", (0.5, 0.41, 0.79, 0.6), True),
    ("act2c", 0.5, 18308, 14.6, "le cœur", "heart", (0.3, 0.15, 0.6, 0.5), False),
    ("final", 3, 2434, 4.2, "la pasta", "pasta", (0.27, 0.2, 0.64, 0.74), (0.2, 0.16, 0.7, 0.76)),
]

INTRO = 2 * BEAT
t = INTRO
shots = []
for sec, beats, mid, tin, word, gloss, box, track, *crop in SHOTS:
    d = beats * BEAT
    shot = dict(section=sec, start=round(t, 4), dur=round(d, 4), clip=mid, tin=tin,
                word=word, gloss=gloss, box=box, track=track is True)
    if crop:
        shot["zoom"], shot["focus"] = crop  # punch in on a small subject
    if isinstance(track, tuple):
        shot["box_end"] = track  # hand-keyed: the box eases from box to box_end
    shots.append(shot)
    t += d
cut = t
timeline = dict(
    bpm=BPM,
    beat=BEAT,
    intro_note=0.3,
    shots=shots,
    headline=[
        dict(text="Your day", start=shots[5]["start"], end=shots[9]["start"]),
        dict(text="is the", start=shots[9]["start"], end=shots[15]["start"]),
        dict(text="lesson.", start=shots[15]["start"], end=cut),
    ],
    cut=round(cut, 4),
    logo_chord=round(cut + BEAT, 4),
    tagline=round(cut + 4 * BEAT, 4),
    ph_line=round(cut + 7 * BEAT, 4),
    fade_out=round(cut + 10.5 * BEAT, 4),
    end=round(cut + 13 * BEAT, 4),
)
json.dump(timeline, open("timeline.json", "w"), ensure_ascii=False, indent=1)
print(f"{len(shots)} shots, cut at {cut:.2f}s, end {timeline['end']:.2f}s")
