@echo off
chcp 65001 >nul
echo 正在启动 Ollama API 适配器...
node "%~dp0server.js"
pause
