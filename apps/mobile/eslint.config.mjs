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
    ignores: ["expo-env.d.ts", ".expo/**", "dist/**"],
  },
];
