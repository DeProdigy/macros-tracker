import rootConfig from "../../eslint.config.mjs";

// Mobile inherits the shared root flat config (typescript-eslint + Prettier
// compat), keeping lint consistent across the monorepo. React-Native-specific
// rule packs (e.g. react-hooks) can layer on top later without re-defining the
// typescript-eslint plugin the root already provides.
export default [
  ...rootConfig,
  {
    // Node-context CommonJS config files (metro.config.js, jest.global-setup.js).
    // These run in Node before the bundler, not on a device, so they get Node
    // globals rather than the React Native ones the root config assumes.
    files: ["*.config.js", "jest.global-setup.js"],
    languageOptions: {
      sourceType: "commonjs",
      globals: {
        require: "readonly",
        module: "writable",
        __dirname: "readonly",
        process: "readonly",
      },
    },
    rules: {
      "@typescript-eslint/no-require-imports": "off",
      "no-undef": "off",
    },
  },
  {
    // Build-time scripts run in Node, not on a device. `make-icons.mjs` draws
    // the app icon, so it reads Buffer and prints to the console. Declared by
    // hand to match the root config, which makes the same trade for its own
    // scripts directory.
    files: ["scripts/**/*.mjs"],
    languageOptions: {
      globals: { Buffer: "readonly", console: "readonly", process: "readonly" },
    },
  },
  {
    ignores: ["expo-env.d.ts", ".expo/**", "dist/**"],
  },
];
