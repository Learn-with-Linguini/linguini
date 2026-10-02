import { SceneImage } from "./SceneImage";

type Props = {
  title: string;
  imageUrl: string | null;
  className?: string;
  lazy?: boolean;
};

export function JournalImage({ title, className, imageUrl, lazy }: Props) {
  return <SceneImage scene={{ imageUrl, title }} className={className} lazy={lazy} />;
}
