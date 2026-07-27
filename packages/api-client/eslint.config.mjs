import rootConfig from "../../eslint.config.mjs";

// Inherits the shared root flat config. The root already ignores
// packages/api-client/src/** as generated output, so this only ever lints the
// three hand-written sources at the package root.
export default [...rootConfig];
