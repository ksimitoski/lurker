import os
import socket
import sys
import uuid
import logging
import threading
import zipfile
import io
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import urllib.parse
from datetime import datetime

# Configure logging to stdout
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("lurker-web")

def format_size(size_bytes):
    """Formats bytes to a human-readable string."""
    if size_bytes == 0:
        return "0 Bytes"
    units = ["Bytes", "KB", "MB", "GB", "TB"]
    i = 0
    while size_bytes >= 1024 and i < len(units) - 1:
        size_bytes /= 1024.0
        i += 1
    return f"{size_bytes:.2f} {units[i]}"

def detect_file_type(file_path):
    """Detects the file type of a file without extension by reading magic bytes and using heuristics."""
    try:
        with open(file_path, "rb") as f:
            header = f.read(512)
    except Exception:
        return "Unknown"

    if not header:
        return "Empty File"

    # Check common magic bytes/signatures
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG Image"
    if header.startswith(b"\xff\xd8\xff"):
        return "JPEG Image"
    if header.startswith(b"GIF87a") or header.startswith(b"GIF89a"):
        return "GIF Image"
    if header.startswith(b"%PDF-"):
        return "PDF Document"
    if header.startswith(b"PK\x03\x04"):
        return "ZIP Archive"
    if header.startswith(b"\x1f\x8b"):
        return "GZIP Archive"
    if header.startswith(b"\x7fELF"):
        return "ELF Executable"
    if header.startswith(b"MZ"):
        return "Windows Executable"
    if header.startswith(b"BM"):
        return "BMP Image"
    if header.startswith(b"ID3") or header.startswith(b"\xff\xfb") or header.startswith(b"\xff\xf3") or header.startswith(b"\xff\xf2"):
        return "MP3 Audio"
    if len(header) >= 12 and header[4:8] == b"ftyp":
        return "MP4 Video"
    if header.startswith(b"OggS"):
        return "Ogg Media"
    if header.startswith(b"\x1a\x45\xdf\xa3"):
        return "MKV/WebM Video"
    if header.startswith(b"RIFF") and len(header) >= 12 and header[8:12] == b"WAVE":
        return "WAV Audio"

    # Check text-based files
    try:
        text = header.decode("utf-8", errors="strict")
        stripped = text.strip()
        if stripped.lower().startswith("<!doctype html") or stripped.lower().startswith("<html"):
            return "HTML Document"
        if stripped.lower().startswith("<?xml"):
            return "XML Document"
        
        # Check executable scripts starting with shebang
        if stripped.startswith("#!"):
            line = stripped.split("\n", 1)[0]
            if "python" in line:
                return "Python Script"
            if "bash" in line or "sh" in line:
                return "Shell Script"
            return "Executable Script"

        # Check for JSON syntax in the header or attempt parsing full file if small
        if stripped.startswith("{") or stripped.startswith("["):
            import json
            try:
                # Try parsing header string as JSON (might succeed if small JSON)
                json.loads(text)
                return "JSON Document"
            except Exception:
                # If it's a small file (< 64KB), we can parse the whole file to confirm JSON
                try:
                    file_size = os.path.getsize(file_path)
                    if file_size < 65536:
                        with open(file_path, "r", encoding="utf-8") as f_text:
                            json.load(f_text)
                        return "JSON Document"
                except Exception:
                    pass

        # Ensure text is printable
        non_printable = 0
        for char in text:
            o = ord(char)
            # Allow common control characters: tab, newline, carriage return
            if o < 32 and o not in (9, 10, 13):
                non_printable += 1
        if non_printable == 0:
            return "Plain Text"
    except UnicodeDecodeError:
        pass

    return "Binary Data"

def handle_client(client_socket, client_address, output_dir):
    logger.info(f"Connection accepted from {client_address}")

    # Generate a random UUID for the filename
    file_uuid = str(uuid.uuid4())

    # Check if path already exists
    while os.path.isfile(os.path.join(output_dir, file_uuid)):
        file_uuid = str(uuid.uuid4())

    # Set final file path
    file_path = os.path.join(output_dir, file_uuid)

    # Receive file chunk by chunk
    try:
        with open(file_path, "wb") as f:
            while True:
                data = client_socket.recv(4096)
                if not data:
                    # EOF
                    break
                f.write(data)
        
        logger.info(f"File transfer complete. Saved to {file_path}")
    except Exception as e:
        logger.error(f"Error during file transfer from {client_address}: {e}")
        # Clean up the file if it was partially written
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info("Removed incomplete/failed file.")
            except Exception as cleanup_err:
                logger.error(f"Failed to clean up incomplete file: {cleanup_err}")
    finally:
        client_socket.close()
        logger.info(f"Client connection closed for {client_address}.")

