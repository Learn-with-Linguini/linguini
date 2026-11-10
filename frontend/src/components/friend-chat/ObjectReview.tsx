import { useEffect, useRef, useState } from "react";
import { Button, Card, ComboBox } from "../ui";
import { CloseIcon, MarkerIcon } from "../icons";
import { ScenePhoto } from "../ScenePhoto";
import { chatDraftKey, chatRoundIntent, getChatPhoto, readChatDraft, saveChatDraft } from "../../lib/friendChats";
import type { ChatRound, ChatSnapshot } from "../../lib/friendChats";
import { sceneReviewPanels, type SceneReviewPanel } from "../../lib/sceneReview";
import { humanizeTerm } from "../../lib/termLabel";
import { trackAction } from "../../lib/analytics";
import type { LanguageItem, SceneSummary } from "../../data/types";
import type { ChatAction } from "./TargetPicker";

// The same review as practice scene analysis, using the friend clue builder's fact names.
const ATTRIBUTE_TYPES = ["color", "size", "shape", "material", "pattern", "state"] as const;
const RELATIONS = [
  ["left_of", "Left of"], ["right_of", "Right of"], ["above", "Above"], ["below", "Below"],
  ["on", "On"], ["under", "Under"], ["inside", "Inside"], ["in_front_of", "In front of"],
  ["behind", "Behind"], ["next_to", "Next to"], ["near", "Near"],
] as const;
const RELATION_CHOICES = RELATIONS.map(([value, label]) => ({ value, label }));
const relationLabel = (value: string) => RELATIONS.find(([key]) => key === value)?.[1] ?? humanizeTerm(value);

type Point = { x: number; y: number };
type Added = Point & { key: string; label: string };
type Relation = { key: string; subjectObjectKey: string; relation: string; referenceObjectKey: string };
interface ReviewDraft {
  removed: string[]; added: Added[]; positions: Record<string, Point>;
  attributes: Record<string, Record<string, string>>; relations: Relation[];
}

function usePhotoUrl(chatId: string, roundId: string) {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController(); let objectUrl: string | null = null;
    void getChatPhoto(chatId, roundId, controller.signal).then(blob => {
      objectUrl = URL.createObjectURL(blob); if (!controller.signal.aborted) setUrl(objectUrl);
    }).catch(() => undefined);
    return () => { controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [chatId, roundId]);
  return url;
}

const smooth = (): ScrollBehavior => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";

