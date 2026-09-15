#!/usr/bin/env node

import { createHash } from "node:crypto";
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const apiRoot = path.join(repoRoot, "apps", "api");
const generatedClientRoot = path.join(repoRoot, "packages", "api-client");
const ignoredDirectories = new Set(["node_modules", ".turbo"]);
const env = { ...process.env, CI: "1" };

function run(label, command, args, cwd = repoRoot) {
  console.log(`\n==> ${label}`);
  const result = spawnSync(command, args, { cwd, env, stdio: "inherit" });
  if (result.error) throw result.error;
  if (result.status !== 0) process.exit(result.status ?? 1);
}

function addDirectoryToHash(hash, directory, relativeDirectory = "") {
  for (const entry of readdirSync(directory, { withFileTypes: true }).sort((a, b) =>
    a.name.localeCompare(b.name),
  )) {
    if (entry.isDirectory() && ignoredDirectories.has(entry.name)) continue;
    const relativePath = path.join(relativeDirectory, entry.name);
    const absolutePath = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      addDirectoryToHash(hash, absolutePath, relativePath);
    } else if (entry.isFile()) {
      hash.update(relativePath);
      hash.update(readFileSync(absolutePath));
    }
  }
}

function generatedClientDigest() {
  const hash = createHash("sha256");
  addDirectoryToHash(hash, generatedClientRoot);
  return hash.digest("hex");
}

run("Start Postgres", "docker", ["compose", "up", "-d", "db"]);

const generatedClientBefore = generatedClientDigest();
run("Regenerate API client", "pnpm", ["generate:api"]);
if (generatedClientDigest() !== generatedClientBefore) {
  console.error(
    "\nGenerated API client was stale. Review and keep the regenerated files, then rerun pnpm pre-pr.",
  );
  process.exit(1);
}

run("Python lint", "uv", ["run", "ruff", "check", "."], apiRoot);
run("Python format check", "uv", ["run", "ruff", "format", "--check", "."], apiRoot);
run("Python typecheck", "uv", ["run", "mypy"], apiRoot);
run(
  "Django migration check",
  "uv",
  ["run", "python", "manage.py", "makemigrations", "--check", "--dry-run"],
  apiRoot,
);
run("Python tests", "uv", ["run", "pytest", "--create-db"], apiRoot);
run("Node lint", "pnpm", ["lint"]);
run("Node format check", "pnpm", ["format:check"]);
run("Node typecheck", "pnpm", ["check-types"]);
run("Node tests", "pnpm", ["test"]);
run("Whitespace check", "git", ["diff", "--check"]);

console.log("\nPre-PR checks passed.");
