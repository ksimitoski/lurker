import os
# pyrefly: ignore [missing-import]
import pytest
import tempfile
import shutil
import json
import urllib.parse
from io import BytesIO
from unittest.mock import MagicMock, patch
import lurker_web

# Mock Request class for testing BaseHTTPRequestHandler synchronously
class MockRequest:
    def __init__(self, request_bytes):
        self.rfile = BytesIO(request_bytes)
        self.wfile = BytesIO()

    def makefile(self, mode, *args, **kwargs):
        if 'r' in mode:
            return self.rfile
        elif 'w' in mode:
            return self.wfile

    def sendall(self, data):
        self.wfile.write(data)

class MockServer:
    def __init__(self):
        self.server_address = ('127.0.0.1', 8080)

def simulate_request(handler_class, method, path, headers=None):
    req_line = f"{method} {path} HTTP/1.1\r\n"
    header_lines = ""
    if headers:
        for k, v in headers.items():
            header_lines += f"{k}: {v}\r\n"
    request_data = (req_line + header_lines + "\r\n").encode('utf-8')
    
    mock_request = MockRequest(request_data)
    # The constructor processes the request synchronously and returns
    handler_class(mock_request, ('127.0.0.1', 12345), MockServer())
    
    mock_request.wfile.seek(0)
    return mock_request.wfile.read()

@pytest.fixture
def temp_output_dir():
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)

def test_format_size():
    assert lurker_web.format_size(0) == "0 Bytes"
    assert lurker_web.format_size(512) == "512.00 Bytes"
    assert lurker_web.format_size(1024) == "1.00 KB"
    assert lurker_web.format_size(1024 * 1024) == "1.00 MB"
    assert lurker_web.format_size(1024 * 1024 * 1024) == "1.00 GB"
    assert lurker_web.format_size(1024 * 1024 * 1024 * 1024) == "1.00 TB"

def test_detect_file_type_magic_bytes(temp_output_dir):
    test_cases = [
        (b"\x89PNG\r\n\x1a\n" + b"some png data", "PNG Image"),
        (b"\xff\xd8\xff" + b"some jpeg data", "JPEG Image"),
        (b"GIF87a" + b"some gif data", "GIF Image"),
        (b"GIF89a" + b"some gif data", "GIF Image"),
        (b"%PDF-1.4" + b"some pdf data", "PDF Document"),
        (b"PK\x03\x04" + b"some zip data", "ZIP Archive"),
        (b"\x1f\x8b" + b"some gzip data", "GZIP Archive"),
        (b"\x7fELF" + b"some elf data", "ELF Executable"),
        (b"MZ" + b"some windows data", "Windows Executable"),
        (b"BM" + b"some bmp data", "BMP Image"),
        (b"ID3" + b"some mp3 data", "MP3 Audio"),
        (b"\xff\xfb" + b"some mp3 data", "MP3 Audio"),
        (b"xxxxftypmp42" + b"some mp4 data", "MP4 Video"),
        (b"OggS" + b"some ogg data", "Ogg Media"),
        (b"\x1a\x45\xdf\xa3" + b"some webm data", "MKV/WebM Video"),
        (b"RIFFxxxxWAVE" + b"some wav data", "WAV Audio"),
    ]

    for magic, expected_type in test_cases:
        path = os.path.join(temp_output_dir, "temp_magic")
        with open(path, "wb") as f:
            f.write(magic)
        assert lurker_web.detect_file_type(path) == expected_type

def test_detect_file_type_text(temp_output_dir):
    # HTML
    path = os.path.join(temp_output_dir, "temp_html")
    with open(path, "w", encoding="utf-8") as f:
        f.write("<!DOCTYPE html><html></html>")
    assert lurker_web.detect_file_type(path) == "HTML Document"

    # XML
    path = os.path.join(temp_output_dir, "temp_xml")
    with open(path, "w", encoding="utf-8") as f:
        f.write("<?xml version='1.0'?><root></root>")
    assert lurker_web.detect_file_type(path) == "XML Document"

    # Python Shebang
    path = os.path.join(temp_output_dir, "temp_py")
    with open(path, "w", encoding="utf-8") as f:
        f.write("#!/usr/bin/env python\nprint('hello')")
    assert lurker_web.detect_file_type(path) == "Python Script"

    # Shell Shebang
    path = os.path.join(temp_output_dir, "temp_sh")
    with open(path, "w", encoding="utf-8") as f:
        f.write("#!/bin/bash\necho 'hello'")
    assert lurker_web.detect_file_type(path) == "Shell Script"

    # Generic Shebang
    path = os.path.join(temp_output_dir, "temp_exec")
    with open(path, "w", encoding="utf-8") as f:
        f.write("#!/usr/bin/custom-exec\n")
    assert lurker_web.detect_file_type(path) == "Executable Script"

    # JSON Document (small)
    path = os.path.join(temp_output_dir, "temp_json")
    with open(path, "w", encoding="utf-8") as f:
        f.write('{"key": "value"}')
    assert lurker_web.detect_file_type(path) == "JSON Document"

    # Plain Text
    path = os.path.join(temp_output_dir, "temp_text")
    with open(path, "w", encoding="utf-8") as f:
        f.write("Hello simple plain text file.")
    assert lurker_web.detect_file_type(path) == "Plain Text"

    # Binary Data (non-printable chars)
    path = os.path.join(temp_output_dir, "temp_binary")
    with open(path, "wb") as f:
        f.write(b"Hello\x00Binary\x01Data")
    assert lurker_web.detect_file_type(path) == "Binary Data"

    # Empty File
    path = os.path.join(temp_output_dir, "temp_empty")
    with open(path, "wb") as f:
        pass
    assert lurker_web.detect_file_type(path) == "Empty File"

    # Missing File
    assert lurker_web.detect_file_type(os.path.join(temp_output_dir, "nonexistent")) == "Unknown"

