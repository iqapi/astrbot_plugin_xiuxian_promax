setlocal
set PS1=%TEMP%\splice_readme.ps1
(
echo $lines = Get-Content -Path 'README.md' -Encoding UTF8
echo $start = ($lines ^| Select-String -SimpleMatch '指令逻辑有向图'^| Select-Object -First 1^).LineNumber
echo $end   = ($lines ^| Select-String -SimpleMatch '## 📜 许可证'^| Select-Object -First 1^).LineNumber
echo $mermaid = $lines[($start-1)..($end-2^)]
echo $head = Get-Content -Path '_readme_head.md' -Encoding UTF8
echo $tail = Get-Content -Path '_readme_tail.md' -Encoding UTF8
echo $out = $head + '' + $mermaid + '' + $tail
echo Set-Content -Path 'README.md' -Value $out -Encoding UTF8
) > %PS1%
powershell -NoProfile -ExecutionPolicy Bypass -File %PS1%
del %PS1%
