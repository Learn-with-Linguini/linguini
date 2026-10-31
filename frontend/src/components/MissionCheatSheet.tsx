import { Fragment, useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getMissionCheatSheet, type MissionCheatSheet } from "../lib/api";
import { trackAction } from "../lib/analytics";
import { queryKeys } from "../lib/queryKeys";
import { speak } from "../lib/speech";
import { HelpIcon, SpeakerIcon } from "./icons";
import { InlineLoader } from "./LoadingScreen";
import { IconButton } from "./ui";
import "./MissionCheatSheet.css";

export function MissionCheatSheetLauncher({
  missionId,
  practiceLevel,
  contentVersion,
  languageCode,
  onOpen,
}: {
  missionId?: string;
  practiceLevel?: string;
  contentVersion?: number;
  languageCode: string;
  onOpen?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const available = Boolean(missionId && practiceLevel && contentVersion);
  const sheet = useQuery({
    queryKey: queryKeys.missionCheatSheet(
      missionId ?? "",
      practiceLevel ?? "",
      contentVersion ?? 0,
      languageCode,
    ),
    queryFn: ({ signal }) => getMissionCheatSheet(
      missionId!, practiceLevel!, contentVersion!, languageCode, signal,
    ),
    enabled: available && open,
    retry: false,
    staleTime: Infinity,
  });

  const close = () => setOpen(false);
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open]);

  const tracking = {
    missionId,
    practiceLevel,
    contentVersion,
    languageCode,
  };

  if (!available) return null;
  return <>
    <button type="button" className="cheatsheet-trigger" aria-label="Open cheatsheet"
      title="Open cheatsheet" aria-haspopup="dialog" aria-expanded={open}
      onClick={() => {
        setOpen(true);
        onOpen?.();
        trackAction("mission_cheatsheet_opened", tracking);
      }}>
      <HelpIcon size={22} />
      <span>Help</span>
    </button>
    {open ? <div className="cheatsheet-backdrop" onMouseDown={event => {
      if (event.target === event.currentTarget) close();
    }}>
      <section className="cheatsheet-sheet" role="dialog" aria-modal="true" aria-label="Mission cheatsheet">
        <div className="cheatsheet-sheet__handle" aria-hidden="true" />
        {sheet.isLoading ? <InlineLoader label="Opening your mission guide…" /> : null}
        {sheet.isError ? <div className="cheatsheet-unavailable" role="status">
          <h3>This cheatsheet is still being prepared</h3>
          <p>It will appear here as soon as this mission and language are ready.</p>
        </div> : null}
        {sheet.data ? <><h2 className="cheatsheet-sheet__title">{sheet.data.title}</h2>
          {sheet.data.summary ? <p className="cheatsheet-sheet__summary">{sheet.data.summary}</p> : null}
          <div className="cheatsheet-concepts">
            {sheet.data.concepts.map(concept => <CheatSheetConceptCard
              key={concept.sectionId ?? concept.conceptId} concept={concept} languageCode={sheet.data.languageCode}
              textDirection={sheet.data.textDirection} />)}
          </div></> : null}
      </section>
    </div> : null}
  </>;
}

function CheatSheetConceptCard({ concept, languageCode, textDirection }: {
  concept: MissionCheatSheet["concepts"][number];
  languageCode: string;
  textDirection: "ltr" | "rtl";
}) {
  return <article className="cheatsheet-concept">
    <div className="stack-2"><h3>{concept.title}</h3>{concept.explanation ? <p>{concept.explanation}</p> : null}</div>
    {concept.tips.length ? <ul className="cheatsheet-tips">{concept.tips.map(tip =>
      typeof tip === "string" ? <li key={tip}>{tip}</li> :
        <li key={`${tip.marker}-${tip.label}`} className="cheatsheet-tip">
          <strong>{tip.marker}: {tip.label}</strong>
          <span lang={languageCode}>{tip.targetText}</span>
          <small>{tip.translation}</small>
        </li>)}</ul> : null}
    {concept.referenceItems.length ? <div className="cheatsheet-reference" aria-label={`${concept.title} reference`}>
      {concept.referenceItems.map(item => <button type="button" className="cheatsheet-reference__item"
        key={`${item.label}-${item.targetText}`} onClick={() => {
          trackAction("mission_cheatsheet_audio_played", { languageCode, conceptId: concept.conceptId });
          speak(item.targetText, languageCode);
        }}>
        <strong>{item.label}</strong>
        <span lang={languageCode}>{item.targetText}</span>
      </button>)}
    </div> : null}
    {concept.patternParts.length ? <div className="cheatsheet-pattern" dir={textDirection} aria-label={concept.formula ?? concept.title}>
      {concept.patternParts.map(part => <div key={part.partId} data-part-id={part.partId} className={`cheatsheet-pattern__part cheatsheet-pattern__part--${part.role}`}>
        <span className="cheatsheet-pattern__label">{part.label}</span>
        {part.text ? <span className="cheatsheet-pattern__pill" lang={languageCode}>{part.text}</span> :
          <span className="cheatsheet-pattern__choices">{part.choices.map((choice, index) =>
            <Fragment key={`${choice.text}-${choice.label}`}>
              {index > 0 ? <span className="cheatsheet-pattern__choice-divider" aria-hidden="true">or</span> : null}
              <span className="cheatsheet-pattern__choice">
                <span className="cheatsheet-pattern__pill" lang={languageCode}>{choice.text}</span>
                <span className="cheatsheet-pattern__choice-label">{choice.label}</span>
              </span>
            </Fragment>)}</span>}
      </div>)}
    </div> : concept.formula ? <p className="cheatsheet-formula" lang={languageCode}>{concept.formula}</p> : null}
    <div className="cheatsheet-examples">
      {concept.examples.map(example => <div key={`${example.targetText}-${example.translation}`} className="cheatsheet-example">
        <div><strong lang={languageCode} dir={textDirection}>{example.targetText}</strong><span>{example.translation}</span>
          {example.note ? <small>{example.note}</small> : null}</div>
        <IconButton label={`Hear ${example.targetText}`} onClick={() => {
          trackAction("mission_cheatsheet_audio_played", { languageCode, conceptId: concept.conceptId });
          speak(example.targetText, languageCode);
        }}><SpeakerIcon size={18} /></IconButton>
      </div>)}
    </div>
  </article>;
}
