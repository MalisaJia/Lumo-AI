// Lumo AI 桌面壳：启动本地后端 exe 并加载其 Web 界面（纯 CommonJS）
const { app, BrowserWindow, dialog } = require('electron');
const { spawn, spawnSync } = require('child_process');
const path = require('path');
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

function createWindow(port) {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    icon: path.join(__dirname, 'build', 'icon.ico'),
    autoHideMenuBar: true,
  });
  mainWindow.loadURL(`http://127.0.0.1:${port}/`);
  mainWindow.on('closed', () => {
    mainWindow = null;
  });
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
