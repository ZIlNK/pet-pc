const { app, BrowserWindow, dialog, ipcMain } = require("electron");
const fs = require("node:fs/promises");
const path = require("node:path");

let controlCenterWindow = null;
const defaultApiBase = "http://127.0.0.1:8080/api";
const gotLock = app.requestSingleInstanceLock();

function apiBaseFromEnvironment() {
  const candidate = process.env.DESKTOP_PET_API_URL || defaultApiBase;
  try {
    const parsed = new URL(candidate);
    if (parsed.protocol === "http:" && parsed.hostname === "127.0.0.1" && parsed.pathname === "/api") {
      return parsed.toString().replace(/\/$/, "");
    }
  } catch {}
  return defaultApiBase;
}

function focusControlCenter() {
  if (!controlCenterWindow) return;
  if (controlCenterWindow.isMinimized()) controlCenterWindow.restore();
  controlCenterWindow.show();
  controlCenterWindow.focus();
}

function createWindow() {
  controlCenterWindow = new BrowserWindow({
    width: 1180,
    height: 820,
    minWidth: 960,
    minHeight: 640,
    show: false,
    autoHideMenuBar: true,
    backgroundColor: "#f6f7f3",
    webPreferences: {
      preload: path.join(__dirname, "electron.preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      additionalArguments: [`--control-center-api-base=${apiBaseFromEnvironment()}`],
    },
  });
  controlCenterWindow.loadFile(path.join(__dirname, "dist", "index.html"));
  controlCenterWindow.once("ready-to-show", focusControlCenter);
  controlCenterWindow.on("close", (event) => {
    event.preventDefault();
    controlCenterWindow.hide();
  });
}

async function chooseFile(filters) {
  const result = await dialog.showOpenDialog(controlCenterWindow, {
    properties: ["openFile"],
    filters,
  });
  if (result.canceled || !result.filePaths[0]) return null;
  const filePath = result.filePaths[0];
  return {
    name: path.basename(filePath),
    bytes: await fs.readFile(filePath),
  };
}

if (!gotLock) {
  app.quit();
} else {
  app.on("second-instance", focusControlCenter);
  app.whenReady().then(() => {
    ipcMain.handle("control-center:choose-image", () => chooseFile([
      { name: "Pet images", extensions: ["gif", "png", "webp", "apng"] },
    ]));
    ipcMain.handle("control-center:choose-archive", () => chooseFile([
      { name: "Pet package", extensions: ["zip"] },
    ]));
    createWindow();
  });
  app.on("window-all-closed", (event) => event.preventDefault());
}
