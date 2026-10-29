## GitHub Copilot Chat

- Extension: 0.59.0 (prod)
- VS Code: 1.131.0 (e4c7e7b1d6d060162f4aa7f8225271b67ce1df75)
- OS: win32 10.0.26200 x64
- GitHub Account: dhanushk300

## Network

User Settings:
```json
  "http.systemCertificatesNode": true,
  "telemetry.telemetryLevel": "all",
  "github.copilot.advanced.debug.useElectronFetcher": true,
  "github.copilot.advanced.debug.useNodeFetcher": false,
  "github.copilot.advanced.debug.useNodeFetchFetcher": true
```

Connecting to https://api.github.com:
- DNS ipv4 Lookup: 20.207.73.85 (248 ms)
- DNS ipv6 Lookup: 64:ff9b::14cf:4955 (194 ms)
- Proxy URL: None (1 ms)
- Electron fetch (configured): HTTP 200 (216 ms)
- Node.js https: HTTP 200 (626 ms)
- Node.js fetch: HTTP 200 (1270 ms)

Connecting to https://api.individual.githubcopilot.com/_ping:
- DNS ipv4 Lookup: 140.82.112.22 (323 ms)
- DNS ipv6 Lookup: 64:ff9b::8c52:7016 (371 ms)
- Proxy URL: None (2 ms)
- Electron fetch (configured): timed out after 10 seconds
- Node.js https: timed out after 10 seconds
- Node.js fetch: timed out after 10 seconds

Connecting to https://proxy.individual.githubcopilot.com/_ping:
- DNS ipv4 Lookup: 52.175.140.176 (517 ms)
- DNS ipv6 Lookup: 64:ff9b::14c7:27e0 (264 ms)
- Proxy URL: None (76 ms)
- Electron fetch (configured): HTTP 200 (212 ms)
- Node.js https: HTTP 200 (730 ms)
- Node.js fetch: HTTP 200 (741 ms)

Connecting to https://mobile.events.data.microsoft.com/OneCollector/1.0?cors=true&content-type=application/x-json-stream (Electron fetch): HTTP 200 (339 ms)
Connecting to https://telemetry.individual.githubcopilot.com/telemetry (Node.js https): HTTP 200 (2462 ms)
Connecting to https://default.exp-tas.com/vscode/ab (Node.js fetch): HTTP 200 (614 ms)

Number of system certificates: 89

## Notes

- Active fetcher: Electron fetch.
- For corporate networks also see: [Troubleshooting firewall settings for GitHub Copilot](https://docs.github.com/en/copilot/troubleshooting-github-copilot/troubleshooting-firewall-settings-for-github-copilot).