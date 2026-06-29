let currentRuntime = null;

export function setPetBubbleRuntime(runtime) {
  currentRuntime = runtime;
}

export function getPetBubbleRuntime() {
  return currentRuntime;
}
