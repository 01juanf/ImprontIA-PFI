import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { shortCommit, versionLabel, UNKNOWN_COMMIT } from "../src/version.ts";

test("shortCommit abrevia un hash de git a 7 caracteres", () => {
  assert.equal(shortCommit("0123456789ABCDEF0123456789abcdef01234567"), "0123456");
  assert.equal(shortCommit("c6e1a61"), "c6e1a61");
});

test("sin commit al compilar se muestra «desconocido»", () => {
  assert.equal(shortCommit(undefined), UNKNOWN_COMMIT);
  assert.equal(shortCommit(""), UNKNOWN_COMMIT);
  assert.equal(shortCommit("desconocido"), UNKNOWN_COMMIT);
  assert.equal(versionLabel("1.0.0", undefined), "ImprontIA v1.0.0 · commit desconocido");
});

test("la etiqueta combina versión y commit corto", () => {
  assert.equal(versionLabel("1.0.0", "c6e1a61ffff0000"), "ImprontIA v1.0.0 · commit c6e1a61");
});

test("la versión del paquete coincide con el archivo VERSION", () => {
  const archivo = readFileSync(new URL("../../VERSION", import.meta.url), "utf-8").trim();
  const pkg = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf-8"));
  assert.equal(pkg.version, archivo);
});
