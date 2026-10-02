import type { PracticeDetail } from "../lib/api";
import { humanizeTerm } from "../lib/termLabel";
import type { Scene } from "../data/types";
import { Card } from "./ui";
import { ScenePhoto } from "./ScenePhoto";

export function TranslationPreview({ preview, scene }: { preview: NonNullable<PracticeDetail["translationPreview"]>; scene?: Scene }) {
  return <Card plain className="translation-preview">
    {scene ? <ScenePhoto scene={scene} items={[]} /> : null}
    <h2>Your translations</h2>
    {([
      ["Objects", preview.objects],
      ["Attributes", preview.attributes],
      ["Relationships", preview.relationships],
    ] as const).map(([label, terms]) => terms.length ? <section key={label} className="translation-preview__group">
      <h3>{label}</h3>
      <div className="translation-preview__terms">{terms.map(term => <span className="translation-preview__term" key={term.key}>
        <span>{humanizeTerm(term.source)}</span><strong>{term.translation}</strong>
      </span>)}</div>
    </section> : null)}
  </Card>;
}
