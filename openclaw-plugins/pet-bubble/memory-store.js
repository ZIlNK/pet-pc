import { randomBytes, randomUUID } from "node:crypto";
import { lstat, readFile, realpath, rename, unlink, writeFile } from "node:fs/promises";
import path from "node:path";

export const START_MARKER = "<!-- desktop-pet-managed-memory:start -->";
export const END_MARKER = "<!-- desktop-pet-managed-memory:end -->";
const TITLE = "## Desktop Pet Managed Memory";
const MEMORY_LINE = /^- <!-- memory:(m_[a-f0-9]+) --> (.+)$/;
const locks = new Map();

export class MemoryStoreError extends Error {
  constructor(message, status = 400) {
    super(message);
    this.name = "MemoryStoreError";
    this.status = status;
  }
}

function countOccurrences(text, token) {
  let count = 0;
  let offset = 0;
  while ((offset = text.indexOf(token, offset)) !== -1) {
    count += 1;
    offset += token.length;
  }
  return count;
}

export function normalizeMemoryText(value) {
  if (typeof value !== "string") {
    throw new MemoryStoreError("memory text must be a string");
  }
  const text = value.replace(/\s+/g, " ").trim();
  if (!text) throw new MemoryStoreError("memory text cannot be empty");
  if (text.length > 500) throw new MemoryStoreError("memory text exceeds 500 characters");
  return text;
}

function renderManagedBlock(memories) {
  const lines = [START_MARKER, TITLE, ""];
  for (const memory of memories) {
    lines.push(`- <!-- memory:${memory.id} --> ${memory.text}`);
  }
  lines.push(END_MARKER);
  return lines.join("\n");
}

export function parseManagedMemory(content) {
  const source = typeof content === "string" ? content : "";
  const startCount = countOccurrences(source, START_MARKER);
  const endCount = countOccurrences(source, END_MARKER);
  if (startCount === 0 && endCount === 0) {
    return { exists: false, memories: [], start: -1, end: -1 };
  }
  if (startCount !== 1 || endCount !== 1) {
    throw new MemoryStoreError("managed memory markers are duplicated or incomplete", 409);
  }
  const start = source.indexOf(START_MARKER);
  const endMarkerStart = source.indexOf(END_MARKER);
  if (endMarkerStart <= start) {
    throw new MemoryStoreError("managed memory markers are out of order", 409);
  }
  const startLineEnd = source.indexOf("\n", start);
  if (startLineEnd === -1 || source.slice(start, startLineEnd).replace(/\r$/, "") !== START_MARKER) {
    throw new MemoryStoreError("managed memory start marker must be on its own line", 409);
  }
  const endLineStart = source.lastIndexOf("\n", endMarkerStart) + 1;
  let end = endMarkerStart + END_MARKER.length;
  if (source.slice(endLineStart, endMarkerStart) !== "" ||
      (source[end] !== undefined && source[end] !== "\n" && source.slice(end, end + 2) !== "\r\n")) {
    throw new MemoryStoreError("managed memory end marker must be on its own line", 409);
  }
  if (source.startsWith("\r\n", end)) end += 2;
  else if (source.startsWith("\n", end)) end += 1;

  const body = source.slice(startLineEnd + 1, endLineStart).replace(/\r\n/g, "\n");
  const lines = body.split("\n");
  if (lines.shift()?.replace(/\r$/, "") !== TITLE) {
    throw new MemoryStoreError("managed memory title is missing or invalid", 409);
  }
  const memories = [];
  const ids = new Set();
  for (const line of lines) {
    if (!line.trim()) continue;
    const match = MEMORY_LINE.exec(line);
    if (!match) throw new MemoryStoreError("managed memory region contains invalid content", 409);
    if (ids.has(match[1])) throw new MemoryStoreError("managed memory contains duplicate IDs", 409);
    ids.add(match[1]);
    memories.push({ id: match[1], text: normalizeMemoryText(match[2]) });
  }
  return { exists: true, memories, start, end };
}

function replaceManagedBlock(content, parsed, memories) {
  const block = renderManagedBlock(memories);
  if (!parsed.exists) {
    if (!content) return `${block}\n`;
    const separator = content.endsWith("\n") ? "\n" : "\n\n";
    return `${content}${separator}${block}\n`;
  }
  const suffix = content.slice(parsed.end);
  const newline = suffix || parsed.end === content.length ? "\n" : "";
  return `${content.slice(0, parsed.start)}${block}${newline}${suffix}`;
}

