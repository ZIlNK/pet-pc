const { contextBridge, ipcRenderer } = require("electron");

const apiBaseArgument = process.argv.find((argument) => argument.startsWith("--control-center-api-base="));
const apiBase = apiBaseArgument?.slice("--control-center-api-base=".length) || "http://127.0.0.1:8080/api";

contextBridge.exposeInMainWorld("controlCenter", {
  apiBase,
  choosePetImage: () => ipcRenderer.invoke("control-center:choose-image"),
  choosePetArchive: () => ipcRenderer.invoke("control-center:choose-archive"),
});
