// Lumo AI 桌面壳：启动本地后端 exe 并加载其 Web 界面（纯 CommonJS）
const { app, BrowserWindow, dialog, ipcMain, session } = require('electron');
const { spawn, spawnSync } = require('child_process');
const path = require('path');
const fs = require('fs');
const net = require('net');
const http = require('http');

let mainWindow = null;
let backendProcess = null;
let backendPid = null;
let backendCleaned = false;
let quitting = false;

// 从 start 端口起逐个尝试监听 127.0.0.1，找到第一个空闲端口
function findFreePort(start = 8000) {
  return new Promise((resolve, reject) => {
    const tryPort = (port) => {
      if (port > 65535) {
        reject(new Error('未找到可用端口'));
        return;
      }
      const server = net.createServer();
      server.once('error', () => {
        server.close(() => tryPort(port + 1));
      });
      server.once('listening', () => {
        server.close(() => resolve(port));
      });
      server.listen(port, '127.0.0.1');
    };
    tryPort(start);
  });
}

// 后端 exe 路径：打包后位于 resources/backend/，开发时使用 PyInstaller 输出目录
function getBackendExePath() {
  return app.isPackaged
    ? path.join(process.resourcesPath, 'backend', 'lumo_backend.exe')
    : path.join(__dirname, '..', 'backend', 'dist', 'lumo_backend', 'lumo_backend.exe');
}

function startBackend(port) {
  const exePath = getBackendExePath();
  const dataDir = path.join(app.getPath('appData'), 'Lumo AI');

  backendProcess = spawn(exePath, [], {
    cwd: path.dirname(exePath),
    env: Object.assign({}, process.env, {
      LUMO_DATA_DIR: dataDir,
      LUMO_PORT: String(port),
      LUMO_RUNTIME: 'desktop',
    }),
    windowsHide: true,
    detached: false,
    stdio: 'ignore',
  });
  backendPid = backendProcess.pid;

  backendProcess.on('error', (err) => {
    dialog.showErrorBox('Lumo AI 启动失败', `无法启动后端服务：\n${err.message}`);
    app.quit();
  });

  backendProcess.on('exit', (code) => {
    backendProcess = null;
    // 后端意外退出：窗口还在且不是主动退出流程时提示并退出
    if (!quitting && mainWindow && !mainWindow.isDestroyed()) {
      dialog.showErrorBox('Lumo AI 后端已停止', `后端服务意外退出（代码 ${code}），应用即将关闭。`);
      app.quit();
    }
  });
}

// 轮询健康检查接口，间隔 500ms，超时 30s
function waitForHealth(port, timeoutMs = 30000) {
  const url = `http://127.0.0.1:${port}/api/health`;
  const deadline = Date.now() + timeoutMs;
  return new Promise((resolve, reject) => {
    const poll = () => {
      const req = http.get(url, (res) => {
        res.resume();
        if (res.statusCode === 200) {
          resolve();
        } else {
          retry();
        }
      });
      req.on('error', retry);
      req.setTimeout(2000, () => {
        req.destroy();
        retry();
      });
    };
    const retry = () => {
      if (Date.now() > deadline) {
        reject(new Error('后端健康检查超时（30 秒）'));
      } else {
        setTimeout(poll, 500);
      }
    };
    poll();
  });
}

ipcMain.handle('pick-folder', async () => {
  const result = await dialog.showOpenDialog({
    properties: ['openDirectory'],
    title: '选择工作区目录',
  });
  if (result.canceled || result.filePaths.length === 0) {
    return null;
  }
  return result.filePaths[0];
});

function createWindow(port) {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    icon: path.join(__dirname, 'build', 'icon.ico'),
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  mainWindow.loadURL(`http://127.0.0.1:${port}/`);
  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// 版本感知的缓存失效：app.getVersion() 变化（升级）后清一次 HTTP 缓存，
// 避免 Chromium 启发式新鲜度复用旧版 SPA；版本一致时绝不多清。
// userData/version-marker.json 记录上次启动的版本；不存在（首次安装或老
// 版本从未写过）时只写入基准版本，不做任何清理。
const VERSION_MARKER_FILE = 'version-marker.json';

function readMarkerVersion() {
  try {
    const raw = fs.readFileSync(path.join(app.getPath('userData'), VERSION_MARKER_FILE), 'utf-8');
    const parsed = JSON.parse(raw);
    return typeof parsed.version === 'string' ? parsed.version : null;
  } catch (_) {
    return null; // 首次运行或文件损坏，无可比基准
  }
}

function writeMarkerVersion(version) {
  const dir = app.getPath('userData');
  try {
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(
      path.join(dir, VERSION_MARKER_FILE),
      JSON.stringify({ version: version }, null, 2),
      'utf-8',
    );
  } catch (err) {
    console.warn('写入版本标记失败:', err.message);
  }
}

async function clearCacheIfUpgraded() {
  try {
    const currentVersion = app.getVersion();
    const previousVersion = readMarkerVersion();
    if (previousVersion === null) {
      writeMarkerVersion(currentVersion);
      return;
    }
    if (previousVersion === currentVersion) return;
    console.log(`检测到版本变化 ${previousVersion} -> ${currentVersion}，清理 HTTP 缓存`);
    await session.defaultSession.clearCache();
    writeMarkerVersion(currentVersion);
  } catch (err) {
    // 缓存清理失败不阻断启动（后端静态资源已带 no-cache 头兜底）
    console.warn('版本感知缓存清理跳过:', err.message);
  }
}

// 用 taskkill 杀掉后端进程树；进程已退出时忽略错误，只清理一次
function cleanupBackend() {
  if (backendCleaned) return;
  backendCleaned = true;
  if (backendPid) {
    try {
      spawnSync('taskkill', ['/pid', String(backendPid), '/T', '/F'], { windowsHide: true });
    } catch (_) {
      // 进程可能已退出，忽略
    }
  }
  backendProcess = null;
}

// 单实例锁：第二个实例启动时聚焦已有窗口
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

  app.whenReady().then(async () => {
    try {
      await clearCacheIfUpgraded();
      const port = await findFreePort(8000);
      startBackend(port);
      await waitForHealth(port);
      createWindow(port);
    } catch (err) {
      dialog.showErrorBox('Lumo AI 启动失败', err.message);
      quitting = true;
      cleanupBackend();
      app.quit();
    }
  });

  app.on('before-quit', () => {
    quitting = true;
    cleanupBackend();
  });

  app.on('window-all-closed', () => {
    quitting = true;
    cleanupBackend();
    app.quit();
  });
}
