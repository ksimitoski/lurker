import os
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

def simulate_post_request(handler_class, path, body_params=None, headers=None):
    if headers is None:
        headers = {}
    
    body_bytes = b""
    if body_params:
        body_str = urllib.parse.urlencode(body_params, doseq=True)
        body_bytes = body_str.encode('utf-8')
        headers["Content-Length"] = str(len(body_bytes))
        headers["Content-Type"] = "application/x-www-form-urlencoded"

    req_line = f"POST {path} HTTP/1.1\r\n"
    header_lines = ""
    for k, v in headers.items():
        header_lines += f"{k}: {v}\r\n"
        
    request_data = (req_line + header_lines + "\r\n").encode('utf-8') + body_bytes
    
    mock_request = MockRequest(request_data)
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
    handler_class = lurker_web.make_handler(temp_output_dir, False, "")
    response = simulate_request(handler_class, "GET", "/")
    
    assert b"200 OK" in response
    assert b"Lurker Dashboard" in response
    assert b"0 Files" in response
    assert b"No files uploaded yet." in response

def test_web_handler_dashboard_with_files(temp_output_dir):
    # Pre-create couple of files
    file1_path = os.path.join(temp_output_dir, "uuid-file-test1.txt")
    with open(file1_path, "wb") as f:
        f.write(b"Hello from file 1")
    
    file2_path = os.path.join(temp_output_dir, "uuid-file-test2.png")
    with open(file2_path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")

    handler_class = lurker_web.make_handler(temp_output_dir, False, "")
    response = simulate_request(handler_class, "GET", "/")
    
    assert b"200 OK" in response
    assert b"2 Files" in response
    assert b"test1.txt" in response
    assert b"test2.png" in response
    assert b"PNG Image" in response
    assert b"Plain Text" in response

def test_web_handler_download_success(temp_output_dir):
    file_content = b"Some data to download"
    filename = "test-download-file"
    with open(os.path.join(temp_output_dir, filename), "wb") as f:
        f.write(file_content)

    handler_class = lurker_web.make_handler(temp_output_dir, False, "")
    response = simulate_request(handler_class, "GET", f"/download/{filename}")

    assert b"200 OK" in response
    assert b"Content-Type: application/octet-stream" in response
    assert f'Content-Disposition: attachment; filename="{filename}"'.encode() in response
    assert f"Content-Length: {len(file_content)}".encode() in response
    assert response.endswith(file_content)

def test_web_handler_download_not_found(temp_output_dir):
    handler_class = lurker_web.make_handler(temp_output_dir, False, "")
    response = simulate_request(handler_class, "GET", "/download/non-existent-file")

    assert b"404 File Not Found" in response

def test_web_handler_download_directory_traversal(temp_output_dir):
    handler_class = lurker_web.make_handler(temp_output_dir, False, "")
    
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
    handler_class = lurker_web.make_handler(temp_output_dir, False, "")
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

def test_web_handler_delete_single_success(temp_output_dir):
    filename = "test-delete-file"
    file_path = os.path.join(temp_output_dir, filename)
    with open(file_path, "wb") as f:
        f.write(b"content")

    assert os.path.exists(file_path)

    handler_class = lurker_web.make_handler(temp_output_dir, False, "")
    response = simulate_post_request(handler_class, "/delete-single", {"delete_single": [filename]})

    assert b"303 See Other" in response or b"303" in response
    assert not os.path.exists(file_path)

def test_web_handler_delete_single_missing(temp_output_dir):
    handler_class = lurker_web.make_handler(temp_output_dir, False, "")
    response = simulate_post_request(handler_class, "/delete-single", {"delete_single": ["non-existent"]})

    assert b"404 File Not Found" in response

def test_web_handler_delete_single_traversal(temp_output_dir):
    # Try directory traversal using path component
    handler_class = lurker_web.make_handler(temp_output_dir, False, "")
    
    # 1. Dot path
    response = simulate_post_request(handler_class, "/delete-single", {"delete_single": ["."]})
    assert b"400 Bad Request" in response

    # 2. Directory traversal attempt
    parent_dir = os.path.dirname(temp_output_dir)
    secret_filename = "secret_delete_test.txt"
    secret_file_path = os.path.join(parent_dir, secret_filename)
    with open(secret_file_path, "wb") as f:
        f.write(b"secret content")

    try:
        # Try to delete using relative path traversal
        response = simulate_post_request(handler_class, "/delete-single", {"delete_single": [f"../{secret_filename}"]})
        # Basename will strip and seek within temp_output_dir, failing with 404 since it's not there
        assert b"404" in response
        assert os.path.exists(secret_file_path)
    finally:
        if os.path.exists(secret_file_path):
            os.remove(secret_file_path)

def test_web_handler_delete_selected_success(temp_output_dir):
    file1 = "file1.txt"
    file2 = "file2.txt"
    path1 = os.path.join(temp_output_dir, file1)
    path2 = os.path.join(temp_output_dir, file2)
    
    with open(path1, "wb") as f: f.write(b"one")
    with open(path2, "wb") as f: f.write(b"two")

    handler_class = lurker_web.make_handler(temp_output_dir, False, "")
    response = simulate_post_request(handler_class, "/delete-selected", {"files": [file1, file2]})

    assert b"303" in response
    assert not os.path.exists(path1)
    assert not os.path.exists(path2)

def test_web_handler_download_selected_zip_success(temp_output_dir):
    file1 = "uuid-file1.txt"
    file2 = "uuid-file2.png"
    path1 = os.path.join(temp_output_dir, file1)
    path2 = os.path.join(temp_output_dir, file2)
    
    with open(path1, "wb") as f: f.write(b"content 1")
    with open(path2, "wb") as f: f.write(b"content 2")

    handler_class = lurker_web.make_handler(temp_output_dir, False, "")
    response = simulate_post_request(handler_class, "/download-selected", {"files": [file1, file2]})

    assert b"200 OK" in response
    assert b"Content-Type: application/zip" in response
    assert b"Content-Disposition: attachment; filename=" in response

    # Parse response to find zip file bytes
    parts = response.split(b"\r\n\r\n", 1)
    assert len(parts) == 2
    zip_bytes = parts[1]

    # Verify zip content
    import zipfile
    import io
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        # Files should be stored under full filename (uuid-file1.txt, uuid-file2.png)
        namelist = z.namelist()
        assert "uuid-file1.txt" in namelist
        assert "uuid-file2.png" in namelist
        assert z.read("uuid-file1.txt") == b"content 1"
        assert z.read("uuid-file2.png") == b"content 2"

def test_web_handler_download_selected_zip_empty(temp_output_dir):
    handler_class = lurker_web.make_handler(temp_output_dir, False, "")
    response = simulate_post_request(handler_class, "/download-selected", {"files": []})

    assert b"400" in response