def test_web_handler_dashboard_empty(temp_output_dir):
    handler_class = lurker_web.make_handler(temp_output_dir)
    response = simulate_request(handler_class, "GET", "/")
    
    assert b"200 OK" in response
    assert b"Lurker Dashboard" in response
    assert b"0 Files Available" in response
    assert b"No files uploaded yet." in response

def test_web_handler_dashboard_with_files(temp_output_dir):
    # Pre-create couple of files
    file1_path = os.path.join(temp_output_dir, "uuid-file-test1.txt")
    with open(file1_path, "wb") as f:
        f.write(b"Hello from file 1")
    
    file2_path = os.path.join(temp_output_dir, "uuid-file-test2.png")
    with open(file2_path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")

    handler_class = lurker_web.make_handler(temp_output_dir)
    response = simulate_request(handler_class, "GET", "/")
    
    assert b"200 OK" in response
    assert b"2 Files Available" in response
    assert b"test1.txt" in response
    assert b"test2.png" in response
    assert b"PNG Image" in response
    assert b"Plain Text" in response

def test_web_handler_download_success(temp_output_dir):
    file_content = b"Some data to download"
    filename = "test-download-file"
    with open(os.path.join(temp_output_dir, filename), "wb") as f:
        f.write(file_content)

    handler_class = lurker_web.make_handler(temp_output_dir)
    response = simulate_request(handler_class, "GET", f"/download/{filename}")

    assert b"200 OK" in response
    assert b"Content-Type: application/octet-stream" in response
    assert f'Content-Disposition: attachment; filename="{filename}"'.encode() in response
    assert f"Content-Length: {len(file_content)}".encode() in response
    assert response.endswith(file_content)

def test_web_handler_download_not_found(temp_output_dir):
    handler_class = lurker_web.make_handler(temp_output_dir)
    response = simulate_request(handler_class, "GET", "/download/non-existent-file")

    assert b"404 File Not Found" in response

def test_web_handler_download_directory_traversal(temp_output_dir):
    handler_class = lurker_web.make_handler(temp_output_dir)
    
    # 1. Test empty, "." and ".." filenames return 400 Bad Request
    response_dot = simulate_request(handler_class, "GET", "/download/.")
    assert b"400 Bad Request" in response_dot

    response_dotdot = simulate_request(handler_class, "GET", "/download/..")
    assert b"400 Bad Request" in response_dotdot

    # 2. Test directory traversal attempt using ".." in path.
    # Create a file in the parent directory of temp_output_dir
    parent_dir = os.path.dirname(temp_output_dir)
    secret_filename = "secret_traversal_test.txt"
    secret_file_path = os.path.join(parent_dir, secret_filename)
    with open(secret_file_path, "wb") as f:
        f.write(b"this is a secret")

    try:
        # Try to download using relative traversal path
        response = simulate_request(handler_class, "GET", f"/download/../{secret_filename}")
        # The basename function will strip "../" and look for "secret_traversal_test.txt" inside temp_output_dir.
        # Since it does not exist there, it should return 404, preventing access to the parent directory file.
        assert b"404 File Not Found" in response
        assert b"this is a secret" not in response
    finally:
        if os.path.exists(secret_file_path):
            os.remove(secret_file_path)

def test_web_handler_not_found_route(temp_output_dir):
    handler_class = lurker_web.make_handler(temp_output_dir)
    response = simulate_request(handler_class, "GET", "/unknown-route")
    assert b"404 File Not Found" in response

@patch("lurker_web.run_tcp_server")
@patch("lurker_web.ThreadingHTTPServer")
def test_main_startup(mock_http_server_class, mock_run_tcp_server):
    env = {
        "LURKER_PORT": "7777",
        "LURKER_WEB_PORT": "8080",
        "LURKER_HOST": "127.0.0.1",
        "LURKER_OUTPUT_DIR": "./received_test"
    }

    mock_httpd = MagicMock()
    mock_http_server_class.return_value = mock_httpd
    # Interrupt serve_forever to stop main gracefully
    mock_httpd.serve_forever.side_effect = KeyboardInterrupt()

    with patch.dict(os.environ, env):
        with patch("os.makedirs") as mock_makedirs:
            lurker_web.main()
            mock_makedirs.assert_called_with("./received_test", exist_ok=True)
            mock_http_server_class.assert_called_once()
            mock_httpd.serve_forever.assert_called_once()
            mock_httpd.server_close.assert_called_once()
