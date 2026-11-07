const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('lumoDesktop', {
  pickFolder: () => ipcRenderer.invoke('pick-folder'),
});
