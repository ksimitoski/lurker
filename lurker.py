import os
import socket
import sys
import uuid
import logging
import threading

# Configure logging to stdout
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("lurker")

def handle_client(client_socket, client_address, output_dir):
    logger.info(f"Connection accepted from {client_address}")

    # Generate a random UUID for the filename
    file_uuid = str(uuid.uuid4())

    # check if path already exists
    while os.path.isfile(os.path.join(output_dir, file_uuid)):
        file_uuid = str(uuid.uuid4())

    # set final file path
    file_path = os.path.join(output_dir, file_uuid)

    # receive file chunk by chunk
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
        # clean up the file if it was partially written
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info("Removed incomplete/failed file.")
            except Exception as cleanup_err:
                logger.error(f"Failed to clean up incomplete file: {cleanup_err}")
    finally:
        client_socket.close()
        logger.info(f"Client connection closed for {client_address}.")

def main():
    # Configuration via environment variables
    port = int(os.environ.get("LURKER_PORT", "7777"))
    host = os.environ.get("LURKER_HOST", "0.0.0.0")
    output_dir = os.environ.get("LURKER_OUTPUT_DIR", "./received")

    # Ensure output directory exists
    try:
        os.makedirs(output_dir, exist_ok=True)
    except Exception as e:
        logger.error(f"Failed to create output directory {output_dir}: {e}")
        sys.exit(1)

    # Set up TCP socket
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # Enable SO_REUSEADDR so we can restart the server immediately without waiting for OS timeout
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        server_socket.bind((host, port))
        server_socket.listen()
        logger.info(f"Lurker listening on {host}:{port}, saving files to {output_dir}")
    except Exception as e:
        logger.error(f"Failed to bind to {host}:{port}: {e}")
        sys.exit(1)

    try:
        while True:
            logger.info("Waiting for connection...")
            client_socket, client_address = server_socket.accept()
            client_thread = threading.Thread(
                target=handle_client,
                args=(client_socket, client_address, output_dir),
                daemon=True
            )
            client_thread.start()

    except KeyboardInterrupt:
        logger.info("Shutdown requested via KeyboardInterrupt.")
    finally:
        server_socket.close()
        logger.info("Server socket closed.")

if __name__ == "__main__":
    main()
