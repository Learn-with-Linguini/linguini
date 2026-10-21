// Size captured UI images: <img class="ui" src="assets/x.png" data-scale="1.2" data-pad="30">
// Captures are at deviceScaleFactor 4, so natural px / 4 = CSS px at 1:1.
const DSF = 4;
window.uiReady = Promise.all(
  [...document.querySelectorAll("img.ui")].map(
    img =>
      new Promise(resolve => {
        const apply = () => {
          const s = Number(img.dataset.scale || 1);
          const pad = Number(img.dataset.pad || 0) * s;
          img.style.width = `${(img.naturalWidth / DSF) * s}px`;
          img.style.height = `${(img.naturalHeight / DSF) * s}px`;
          img.style.margin = `${-pad}px`;
          resolve();
        };
        if (img.complete && img.naturalWidth) apply();
        else img.addEventListener("load", apply, { once: true });
      }),
  ),
).then(() => document.fonts.ready);
