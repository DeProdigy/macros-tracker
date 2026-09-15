#!/usr/bin/env node

import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const apiRoot = path.join(repoRoot, "apps", "api");
// Match CI: Jest must reject new snapshots and Turbo must avoid its interactive UI.
const env = { ...process.env, CI: "1" };

function run(label, command, args, cwd = repoRoot) {
  console.log(`\n==> ${label}`);
  const result = spawnSync(command, args, { cwd, env, stdio: "inherit" });
  if (result.error) {
    console.error(`\n${command} is not installed or not on PATH.`);
    process.exit(1);
  }
  if (result.status !== 0) process.exit(result.status ?? 1);
}

run("Start Postgres", "docker", ["compose", "up", "-d", "--wait", "db"]);

run("Regenerate API client", "pnpm", ["generate:api"]);
run("Stage new generated files", "git", ["add", "--intent-to-add", "packages/api-client"]);
run("Fail on API client drift", "git", ["diff", "--exit-code", "--", "packages/api-client"]);

run("Python lint", "uv", ["run", "ruff", "check", "."], apiRoot);
run("Python format check", "uv", ["run", "ruff", "format", "--check", "."], apiRoot);
run("Python typecheck", "uv", ["run", "mypy"], apiRoot);
run(
  "Django migration check",
  "uv",
  ["run", "python", "manage.py", "makemigrations", "--check", "--dry-run"],
  apiRoot,
);
// Rebuild the test database so every migration is exercised like CI.
run("Python tests", "uv", ["run", "pytest", "--create-db"], apiRoot);
run("Node lint", "pnpm", ["lint"]);
run("Node format check", "pnpm", ["format:check"]);
run("Node typecheck", "pnpm", ["check-types"]);
run("Node tests", "pnpm", ["test"]);
run("Whitespace check", "git", ["diff", "--check", "origin/main...HEAD"]);

console.log("\nPre-PR checks passed.");
