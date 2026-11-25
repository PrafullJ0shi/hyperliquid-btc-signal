// Pre-render TeX to static SVG (no runtime script or font on the site).
// stdin: JSON {id: {tex, display}}   stdout: JSON {id: "<svg ...>"}
const { mathjax } = require("mathjax-full/js/mathjax.js");
const { TeX } = require("mathjax-full/js/input/tex.js");
const { SVG } = require("mathjax-full/js/output/svg.js");
const { liteAdaptor } = require("mathjax-full/js/adaptors/liteAdaptor.js");
const { RegisterHTMLHandler } = require("mathjax-full/js/handlers/html.js");
const { AllPackages } = require("mathjax-full/js/input/tex/AllPackages.js");

const adaptor = liteAdaptor();
RegisterHTMLHandler(adaptor);
const doc = mathjax.document("", {
  InputJax: new TeX({ packages: AllPackages.filter((p) => p !== "noundefined") }),
  OutputJax: new SVG({ fontCache: "none" }),
});
let raw = "";
process.stdin.on("data", (d) => (raw += d));
process.stdin.on("end", () => {
  const items = JSON.parse(raw);
  const out = {};
  for (const [id, { tex, display }] of Object.entries(items)) {
    const node = doc.convert(tex, { display: !!display });
    out[id] = adaptor.innerHTML(node);
  }
  process.stdout.write(JSON.stringify(out));
});
