import test from "node:test";
import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, rm, symlink, writeFile } from "node:fs/promises";
import path from "node:path";
import {
  MemoryStoreError,
  START_MARKER,
  addManagedMemory,
  clearManagedMemories,
  deleteManagedMemory,
  listManagedMemories,
  parseManagedMemory
} from "../memory-store.js";

async function workspace(t) {
  const root = await mkdtemp(path.join(process.cwd(), ".pet-bubble-test-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  return root;
}

test("creates, lists, deletes, and clears the managed region", async (t) => {
  const root = await workspace(t);
  await writeFile(path.join(root, "MEMORY.md"), "# Human notes\n\nKeep this.\n", "utf8");
  const first = await addManagedMemory(root, "  likes   coffee  ");
  const second = await addManagedMemory(root, "prefers short replies");
  assert.match(first.id, /^m_[a-f0-9]{6}$/);
  assert.deepEqual(await listManagedMemories(root), [
    { id: first.id, text: "likes coffee" },
    { id: second.id, text: "prefers short replies" }
  ]);
  await deleteManagedMemory(root, first.id);
  assert.deepEqual(await listManagedMemories(root), [second]);
  await clearManagedMemories(root);
  assert.deepEqual(await listManagedMemories(root), []);
  const content = await readFile(path.join(root, "MEMORY.md"), "utf8");
  assert.ok(content.startsWith("# Human notes\n\nKeep this.\n"));
  assert.ok(content.includes(START_MARKER));
});

test("rejects damaged or noncanonical managed regions with 409", () => {
  for (const content of [
    `${START_MARKER}\n## Desktop Pet Managed Memory\n`,
    `${START_MARKER}\n## Wrong\n<!-- desktop-pet-managed-memory:end -->`,
    `${START_MARKER}\n## Desktop Pet Managed Memory\ninvalid\n<!-- desktop-pet-managed-memory:end -->`,
    `${START_MARKER}\n## Desktop Pet Managed Memory\n${START_MARKER}\n<!-- desktop-pet-managed-memory:end -->`
  ]) {
    assert.throws(
      () => parseManagedMemory(content),
      (error) => error instanceof MemoryStoreError && error.status === 409
    );
  }
});

test("preserves content outside the managed region", async (t) => {
  const root = await workspace(t);
  const before = "front matter\n\n";
  const after = "\nmanual tail\n";
  await writeFile(
    path.join(root, "MEMORY.md"),
    `${before}${START_MARKER}\n## Desktop Pet Managed Memory\n\n<!-- desktop-pet-managed-memory:end -->${after}`,
    "utf8"
  );
  await addManagedMemory(root, "new memory");
  const content = await readFile(path.join(root, "MEMORY.md"), "utf8");
  assert.ok(content.startsWith(before));
  assert.ok(content.endsWith(after));
});

test("normalizes one line and enforces the 500 character limit", async (t) => {
  const root = await workspace(t);
  const memory = await addManagedMemory(root, "line one\nline two");
  assert.equal(memory.text, "line one line two");
  await assert.rejects(() => addManagedMemory(root, "x".repeat(501)), /500/);
});

test("serializes concurrent writes per workspace", async (t) => {
  const root = await workspace(t);
  await Promise.all(Array.from({ length: 20 }, (_, index) => addManagedMemory(root, `memory ${index}`)));
  const memories = await listManagedMemories(root);
  assert.equal(memories.length, 20);
  assert.equal(new Set(memories.map((item) => item.id)).size, 20);
});

test("rejects symbolic-link MEMORY.md files", async (t) => {
  const root = await workspace(t);
  const outside = path.join(root, "outside.md");
  await writeFile(outside, "outside", "utf8");
  try {
    await symlink(outside, path.join(root, "MEMORY.md"), "file");
  } catch (error) {
    if (["EPERM", "EACCES", "UNKNOWN"].includes(error?.code)) {
      t.skip("symlink creation is unavailable on this Windows host");
      return;
    }
    throw error;
  }
  await assert.rejects(
    () => listManagedMemories(root),
    (error) => error instanceof MemoryStoreError && error.status === 403
  );
});
