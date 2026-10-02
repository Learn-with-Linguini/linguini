import { useRef, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { Button, Card, ComboBox } from "../components/ui";
import { ArrowRightIcon, CloseIcon } from "../components/icons";
import { ScenePhoto } from "../components/ScenePhoto";
import { AnalysisScan } from "../components/AnalysisScan";
import { TranslationPreview } from "../components/TranslationPreview";
import { LeaveSession } from "../components/LeaveSession";
import { useScene } from "../state/useScene";
import { useAppState } from "../state/useAppState";
import { sessionDestination } from "../lib/sessionRoute";
import { humanizeTerm } from "../lib/termLabel";
import type { PracticeReview } from "../lib/api";
import type { LanguageItem } from "../data/types";

const ATTRIBUTE_TYPES = ["color", "size", "shape", "material", "pattern", "state", "quantity"] as const;
const RELATION_OPTIONS = [
  ["leftOf", "Left of"], ["rightOf", "Right of"], ["above", "Above"], ["below", "Below"],
  ["on", "On"], ["under", "Under"], ["in", "Inside"], ["inFrontOf", "In front of"],
  ["behind", "Behind"], ["nextTo", "Next to"], ["near", "Near"],
] as const;
const RELATION_CHOICES = RELATION_OPTIONS.map(([value, label]) => ({ value, label }));
type AnalysisPanel = "objects" | "attributes" | "relations";

function relationLabel(relation: string) {
  return RELATION_OPTIONS.find(([value]) => value === relation)?.[1]
    ?? humanizeTerm(relation);
}

export function PracticeAnalysis() {
  const navigate = useNavigate();
  const scene = useScene();
  const { session, saveReview, practiceSaving, practiceError, practiceStalled, retryProcessing } = useAppState();
  const [removed, setRemoved] = useState<string[]>([]);
  const [added, setAdded] = useState<PracticeReview["addedObjects"]>([]);
  const [relations, setRelations] = useState<PracticeReview["relations"]>(() => session?.sceneObjectRelations ?? []);
  const [sceneTitle, setSceneTitle] = useState(session?.session.sessionTitle ?? scene.title);
  const [positions, setPositions] = useState<Record<string, { x: number; y: number }>>({});
  const [movingObjectId, setMovingObjectId] = useState<string | null>(null);
  const [panel, setPanel] = useState<AnalysisPanel>("objects");
  const [attributes, setAttributes] = useState<Record<string, Record<string, string>>>(() =>
    Object.fromEntries((session?.sceneObjects ?? []).map(item => [item.id,
      Object.fromEntries(Object.entries(item.attributes ?? {}).filter((entry): entry is [string, string] => typeof entry[1] === "string"))])));
  const [attributeObjectId, setAttributeObjectId] = useState(session?.sceneObjects[0]?.id ?? "");
  const [subject, setSubject] = useState("");
  const [relationText, setRelationText] = useState("");
  const [reference, setReference] = useState("");
  const [label, setLabel] = useState("");
  const [pending, setPending] = useState<{ label: string; id?: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const photoRef = useRef<HTMLDivElement>(null);
  const base = `/practice/sessions/${scene.sessionId}`;
  if (!session) return null;
  if (["completed", "failed", "abandoned"].includes(session.session.status)) {
    const dest = sessionDestination(session);
    return <Navigate to={dest.path} replace state={dest.notice ? { practiceNotice: dest.notice } : undefined} />;
  }
  if (["created", "analyzingScene", "generatingTasks"].includes(session.session.status)) return <div className="stack analysis-page">
    <h1>Scene analysis</h1>
    {session.session.status === "generatingTasks" && session.translationPreview ? <>
      <TranslationPreview preview={session.translationPreview} scene={scene} />
      <section role="status" className="panel-note">
        {session.tasks.some(task => task.kind === "vocabularyIntroduction") ? <>
          <Button block onClick={() => navigate(`${base}/learn/${session.tasks.find(task => task.kind === "vocabularyIntroduction")!.id}`)}>
            Begin learning <ArrowRightIcon />
          </Button>
        </> : <>
          <h2>Preparing your first task...</h2>
          <p className="muted">Your translations are ready. Your first task will appear here shortly.</p>
        </>}
        {practiceStalled ? <Button onClick={() => retryProcessing(session.session.id)}>Check again</Button> : null}
        {practiceError ? <p role="alert">{practiceError}</p> : null}
      </section>
    </> : <>
    {practiceStalled ? <section className="analysis-loading" aria-live="polite">
      <div className="analysis-loading__copy"><h2>Still working on your scene...</h2><p className="muted">This is taking longer than usual. You can check again.</p>{practiceError ? <p role="alert">{practiceError}</p> : null}<Button onClick={() => retryProcessing(session.session.id)}>Retry</Button></div>
    </section> : <section className="analysis-loading" aria-live="polite" aria-busy="true">
      <AnalysisScan scene={scene} />
      <div className="analysis-loading__copy"><h2>{session.session.status === "generatingTasks" ? "Translating your scene..." : "Finding objects in your image..."}</h2><p className="muted">{session.session.status === "generatingTasks" ? "Turning your confirmed words into your learning language." : "This will only take a moment."}</p></div>
    </section>}
    </>}
  </div>;
  const locked = session.tasks.some(task => task.status !== "pending");
  const kept = scene.items.filter(item => !removed.includes(item.id));
  const custom: LanguageItem[] = added.map((item, index) => ({ id: `custom-${item.id}`, word: item.label,
    translation: item.label, wordClass: "noun", gender: null, marker: scene.items.length + index + 1,
    x: item.x * 100, y: item.y * 100, attributes: attributes[item.id] ?? {}, example: "", exampleTranslation: "" }));
  const positionedKept = kept.map(item => {
    const position = positions[item.id];
    return position ? { ...item, x: position.x * 100, y: position.y * 100 } : item;
  });
  const movingItem = movingObjectId ? kept.find(item => item.id === movingObjectId) : null;
  const placementLabel = pending?.label ?? movingItem?.translation ?? null;
  const relationObjects = [...kept.map(item => ({ id: item.id, label: item.translation })), ...added];
  const selectedIds = new Set(relationObjects.map(item => item.id));
  const attributeCount = [...selectedIds].reduce((sum, id) => sum + Object.values(attributes[id] ?? {}).filter(Boolean).length, 0);
  const activeAttributeObjectId = selectedIds.has(attributeObjectId) ? attributeObjectId : relationObjects[0]?.id ?? "";
  const visibleRelations = relations.filter(row => selectedIds.has(row.subjectSceneObjectId) && selectedIds.has(row.referenceSceneObjectId));
  const addRelation = () => {
    const text = relationText;
    if (!text || subject === reference || !selectedIds.has(subject) || !selectedIds.has(reference)) return;
    if (visibleRelations.some(row => row.subjectSceneObjectId === subject && row.referenceSceneObjectId === reference && row.relation.toLowerCase() === text.toLowerCase())) {
      setError("That relation is already in your list."); return;
    }
    setRelations(current => [...current, { id: crypto.randomUUID(), subjectSceneObjectId: subject, relation: text, referenceSceneObjectId: reference, sourceRelationKey: null }]);
    setRelationText(""); setError(null);
  };
  const startAdding = () => {
    const word = label.trim();
    if (!word || placementLabel || practiceSaving) return;
    if ([...kept.map(item => item.translation), ...added.map(item => item.label)].some(item => item.toLowerCase() === word.toLowerCase())) {
      setError("That word is already in your list."); return;
    }
    setPending({ label: word });
    setError(null);
    photoRef.current?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "center" });
  };
  const place = ({ x, y }: { x: number; y: number }) => {
    if (practiceSaving) return;
    const location = { x: Math.min(x / 100, 0.99), y: Math.min(y / 100, 0.99) };
    if (movingObjectId) {
      setPositions(current => ({ ...current, [movingObjectId]: location }));
      setMovingObjectId(null);
      return;
    }
    if (!pending) return;
    setAdded(current => pending.id
      ? current.map(item => item.id === pending.id ? { ...item, ...location } : item)
      : [...current, { id: crypto.randomUUID(), label: pending.label, ...location }]);
    setPending(null); setLabel("");
  };
  const replaceLocation = (item: PracticeReview["addedObjects"][number]) => {
    setPending({ id: item.id, label: item.label });
    setError(null);
    photoRef.current?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "center" });
  };
  const moveExistingObject = (objectId: string) => {
    setMovingObjectId(objectId);
    setError(null);
    photoRef.current?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "center" });
  };
  const proceed = async () => {
    if (pending || practiceSaving || (!kept.length && !added.length)) return;
    const selectedAttributes = Object.fromEntries([...kept.map(item => item.id), ...added.map(item => item.id)]
      .map(id => [id, attributes[id] ?? {}]));
    if (locked) {
      navigate(`${base}/mic-test`);
      return;
    }
    // Stay on the translating screen while background generation runs.
    // SessionRoute forwards to the mic check when the session becomes ready.
    await saveReview({
      sceneTitle: sceneTitle.trim() || undefined,
      acceptedObjectIds: kept.map(item => item.id),
      addedObjects: added,
      relations: visibleRelations,
      objectAttributes: selectedAttributes,
      repositionedObjects: Object.entries(positions).map(([id, anchorPoint]) => ({ id, anchorPoint })),
    });
  };
  return <div className="stack analysis-page">
    <div className="analysis-titlebar">
      <h1>Scene analysis</h1>
      <LeaveSession sessionId={session.session.id} warning={locked ? "Words you have already practised stay in your word bank, but this scene's remaining tasks are dropped." : "The words you picked for this scene will not be saved."} />
    </div>
    <div className="analysis-layout">
      <div className="analysis-stage-column">
        <div ref={photoRef} className={`analysis-photo-stage${placementLabel ? " analysis-photo-stage--placing" : ""}`}>
          {placementLabel ? <div className="analysis-placement-prompt" role="status">
            <span>Tap the centre of <strong>{placementLabel}</strong></span>
            <button type="button" onClick={() => { setPending(null); setMovingObjectId(null); }}>Cancel</button>
          </div> : null}
          <ScenePhoto scene={scene} items={[...positionedKept, ...custom]} onLocationSelect={placementLabel ? place : undefined}
            locationLabel={placementLabel ? `Choose the location of ${placementLabel}` : undefined} />
        </div>
        <div className="analysis-panel-tabs" role="tablist" aria-label="Scene analysis details">
          {(["objects", "attributes", "relations"] as const).map(value => <button key={value} type="button" role="tab"
            aria-selected={panel === value} className={panel === value ? "is-active" : ""} onClick={() => setPanel(value)}>
            {value[0].toUpperCase() + value.slice(1)}
            <span>{value === "objects" ? kept.length + added.length : value === "attributes" ? attributeCount : visibleRelations.length}</span>
          </button>)}
        </div>
      </div>
      <div className="analysis-review-column">
        {panel === "objects" ? <section className="analysis-results" aria-labelledby="analysis-found-title">
          <div><h2 id="analysis-found-title">{kept.length + added.length} words selected</h2>
            <p className="muted">{locked ? "Your lesson has started. Start a new practice to change its words." : "Keep what matches your photo. Remove or add anything you need."}</p>
          </div>
          <label className="analysis-scene-title" htmlFor="analysis-scene-title">
            <span className="field__label">Scene title</span>
            <input id="analysis-scene-title" className="input" maxLength={200} value={sceneTitle} disabled={locked || practiceSaving}
              onChange={event => setSceneTitle(event.target.value)} />
          </label>
          <Card plain className="analysis-word-card">
            <div className="analysis-word-list" aria-label="Words in this scene">
              {kept.map(item => <div className="analysis-word-row" key={item.id}>
                <span className="analysis-word-row__marker">{item.marker}</span>
                <div className="grow"><strong>{item.translation}</strong>
                  {!locked ? <button className="analysis-location-action" type="button" disabled={practiceSaving || !!placementLabel}
                    onClick={() => moveExistingObject(item.id)}>Move marker</button> : null}
                </div>
                {!locked ? <button className="analysis-word-row__remove" type="button" disabled={practiceSaving} aria-label={`Remove ${item.translation}`}
                  onClick={() => setRemoved(current => [...current, item.id])}><CloseIcon size={18} /></button> : null}
              </div>)}
              {added.map((item, index) => <div className="analysis-word-row" key={item.id}>
                <span className="analysis-word-row__marker analysis-word-row__marker--custom">{scene.items.length + index + 1}</span>
                <div className="grow"><strong>{item.label}</strong>
                  <button className="analysis-location-action" type="button" disabled={practiceSaving || !!placementLabel}
                    onClick={() => replaceLocation(item)}>Change location</button>
                </div>
                <button className="analysis-word-row__remove" type="button" disabled={practiceSaving} aria-label={`Remove ${item.label}`}
                  onClick={() => setAdded(current => current.filter(row => row.id !== item.id))}><CloseIcon size={18} /></button>
              </div>)}
              {!kept.length && !added.length ? <p className="small muted">Add a word you can see below.</p> : null}
            </div>
            {removed.length ? (
              <div className="analysis-restore">
                <Button variant="quiet" disabled={practiceSaving} onClick={() => setRemoved([])}>
                  Restore removed words
                </Button>
              </div>
            ) : null}
          </Card>
          {!locked ? <form className="analysis-add-word" onSubmit={event => { event.preventDefault(); startAdding(); }}>
            <label className="field__label" htmlFor="analysis-new-word">Add another object you see</label>
            <div className="analysis-add-word__controls">
              <input id="analysis-new-word" className="input" maxLength={200} value={label} placeholder="e.g. window" disabled={practiceSaving || !!placementLabel} onChange={event => setLabel(event.target.value)} />
              <Button variant="secondary" type="submit" disabled={!label.trim() || !!placementLabel || practiceSaving || added.length >= 20}>Select location</Button>
            </div>
          </form> : null}
        </section> : null}
        {panel === "attributes" ? <section className="analysis-results" aria-labelledby="analysis-attributes-title">
          <div><h2 id="analysis-attributes-title">Visible attributes</h2><p className="muted">Correct only what you can clearly see in the photo.</p></div>
          <Card plain className="analysis-word-card analysis-attribute-card">
            <label className="field__label" htmlFor="attribute-object">Object</label>
            <ComboBox id="attribute-object" value={activeAttributeObjectId}
              options={relationObjects.map(item => ({ value: item.id, label: item.label }))}
              onChange={setAttributeObjectId} />
            <div className="analysis-attribute-fields">
              {ATTRIBUTE_TYPES.map(type => { const value = attributes[activeAttributeObjectId]?.[type] ?? ""; return <label key={type}><span>{type}</span><input className={`input${value.trim() ? " is-filled" : ""}`} value={value}
                placeholder={`No ${type}`} disabled={locked || practiceSaving} onChange={event => setAttributes(current => ({ ...current,
                  [activeAttributeObjectId]: { ...(current[activeAttributeObjectId] ?? {}), [type]: event.target.value } }))} /></label>; })}
            </div>
          </Card>
        </section> : null}
        {panel === "relations" ? <section className="analysis-results" aria-labelledby="analysis-relations-title">
          <h2 id="analysis-relations-title">How objects relate</h2>
          <p className="muted">Keep or add connections you can see, such as a cup on a table. Removing a word also removes its connections.</p>
          <Card plain className="analysis-word-card">
            <div className="analysis-word-list">
              {visibleRelations.map((row, index) => <div className="analysis-relation-row" key={row.id}>
                <span className="analysis-word-row__marker analysis-relation-row__marker">{index + 1}</span>
                <div className="analysis-relation-row__flow">
                  <strong>{relationObjects.find(item => item.id === row.subjectSceneObjectId)?.label}</strong>
                  {locked ? <span className="analysis-relation-row__relation">{relationLabel(row.relation)}</span> :
                    <ComboBox compact ariaLabel="Connection" value={row.relation}
                      options={!RELATION_OPTIONS.some(option => option[0] === row.relation)
                        ? [{ value: row.relation, label: relationLabel(row.relation) }, ...RELATION_CHOICES]
                        : RELATION_CHOICES}
                      onChange={value => setRelations(current => current.map(item => item.id === row.id ? { ...item, relation: value } : item))} />}
                  <strong>{relationObjects.find(item => item.id === row.referenceSceneObjectId)?.label}</strong>
                </div>
                {!locked ? <button type="button" className="analysis-word-row__remove" disabled={practiceSaving} aria-label={`Remove relation ${row.relation}`} onClick={() => setRelations(current => current.filter(item => item.id !== row.id))}><CloseIcon size={18} /></button> : null}
              </div>)}
              {!visibleRelations.length ? <p className="small muted">No connections selected. You can continue without adding any.</p> : null}
            </div>
            {!locked ? <form className="stack" onSubmit={event => { event.preventDefault(); addRelation(); }}>
              <label className="field__label" htmlFor="relation-subject">Object</label>
              <ComboBox id="relation-subject" value={subject} disabled={practiceSaving} placeholder="Choose an object"
                options={relationObjects.map(item => ({ value: item.id, label: item.label }))} onChange={setSubject} />
              <label className="field__label" htmlFor="relation-text">Connection</label>
              <ComboBox id="relation-text" value={relationText} disabled={practiceSaving} placeholder="Choose a connection"
                options={RELATION_CHOICES} onChange={setRelationText} />
              <label className="field__label" htmlFor="relation-reference">Related object</label>
              <ComboBox id="relation-reference" value={reference} disabled={practiceSaving} placeholder="Choose another object"
                options={relationObjects.filter(item => item.id !== subject).map(item => ({ value: item.id, label: item.label }))}
                onChange={setReference} />
              <Button type="submit" variant="secondary" disabled={practiceSaving || !relationText.trim() || subject === reference || !selectedIds.has(subject) || !selectedIds.has(reference) || visibleRelations.length >= 100}>Add connection</Button>
            </form> : null}
          </Card>
        </section> : null}
        {error || practiceError ? <p role="alert">{error ?? practiceError}</p> : null}
        <Button block className="analysis-continue" disabled={practiceSaving || !!placementLabel || (!kept.length && !added.length)} onClick={() => void proceed()}>
          {practiceSaving ? "Saving your words..." : "Continue"} <ArrowRightIcon />
        </Button>
      </div>
    </div>
  </div>;
}
