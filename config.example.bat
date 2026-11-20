@echo off
rem Local settings for the IPMI console launcher.
rem 1. Copy this file to config.bat
rem 2. Fill in your BMC address and credentials
rem (config.bat is in .gitignore and will not be committed)

set "BMC_HOST=192.168.1.100"
set "BMC_USER=ADMIN"
set "BMC_PWD=your_password"

rem Optional: full path to python.exe if python is not in PATH
rem set "PY=C:\Python312\python.exe"
