import os
import socket
# pyrefly: ignore [missing-import]
import pytest
import tempfile
import shutil
from unittest.mock import MagicMock, patch
import lurker

@pytest.fixture
def temp_output_dir():
    # Set up a temporary directory for output files
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)

def test_handle_client_success(temp_output_dir):
    # Mock socket that returns test data and then EOF
    mock_socket = MagicMock()
    mock_socket.recv.side_effect = [b"hello ", b"world!", b""]
    
    client_address = ("127.0.0.1", 12345)
    
    # We want to patch uuid.uuid4 to return a predictable name
    with patch("uuid.uuid4") as mock_uuid:
        mock_uuid.return_value = "test-uuid-1234"
        lurker.handle_client(mock_socket, client_address, temp_output_dir)
        
    expected_file_path = os.path.join(temp_output_dir, "test-uuid-1234")
    assert os.path.exists(expected_file_path)
    with open(expected_file_path, "rb") as f:
        assert f.read() == b"hello world!"
        
    mock_socket.close.assert_called_once()

def test_handle_client_error_cleanup(temp_output_dir):
    # Mock socket that raises an exception during transmission
    mock_socket = MagicMock()
    mock_socket.recv.side_effect = ConnectionResetError("Connection lost")
    
    client_address = ("127.0.0.1", 12345)
    
    with patch("uuid.uuid4") as mock_uuid:
        mock_uuid.return_value = "error-uuid-5678"
        lurker.handle_client(mock_socket, client_address, temp_output_dir)
        
    expected_file_path = os.path.join(temp_output_dir, "error-uuid-5678")
    # File should have been removed due to cleanup
    assert not os.path.exists(expected_file_path)
    mock_socket.close.assert_called_once()

def test_handle_client_uuid_collision(temp_output_dir):
    # Test that handle_client loops until a unique UUID is generated
    # Pre-create a file with the first UUID
    first_uuid = "collision-123"
    second_uuid = "unique-456"
    
    with open(os.path.join(temp_output_dir, first_uuid), "wb") as f:
        f.write(b"existing content")
        
    mock_socket = MagicMock()
    mock_socket.recv.side_effect = [b"new content", b""]
    
    with patch("uuid.uuid4") as mock_uuid:
        mock_uuid.side_effect = [first_uuid, second_uuid]
        lurker.handle_client(mock_socket, ("127.0.0.1", 12345), temp_output_dir)
        
    # First file should remain untouched
    with open(os.path.join(temp_output_dir, first_uuid), "rb") as f:
        assert f.read() == b"existing content"
        
    # Second file should have the new content
    with open(os.path.join(temp_output_dir, second_uuid), "rb") as f:
        assert f.read() == b"new content"

@patch("sys.exit")
def test_main_startup_and_keyboard_interrupt(mock_exit, temp_output_dir):
    # Test the main entry point socket bind and keyboard interrupt flow
    env = {
        "LURKER_PORT": "12345",
        "LURKER_HOST": "127.0.0.1",
        "LURKER_OUTPUT_DIR": temp_output_dir
    }
    
    with patch.dict(os.environ, env):
        with patch("socket.socket") as mock_socket_class:
            mock_server_socket = MagicMock()
            mock_socket_class.return_value = mock_server_socket
            
            # Raise KeyboardInterrupt when accept() is called to exit the infinite loop
            mock_server_socket.accept.side_effect = KeyboardInterrupt()
            
            lurker.main()
            
            # Verify options configured on server socket
            mock_server_socket.setsockopt.assert_called_with(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            mock_server_socket.bind.assert_called_with(("127.0.0.1", 12345))
            mock_server_socket.listen.assert_called_once()
            mock_server_socket.close.assert_called_once()

@patch("sys.exit")
def test_main_bind_failure(mock_exit, temp_output_dir):
    env = {
        "LURKER_PORT": "12345",
        "LURKER_HOST": "127.0.0.1",
        "LURKER_OUTPUT_DIR": temp_output_dir
    }
    
    mock_exit.side_effect = SystemExit(1)
    with patch.dict(os.environ, env):
        with patch("socket.socket") as mock_socket_class:
            mock_server_socket = MagicMock()
            mock_socket_class.return_value = mock_server_socket
            mock_server_socket.bind.side_effect = OSError("Address already in use")
            
            with pytest.raises(SystemExit):
                lurker.main()
            
            mock_exit.assert_called_with(1)
