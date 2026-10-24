import { useEffect, useRef, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { Button, Card, ComboBox } from "../components/ui";
import { ArrowRightIcon, CloseIcon, MarkerIcon } from "../components/icons";
import { ScenePhoto } from "../components/ScenePhoto";
import { AnalysisScan } from "../components/AnalysisScan";
import { TranslationPreview } from "../components/TranslationPreview";
import { SessionPersonalization } from "../components/SessionPersonalization";
import { LeaveSession } from "../components/LeaveSession";
import { SceneShortfallNotice } from "../components/SceneShortfallNotice";
import { useScene } from "../state/useScene";
import { useAppState } from "../state/useAppState";
import { sessionDestination } from "../lib/sessionRoute";
import { humanizeTerm } from "../lib/termLabel";
import { abandonPractice, type PracticeReview, type ShortfallKind } from "../lib/api";
import { friendlyError } from "../lib/queryKeys";
import { SHORTFALL_ACTIONS } from "../lib/sceneShortfall";
import { countGroups, objectCounts } from "../lib/countGroups";
import { initialReviewMarkers, initiallyHiddenObjectIds, sceneReviewPanels, type SceneReviewPanel } from "../lib/sceneReview";
import { trackAction } from "../lib/analytics.ts";
import type { LanguageItem } from "../data/types";

const ATTRIBUTE_TYPES = ["color", "size", "shape", "material", "pattern", "state"] as const;
const RELATION_OPTIONS = [
  ["leftOf", "Left of"], ["rightOf", "Right of"], ["above", "Above"], ["below", "Below"],
  ["on", "On"], ["under", "Under"], ["in", "Inside"], ["inFrontOf", "In front of"],
  ["behind", "Behind"], ["nextTo", "Next to"], ["near", "Near"],
] as const;
const RELATION_CHOICES = RELATION_OPTIONS.map(([value, label]) => ({ value, label }));
type AnalysisPanel = SceneReviewPanel;
type AddedReviewObject = PracticeReview["addedObjects"][number] & { marker: number };

function canonicalRelationValue(relation: string) {
  const normalized = relation.trim().replace(/[\s_-]+/g, "").toLowerCase();
  return RELATION_OPTIONS.find(([value, label]) =>
    value.toLowerCase() === normalized || label.replace(/[\s_-]+/g, "").toLowerCase() === normalized,
  )?.[0] ?? relation;
}

function relationLabel(relation: string) {
  const canonical = canonicalRelationValue(relation);
  return RELATION_OPTIONS.find(([value]) => value === canonical)?.[1]
    ?? humanizeTerm(relation);
}

export function PracticeAnalysis() {
  const navigate = useNavigate();
  const scene = useScene();
  const { session, saveReview, reviewShortfall, practiceSaving, practiceError, practiceStalled, retryProcessing, retryAnalysis } = useAppState();
  const [removed, setRemoved] = useState<string[]>(() => {
    return initiallyHiddenObjectIds(
      (session?.sceneObjects ?? []).map(item => item.id),
      session?.suggestedSceneObjectIds,
    );
  });
  const [explicitlyRemoved, setExplicitlyRemoved] = useState<string[]>([]);
  const [added, setAdded] = useState<AddedReviewObject[]>([]);
  const reviewMarkers = initialReviewMarkers(
    (session?.sceneObjects ?? []).map(item => item.id),
    session?.suggestedSceneObjectIds,
  );
  const nextMarker = useRef(Object.keys(reviewMarkers).length + 1);
  const [relations, setRelations] = useState<PracticeReview["relations"]>(() => session?.sceneObjectRelations ?? []);
  const [sceneTitle, setSceneTitle] = useState(session?.session.sessionTitle ?? scene.title);
  const [positions, setPositions] = useState<Record<string, { x: number; y: number }>>({});
  const [movingObjectId, setMovingObjectId] = useState<string | null>(null);
  const [panel, setPanel] = useState<AnalysisPanel>("objects");
  const [attributes, setAttributes] = useState<Record<string, Record<string, string>>>(() =>
    Object.fromEntries((session?.sceneObjects ?? []).map(item => [item.id,
      Object.fromEntries(Object.entries(item.attributes ?? {}).filter((entry): entry is [string, string] => entry[0] !== "quantity" && typeof entry[1] === "string"))])));
  const [attributeObjectId, setAttributeObjectId] = useState(session?.sceneObjects[0]?.id ?? "");
  const [subject, setSubject] = useState("");
  const [relationText, setRelationText] = useState("");
  const [reference, setReference] = useState("");
  const [label, setLabel] = useState("");
  const [pending, setPending] = useState<{ label: string; id?: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [leavingPhoto, setLeavingPhoto] = useState(false);
  const photoRef = useRef<HTMLDivElement>(null);
  const tabsRef = useRef<HTMLDivElement>(null);
  const shortfallRef = useRef<HTMLDivElement>(null);
  // A rejected review, or a generation that found nothing checkable, says what is short.
  const shortfall = session?.session.status === "awaitingObjectReview"
    ? reviewShortfall ?? session.sceneShortfall ?? null
    : null;
  const shortfallKey = shortfall?.missing.join(",") ?? "";
  const hydratedSessionId = useRef<string | null>(null);
  const base = `/practice/sessions/${scene.sessionId}`;
  useEffect(() => {
    if (!session || hydratedSessionId.current === session.session.id) return;
    hydratedSessionId.current = session.session.id;
    setRemoved(initiallyHiddenObjectIds(
      session.sceneObjects.map(item => item.id),
      session.suggestedSceneObjectIds,
    ));
    setExplicitlyRemoved([]);
    setAdded([]);
    nextMarker.current = Object.keys(initialReviewMarkers(
      session.sceneObjects.map(item => item.id),
      session.suggestedSceneObjectIds,
    )).length + 1;
    setRelations(session.sceneObjectRelations);
    setAttributes(Object.fromEntries(session.sceneObjects.map(item => [item.id,
      Object.fromEntries(Object.entries(item.attributes ?? {}).filter((entry): entry is [string, string] => entry[0] !== "quantity" && typeof entry[1] === "string"))])));
    setAttributeObjectId(session.sceneObjects[0]?.id ?? "");
    setSceneTitle(session.session.sessionTitle ?? scene.title);
  }, [scene.title, session]);
  useEffect(() => {
    if (!shortfallKey) return;
    trackAction("scene_shortfall_shown", { missing: shortfallKey });
    shortfallRef.current?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "nearest" });
  }, [shortfallKey]);
  useEffect(() => {
    if (!pending && !movingObjectId) return;
    const cancelOutside = (event: PointerEvent) => {
      if (photoRef.current?.contains(event.target as Node)) return;
      setPending(null);
      setMovingObjectId(null);
    };
    document.addEventListener("pointerdown", cancelOutside);
    return () => document.removeEventListener("pointerdown", cancelOutside);
  }, [movingObjectId, pending]);
  if (!session) return null;
  if (session.session.status === "failed" && session.analysisRetryable) return <div className="stack analysis-page">
    <h1>Scene analysis</h1>
    <section className="analysis-loading" aria-live="polite">
      <div className="analysis-loading__copy">
        <h2>We couldn't analyse that photo</h2>
        <p className="muted">Something went wrong while finding objects in your photo. Your photo is saved, so you can try again without uploading it.</p>
        {practiceError ? <p role="alert">{practiceError}</p> : null}
        <div className="stack-2">
          <Button disabled={practiceSaving} onClick={() => void retryAnalysis(session.session.id)}>Try again</Button>
          <Button variant="secondary" disabled={practiceSaving} onClick={() => navigate("/practice", { state: {
            practiceNotice: "Your last photo is still saved. You can try it again or choose another one.",
            retrySessionId: session.session.id,
          } })}>Choose another photo</Button>
        </div>
      </div>
    </section>
  </div>;
  if (["completed", "failed", "abandoned"].includes(session.session.status)) {
    const dest = sessionDestination(session);
    return <Navigate to={dest.path} replace state={dest.notice ? { practiceNotice: dest.notice } : undefined} />;
  }
  if (["created", "analyzingScene", "generatingTasks"].includes(session.session.status)) return <div className="stack analysis-page">
    <h1>Scene analysis</h1>
    {session.session.status === "generatingTasks" && session.translationPreview ? <>
      <TranslationPreview preview={session.translationPreview} scene={scene} />
      <SessionPersonalization personalization={session.personalization} languageCode={scene.languageCode} />
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
      <div className="analysis-loading__copy"><h2>{session.session.status === "generatingTasks" ? "Translating your scene..." : "Finding objects in your image..."}</h2><p className="muted">{session.session.status === "generatingTasks" ? "Turning your confirmed words into your learning language." : "AI is suggesting objects for you to check before learning."}</p></div>
    </section>}
    </>}
  </div>;
  const locked = session.tasks.some(task => task.status !== "pending");
  const kept = scene.items
    .filter(item => !removed.includes(item.id))
    .map(item => ({ ...item, marker: reviewMarkers[item.id] ?? item.marker }));
  const custom: LanguageItem[] = added.map(item => ({ id: `custom-${item.id}`, word: item.label,
    translation: item.label, wordClass: "noun", gender: null, marker: item.marker,
    x: item.x * 100, y: item.y * 100, attributes: attributes[item.id] ?? {}, example: "", exampleTranslation: "" }));
  const positionedKept = kept.map(item => {
    const position = positions[item.id];
    return position
      ? { ...item, x: position.x * 100, y: position.y * 100 }
      : item;
  });
  const movingItem = movingObjectId ? kept.find(item => item.id === movingObjectId) : null;
  const placementLabel = pending?.label ?? movingItem?.translation ?? null;
  const rawRelationObjects = [
    ...positionedKept.map(item => ({
      id: item.id,
      label: session.sceneObjects.find(object => object.id === item.id)?.label ?? item.translation,
      marker: item.marker,
    })),
    ...added,
  ];
  const relationObjects = rawRelationObjects;
  const selectedIds = new Set(relationObjects.map(item => item.id));
  const attributeCount = [...selectedIds].reduce((sum, id) => sum + Object.values(attributes[id] ?? {}).filter(Boolean).length, 0);
  const activeAttributeObjectId = selectedIds.has(attributeObjectId) ? attributeObjectId : relationObjects[0]?.id ?? "";
  const groups = countGroups([
    ...kept.map(item => {
      const object = session.sceneObjects.find(row => row.id === item.id);
      return { id: item.id, label: object?.label ?? item.translation, attributes: object?.attributes };
    }),
    ...added.map(item => ({ id: item.id, label: item.label })),
  ]);
  const verifiedCounts = Object.fromEntries(groups.map(group => [group.key, String(group.objectIds.length)]));
  const panels = sceneReviewPanels();
  const removeObjects = (objectIds: string[]) => {
    const ids = new Set(objectIds);
    const analysedIds = new Set(session.sceneObjects.map(item => item.id));
    const analysed = objectIds.filter(id => analysedIds.has(id));
    setRemoved(current => [...new Set([...current, ...analysed])]);
    setExplicitlyRemoved(current => [...new Set([...current, ...analysed])]);
    setAdded(current => current.filter(item => !ids.has(item.id)));
  };
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
      : [...current, { id: crypto.randomUUID(), label: pending.label, marker: nextMarker.current++, ...location }]);
    setPending(null); setLabel("");
  };
  const replaceLocation = (item: AddedReviewObject) => {
    setPending({ id: item.id, label: item.label });
    setError(null);
    photoRef.current?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "center" });
  };
  const moveExistingObject = (objectId: string) => {
    setMovingObjectId(objectId);
    setError(null);
    photoRef.current?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "center" });
  };
  const addMissing = (kind: ShortfallKind) => {
    trackAction("scene_shortfall_add_clicked", { kind });
    setPanel(SHORTFALL_ACTIONS[kind].panel);
    tabsRef.current?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
    if (kind === "objects" || kind === "counts") requestAnimationFrame(() => document.getElementById("analysis-new-word")?.focus({ preventScroll: true }));
  };
  const tryAnotherPhoto = async () => {
    if (leavingPhoto) return;
    trackAction("scene_shortfall_new_photo", { missing: shortfallKey });
    setLeavingPhoto(true); setError(null);
    try {
      // Nothing from this review was saved, so the session is left before choosing again.
      await abandonPractice(session.session.id);
      navigate("/practice", { replace: true, state: {
        practiceNotice: "Take or choose a photo with a few objects you can count, describe or relate to each other.",
      } });
    } catch (reason) {
      setError(friendlyError(reason));
      setLeavingPhoto(false);
    }
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
    trackAction("scene_review_confirmed", {
      acceptedCount: kept.length,
      addedCount: added.length,
    });
    await saveReview({
      sceneTitle: sceneTitle.trim() || undefined,
      acceptedObjectIds: kept.map(item => item.id),
      addedObjects: added.map(({ marker: _marker, ...item }) => item),
      relations: visibleRelations.map(row => ({ ...row, relation: canonicalRelationValue(row.relation) })),
      objectAttributes: selectedAttributes,
      objectCounts: objectCounts(groups, verifiedCounts),
      repositionedObjects: Object.entries(positions).map(([id, anchorPoint]) => ({ id, anchorPoint })),
    });
  };
  return <div className={`stack analysis-page${placementLabel ? " analysis-page--placing" : ""}`}>
    <div className="analysis-titlebar">
      <h1>Scene analysis</h1>
      <LeaveSession sessionId={session.session.id} warning={locked ? "Words you have already practised stay in your word bank, but this scene's remaining tasks are dropped." : "The words you picked for this scene will not be saved."} />
    </div>
    <div className="analysis-layout">
      <div className="analysis-stage-column">
        <div ref={photoRef} className={`analysis-photo-stage${placementLabel ? " analysis-photo-stage--placing" : ""}`}>
          {placementLabel ? <div className="analysis-placement-prompt" role="status">
            <span><strong>Select new location</strong><small>Tap the centre of {placementLabel} in the image.</small></span>
            <button type="button" onClick={() => { setPending(null); setMovingObjectId(null); }}>Cancel</button>
          </div> : null}
          <ScenePhoto scene={scene} items={[...positionedKept, ...custom]} onLocationSelect={placementLabel ? place : undefined}
            locationLabel={placementLabel ? `Choose the location of ${placementLabel}` : undefined} />
        </div>
        <div ref={tabsRef} className="analysis-panel-tabs" role="tablist" aria-label="Scene analysis details">
          {panels.map(value => <button key={value} type="button" role="tab"
            aria-selected={panel === value} className={panel === value ? "is-active" : ""} onClick={() => setPanel(value)}>
            {value === "attributes" ? "Adjectives" : value[0].toUpperCase() + value.slice(1)}
            <span>{value === "objects" ? relationObjects.length : value === "attributes" ? attributeCount : visibleRelations.length}</span>
          </button>)}
        </div>
      </div>
      <div className="analysis-review-column">
        {panel === "objects" ? <section className="analysis-results" aria-labelledby="analysis-found-title">
          <div><h2 id="analysis-found-title">Check what this lesson will use</h2>
            <p className="muted">{locked ? "Your lesson has started. Start a new practice to change its objects." : "AI suggestions can be wrong. Each row matches a numbered marker. Remove objects that aren't there, add missing ones, or move misplaced markers."}</p>
          </div>
          <label className="analysis-scene-title" htmlFor="analysis-scene-title">
            <span className="field__label">Scene title</span>
            <input id="analysis-scene-title" className="input" maxLength={200} value={sceneTitle} disabled={locked || practiceSaving}
              onChange={event => setSceneTitle(event.target.value)} />
          </label>
          <Card plain className="analysis-word-card">
            <div className="analysis-word-list" aria-label="Words in this scene">
              {relationObjects.map(instance => {
                const sceneItem = kept.find(row => row.id === instance.id);
                const addedItem = added.find(row => row.id === instance.id);
                return <div className="analysis-word-row analysis-object-row" key={instance.id}>
                  <span className={`analysis-word-row__marker${addedItem ? " analysis-word-row__marker--custom" : ""}`}>{instance.marker}</span>
                  <strong>{humanizeTerm(instance.label)}</strong>
                  {!locked ? <div className="analysis-object-instance__actions">
                    <button className="analysis-marker-action" type="button" disabled={practiceSaving || !!placementLabel}
                      aria-label={`Change location of marker ${instance.marker}, ${instance.label}`} title="Change location"
                      onClick={() => sceneItem ? moveExistingObject(instance.id) : replaceLocation(addedItem!)}><MarkerIcon size={19} /></button>
                    <button className="analysis-word-row__remove" type="button" disabled={practiceSaving} aria-label={`Remove marker ${instance.marker}, ${instance.label}`}
                      onClick={() => removeObjects([instance.id])}><CloseIcon size={18} /></button>
                  </div> : null}
                </div>;
              })}
              {!kept.length && !added.length ? <p className="small muted">Add a word you can see below.</p> : null}
            </div>
            {explicitlyRemoved.length ? (
              <div className="analysis-restore">
                <Button variant="quiet" disabled={practiceSaving} onClick={() => {
                  setRemoved(current => current.filter(id => !explicitlyRemoved.includes(id)));
                  setExplicitlyRemoved([]);
                }}>
                  Restore removed objects
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
          <section className="analysis-object-counts" aria-labelledby="analysis-object-counts-title">
            <div>
              <h3 id="analysis-object-counts-title">Count</h3>
              <p className="small muted">Counts update when you add or remove objects.</p>
            </div>
            <dl>
              {groups.map(group => <div key={group.key}>
                <dt>{humanizeTerm(group.label)}</dt>
                <dd aria-label={`${group.objectIds.length} ${group.objectIds.length === 1 ? "object" : "objects"}`}>{group.objectIds.length}</dd>
              </div>)}
            </dl>
          </section>
        </section> : null}
        {panel === "attributes" ? <section className="analysis-results" aria-labelledby="analysis-attributes-title">
          <div><h2 id="analysis-attributes-title">Visible adjectives</h2><p className="muted">Correct only what you can clearly see in the photo.</p></div>
          <Card plain className="analysis-word-card analysis-attribute-card">
            <label className="field__label" htmlFor="attribute-object">Object</label>
            <ComboBox id="attribute-object" value={activeAttributeObjectId}
              options={relationObjects.map(item => ({ value: item.id, label: item.label, marker: item.marker }))}
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
              {visibleRelations.map(row => {
                const subjectObject = relationObjects.find(item => item.id === row.subjectSceneObjectId);
                const referenceObject = relationObjects.find(item => item.id === row.referenceSceneObjectId);
                const relation = canonicalRelationValue(row.relation);
                return <div className="analysis-relation-row" key={row.id}>
                  <div className="analysis-relation-row__object">
                    <span className="analysis-word-row__marker">{subjectObject?.marker}</span>
                    <strong>{subjectObject?.label}</strong>
                  </div>
                  <div className="analysis-relation-row__connection">
                    {locked ? <span className="analysis-relation-row__relation">{relationLabel(relation)}</span> :
                      <ComboBox compact ariaLabel="Connection" value={relation}
                        options={!RELATION_OPTIONS.some(option => option[0] === relation)
                          ? [{ value: relation, label: relationLabel(relation) }, ...RELATION_CHOICES]
                          : RELATION_CHOICES}
                        onChange={value => setRelations(current => current.map(item => item.id === row.id ? { ...item, relation: value } : item))} />}
                  </div>
                  <div className="analysis-relation-row__object">
                    <span className="combobox__marker">{referenceObject?.marker}</span>
                    <strong>{referenceObject?.label}</strong>
                  </div>
                  {!locked ? <button type="button" className="analysis-word-row__remove" disabled={practiceSaving} aria-label={`Remove relation ${row.relation}`} onClick={() => setRelations(current => current.filter(item => item.id !== row.id))}><CloseIcon size={18} /></button> : null}
              </div>;
              })}
              {!visibleRelations.length ? <p className="small muted">No connections selected. You can continue without adding any.</p> : null}
            </div>
            {!locked ? <form className="stack analysis-relation-form" onSubmit={event => { event.preventDefault(); addRelation(); }}>
              <label className="field__label" htmlFor="relation-subject">Object</label>
              <ComboBox id="relation-subject" value={subject} disabled={practiceSaving} placeholder="Choose an object"
                options={relationObjects.map(item => ({ value: item.id, label: item.label, marker: item.marker }))} onChange={setSubject} />
              <label className="field__label" htmlFor="relation-text">Connection</label>
              <ComboBox id="relation-text" value={relationText} disabled={practiceSaving} placeholder="Choose a connection"
                options={RELATION_CHOICES} onChange={setRelationText} />
              <label className="field__label" htmlFor="relation-reference">Related object</label>
              <ComboBox id="relation-reference" value={reference} disabled={practiceSaving} placeholder="Choose another object"
                options={relationObjects.filter(item => item.id !== subject).map(item => ({ value: item.id, label: item.label, marker: item.marker }))}
                onChange={setReference} />
              <Button type="submit" variant="secondary" disabled={practiceSaving || !relationText.trim() || subject === reference || !selectedIds.has(subject) || !selectedIds.has(reference) || visibleRelations.length >= 100}>Add connection</Button>
            </form> : null}
          </Card>
        </section> : null}
        {shortfall && !locked ? <div ref={shortfallRef}>
          <SceneShortfallNotice shortfall={shortfall} busy={practiceSaving || leavingPhoto}
            onAdd={addMissing} onTryAnotherPhoto={() => void tryAnotherPhoto()} />
        </div> : null}
        {error || practiceError ? <p role="alert">{error ?? practiceError}</p> : null}
        <Button block className="analysis-continue" disabled={practiceSaving || leavingPhoto || !!placementLabel || (!kept.length && !added.length)} onClick={() => void proceed()}>
          {practiceSaving ? "Saving your review..." : "Confirm lesson facts"} <ArrowRightIcon />
        </Button>
      </div>
    </div>
  </div>;
}
