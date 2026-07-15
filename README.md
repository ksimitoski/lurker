# Lurker 🕵️‍♂️

A lightweight, zero-dependency TCP file receiver with an integrated modern web dashboard. 

Lurker is designed for quick and easy file or log exfiltration and transfers over raw TCP connections. It accepts incoming TCP streams concurrently and saves them as uniquely named files. The integrated web dashboard provides a clean user interface to browse, inspect, and download the received files.

---

## Features

- **Zero Dependencies**: Written purely in Python using the standard library. No packages to install.
- **Concurrent TCP File Receiver**: Listens on a custom port and handles multiple concurrent connections using multithreading.
- **Auto-Generating Unique Names**: Automatically saves each received stream as a unique UUID file.
- **Elegant Web Dashboard**: Built-in HTTP server serving a sleek, dark-themed dashboard to view, sort, and download received files.
- **Docker Ready**: Includes a lightweight `Dockerfile` based on `python:3.11-slim` for easy deployments.
- **Highly Configurable**: Customizable via standard environment variables.

---

## How It Works

The project contains two main executable scripts:

1. **[lurker.py](file:///home/mryuck/projects/python/lurker/lurker.py)**: The raw TCP listener. When run, it listens for incoming connections on a port (default: `7777`) and saves the exact bytes sent by clients directly into the output directory.
2. **[lurker_web.py](file:///home/mryuck/projects/python/lurker/lurker_web.py)**: The complete package. It starts the TCP listener in a background thread and runs a concurrent web server (default: `8080`) on the main thread to serve the files dashboard.

---

## Configuration

Lurker can be customized using the following environment variables:

| Environment Variable | Description | Default Value |
| :--- | :--- | :--- |
| `LURKER_HOST` | Host address to bind the servers to | `0.0.0.0` |
| `LURKER_PORT` | Port for the TCP file receiver listener | `7777` |
| `LURKER_WEB_PORT` | Port for the HTTP web dashboard | `8080` |
| `LURKER_OUTPUT_DIR` | Directory where received files are saved | `./received` (or `/data` in Docker) |

---

## Getting Started

### Method 1: Running with Python locally

Start the full application (TCP listener + Web Dashboard):

```bash
python lurker_web.py
```

If you only want the TCP listener (without the web dashboard interface):

```bash
python lurker.py
```

### Method 2: Running with Docker

1. **Build the Docker Image**:
   ```bash
   docker build -t lurker .
   ```

2. **Run the Container**:
   Make sure to map the TCP listener and Web Dashboard ports, and mount a volume for persisting files:
   ```bash
   docker run -d \
     -p 7777:7777 \
     -p 8080:8080 \
     -v $(pwd)/received:/data \
     --name lurker \
     lurker
   ```

---

## Client Usage Examples

Once Lurker is running, you can stream files, command output, or any raw data to the listener from any network-reachable client.

### 1. Using Netcat (`nc`)

Send a local file:
```bash
nc <lurker-ip> 7777 < my-file.txt
```

Stream command output:
```bash
uname -a | nc <lurker-ip> 7777
```

### 2. Using Bash redirect (No tools required)

If the client machine doesn't have `nc` installed, you can use Bash's built-in socket redirect:
```bash
cat my-file.txt > /dev/tcp/<lurker-ip>/7777
```

### 3. Using Python on the client

Send data programmatically or from a quick Python command:
```python
import socket

# Send file content
with open("my-file.txt", "rb") as f:
    data = f.read()

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect(("<lurker-ip>", 7777))
s.sendall(data)
s.close()
```

---

## Dashboard Interface

Once files have been received, navigate to the web dashboard:

```
http://localhost:8080
```

The web dashboard displays:
- Total number of files available.
- Filename (UUID).
- File Type (automatically detected using magic bytes and heuristics).
- File size (automatically formatted as KB, MB, etc.).
- File upload/modification timestamp.
- Download buttons for each file.
