import socket
import time

server_address = ('localhost', 9002)

def receive_data(sock):
    try:
        data = sock.recv(8192)  # Adjust the buffer size as needed
        return data.decode("utf-8")
    except Exception as e:
        print(f"Error receiving data: {e}")
        return None

def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        sock.connect(server_address)
        print("Connected to the server.")

        while True:
            message = "GetData"
            sock.sendall(message.encode("utf-8"))

            data = receive_data(sock)
            if data is not None:
                print(f"Received data: {data}")
            else:
                break  # Exit the loop if there's an error

            time.sleep(1)  # Wait for 1 second before sending the next message

    except Exception as e:
        print(f"Error: {e}")
    finally:
        sock.close()
        print("Socket connection closed.")

if __name__ == "__main__":
    main()