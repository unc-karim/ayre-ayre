import socket
import os
import threading
import json
import random

class Client:
    """Client class for handling socket communication with server"""
    def __init__(self, server_port, p2p_server_port ): ##does it need another port??
        """Initialize client with ports and socket"""
        self.ip = "localhost"
        #self.port = port
        self.client_socket = None
        #self.peer_socket=None
        self.p2p_server_socket =None
        self.p2p_server_port= self.random_port()
        self.id = None
        self.server_port = server_port
        self.budget = float('inf')


    def random_port(self):
        while True:
            port = random.randint(2000, 65535)
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind(("localhost", port))
                    return port
                except OSError:
                    continue


    def start_connection(self):
        """Establish socket connection to server"""
        try:
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket.connect(("localhost", self.server_port))
        except socket.error as e:
            print(f"Error connecting to server: {e}")

    def login(self, username, password):
        """Send login request to server"""
        try:
            message = {"command": "login", "username": username, "password": password, "ip":self.ip, "port":self.p2p_server_port}
            message_json = json.dumps(message)
            self.client_socket.send(message_json.encode('utf-8'))
            response = self.client_socket.recv(1024).decode('utf-8')
            self.id = self.client_socket.recv(1024).decode('utf-8')
            threading.Thread(target=self.p2p_serverside, daemon=True).start() # give self as arg??
            return response
        except socket.error as e:
            print(f"Error during login: {e}")
            return "Error during login."

    def register(self, username, email, password, name):
        """Register new user account"""
        try:
            message = {"command": "Register", "username": username, "email": email, "password": password,"name": name}
            message_json = json.dumps(message)
            self.client_socket.send(message_json.encode('utf-8'))
            response = self.client_socket.recv(1024).decode('utf-8')
            return response
        except socket.error as e:
            print(f"Error during registration: {e}")
            return "Error during registration."

    def send_image(self, image_path):
        """Send image file to server"""
        try:
            if not os.path.exists(image_path):
                print("Error: Image file not found")
                return False
            image_size = os.path.getsize(image_path)
            self.client_socket.send(str(image_size).encode('utf-8'))
            response = self.client_socket.recv(1024).decode('utf-8')
            if response != "READY":
                return False
            bytes_sent = 0
            with open(image_path, 'rb') as f:
                while bytes_sent < image_size:
                    chunk = f.read(8192)
                    if not chunk:
                        break
                    self.client_socket.sendall(chunk)
                    bytes_sent += len(chunk)
                    progress_msg = self.client_socket.recv(1024).decode('utf-8')
                    if progress_msg.startswith("PROGRESS:"):
                        progress = float(progress_msg.split(":")[1])
                    else:
                        return False
            final_response = self.client_socket.recv(1024).decode('utf-8')
            if final_response.startswith("SUCCESS"):
                return True
            else:
                print(f"Upload failed: {final_response}")
                return False
        except Exception as e:
            print(f"Error sending image: {e}")
            return False

    def receive_image(self, save_path):
        """Receive image file from server"""
        try:
            size_data = self.client_socket.recv(1024).decode('utf-8')
            if size_data.startswith("ERROR"):
                print(f"Server error: {size_data}")
                return False
            image_size = int(size_data)
            self.client_socket.send("READY".encode('utf-8'))
            received_data = bytearray()
            received_size = 0
            while received_size < image_size:
                chunk_size = min(8192, image_size - received_size)
                chunk = self.client_socket.recv(chunk_size)
                if not chunk:
                    break
                received_data.extend(chunk)
                received_size += len(chunk)
                progress = (received_size / image_size) * 100
                self.client_socket.send(f"PROGRESS:{progress:.2f}".encode('utf-8'))
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            with open(save_path, 'wb') as f:
                f.write(received_data)
            self.client_socket.send("SUCCESS: Image received".encode('utf-8'))
            return True
        except Exception as e:
            print(f"Error receiving image: {e}")
            return False
    
    def get_items(self, currency="USD"):
        """Get list of available items with currency conversion."""
        try:
            message = {"command": "display", "self_id": self.id, "currency": currency}
            message_json = json.dumps(message)
            self.client_socket.send(message_json.encode('utf-8'))
            
            items_json = self.client_socket.recv(8192).decode('utf-8')
            print(f"Raw server response: {items_json}")
            
            if not items_json:
                raise ValueError("Received empty response from server.")
            
            if '"error"' in items_json:
                error_message = json.loads(items_json)
                raise ValueError(f"Server Error: {error_message['error']}")
            
            items = json.loads(items_json)
            if isinstance(items, list):
                return items
            else:
                raise ValueError("Server response is not in the expected list format.")
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON: {e}")
            return "Error decoding JSON response."
        except ValueError as e:
            print(f"Error: {e}")
            return str(e)
        except Exception as e:
            print(f"Unexpected error: {e}")
            return "Error retrieving items."
                
    def sell_item(self, product_name, price, description, image_path, amount):
        """List new item for sale"""
        try:
            message = {"command": "sell","product_name": product_name,"price": price,"self_id": self.id,"image_path": image_path,"description": description, "amount": amount}
            message_json = json.dumps(message)
            self.client_socket.send(message_json.encode('utf-8'))
            if self.send_image(image_path):
                response = self.client_socket.recv(1024).decode('utf-8')
                return response
            else:
                return "Failed to upload product image"
        except socket.error as e:
            print(f"Error selling item: {e}")
            return "Error selling item."
    
    def check_if_owner_online(self, owner_username):
        try:
            message = {
                "command":"chech_online",
                "owner_username":{owner_username}
            }
            message_json = json.dumps(message)
            self.client_socket.send(message_json.encode('utf-8'))
            response = self.client_socket.recv(1024).decode('utf-8')
            response_json = json.loads(response)
            return response_json
        except socket.error as e:
            print(f"Error checking online status: {e}")
            return "Error checking online status."
        

    def listen_for_messages(self):
        while True:
            try:
                message = self.client_socket.recv(1024).decode('utf-8')
                message_json = json.loads(message)
                if message_json:
                    print(message_json["message"])
            except Exception as e:
                print(f"Error receiving message: {e}")
                break

    def send_message(self, recipient_username, message):
        try:
            full_message = {
                "command": "send_message",
                "self_id": self.id, 
                "recipient_username": recipient_username,
                "message": message
            }
            full_message_json = json.dumps(full_message)
            self.client_socket.send(full_message_json.encode('utf-8'))
        except socket.error as e:
            print(f"Error sending message: {e}")

    def send_message_loop(self):
        while True:
            recipient_username = input("Enter recipient username: ")
            message = input("Enter your message: ")
            self.send_message(recipient_username, message)

    def communicate(self):
        threading.Thread(target=self.listen_for_messages, daemon=True).start()

    def get_ip_and_port(self,username):
        try:
            message= { 
                "command": "get_ip_and_port",
                "username":username
            }
            message_json = json.dumps(message)
            self.client_socket.send(message_json.encode('utf-8'))
            response = self.client_socket.recv(1024).decode('utf-8')                ##maek json??
            response_json=json.loads(response)
            return response_json["ip"],response_json["port"]
        except socket.error as e:
            print(f"Error fetching IP and port: {e}")
            return None, None
        
    def send_message_p2p_loop( self, peer_socket):
        try:
            while True:
                message = input("Enter your message (type 'stop' to end): ")
                if message.strip().lower() == "stop":
                    # Send a stop message to inform the peer
                    peer_socket.send("stop".encode('utf-8'))
                    peer_socket.close()
                    print("Communication closed.")
                    break
                elif message.strip():
                    # Send message
                    #message_json = json.dumps({"message": message})  make json??
                    peer_socket.send(message.encode('utf-8'))
                else:
                    print("Message cannot be empty.")
        except socket.error as e:
            print(f"Error during P2P message sending: {e}")
        except Exception as e:
            print(f"Unexpected error: {e}")

    def send_message_p2p(self,recipient_username):
        recipient_ip,recipient_port=self.get_ip_and_port(recipient_username)
        if not recipient_ip or not recipient_port:
            print("Could not retrieve peer's IP and port.")
            return
        try:
            peer_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            peer_socket.connect((recipient_ip, recipient_port))
            print(f"Connected to {recipient_ip}:{recipient_port}")
            #threading.Thread(target=self.send_message_p2p_loop, args=(peer_socket,), daemon=True).start()    ##do we need a thread here??
            #self.listen_for_messages_p2p(peer_socket)   # hay idk sho wad3a mafrood shila??
            self.send_message_p2p_loop(peer_socket)
        except socket.error as e:
            print(f"Error connecting to peer: {e}")

    def p2p_serverside(self):
        p2p_server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        p2p_server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
        # Bind to a fixed P2P port and listen for incoming connections
            p2p_server_socket.bind((self.ip, self.p2p_server_port))
            p2p_server_socket.listen(100)
            print(f"P2P server listening on port {self.p2p_server_port}...")
            
            while True:
                try:
                    conn, addr = p2p_server_socket.accept()
                    print(f"Accepted connection from {addr}")
                    threading.Thread(target=self.listen_for_messages_p2p, args=(conn, addr), daemon=True).start()
                except socket.error as e:
                    print(f"Error accepting connection: {e}")
        except socket.error as e:
            print(f"Error setting up P2P server: {e}")

    def listen_for_messages_p2p(self, conn,addr):
        try:
            while True:
                message = conn.recv(1024).decode('utf-8')  #check if tehre is message first??
                if not message:
                    print(f"Peer {addr} disconnected.")
                    break
                if message.lower() == "stop":
                    conn.close()
                    print("Peer closed the communication.")
                    break
                else:
                    #message_json = json.loads(message)
                    #if "message" in message_json:
                    print(f"Received message: {message}")
                    #else:
                        #print("Invalid message format received.")
        except socket.error as e:
            print(f"Error receiving message from peer: {e} addr {addr}")


    def communicate_p2p(self):
        """Start the P2P communication by ensuring the peer socket is initialized."""
        if self.peer_socket:
            # Start listening for messages from the peer
            threading.Thread(target=self.listen_for_messages_p2p, args=(self.peer_socket,), daemon=True).start()
        else:
            print("No peer connection established.")

    def filter_by_owner(self, owner_username):
        """Get items filtered by owner"""
        try:
            msg = {"command": "filter_by_owner", "owner_username": owner_username}
            msg_json = json.dumps(msg)
            self.client_socket.send(msg_json.encode('utf-8'))
            items_json = self.client_socket.recv(65536).decode('utf-8')
            try:
                data = json.loads(items_json)
                if 'error' in data:
                    return data['error']
                    
                items = data.get("items", [])
                total_images = data.get("total_images", 0)
                if total_images == 0:
                    return "No items available."
                    
                os.makedirs("received_images", exist_ok=True)
                formatted_items = []
                for i in range(total_images):
                    image_path = os.path.join("received_images", f"{items[i]['id']}.jpg")
                    if hasattr(self, 'receive_image') and callable(getattr(self, 'receive_image')):
                        if self.receive_image(image_path):
                            items[i]['image_path'] = image_path
                        else:
                            items[i]['image_path'] = None
                    else:
                        items[i]['image_path'] = None

                    formatted_item = (
                        f"Name: {items[i]['name']}\n"
                        f"Price: ${items[i]['price']}\n"
                        f"Description: {items[i]['description']}\n"
                        f"Image: {'Available' if items[i]['image_path'] else 'Not Available'}\n"
                    )
                    formatted_items.append(formatted_item)
                return "\n".join(formatted_items)
            except json.JSONDecodeError:
                return "Error: Invalid response from server"
        except Exception as e:
            print(f"Error retrieving items: {e}")
            return "Error retrieving items."
        
    def set_budget(self, budget):
        """Set the user's budget"""
        self.budget = budget
        print(f"Your budget is set to ${self.budget}")

    def update_budget(self, amount):
        """Update the budget after a purchase"""
        self.budget -= amount
        print(f"Your remaining budget is ${self.budget}")

    def check_budget(self, price):
        """Check if the user has enough budget to make the purchase"""
        if price > self.budget:
            print(f"Warning: You are about to exceed your budget of ${self.budget}")
            return False
        return True
        
    def purchase_product(self, product_name):
        """Purchase a product"""
        try:
            if not self.id:
                return "Please log in first."
            message = {"command": "get_price", "product_name":  product_name}
            message_json = json.dumps(message)
            self.client_socket.send(message_json.encode('utf-8'))
            response = self.client_socket.recv(1024).decode('utf-8')
            response_json = json.loads(response)
            # Get the product price from the server response
            price = response_json["price"]
            # Check if the user has enough budget
            if not self.check_budget(price):
                return "Purchase cannot be completed. Not enough budget."          #aw print eror then return??
            message = {"command": "Purchase", "product_name": product_name, "self_id": self.id}
            message_json = json.dumps(message)
            self.client_socket.send(message_json.encode('utf-8'))
            response = self.client_socket.recv(1024).decode('utf-8')
            response_json = json.loads(response)
            # Get the product price from the server response
            price = response_json["price"]
            # Proceed with the purchase if budget is sufficient
            self.update_budget(price)
            return response_json['message']
        except socket.error as e:
            print(f"Error purchasing product: {e}")
            return "Connection error. Please try again later."
        except Exception as e:
            print(f"Unexpected error during purchase: {e}")
            return "An unexpected error occurred."
        
    def view_sold_product_buyers(self):
        """View buyers of products sold by current user"""
        try:
            if not self.id:
                return "Please log in first."
            message = {"command": "view_buyers", "self_id": self.id}
            message_json = json.dumps(message)
            self.client_socket.send(message_json.encode('utf-8'))
            buyers_info = self.client_socket.recv(65536).decode('utf-8')
            buyers_info_json = json.loads(buyers_info)
            if "error" in buyers_info_json:
                return buyers_info_json["error"]
            elif "message" in buyers_info_json:
                return buyers_info_json["message"]
            else:
                formatted_buyers = []
                for product in buyers_info_json.get("products", []):
                    formatted_buyer = (
                        f"Product ID: {product['product_id']}\n"
                        f"Name: {product['name']}\n"
                        f"Buyer: {product['buyer']}\n"
                        f"Email: {product['email']}\n"
                        f"Price: ${product['price']}\n"
                    )
                    formatted_buyers.append(formatted_buyer)
                return "\n".join(formatted_buyers)
        except socket.error as e:
            print(f"Error retrieving buyer information: {e}")
            return "Connection error. Please try again later."
        except json.JSONDecodeError:
            return "Error: Invalid response from server"
        except Exception as e:
            print(f"Unexpected error retrieving buyers: {e}")
            return "An unexpected error occurred."
        
    def logout(self):
        """Logout the current user"""
        try:
            if not self.id:
                return "Not logged in."
            if not self.client_socket:
                return "Not connected to server."
                
            logout_message = {
                "command": "logout"
            }
            logout_message_json = json.dumps(logout_message)
            self.client_socket.send(logout_message_json.encode('utf-8'))
            response = self.client_socket.recv(1024).decode('utf-8')
            response_json = json.loads(response)
            
            if response_json["message"] == "logout successful":
                self.client_socket.close()
                self.id = None
                self.client_socket = None
                return "Logged out successfully."
            return "Error logging out."
            
        except socket.error as e:
            print(f"Error during logout: {e}")
            return "Connection error during logout."
        except Exception as e:
            print(f"Unexpected error during logout: {e}")
            return "An unexpected error occurred during logout."
        

    def rate(self, rating, product_id):
        """Submit a rating for a product."""
        if not (1 <= rating <= 5):
            return "Rating must be between 1 and 5."
        
        if not self.client_socket:
            return "Not connected to server."
            
        if not self.id:
            return "Not logged in."
        
        try:
            msg = {
                "command": "rate",
                "rating": rating,
                "product_id": product_id,
                "self_id": self.id
            }
            self.client_socket.send(json.dumps(msg).encode('utf-8'))
            response = self.client_socket.recv(1024).decode('utf-8')
            response_json = json.loads(response)
            return response_json.get("message", "Unknown response from server")
            
        except socket.error as e:
            print(f"Error during rating: {e}")
            return "Connection error during rating."
        except json.JSONDecodeError as e:
            print(f"Error decoding server response: {e}")
            return "Error: Invalid response from server"
        except Exception as e:
            print(f"Unexpected error during rating: {e}")
            return "An unexpected error occurred during rating."
        
    
    def display_rating(self, product_id):
        """Display the rating for a product."""
        if not self.client_socket:
            return "Not connected to server."
            
        try:
            msg = json.dumps({
                "command": "display_rating", 
                "product_id": product_id
            })
            self.client_socket.send(msg.encode('utf-8'))
            
            response = self.client_socket.recv(1024).decode('utf-8')
            response_json = json.loads(response)
            
            if "message" in response_json:
                return response_json["message"]
            else:
                return f"Product: {response_json['name']}\nRating: {response_json['rating']}"
                
        except socket.error as e:
            print(f"Connection error getting rating: {e}")
            return "Connection error while getting rating."
        except json.JSONDecodeError as e:
            print(f"Error decoding server response: {e}")
            return "Error: Invalid response from server"
        except Exception as e:
            print(f"Unexpected error getting rating: {e}")
            return "An unexpected error occurred while getting rating."

    def search_product(self, search):
        try:
            msg = json.dumps({
                "command":"search",
                "item": search,
                "self_id" : self.id
            })
            self.client_socket.send(msg.encode('utf-8'))
            items_json = self.client_socket.recv(8192).decode('utf-8')
            items = json.loads(items_json)
            if not items:
                return "No items available."
            os.makedirs("received_images", exist_ok=True)
            self.client_socket.send("READY_FOR_IMAGES".encode('utf-8'))
            formatted_items = []
            for item in items:
                image_path = os.path.join("received_images", f"{item['id']}.jpg")
                if self.receive_image(image_path):
                    item['image_path'] = image_path
                else:
                    item['image_path'] = None
                formatted_item = (
                    f"Name: {item['name']}\n"
                    f"Price: ${item['price']}\n"
                    f"Description: {item['description']}\n"
                    f"Image: {'Available' if item['image_path'] else 'Not Available'}\n"
                )
                formatted_items.append(formatted_item)
                self.client_socket.send("NEXT_IMAGE".encode('utf-8'))
                return "\n".join(formatted_items)
        except socket.error as e:
            print(f"Error retrieving items: {e}")
            return "Error retrieving items."
        except json.JSONDecodeError as e:
            print(f"Error parsing items data: {e}")
            return "Error processing items data."
        except Exception as e:
            print(f"Unexpected error: {e}")
            return "An unexpected error occurred."
        

    def filter_by_budget(self):
        """Get items filtered by owner"""
        try:
            msg = {"command": "filter_by_owner", "budget": self.budget, "self_id" : self.id}
            msg_json = json.dumps(msg)
            self.client_socket.send(msg_json.encode('utf-8'))
            items_json = self.client_socket.recv(65536).decode('utf-8')
            try:
                data = json.loads(items_json)
                if 'error' in data:
                    return data['error']
                    
                items = data.get("items", [])
                total_images = data.get("total_images", 0)
                if total_images == 0:
                    return "No items available."
                    
                os.makedirs("received_images", exist_ok=True)
                formatted_items = []
                for i in range(total_images):
                    image_path = os.path.join("received_images", f"{items[i]['id']}.jpg")
                    if hasattr(self, 'receive_image') and callable(getattr(self, 'receive_image')):
                        if self.receive_image(image_path):
                            items[i]['image_path'] = image_path
                        else:
                            items[i]['image_path'] = None
                    else:
                        items[i]['image_path'] = None

                    formatted_item = (
                        f"Name: {items[i]['name']}\n"
                        f"Price: ${items[i]['price']}\n"
                        f"Description: {items[i]['description']}\n"
                        f"Image: {'Available' if items[i]['image_path'] else 'Not Available'}\n"
                    )
                    formatted_items.append(formatted_item)
                return "\n".join(formatted_items)
            except json.JSONDecodeError:
                return "Error: Invalid response from server"
        except Exception as e:
            print(f"Error retrieving items: {e}")
            return "Error retrieving items."