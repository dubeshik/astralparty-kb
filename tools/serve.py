#!/usr/bin/env python3
"""启动本地静态服务器，供浏览器访问知识库查看器。"""
import http.server
import os
import socketserver
import webbrowser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 8765

os.chdir(ROOT)


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    url = f"http://127.0.0.1:{PORT}/viewer/index.html"
    print(f"知识库已启动：{url}\n按 Ctrl+C 停止", flush=True)
    try:
        with Server(("127.0.0.1", PORT), Handler) as httpd:
            webbrowser.open(url)
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
