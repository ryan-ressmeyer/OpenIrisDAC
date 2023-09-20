import socket
import time
import json

class OpenIrisClient:
    def __init__(self, server_address='localhost', port=9003):
        self.server_address = (server_address, port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(.05) # 200 Hz

    def receive_data(self):
        try:
            self.sock.sendto("getdata".encode("utf-8"), self.server_address)
            data = self.sock.recvfrom(8192)  # Adjust the buffer size as needed
            return json.loads(data[0].decode("utf-8"))
        except Exception as e:
            #print(f"Error receiving data: {e}")
            return None
    
    def __enter__(self):
        self.sock.connect(self.server_address)
        return self
    
    def __exit__(self, exc_type, exc_value, traceback):
        self.sock.close()
        print("Socket connection closed.")

if __name__ == "__main__":
    with OpenIrisClient() as client:
        while True:
            data = client.receive_data()
            if data is not None:
                print(f"Received data: {data}")
            else:
                break
            time.sleep(.1)
    
