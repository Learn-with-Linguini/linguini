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
  return <Card plain className="translation-preview">
    {scene ? <ScenePhoto scene={scene} items={[]} /> : null}
    <h2>Vocabulary preview</h2>
    {([
      ["Objects", preview.objects],
      ["Adjectives", preview.attributes],
      ["Relations", preview.relationships],
    ] as const).map(([label, terms]) => {
      const uniqueTerms = uniquePreviewTerms(terms);
      return uniqueTerms.length ? <section key={label} className="translation-preview__group">
      <h3>{label}</h3>
      <div className="translation-preview__terms">{uniqueTerms.map(term => <span className="translation-preview__term" key={term.key}>
        <span>{humanizeTerm(term.source)}</span><strong>{term.translation}</strong>
      </span>)}</div>
    </section> : null;
    })}
  </Card>;
}
