import type { PracticeDetail } from "../lib/api";
import { humanizeTerm } from "../lib/termLabel";
import type { Scene } from "../data/types";
import { Card } from "./ui";
import { ScenePhoto } from "./ScenePhoto";

type PreviewTerm = NonNullable<PracticeDetail["translationPreview"]>["objects"][number];

function uniquePreviewTerms(terms: PreviewTerm[]) {
  const seen = new Set<string>();
  return terms.filter(term => {
    const identity = `${term.source.trim().toLocaleLowerCase()}\u0000${term.translation.trim().toLocaleLowerCase()}`;
    if (seen.has(identity)) return false;
    seen.add(identity);
    return true;
  });
}

export function TranslationPreview({ preview, scene }: { preview: NonNullable<PracticeDetail["translationPreview"]>; scene?: Scene }) {
  const groups = ([
    ["Objects", preview.objects],
    ["Attributes", preview.attributes],
    ["Relationships", preview.relationships],
  ] as const).map(([label, terms]) => [label, uniquePreviewTerms(terms)] as const)
    .filter(([, terms]) => terms.length);
  const termCount = groups.reduce((total, [, terms]) => total + terms.length, 0);

  return <Card plain className="translation-preview">
    {scene ? <ScenePhoto scene={scene} items={[]} /> : null}
    <details className="translation-preview__drawer">
      <summary><span><strong>Review translations</strong><small>{termCount} useful phrases from this scene</small></span><span aria-hidden="true">⌄</span></summary>
      <div className="translation-preview__groups">{groups.map(([label, terms]) => <section key={label} className="translation-preview__group">
        <h3>{label}</h3>
        <div className="translation-preview__terms">{terms.map(term => <span className="translation-preview__term" key={term.key}>
          <span>{humanizeTerm(term.source)}</span><strong>{term.translation}</strong>
        </span>)}</div>
      </section>)}</div>
    </details>
  </Card>;
}