export function ObjectReview({ chat, round, disabled, command }: { chat: ChatSnapshot; round: ChatRound; disabled: boolean; command: ChatAction }) {
  const detected = round.reviewObjects ?? [];
  const key = chatDraftKey(chat.meId, chat.id, `${round.id}:review`);
  const [draft, setDraft] = useState<ReviewDraft>(() => readChatDraft(key, {
    removed: [], added: [], positions: {}, relations: round.reviewRelations ?? [],
    attributes: Object.fromEntries(detected.map(item => [item.key, Object.fromEntries(Object.entries(item.attributes ?? {})
      .map(([type, value]) => [type === "colour" ? "color" : type, value]).filter(([type]) => (ATTRIBUTE_TYPES as readonly string[]).includes(type)))])),
  }));
  const [explicitlyRemoved, setExplicitlyRemoved] = useState<string[]>([]);
  const [panel, setPanel] = useState<SceneReviewPanel>("objects");
  const [label, setLabel] = useState("");
  const [pending, setPending] = useState<{ label: string; key?: string } | null>(null);
  const [moving, setMoving] = useState<string | null>(null);
  const [attributeKey, setAttributeKey] = useState(detected[0]?.key ?? "");
  const [subject, setSubject] = useState(""); const [relationText, setRelationText] = useState(""); const [reference, setReference] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const photoRef = useRef<HTMLDivElement>(null);
  const url = usePhotoUrl(chat.id, round.id);
  useEffect(() => { saveChatDraft(key, draft); }, [key, draft]);
  useEffect(() => {
    if (!pending && !moving) return;
    const cancelOutside = (event: PointerEvent) => {
      if (photoRef.current?.contains(event.target as Node)) return;
      setPending(null); setMoving(null);
    };
    document.addEventListener("pointerdown", cancelOutside);
    return () => document.removeEventListener("pointerdown", cancelOutside);
  }, [moving, pending]);

  const busy = disabled || saving;
  const kept = detected.filter(item => !draft.removed.includes(item.key))
    .map((item, index) => ({ ...item, ...(draft.positions[item.key] ?? {}), marker: index + 1, custom: false }));
  const added = draft.added.map((item, index) => ({ ...item, marker: kept.length + index + 1, custom: true }));
  const objects = [...kept, ...added];
  const selected = new Set(objects.map(item => item.key));
  const markers: LanguageItem[] = objects.map(item => ({ id: item.custom ? `custom-${item.key}` : item.key, word: humanizeTerm(item.label),
    translation: humanizeTerm(item.label), wordClass: "noun", gender: null, marker: item.marker, x: item.x * 100, y: item.y * 100,
    attributes: draft.attributes[item.key] ?? {}, example: "", exampleTranslation: "" }));
  const placementLabel = pending?.label ?? (moving ? humanizeTerm(objects.find(item => item.key === moving)?.label ?? "") : null);
  const visibleRelations = draft.relations.filter(row => selected.has(row.subjectObjectKey) && selected.has(row.referenceObjectKey));
  const attributeCount = objects.reduce((sum, item) => sum + Object.values(draft.attributes[item.key] ?? {}).filter(value => value.trim()).length, 0);
  const activeAttributeKey = selected.has(attributeKey) ? attributeKey : objects[0]?.key ?? "";
  const objectOptions = objects.map(item => ({ value: item.key, label: humanizeTerm(item.label), marker: item.marker }));
  const update = (change: (current: ReviewDraft) => ReviewDraft) => { setDraft(change); setError(null); };
  const scrollToPhoto = () => photoRef.current?.scrollIntoView?.({ behavior: smooth(), block: "center" });

  const remove = (itemKey: string) => {
    if (detected.some(item => item.key === itemKey)) {
      update(current => ({ ...current, removed: [...new Set([...current.removed, itemKey])] }));
      setExplicitlyRemoved(current => [...new Set([...current, itemKey])]);
    } else update(current => ({ ...current, added: current.added.filter(item => item.key !== itemKey) }));
  };
  const place = ({ x, y }: Point) => {
    if (busy) return;
    const location = { x: Math.min(x / 100, 0.99), y: Math.min(y / 100, 0.99) };
    if (moving) {
      if (detected.some(item => item.key === moving)) update(current => ({ ...current, positions: { ...current.positions, [moving]: location } }));
      else update(current => ({ ...current, added: current.added.map(item => item.key === moving ? { ...item, ...location } : item) }));
      setMoving(null); return;
    }
    if (!pending) return;
    update(current => ({ ...current, added: [...current.added, { key: `added-${crypto.randomUUID()}`, label: pending.label, ...location }] }));
    setPending(null); setLabel("");
  };
  const startAdding = () => {
    const word = label.trim();
    if (!word || placementLabel || busy) return;
    setPending({ label: word }); setError(null); scrollToPhoto();
  };
  const addRelation = () => {
    if (!relationText || subject === reference || !selected.has(subject) || !selected.has(reference)) return;
    if (visibleRelations.some(row => row.subjectObjectKey === subject && row.referenceObjectKey === reference && row.relation === relationText)) {
      setError("That relation is already in your list."); return;
    }
    update(current => ({ ...current, relations: [...current.relations, { key: `new-${crypto.randomUUID()}`, subjectObjectKey: subject, relation: relationText, referenceObjectKey: reference }] }));
    setRelationText("");
  };
  const confirm = async () => {
    if (pending || moving || busy || !objects.length) return;
    setSaving(true);
    const keys = objects.map(item => item.key);
    const next = await command(chatRoundIntent(round.id, "objects"), {
      acceptedObjectKeys: kept.map(item => item.key),
      addedObjects: draft.added.map(({ key: addedKey, label: name, x, y }) => ({ key: addedKey, label: name.slice(0, 60), x, y })),
      movedObjects: kept.filter(item => draft.positions[item.key]).map(item => ({ key: item.key, ...draft.positions[item.key] })),
      objectAttributes: Object.fromEntries(keys.map(itemKey => [itemKey, Object.fromEntries(Object.entries(draft.attributes[itemKey] ?? {})
        .filter(([type]) => (ATTRIBUTE_TYPES as readonly string[]).includes(type)).map(([type, value]) => [type, value.trim().slice(0, 60)]))])),
      relations: visibleRelations.map(({ subjectObjectKey, relation, referenceObjectKey }) => ({ subjectObjectKey, relation, referenceObjectKey })),
    });
    setSaving(false);
    if (next) {
      saveChatDraft(key, null);
      trackAction("ispy_friend_objects_reviewed", { kept: kept.length, added: added.length,
        removed: detected.length - kept.length, moved: Object.keys(draft.positions).length });
    }
  };

  return <section className="stack analysis-page friend-object-review" aria-labelledby="friend-review-title">
    <div><h2 id="friend-review-title">Check the objects</h2>
      <p className="small muted">{chat.partner?.displayName ?? "Your friend"} will choose from these markers, so make sure they’re right. Remove anything wrong, move a marker onto the right spot, and add anything we missed.</p></div>
    <div className="analysis-layout">
      <div className="analysis-stage-column">
        <div ref={photoRef} className={`analysis-photo-stage${placementLabel ? " analysis-photo-stage--placing" : ""}`}>
          {placementLabel ? <div className="analysis-placement-prompt" role="status">
            <span><strong>Select new location</strong><small>Tap the centre of {placementLabel} in the image.</small></span>
            <button type="button" onClick={() => { setPending(null); setMoving(null); }}>Cancel</button>
          </div> : null}
          <ScenePhoto scene={{ id: round.id, mediaAssetId: "", blurb: "", title: "Your photo", imageUrl: url ?? undefined } satisfies Partial<SceneSummary> as SceneSummary} items={markers} onLocationSelect={placementLabel ? place : undefined}
            locationLabel={placementLabel ? `Choose the location of ${placementLabel}` : undefined} />
        </div>
        <div className="analysis-confirm">
          {error ? <p role="alert">{error}</p> : null}
          <Button block className="analysis-continue" disabled={busy || !!placementLabel || !objects.length} onClick={() => void confirm()}>
            {saving ? "Translating your objects…" : "Confirm objects"}
          </Button>
        </div>
      </div>
      <div className="analysis-review-column">
        <div className="analysis-panel-tabs" role="tablist" aria-label="Photo object details">
          {sceneReviewPanels().map(value => <button key={value} type="button" role="tab" aria-selected={panel === value}
            className={panel === value ? "is-active" : ""} onClick={() => setPanel(value)}>
            {value === "attributes" ? "Adjectives" : value[0].toUpperCase() + value.slice(1)}
            <span>{value === "objects" ? objects.length : value === "attributes" ? attributeCount : visibleRelations.length}</span>
          </button>)}
        </div>
        {panel === "objects" ? <section className="analysis-results" aria-label="Objects">
          <form className="analysis-add-word" onSubmit={event => { event.preventDefault(); startAdding(); }}>
            <label className="field__label" htmlFor="friend-review-new-word">Add another object you see</label>
            <div className="analysis-add-word__controls">
              <input id="friend-review-new-word" className="input" maxLength={60} value={label} placeholder="e.g. window" disabled={busy || !!placementLabel} onChange={event => setLabel(event.target.value)} />
              <Button variant="secondary" type="submit" disabled={!label.trim() || !!placementLabel || busy || draft.added.length >= 20}>Select location</Button>
            </div>
          </form>
          <Card plain className="analysis-word-card analysis-word-card--objects">
            <div className="analysis-word-list" aria-label="Objects in this photo">
              {objects.map(item => <div className="analysis-word-row analysis-object-row" key={item.key}>
                <span className={`analysis-word-row__marker${item.custom ? " analysis-word-row__marker--custom" : ""}`}>{item.marker}</span>
                <strong>{humanizeTerm(item.label)}</strong>
                <div className="analysis-object-instance__actions">
                  <button className="analysis-marker-action" type="button" disabled={busy || !!placementLabel}
                    aria-label={`Change location of marker ${item.marker}, ${item.label}`} title="Change location"
                    onClick={() => { setMoving(item.key); setError(null); scrollToPhoto(); }}><MarkerIcon size={19} /></button>
                  <button className="analysis-word-row__remove" type="button" disabled={busy} aria-label={`Remove marker ${item.marker}, ${item.label}`}
                    onClick={() => remove(item.key)}><CloseIcon size={18} /></button>
                </div>
              </div>)}
              {!objects.length ? <p className="small muted">Add an object you can see above.</p> : null}
            </div>
            {explicitlyRemoved.length ? <div className="analysis-restore">
              <Button variant="quiet" disabled={busy} onClick={() => {
                update(current => ({ ...current, removed: current.removed.filter(itemKey => !explicitlyRemoved.includes(itemKey)) }));
                setExplicitlyRemoved([]);
              }}>Restore removed objects</Button>
            </div> : null}
          </Card>
        </section> : null}
        {panel === "attributes" ? <section className="analysis-results" aria-label="Adjectives">
          <p className="muted analysis-panel-hint">Add or edit adjectives for the selected object. Clues are built from these.</p>
          <Card plain className="analysis-word-card analysis-attribute-card">
            <ComboBox id="friend-attribute-object" ariaLabel="Object" value={activeAttributeKey} options={objectOptions} onChange={setAttributeKey} />
            <div className="analysis-attribute-fields">
              {ATTRIBUTE_TYPES.map(type => { const value = draft.attributes[activeAttributeKey]?.[type] ?? ""; return <label key={type}><span>{type}</span>
                <input className={`input${value.trim() ? " is-filled" : ""}`} value={value} maxLength={60} placeholder={`No ${type}`} disabled={busy}
                  onChange={event => update(current => ({ ...current, attributes: { ...current.attributes,
                    [activeAttributeKey]: { ...(current.attributes[activeAttributeKey] ?? {}), [type]: event.target.value } } }))} /></label>; })}
            </div>
          </Card>
        </section> : null}
        {panel === "relations" ? <section className="analysis-results" aria-label="Relations">
          <Card plain className="analysis-word-card analysis-word-card--relations">
            <div className="analysis-word-list">
              {visibleRelations.map(row => {
                const subjectObject = objects.find(item => item.key === row.subjectObjectKey);
                const referenceObject = objects.find(item => item.key === row.referenceObjectKey);
                return <div className="analysis-relation-row" key={row.key}>
                  <div className="analysis-relation-row__object"><span className="analysis-word-row__marker">{subjectObject?.marker}</span><strong>{humanizeTerm(subjectObject?.label ?? "")}</strong></div>
                  <div className="analysis-relation-row__connection">
                    <ComboBox compact ariaLabel="Connection" value={row.relation}
                      options={RELATIONS.some(([value]) => value === row.relation) ? RELATION_CHOICES : [{ value: row.relation, label: relationLabel(row.relation) }, ...RELATION_CHOICES]}
                      onChange={value => update(current => ({ ...current, relations: current.relations.map(item => item.key === row.key ? { ...item, relation: value } : item) }))} />
                  </div>
                  <div className="analysis-relation-row__object"><span className="combobox__marker">{referenceObject?.marker}</span><strong>{humanizeTerm(referenceObject?.label ?? "")}</strong></div>
                  <button type="button" className="analysis-word-row__remove" disabled={busy} aria-label={`Remove relation ${relationLabel(row.relation)}`}
                    onClick={() => update(current => ({ ...current, relations: current.relations.filter(item => item.key !== row.key) }))}><CloseIcon size={18} /></button>
                </div>;
              })}
              {!visibleRelations.length ? <p className="small muted">No connections selected. You can continue without adding any.</p> : null}
            </div>
          </Card>
          <p className="muted analysis-panel-hint">Add any connections we missed such as a cup on a table.</p>
          <Card plain className="analysis-word-card">
            <form className="stack analysis-relation-form" onSubmit={event => { event.preventDefault(); addRelation(); }}>
              <label className="field__label" htmlFor="friend-relation-subject">Object</label>
              <ComboBox id="friend-relation-subject" value={subject} disabled={busy} placeholder="Choose an object" options={objectOptions} onChange={setSubject} />
              <label className="field__label" htmlFor="friend-relation-text">Connection</label>
              <ComboBox id="friend-relation-text" value={relationText} disabled={busy} placeholder="Choose a connection" options={RELATION_CHOICES} onChange={setRelationText} />
              <label className="field__label" htmlFor="friend-relation-reference">Related object</label>
              <ComboBox id="friend-relation-reference" value={reference} disabled={busy} placeholder="Choose another object"
                options={objectOptions.filter(item => item.value !== subject)} onChange={setReference} />
              <Button type="submit" variant="secondary" disabled={busy || !relationText || subject === reference || !selected.has(subject) || !selected.has(reference) || visibleRelations.length >= 100}>Add connection</Button>
            </form>
          </Card>
        </section> : null}
      </div>
    </div>
  </section>;
}
