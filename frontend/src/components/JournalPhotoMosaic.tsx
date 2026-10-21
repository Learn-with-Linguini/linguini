import { MediaImage } from "./MediaImage";

type MosaicPhoto = { mediaAssetId: string; imageUrl: string | null };

export function JournalPhotoMosaic({ photos, title }: { photos: MosaicPhoto[]; title: string }) {
  if (photos.length === 0) return null;
  const tiles = photos.slice(0, 4);
  const remaining = photos.length - tiles.length;

  return (
    <span className={`journal-mosaic journal-mosaic--${tiles.length}`} aria-hidden={false}>
      {tiles.map((photo, index) => (
        <span key={photo.mediaAssetId} className="journal-mosaic__tile">
          <MediaImage assetId={photo.mediaAssetId} title={`${title}, photo ${index + 1}`} width={320} lazy />
          {remaining > 0 && index === tiles.length - 1 ? (
            <span className="journal-mosaic__more">+{remaining}</span>
          ) : null}
        </span>
      ))}
    </span>
  );
}