def run_tcp_server(host, port, output_dir):
    # Set up TCP socket
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        server_socket.bind((host, port))
        server_socket.listen()
        logger.info(f"Lurker TCP listener running on {host}:{port}, saving files to {output_dir}")
    except Exception as e:
        logger.error(f"Failed to bind TCP server to {host}:{port}: {e}")
        return

    try:
        while True:
            client_socket, client_address = server_socket.accept()
            client_thread = threading.Thread(
                target=handle_client,
                args=(client_socket, client_address, output_dir),
                daemon=True
            )
            client_thread.start()
    except Exception as e:
        logger.error(f"TCP server error: {e}")
    finally:
        server_socket.close()
        logger.info("TCP server socket closed.")

# HTML/CSS Templates
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Lurker - File Dashboard</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-color: #0b0f19;
            --card-bg: #111827;
            --border-color: #1f2937;
            --text-primary: #f3f4f6;
            --text-secondary: #9ca3af;
            --accent-color: #3b82f6;
            --accent-hover: #2563eb;
            --accent-glow: rgba(59, 130, 246, 0.15);
            --danger-color: #ef4444;
            --danger-hover: #dc2626;
            --danger-glow: rgba(239, 68, 68, 0.15);
            --row-hover: #1f2937;
        }}

        body {{
            background-color: var(--bg-color);
            color: var(--text-primary);
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            margin: 0;
            padding: 2rem;
            display: flex;
            justify-content: center;
            align-items: flex-start;
            min-height: 100vh;
        }}

        .container {{
            width: 100%;
            max-width: 1000px;
            margin: 0 auto;
        }}

        header {{
            margin-bottom: 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        h1 {{
            font-size: 1.8rem;
            font-weight: 700;
            margin: 0;
            background: linear-gradient(135deg, #60a5fa, #3b82f6);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }}

        .stats-badge {{
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            padding: 0.5rem 1rem;
            border-radius: 9999px;
            font-size: 0.85rem;
            color: var(--text-secondary);
            font-weight: 500;
        }}

        .actions-bar {{
            display: none;
            align-items: center;
            justify-content: space-between;
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 1rem 1.5rem;
            margin-bottom: 1.5rem;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
        }}

        .actions-bar.active {{
            display: flex;
            animation: fadeIn 0.2s ease;
        }}

        .actions-buttons {{
            display: flex;
            gap: 0.75rem;
        }}

        .selected-count {{
            font-size: 0.9rem;
            color: var(--text-secondary);
            font-weight: 500;
        }}

        .action-btn {{
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            color: white;
            border: none;
            padding: 0.6rem 1.2rem;
            border-radius: 6px;
            font-size: 0.85rem;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s ease;
        }}

        .download-selected-btn {{
            background-color: var(--accent-color);
        }}

        .download-selected-btn:hover {{
            background-color: var(--accent-hover);
            transform: translateY(-1px);
            box-shadow: 0 4px 12px var(--accent-glow);
        }}

        .delete-selected-btn {{
            background-color: var(--danger-color);
        }}

        .delete-selected-btn:hover {{
            background-color: var(--danger-hover);
            transform: translateY(-1px);
            box-shadow: 0 4px 12px var(--danger-glow);
        }}

        .table-container {{
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
        }}

        .div-table {{
            display: flex;
            flex-direction: column;
            width: 100%;
        }}

        .div-table-header {{
            display: grid;
            grid-template-columns: 60px 2fr 1.2fr 0.8fr 1.2fr 1.8fr;
            padding: 1rem 1.5rem;
            background-color: rgba(255, 255, 255, 0.02);
            border-bottom: 1px solid var(--border-color);
            font-weight: 600;
            font-size: 0.85rem;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            align-items: center;
        }}

        .div-table-row {{
            display: grid;
            grid-template-columns: 60px 2fr 1.2fr 0.8fr 1.2fr 1.8fr;
            padding: 1.2rem 1.5rem;
            border-bottom: 1px solid var(--border-color);
            align-items: center;
            transition: all 0.2s ease;
        }}

        .div-table-row:last-child {{
            border-bottom: none;
        }}

        .div-table-row:hover {{
            background-color: var(--row-hover);
            box-shadow: inset 4px 0 0 var(--accent-color);
        }}

        .checkbox-cell {{
            display: flex;
            align-items: center;
            justify-content: flex-start;
        }}

        input[type="checkbox"] {{
            appearance: none;
            -webkit-appearance: none;
            width: 18px;
            height: 18px;
            border: 2px solid var(--border-color);
            border-radius: 4px;
            background-color: transparent;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            transition: all 0.2s ease;
            position: relative;
        }}

        input[type="checkbox"]:checked {{
            background-color: var(--accent-color);
            border-color: var(--accent-color);
        }}

        input[type="checkbox"]:checked::after {{
            content: "";
            width: 4px;
            height: 8px;
            border: solid white;
            border-width: 0 2px 2px 0;
            transform: rotate(45deg);
            position: absolute;
            top: 2px;
            left: 5px;
        }}

        input[type="checkbox"]:hover {{
            border-color: var(--accent-color);
            box-shadow: 0 0 8px var(--accent-glow);
        }}

        .file-name-cell {{
            display: flex;
            align-items: center;
            gap: 0.75rem;
            font-weight: 500;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            min-width: 0;
        }}

        .file-icon {{
            color: var(--accent-color);
            flex-shrink: 0;
            display: flex;
            align-items: center;
            justify-content: center;
        }}

        .file-type-cell {{
            color: var(--text-secondary);
            font-size: 0.9rem;
            font-weight: 500;
        }}

        .file-size-cell {{
            color: var(--text-primary);
            font-size: 0.9rem;
        }}

        .file-time-cell {{
            color: var(--text-secondary);
            font-size: 0.9rem;
        }}

        .file-action-cell {{
            display: flex;
            justify-content: flex-start;
            gap: 0.5rem;
        }}

        .download-btn {{
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            background-color: var(--accent-color);
            color: white;
            text-decoration: none;
            padding: 0.5rem 1.2rem;
            border-radius: 6px;
            font-size: 0.85rem;
            font-weight: 500;
            transition: all 0.2s ease;
        }}

        .download-btn:hover {{
            background-color: var(--accent-hover);
            transform: translateY(-1px);
            box-shadow: 0 4px 12px var(--accent-glow);
        }}

        .download-btn:active {{
            transform: translateY(0);
        }}

        .delete-btn-single {{
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            background-color: transparent;
            color: var(--danger-color);
            border: 1px solid var(--danger-color);
            padding: 0.5rem 1.2rem;
            border-radius: 6px;
            font-size: 0.85rem;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s ease;
        }}

        .delete-btn-single:hover {{
            background-color: var(--danger-color);
            color: white;
            transform: translateY(-1px);
            box-shadow: 0 4px 12px var(--danger-glow);
        }}

        .delete-btn-single:active {{
            transform: translateY(0);
        }}

        .empty-state {{
            padding: 5rem 2rem;
            text-align: center;
            color: var(--text-secondary);
        }}

        .empty-icon {{
            font-size: 3rem;
            margin-bottom: 1.2rem;
            color: var(--border-color);
            display: flex;
            justify-content: center;
        }}

        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(-5px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}

        @media (max-width: 768px) {{
            .div-table-header {{
                display: none;
            }}
            .div-table-row {{
                grid-template-columns: 1fr;
                gap: 0.75rem;
                padding: 1.2rem;
            }}
            .file-action-cell {{
                margin-top: 0.25rem;
            }}
            .checkbox-cell {{
                margin-bottom: 0.5rem;
            }}
            .actions-bar {{
                flex-direction: column;
                gap: 1rem;
                align-items: flex-start;
            }}
            .actions-buttons {{
                width: 100%;
                justify-content: space-between;
            }}
        }}
    </style>
    <script>
        function toggleSelectAll(master) {{
            const checkboxes = document.querySelectorAll('input[name="files"]');
            checkboxes.forEach(cb => {{
                cb.checked = master.checked;
            }});
            updateActionsBar();
        }}

        function updateActionsBar() {{
            const checkboxes = document.querySelectorAll('input[name="files"]');
            const checkedCount = Array.from(checkboxes).filter(cb => cb.checked).length;
            const actionsBar = document.getElementById('actions-bar');
            const selectedCount = document.getElementById('selected-count');
            const selectAll = document.getElementById('select-all');
            
            if (selectAll) {{
                selectAll.checked = checkedCount === checkboxes.length && checkboxes.length > 0;
            }}
            
            if (checkedCount > 0) {{
                selectedCount.textContent = checkedCount === 1 ? '1 file selected' : `${{checkedCount}} files selected`;
                actionsBar.classList.add('active');
            }} else {{
                actionsBar.classList.remove('active');
            }}
        }}
    </script>
</head>
<body>
    <div class="container">
        <header>
            <h1>
                <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
                Lurker Dashboard
            </h1>
            <div class="stats-badge">{total_files} Files Available</div>
        </header>

        <form id="files-form" method="POST">
            <div class="actions-bar" id="actions-bar">
                <div class="selected-count" id="selected-count">0 files selected</div>
                <div class="actions-buttons">
                    <button type="submit" formaction="/download-selected" class="action-btn download-selected-btn">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
                        Download Selected
                    </button>
                    <button type="submit" formaction="/delete-selected" class="action-btn delete-selected-btn" onclick="return confirm('Are you sure you want to delete the selected files?');">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
                        Delete Selected
                    </button>
                </div>
            </div>

            <div class="table-container">
                <div class="div-table">
                    {table_content}
                </div>
            </div>
        </form>
    </div>
</body>
</html>
"""

HEADER_HTML = """
<div class="div-table-header">
    <div class="checkbox-cell">
        <input type="checkbox" id="select-all" onclick="toggleSelectAll(this)">
    </div>
    <div>File Name</div>
    <div>File Type</div>
    <div>Size</div>
    <div>Uploaded</div>
    <div>Action</div>
</div>
"""

ROW_HTML = """
<div class="div-table-row">
    <div class="checkbox-cell">
        <input type="checkbox" name="files" value="{filename}" onclick="updateActionsBar()">
    </div>
    <div class="file-name-cell">
        <span class="file-icon">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>
        </span>
        {display_name}
    </div>
    <div class="file-type-cell">{type}</div>
    <div class="file-size-cell">{size}</div>
    <div class="file-time-cell">{time}</div>
    <div class="file-action-cell">
        <a href="/download/{filename}" class="download-btn">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
            Download
        </a>
        <button type="submit" name="delete_single" value="{filename}" formaction="/delete-single" class="delete-btn-single" onclick="return confirm('Are you sure you want to delete this file?');">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
            Delete
        </button>
    </div>
</div>
"""

EMPTY_HTML = """
<div class="empty-state">
    <div class="empty-icon">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>
    </div>
    <p>No files uploaded yet.</p>
</div>
"""

def make_handler(output_dir):
    class LurkerWebHandler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            logger.info("%s - %s" % (self.address_string(), format % args))

        def serve_dashboard(self):
            try:
                # Read all files in the output directory
                files = []
                if os.path.exists(output_dir):
                    for name in os.listdir(output_dir):
                        path = os.path.join(output_dir, name)
                        if os.path.isfile(path):
                            stat = os.stat(path)
                            files.append({
                                'name': name,
                                'type': detect_file_type(path),
                                'size': format_size(stat.st_size),
                                'raw_size': stat.st_size,
                                'mtime': stat.st_mtime,
                                'time': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                            })
                
                # Sort files by modification time descending (newest first)
                files.sort(key=lambda x: x['mtime'], reverse=True)

                if not files:
                    table_content = EMPTY_HTML
                else:
                    rows = [HEADER_HTML]
                    for f in files:
                        display_name = f['name'].split('-')[-1]
                        rows.append(ROW_HTML.format(display_name=display_name, filename=f['name'], type=f['type'], size=f['size'], time=f['time']))
                    table_content = "\n".join(rows)

                html = HTML_TEMPLATE.format(
                    total_files=len(files),
                    table_content=table_content
                )

                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html.encode('utf-8'))))
                self.end_headers()
                self.wfile.write(html.encode('utf-8'))
            except Exception as e:
                logger.error(f"Error serving dashboard: {e}")
                self.send_error(500, "Internal Server Error")

        def serve_file(self, filename):
            # Unquote filename to handle URL-encoded paths
            filename = urllib.parse.unquote(filename)
            # Clean filename to prevent directory traversal
            filename = os.path.basename(filename)
            if not filename or filename == "." or filename == "..":
                self.send_error(400, "Bad Request")
                return

            full_path = os.path.normpath(os.path.join(output_dir, filename))
            # Verify the path is inside output_dir
            if not full_path.startswith(os.path.abspath(output_dir)):
                self.send_error(403, "Forbidden")
                return

            if not os.path.isfile(full_path):
                self.send_error(404, "File Not Found")
                return

            try:
                file_size = os.path.getsize(full_path)
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
                self.send_header("Content-Length", str(file_size))
                self.end_headers()

                with open(full_path, "rb") as f:
                    while True:
                        chunk = f.read(4096)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
            except Exception as e:
                logger.error(f"Error sending file {filename}: {e}")
                try:
                    self.send_error(500, "Internal Server Error")
                except Exception:
                    pass

        def delete_file(self, filename, redirect=True):
            filename = urllib.parse.unquote(filename)
            filename = os.path.basename(filename)
            if not filename or filename in (".", ".."):
                self.send_error(400, "Bad Request")
                return

            full_path = os.path.normpath(os.path.join(output_dir, filename))
            if not full_path.startswith(os.path.abspath(output_dir)):
                self.send_error(403, "Forbidden")
                return

            if not os.path.isfile(full_path):
                if redirect:
                    self.send_error(404, "File Not Found")
                return

            try:
                os.remove(full_path)
                logger.info(f"Deleted file: {filename}")
                if redirect:
                    self.send_response(303)
                    self.send_header("Location", "/")
                    self.end_headers()
            except Exception as e:
                logger.error(f"Error deleting file {filename}: {e}")
                if redirect:
                    self.send_error(500, "Internal Server Error")

        def download_selected_zip(self, filenames):
            if not filenames:
                self.send_error(400, "No files selected")
                return

            zip_buffer = io.BytesIO()
            try:
                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                    for filename in filenames:
                        filename = urllib.parse.unquote(filename)
                        filename = os.path.basename(filename)
                        if not filename or filename in (".", ".."):
                            continue

                        full_path = os.path.normpath(os.path.join(output_dir, filename))
                        if not full_path.startswith(os.path.abspath(output_dir)):
                            continue

                        if os.path.isfile(full_path):
                            zip_file.write(full_path, arcname=filename)

                zip_buffer.seek(0)
                zip_data = zip_buffer.getvalue()
                zip_name = f"lurker_download_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"

                self.send_response(200)
                self.send_header("Content-Type", "application/zip")
                self.send_header("Content-Disposition", f'attachment; filename="{zip_name}"')
                self.send_header("Content-Length", str(len(zip_data)))
                self.end_headers()
                self.wfile.write(zip_data)
            except Exception as e:
                logger.error(f"Error creating zip archive: {e}")
                self.send_error(500, "Internal Server Error")

        def do_GET(self):
            parsed_path = urllib.parse.urlparse(self.path)
            path = parsed_path.path

            if path == "/":
                self.serve_dashboard()
            elif path.startswith("/download/"):
                filename = path[len("/download/"):]
                self.serve_file(filename)
            else:
                self.send_error(404, "File Not Found")

        def do_POST(self):
            parsed_path = urllib.parse.urlparse(self.path)
            path = parsed_path.path

            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            params = urllib.parse.parse_qs(post_data.decode('utf-8'))

            if path == "/delete-single":
                filename_list = params.get('delete_single', [])
                if not filename_list:
                    self.send_error(400, "Bad Request")
                    return
                filename = filename_list[0]
                self.delete_file(filename)
                
            elif path == "/delete-selected":
                filenames = params.get('files', [])
                for filename in filenames:
                    self.delete_file(filename, redirect=False)
                self.send_response(303)
                self.send_header("Location", "/")
                self.end_headers()

            elif path == "/download-selected":
                filenames = params.get('files', [])
                self.download_selected_zip(filenames)

            else:
                self.send_error(404, "File Not Found")

    return LurkerWebHandler

def main():
    # Configuration via environment variables
    port = int(os.environ.get("LURKER_PORT", "7777"))
    web_port = int(os.environ.get("LURKER_WEB_PORT", "8080"))
    host = os.environ.get("LURKER_HOST", "0.0.0.0")
    output_dir = os.environ.get("LURKER_OUTPUT_DIR", "./received")

    # Ensure output directory exists
    try:
        os.makedirs(output_dir, exist_ok=True)
    except Exception as e:
        logger.error(f"Failed to create output directory {output_dir}: {e}")
        sys.exit(1)

    # Start TCP receiver in a background thread
    tcp_thread = threading.Thread(
        target=run_tcp_server,
        args=(host, port, output_dir),
        daemon=True
    )
    tcp_thread.start()

    # Start Web server on the main thread
    server_address = (host, web_port)
    httpd = ThreadingHTTPServer(server_address, make_handler(output_dir))
    logger.info(f"Lurker Web server running on {host}:{web_port}, serving files from {output_dir}")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutdown requested via KeyboardInterrupt.")
    finally:
        httpd.server_close()
        logger.info("Web server stopped.")

if __name__ == "__main__":
    main()