async function assertSafeWorkspace(workspaceDir) {
  const resolved = path.resolve(workspaceDir);
  let workspaceStat;
  try {
    workspaceStat = await lstat(resolved);
  } catch (error) {
    if (error?.code === "ENOENT") throw new MemoryStoreError("agent workspace does not exist", 404);
    throw error;
  }
  if (!workspaceStat.isDirectory() || workspaceStat.isSymbolicLink()) {
    throw new MemoryStoreError("agent workspace must be a real directory", 403);
  }
  const realWorkspace = await realpath(resolved);
  if (path.resolve(realWorkspace) !== resolved) {
    throw new MemoryStoreError("symbolic-link workspaces are not allowed", 403);
  }
  const memoryPath = path.join(realWorkspace, "MEMORY.md");
  try {
    const memoryStat = await lstat(memoryPath);
    if (memoryStat.isSymbolicLink() || !memoryStat.isFile()) {
      throw new MemoryStoreError("MEMORY.md must be a regular file", 403);
    }
  } catch (error) {
    if (error?.code !== "ENOENT") throw error;
  }
  return { workspaceDir: realWorkspace, memoryPath };
}

async function readMemoryFile(memoryPath) {
  try {
    return await readFile(memoryPath, "utf8");
  } catch (error) {
    if (error?.code === "ENOENT") return "";
    throw error;
  }
}

async function atomicWrite(memoryPath, content) {
  const directory = path.dirname(memoryPath);
  const token = `${process.pid}-${randomUUID()}`;
  const tempPath = path.join(directory, `.MEMORY.md.desktop-pet-${token}.tmp`);
  const backupPath = path.join(directory, `.MEMORY.md.desktop-pet-${token}.bak`);
  await writeFile(tempPath, content, { encoding: "utf8", flag: "wx" });
  try {
    await rename(tempPath, memoryPath);
    return;
  } catch (error) {
    if (process.platform !== "win32" || !["EEXIST", "EPERM", "ENOTEMPTY"].includes(error?.code)) {
      try { await unlink(tempPath); } catch {}
      throw error;
    }
  }

  // Windows does not consistently allow rename() to replace an existing file.
  // Keep the old file as a rollback copy while swapping the same-directory temp.
  let backedUp = false;
  try {
    await rename(memoryPath, backupPath);
    backedUp = true;
    await rename(tempPath, memoryPath);
    await unlink(backupPath);
  } catch (error) {
    if (backedUp) {
      try { await rename(backupPath, memoryPath); } catch {}
    }
    try { await unlink(tempPath); } catch {}
    throw error;
  }
}

async function withAgentLock(lockKey, operation) {
  const previous = locks.get(lockKey) ?? Promise.resolve();
  let release;
  const current = new Promise((resolve) => { release = resolve; });
  locks.set(lockKey, current);
  await previous.catch(() => {});
  try {
    return await operation();
  } finally {
    release();
    if (locks.get(lockKey) === current) locks.delete(lockKey);
  }
}

async function updateMemories(workspaceDir, updater) {
  const safe = await assertSafeWorkspace(workspaceDir);
  return withAgentLock(safe.workspaceDir, async () => {
    const content = await readMemoryFile(safe.memoryPath);
    const parsed = parseManagedMemory(content);
    const result = updater(parsed.memories.map((item) => ({ ...item })));
    await atomicWrite(safe.memoryPath, replaceManagedBlock(content, parsed, result.memories));
    return result.value;
  });
}

export async function listManagedMemories(workspaceDir) {
  const safe = await assertSafeWorkspace(workspaceDir);
  const content = await readMemoryFile(safe.memoryPath);
  return parseManagedMemory(content).memories;
}

export async function addManagedMemory(workspaceDir, text) {
  const normalized = normalizeMemoryText(text);
  return updateMemories(workspaceDir, (memories) => {
    let id;
    do id = `m_${randomBytes(3).toString("hex")}`;
    while (memories.some((item) => item.id === id));
    const memory = { id, text: normalized };
    memories.push(memory);
    return { memories, value: memory };
  });
}

export async function deleteManagedMemory(workspaceDir, memoryId) {
  if (typeof memoryId !== "string" || !/^m_[a-f0-9]+$/.test(memoryId)) {
    throw new MemoryStoreError("invalid memory ID");
  }
  return updateMemories(workspaceDir, (memories) => {
    const next = memories.filter((item) => item.id !== memoryId);
    if (next.length === memories.length) throw new MemoryStoreError("memory not found", 404);
    return { memories: next, value: { deleted: memoryId } };
  });
}

export async function clearManagedMemories(workspaceDir) {
  return updateMemories(workspaceDir, () => ({ memories: [], value: { cleared: true } }));
}
