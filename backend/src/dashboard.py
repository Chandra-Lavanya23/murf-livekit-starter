import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime

# Add src folder to sys.path to resolve db imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db

class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/metrics":
            # API endpoint: Return metrics and recent calls (no sensitive fields)
            try:
                metrics = db.get_call_metrics()
                recent = db.get_recent_calls(limit=10)
                
                response_data = {
                    "metrics": metrics,
                    "recent_calls": recent
                }
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(response_data).encode("utf-8"))
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
                
        elif self.path == "/" or self.path == "/index.html":
            # HTML endpoint: Serve a premium, responsive glassmorphic dashboard
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            
            html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DhanaMitra Analytics Dashboard</title>
    <!-- Google Fonts -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <!-- Tailwind CSS CDN -->
    <script src="https://cdn.tailwindcss.com"></script>
    <!-- Lucide Icons -->
    <script src="https://unpkg.com/lucide@latest"></script>
    <script>
        tailwind.config = {
            theme: {
                extend: {
                    fontFamily: {
                        sans: ['Outfit', 'sans-serif'],
                    },
                },
            },
        }
    </script>
    <style>
        body {
            background: radial-gradient(circle at top right, rgba(15, 23, 42, 0.95), rgba(8, 10, 15, 1));
            color: #f1f5f9;
        }
        .glass-panel {
            background: rgba(30, 41, 59, 0.45);
            backdrop-filter: blur(16px);
            border: 1px solid rgba(255, 255, 255, 0.08);
        }
    </style>
