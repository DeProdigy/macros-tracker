// @ts-check
import js from "@eslint/js";
import tseslint from "typescript-eslint";
import prettier from "eslint-config-prettier";

// Root ESLint flat config, shared by every TypeScript package in the monorepo.
// Packages extend this by importing it from their own eslint.config.mjs.
export default tseslint.config(
  {
    ignores: [
      "**/node_modules/**",
      "**/dist/**",
      "**/build/**",
      "**/.turbo/**",
      "**/.expo/**",
      // Generated API client — build output, never hand-edited or linted (see plans/01-architecture.md).
      "packages/api-client/src/**",
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    rules: {
      // CLAUDE.md rule: no `any` without a comment justifying it.
      "@typescript-eslint/no-explicit-any": "warn",
    },
  },
  // Keep last: disables stylistic rules that Prettier owns.
  prettier,
);