</head>
<body class="min-h-screen font-sans flex flex-col">
    <!-- Header -->
    <header class="border-b border-slate-800 bg-slate-950/60 backdrop-blur-md sticky top-0 z-50 px-6 py-4">
        <div class="max-w-6xl mx-auto flex items-center justify-between">
            <div class="flex items-center gap-3">
                <div class="h-10 w-10 rounded-xl bg-gradient-to-tr from-teal-500 to-indigo-600 flex items-center justify-center shadow-lg shadow-teal-500/20">
                    <i data-lucide="bar-chart-3" class="h-5 w-5 text-white"></i>
                </div>
                <div>
                    <h1 class="text-lg font-bold tracking-tight bg-gradient-to-r from-white via-slate-200 to-slate-400 bg-clip-text text-transparent">DhanaMitra Financial Services</h1>
                    <p class="text-[10px] text-teal-400 font-semibold uppercase tracking-wider">Voice Agent Call Analytics</p>
                </div>
            </div>
            <div class="flex items-center gap-2 bg-slate-900 border border-slate-800 px-3.5 py-1.5 rounded-full">
                <span class="relative flex h-2 w-2">
                    <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                    <span class="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                </span>
                <span class="text-xs text-slate-300 font-medium">Live Monitoring</span>
                <span class="text-slate-600 text-xs px-1">|</span>
                <span id="refresh-counter" class="text-[10px] text-slate-500 font-mono">Updating...</span>
            </div>
        </div>
    </header>

    <!-- Main Content -->
    <main class="flex-grow max-w-6xl w-full mx-auto p-6 md:p-8 space-y-8">
        
        <!-- Summary Cards Grid -->
        <section class="grid grid-cols-1 md:grid-cols-3 gap-6">
            <!-- Total Calls Card -->
            <div class="glass-panel rounded-3xl p-6 relative overflow-hidden transition-all duration-300 hover:scale-[1.02] group">
                <div class="absolute -right-4 -bottom-4 opacity-5 group-hover:opacity-10 transition-opacity duration-300">
                    <i data-lucide="phone" class="h-32 w-32 text-indigo-500"></i>
                </div>
                <div class="flex items-center justify-between">
                    <span class="text-xs text-slate-400 font-semibold uppercase tracking-wider">Total Calls</span>
                    <div class="h-9 w-9 rounded-xl bg-indigo-500/10 border border-indigo-500/25 flex items-center justify-center text-indigo-400">
                        <i data-lucide="phone-call" class="h-4.5 w-4.5"></i>
                    </div>
                </div>
                <div class="mt-4">
                    <h2 id="total-calls" class="text-4xl md:text-5xl font-extrabold tracking-tight font-mono">0</h2>
                    <p class="text-xs text-slate-500 mt-2 font-medium">Accumulated call interactions</p>
                </div>
            </div>

            <!-- Successful Calls Card -->
            <div class="glass-panel rounded-3xl p-6 relative overflow-hidden transition-all duration-300 hover:scale-[1.02] group">
                <div class="absolute -right-4 -bottom-4 opacity-5 group-hover:opacity-10 transition-opacity duration-300">
                    <i data-lucide="check-circle-2" class="h-32 w-32 text-emerald-500"></i>
                </div>
                <div class="flex items-center justify-between">
                    <span class="text-xs text-slate-400 font-semibold uppercase tracking-wider">Successful Calls</span>
                    <div class="h-9 w-9 rounded-xl bg-emerald-500/10 border border-emerald-500/25 flex items-center justify-center text-emerald-400">
                        <i data-lucide="check-circle" class="h-4.5 w-4.5"></i>
                    </div>
                </div>
                <div class="mt-4">
                    <h2 id="successful-calls" class="text-4xl md:text-5xl font-extrabold tracking-tight text-emerald-400 font-mono">0</h2>
                    <p class="text-xs text-emerald-500/80 mt-2 font-semibold flex items-center gap-1">
                        <i data-lucide="shield-check" class="h-3.5 w-3.5"></i>
                        <span>Scheme check or doc list provided</span>
                    </p>
                </div>
            </div>

            <!-- Failed Calls Card -->
            <div class="glass-panel rounded-3xl p-6 relative overflow-hidden transition-all duration-300 hover:scale-[1.02] group">
                <div class="absolute -right-4 -bottom-4 opacity-5 group-hover:opacity-10 transition-opacity duration-300">
                    <i data-lucide="x-circle" class="h-32 w-32 text-rose-500"></i>
                </div>
                <div class="flex items-center justify-between">
                    <span class="text-xs text-slate-400 font-semibold uppercase tracking-wider">Failed Calls</span>
                    <div class="h-9 w-9 rounded-xl bg-rose-500/10 border border-rose-500/25 flex items-center justify-center text-rose-400">
                        <i data-lucide="phone-off" class="h-4.5 w-4.5"></i>
                    </div>
                </div>
                <div class="mt-4">
                    <h2 id="failed-calls" class="text-4xl md:text-5xl font-extrabold tracking-tight text-rose-400 font-mono">0</h2>
                    <p class="text-xs text-rose-400/80 mt-2 font-semibold flex items-center gap-1">
                        <i data-lucide="shield-alert" class="h-3.5 w-3.5"></i>
                        <span>Incomplete or ended early</span>
                    </p>
                </div>
            </div>
        </section>

        <!-- Calls Logs Section -->
        <section class="glass-panel rounded-3xl overflow-hidden border border-slate-800">
            <div class="p-6 border-b border-slate-800 flex items-center justify-between bg-slate-900/30">
                <div class="flex items-center gap-2.5">
                    <div class="h-8 w-8 rounded-lg bg-teal-500/10 flex items-center justify-center text-teal-400">
                        <i data-lucide="history" class="h-4 w-4"></i>
                    </div>
                    <div>
                        <h3 class="text-sm font-bold">Recent Call Logs</h3>
                        <p class="text-[11px] text-slate-500">Real-time listing of recent transactions</p>
                    </div>
                </div>
                <span class="text-[10px] text-slate-400 font-medium px-2 py-1 rounded bg-slate-800">Limit: 10 calls</span>
            </div>

            <!-- Table Container -->
            <div class="overflow-x-auto w-full">
                <table class="w-full text-left border-collapse">
                    <thead>
                        <tr class="border-b border-slate-800 text-[10px] text-slate-400 font-semibold uppercase tracking-wider bg-slate-950/20">
                            <th class="py-4 px-6">Timestamp</th>
                            <th class="py-4 px-6">Call ID</th>
                            <th class="py-4 px-6">Channel</th>
                            <th class="py-4 px-6">Outcome</th>
                        </tr>
                    </thead>
                    <tbody id="call-logs-body" class="divide-y divide-slate-800/50 text-sm">
                        <!-- Dynamic Rows Inject here -->
                        <tr>
                            <td colspan="4" class="py-8 text-center text-slate-500">
                                <div class="flex flex-col items-center justify-center gap-2">
                                    <i data-lucide="loader-2" class="h-5 w-5 animate-spin text-teal-500"></i>
                                    <span>Fetching records...</span>
                                </div>
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </section>

    </main>

    <!-- Footer -->
    <footer class="border-t border-slate-900 bg-slate-950/80 py-6 px-6 text-center text-xs text-slate-600 font-medium mt-auto">
        <div class="max-w-6xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
            <p>DhanaMitra Financial Services &copy; 2026. All analytics data is anonymized.</p>
            <div class="flex items-center gap-2 text-[11px]">
                <i data-lucide="shield-check" class="h-3.5 w-3.5 text-teal-500"></i>
                <span>Strict Security Compliance (Day 8 Sandbox Mode)</span>
            </div>
        </div>
    </footer>

    <!-- Scripting for UI and Polling -->
    <script>
        function formatLocalTime(isoStr) {
            try {
                const dt = new Date(isoStr);
                return dt.toLocaleString();
            } catch (e) {
                return isoStr;
            }
        }

        async function fetchMetrics() {
            const counterEl = document.getElementById("refresh-counter");
            try {
                const response = await fetch("/api/metrics");
                if (!response.ok) throw new Error("API error");
                const data = await response.json();
                
                // Update Metrics Card Values
                document.getElementById("total-calls").innerText = data.metrics.total_calls;
                document.getElementById("successful-calls").innerText = data.metrics.successful_calls;
                document.getElementById("failed-calls").innerText = data.metrics.failed_calls;
                
                // Update Call Table
                const tbody = document.getElementById("call-logs-body");
                if (data.recent_calls.length === 0) {
                    tbody.innerHTML = `
                        <tr>
                            <td colspan="4" class="py-8 text-center text-slate-500 font-medium">
                                <div class="flex flex-col items-center justify-center gap-2">
                                    <i data-lucide="phone-off" class="h-5 w-5 text-slate-600"></i>
                                    <span>No calls recorded yet. Perform a call to see stats.</span>
                                </div>
                            </td>
                        </tr>
                    `;
                } else {
                    tbody.innerHTML = data.recent_calls.map(call => {
                        const isSuccess = call.outcome === "SUCCESS";
                        const isSip = call.channel.toUpperCase() === "SIP";
                        
                        const outcomeBadge = isSuccess 
                            ? `<span class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"><span class="h-1.5 w-1.5 rounded-full bg-emerald-400"></span>SUCCESS</span>`
                            : `<span class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-500/10 text-rose-400 border border-rose-500/20"><span class="h-1.5 w-1.5 rounded-full bg-rose-400"></span>FAILED</span>`;
                            
                        const channelBadge = isSip
                            ? `<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-lg text-xs font-medium bg-purple-500/10 text-purple-300 border border-purple-500/20">SIP / Telephony</span>`
                            : `<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-lg text-xs font-medium bg-sky-500/10 text-sky-300 border border-sky-500/20">Web Browser</span>`;
                        
                        return `
                            <tr class="hover:bg-slate-900/20 transition-colors duration-150">
                                <td class="py-4 px-6 text-slate-300 font-mono text-xs">${formatLocalTime(call.timestamp)}</td>
                                <td class="py-4 px-6 text-slate-400 font-mono text-xs select-all">${call.call_id}</td>
                                <td class="py-4 px-6">${channelBadge}</td>
                                <td class="py-4 px-6">${outcomeBadge}</td>
                            </tr>
                        `;
                    }).join("");
                }
                
                lucide.createIcons();
                
                const now = new Date();
                counterEl.innerText = "Last checked: " + now.toLocaleTimeString();
            } catch (err) {
                console.error("Failed fetching metrics:", err);
                counterEl.innerText = "Connection lost";
            }
        }

        // Run immediately and poll every 2.5 seconds
        fetchMetrics();
        setInterval(fetchMetrics, 2500);
        
        // Initial icon load
        lucide.createIcons();
    </script>
</body>
</html>
"""
            self.wfile.write(html_content.encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

def run(port=8000):
    server_address = ("", port)
    httpd = HTTPServer(server_address, DashboardHandler)
    print(f"Starting dashboard server on port {port}...")
    print(f"Open http://localhost:{port}/ in your browser.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\\nStopping dashboard server.")

if __name__ == "__main__":
    run()
