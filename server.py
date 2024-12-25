import socket
import threading
import sqlite3
import bcrypt
import os
import json
import sys
from datetime import datetime, timedelta

# Dictionary to track currently connected users
online_users = {}

def authenticate_user(server_socket, username, password, db):
    """Authenticate a user by checking username and password against database"""
    try:
        cursor = db.cursor()
        cursor.execute("SELECT password FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        if row:
            stored_enc_password = row[0]
            if bcrypt.checkpw(password.encode('utf-8'), stored_enc_password):
                return True
        return False
    except sqlite3.Error as e:
        print(f"Database error during authentication: {e}")
        return False

def handle_client(server_socket, client_socket, addr, db_path):
    """Handle individual client connections and process their requests"""
    try:
        db = sqlite3.connect(db_path)
    except sqlite3.Error as e:
        print(f"Error connecting to the database: {e}")
        client_socket.send("Server error. Please try again later.".encode('utf-8'))
        client_socket.close()
        return
    while True:
        try:
            raw_message = client_socket.recv(1024).decode('utf-8')
            message = json.loads(raw_message)
            if message:
                handle_commands(server_socket, client_socket, message, db)
            else:
                break
        except Exception as e:
            print(f"Error with client {addr}: {e}")
            break
    
    # Clean up user from online_users if they're still there
    for username, sock in list(online_users.items()):
        if sock == client_socket:
            del online_users[username]
            break
            
    db.close()
    client_socket.close()

def handle_logout(client_socket):
    """Handle user logout by removing from online users and closing connection"""
    try:
        # Find username by client_socket
        username = None
        for user, sock in list(online_users.items()):         #check 
            if sock == client_socket:
                username = user
                del online_users[username]
                break
                
        response = {
            "message": "logout successful"
        }
        response_json = json.dumps(response)
        client_socket.send(response_json.encode('utf-8'))
        
        # Close the connection after sending response
        client_socket.close()
        
    except Exception as e:
        print(f"Error during logout: {e}")
        response = {
            "message": "error during logout"
        }
        try:
            response_json = json.dumps(response)
            client_socket.send(response_json.encode('utf-8'))
        except:
            pass
        finally:
            client_socket.close()

def register_user(server_socket, client_socket, username, email, password, name, db):     
    """Register a new user in the database"""
    cursor = db.cursor()
    try:
        enc_pass = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        cursor.execute("INSERT INTO users (username, email, password, name) VALUES (?, ?, ?, ?)",
                       (username, email, enc_pass, name))
        db.commit()
        client_socket.send("Registration successful.".encode('utf-8'))
        #login_user(server_socket, client_socket, username, password, "", "", db)  # Auto-login
    except sqlite3.IntegrityError:
        client_socket.send("Username already exists.".encode('utf-8'))
    except sqlite3.Error as e:
        print(f"Database error during registration: {e}")
        client_socket.send("Server error. Please try again later.".encode('utf-8'))   

def login_user(server_socket, client_socket, username, password, ip, port, db):
    """Log in an existing user"""
    try:
        if authenticate_user(server_socket, username, password, db):
            online_users[username] = (client_socket,ip ,port)                                                  ##
            client_socket.send(f"Login successful.\nWelcome {username}".encode('utf-8'))
            send_id(client_socket, db, username)
        else:
            client_socket.send("Invalid username or password.".encode('utf-8'))
    except Exception as e:
        print(f"Error during login: {e}")
        client_socket.send("Server error. Please try again later.".encode('utf-8'))

def receive_image(client_socket, image_id):
    """Receive and save an image from the client"""
    try:
        size_data = client_socket.recv(1024).decode('utf-8')
        if not size_data.isdigit():
            client_socket.send("ERROR: Invalid file size received".encode('utf-8'))
            return False
        image_size = int(size_data)
        if image_size <= 0:
            client_socket.send("ERROR: Invalid file size".encode('utf-8'))
            return False
        client_socket.send("READY".encode('utf-8'))
        received_data = bytearray()
        received_size = 0
        while received_size < image_size:
            remaining = image_size - received_size
            chunk_size = min(8192, remaining)
            chunk = client_socket.recv(chunk_size)
            if not chunk:
                break
            received_data.extend(chunk)
            received_size += len(chunk)
            progress = (received_size / image_size) * 100
            client_socket.send(f"PROGRESS:{progress:.2f}".encode('utf-8'))
        if received_size != image_size:
            client_socket.send("ERROR: Incomplete transfer".encode('utf-8'))
            return False
        image_path = os.path.join("product_images", f"{image_id}.jpg")
        os.makedirs("product_images", exist_ok=True)
        with open(image_path, 'wb') as f:
            f.write(received_data)
        client_socket.send("SUCCESS: Image received".encode('utf-8'))
        return True
    except Exception as e:
        print(f"Error receiving image: {e}")
        client_socket.send(f"ERROR: {str(e)}".encode('utf-8'))
        return False

def receive_ack(client_socket):
    """Receive acknowledgment from client"""
    return client_socket.recv(1024).decode('utf-8') == "ACK"

def send_data(client_socket, data):
    """Send data to client, converting dict to JSON if needed"""
    if isinstance(data, dict):
        data = json.dumps(data)
    client_socket.sendall(data.encode('utf-8'))


def send_image(client_socket, image_id):
    """Send an image to the client"""
    try:
        image_path = os.path.join("product_images", f"{image_id}.jpg")
        
        if not os.path.exists(image_path):
            client_socket.send("ERROR: Image not found".encode('utf-8'))
            return False
        image_size = os.path.getsize(image_path)
        client_socket.send(str(image_size).encode('utf-8'))
        response = client_socket.recv(1024).decode('utf-8')
        if response != "READY":
            return False
        bytes_sent = 0
        with open(image_path, 'rb') as f:
            while bytes_sent < image_size:
                chunk = f.read(8192)
                if not chunk:
                    break
                client_socket.sendall(chunk)
                bytes_sent += len(chunk)
                progress_ack = client_socket.recv(1024).decode('utf-8')
                if not progress_ack.startswith("PROGRESS:"):
                    return False
        final_response = client_socket.recv(1024).decode('utf-8')
        return final_response == "SUCCESS: Image received"
    except Exception as e:
        print(f"Error sending image: {e}")
        return False

def get_item_id(id, name, price, description, db):
    """Get item ID from database based on attributes"""
    cursor = db.cursor()
    cursor.execute("SELECT id FROM products where (owner_id, name, price, description) = (?,?,?,?) ", (id, name, price, description))
    row = cursor.fetchone()
    if row:
        item_id = row[0]
        return item_id

def get_item_price(name, db):
    """Get price of the product from the database based on its name"""
    cursor = db.cursor()
    try:
        cursor.execute("SELECT price FROM products WHERE name = ?", (name,))
        row = cursor.fetchone()
        if row:
            price = row[0]
            return price
        else:
            return None  # Return None if the product name is not found
    except sqlite3.Error as e:
        print(f"Database error when retrieving price for product '{name}': {e}")
        return None

def register_item(server_socket, client_socket, name, price, image, description, amount, id, db):
    """Register a new item in the database"""
    try:
        cursor = db.cursor()
        cursor.execute("""
            INSERT INTO products (owner_id, name, price, description, amount, status) 
            VALUES (?, ?, ?, ?, ?, 'available')
        """, (id, name, price, description, amount))
        db.commit()
        product_id = cursor.lastrowid
        if receive_image(client_socket, product_id):
            cursor.execute("""
                UPDATE products 
                SET image = ? 
                WHERE id = ?
            """, (f"{product_id}.jpg", product_id))
            db.commit()
            client_socket.send("Product registered successfully with image.".encode('utf-8'))
        else:
            client_socket.send("Product registered but image upload failed.".encode('utf-8'))
    except sqlite3.Error as e:
        print(f"Database error during product registration: {e}")
        client_socket.send("Server error. Please try again later.".encode('utf-8'))

def send_id(client_socket, db, username):
    """Send user ID to client"""
    cursor = db.cursor()
    try:
        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        if row:
            id = row[0]
            client_socket.send(str(id).encode('utf-8'))
        else:
            client_socket.send("User ID not found.".encode('utf-8'))
    except sqlite3.Error as e:
        print(f"Database error when retrieving user ID: {e}")
        client_socket.send("Server error. Please try again later.".encode('utf-8'))

def get_id(db, username):
    """Get user ID from database"""
    cursor = db.cursor()
    cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    if row:
        return row[0]
    return None

def filter_by_owner(client_socket, owner_id, db):
    """Filter and return items by owner ID"""
    cursor = db.cursor()
    try:
        cursor.execute("SELECT id, name, price, description FROM products WHERE owner_id = ? AND amount > 0", (owner_id,))
        rows = cursor.fetchall()
        items_data = []
        for row in rows:
            item = {
                'id': row[0],
                'name': row[1],
                'price': row[2],
                'description': row[3]
            }
            items_data.append(item)

        if not items_data:
            client_socket.send(json.dumps({"items": [], "total_images": 0}).encode('utf-8'))
            return
        items_json = json.dumps({"items": items_data, "total_images": len(items_data)})
        client_socket.send(items_json.encode('utf-8'))
        for item in items_data:
            send_image(client_socket, item['id'])
    except Exception as e:
        print(f"Error in filter_by_owner: {e}")
        client_socket.send(json.dumps({"error": "Server error. Please try again later."}).encode('utf-8'))

def purchase_product(server_socket, client_socket, product_name, buyer_id, db):
    """Process product purchase based on product name"""
    cursor = db.cursor()
    try:
        cursor.execute("SELECT id, status, owner_id, amount FROM products WHERE name = ?", (product_name,))
        product = cursor.fetchone()
        if not product:
            client_socket.send(json.dumps({"status": "Product_not_found"}).encode('utf-8'))
            return

        product_id, status, owner_id, amount = product
        if status != 'available':
            client_socket.send(json.dumps({"status": "Product_sold"}).encode('utf-8'))
            return

        if owner_id == buyer_id:
            client_socket.send(json.dumps({"status": "Product_is_yours"}).encode('utf-8'))
            return

        cursor.execute("BEGIN TRANSACTION")
        cursor.execute("""
            UPDATE products 
            SET amount = amount - 1, status = CASE WHEN amount = 1 THEN 'sold' ELSE 'available' END, buyer_id = ?
            WHERE id = ? AND status = 'available'""",
            (buyer_id, product_id))
        
        if cursor.rowcount == 0:
            cursor.execute("ROLLBACK")
            client_socket.send(json.dumps({"status": "Product_is_not_available"}).encode('utf-8'))
            return

        cursor.execute("COMMIT")
        pickup_date = (datetime.now() + timedelta(days=5)).strftime('%Y-%m-%d')
        client_socket.send(json.dumps({"status": "success", "message": f"Purchase successful! Please collect your item from the aubpost office on {pickup_date}."}).encode('utf-8'))

        if owner_id in online_users:
            owner_socket = online_users[owner_id][0]                          ###use id or username
            owner_socket.send(json.dumps({"status": "notification", "message": f"Your product with name {product_name} has been purchased by user ID {buyer_id}."}).encode('utf-8'))

    except sqlite3.Error as e:
        cursor.execute("ROLLBACK")
        print(f"Database error during product purchase: {e}")
        client_socket.send(json.dumps({"status": "error", "message": "Server error. Please try again later."}).encode('utf-8'))

def view_sold_product_buyers(server_socket, client_socket, seller_id, db):
    """View buyers of sold products for a seller"""
    cursor = db.cursor()
    try:
        cursor.execute("""
            SELECT 
                p.name,
                p.id,
                u.username,
                u.email,
                p.price
            FROM products p
            LEFT JOIN users u ON p.buyer_id = u.id
            WHERE p.owner_id = ? 
            AND p.buyer_id IS NOT NULL
            ORDER BY p.id DESC""", (seller_id,))
        rows = cursor.fetchall()
        if not rows:
            client_socket.send(json.dumps({"message": "No products sold yet."}).encode('utf-8'))
            return
        products = []
        for row in rows:
            product_info = {
                "product_id": row[1],
                "name": row[0],
                "buyer": row[2] if row[2] else "Unknown",
                "email": row[3] if row[3] else "Unknown",
                "price": f"{row[4]:.2f}"
            }
            products.append(product_info)
        response = json.dumps({"products": products})
        client_socket.send(response.encode('utf-8'))
    except sqlite3.Error as e:
        print(f"Database error retrieving buyer info: {e}")
        error_response = json.dumps({"error": "Server error. Please try again later."})
        client_socket.send(error_response.encode('utf-8'))
    except Exception as e:
        print(f"Unexpected error: {e}")
        error_response = json.dumps({"error": "An unexpected error occurred."})
        client_socket.send(error_response.encode('utf-8'))

def create_Tables(db_path):
        """Create database tables if they don't exist"""
        db = sqlite3.connect(db_path)
        cursor = db.cursor()
        db.execute("PRAGMA foreign_keys=on")
        cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            username TEXT UNIQUE, 
                            email TEXT, 
                            password TEXT,
                            name TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS products (
                            id INTEGER PRIMARY KEY AUTOINCREMENT, 
                            owner_id INTEGER , 
                            name TEXT, 
                            price REAL, 
                            description TEXT, 
                            image BLOB,
                            amount INTEGER,
                            rating REAL DEFAULT 0,
                            num_raters INTEGER DEFAULT 0, 
                            buyer_id INTEGER, 
                            status TEXT DEFAULT 'available', 
                            FOREIGN KEY (owner_id) REFERENCES users(id), 
                            FOREIGN KEY (buyer_id) REFERENCES users(id))''')

        db.commit()
        db.close()
    
def handle_commands(server_socket, client_socket, msg, db):
    """Process client commands"""
    command = msg["command"]
    try:
        if command == "Register":
            username = msg["username"]
            email = msg["email"]
            password = msg["password"]
            name = msg["name"]
            register_user(server_socket, client_socket, username, email, password, name, db)
        elif command == "login":  
            username = msg["username"]
            password = msg["password"]
            login_user(server_socket, client_socket, username, password, db)
        elif command == "display":
            id = msg["self_id"]
            send_items(client_socket, db, id)
        elif command == "sell":
            name = msg["product_name"]  
            price = msg["price"]
            description = msg["description"]
            amount = msg["amount"]
            id = msg["self_id"]
            image = msg["image_path"]
            register_item(server_socket, client_socket, name, price, image, description, amount, id, db)
        elif command == "check_online":
            username = msg["owner_username"]
            check_online_status(client_socket, username)
        elif command == "send_message":
            sender_username = msg["self_id"]
            recipient_username = msg["recipient_username"]
            message = msg["message"]
            send_message(sender_username, recipient_username, message)
        elif command == "filter_by_owner":
                owner_username = msg["owner_username"]
                owner_id = get_id(db, owner_username)
                if owner_id is None:
                    client_socket.send(json.dumps("User not found.").encode('utf-8'))
                    return
                filter_by_owner(client_socket, owner_id, db)
        elif command == "filter_by_budget":
            budget = msg["budget"]
            self_id = msg["self_id"]
            if budget == float("inf"):
                client_socket.send(json.dumps("there is no budget").encode('utf-8'))
            filter_by_budget(client_socket, budget, db, self_id)
        elif command == "Purchase":
            product_name = msg["product_name"]
            buyer_id = msg["self_id"]
            purchase_product(server_socket, client_socket, product_name, buyer_id, db)
        elif command == "view_buyers":
            seller_id = msg["self_id"]
            view_sold_product_buyers(server_socket, client_socket, seller_id, db)
        elif command == "logout":
            handle_logout(client_socket)
        elif command == "rate":
            rating = float(msg["rating"])
            product_id = msg["product_id"]
            user_id = msg["self_id"]
            
            cursor = db.cursor()
            cursor.execute("""
                SELECT buyer_id FROM products 
                WHERE id = ? AND buyer_id = ?
            """, (product_id, user_id))
            
            if cursor.fetchone():
                response = rate(rating, product_id, db)
                client_socket.send(response.encode('utf-8'))
            else:
                response = json.dumps({"message": "You can only rate products you have purchased."})
                client_socket.send(response.encode('utf-8'))
        elif command == "display_rating":
            product_id = msg["product_id"]
            display_rating(product_id, client_socket, db)
        elif command == "search":
            item = msg["item"]
            self_id = msg["self_id"]
            search(item,client_socket,db,self_id)
        elif command == "get_ip_and_port":
            username=msg["username"]
            if username in online_users:
                ip=online_users[username][1]
                port=online_users[username][2]
                #print("this is the ip in the server:"+str(ip))
                #print("this is the port in the server:"+str(port))
                message={ "ip":ip, "port": port}
                response = json.dumps(message)
            else:
                response = {"error": "User not online"}
            client_socket.send(response.encode('utf-8'))
        elif command == "get_price":
            item_name = msg["product_name"]
            price = get_item_price(item_name, db)
            if price is not None:
                response = {"status": "success", "price": price}
            else:
                response = {"status": "error", "message": "Item not found"}
            response_json=response = json.dumps(response)
            client_socket.send(response_json.encode('utf-8'))
    except IndexError as e:
        print(f"Command format error: {e}")
        client_socket.send("Invalid command format.".encode('utf-8'))
    except Exception as e:
        print(f"Error handling command '{command}': {e}")
        client_socket.send("Server error. Please try again later.".encode('utf-8'))

def rate(rating, product_id, db):
    """Calculate the new rating based on the number of raters and the previous rating"""
    try:
        cursor = db.cursor()
        cursor.execute("SELECT rating, num_raters FROM products WHERE id = ?", (product_id,))
        row = cursor.fetchone()
        if row:
            current_rating, num_raters = row
            new_num_raters = num_raters + 1
            new_rating = ((current_rating * num_raters) + rating) / new_num_raters
            cursor.execute("UPDATE products SET rating = ?, num_raters = ? WHERE id = ?", (new_rating, new_num_raters, product_id))
            db.commit()
            response = {"message": "Rating submitted successfully."}
        else:
            response = {"message": "Product not found."}
        return json.dumps(response)
    except sqlite3.Error as e:
        print(f"Database error during rating: {e}")
        return json.dumps({"message": "Server error. Please try again later."})
    except Exception as e:
        print(f"Unexpected error during rating: {e}")
        return json.dumps({"message": "An unexpected error occurred."})

def send_items(client_socket, db, id):
    """Fetch all products from the database and return them to the client"""
    cursor = db.cursor()
    try:
        cursor.execute("SELECT id, name, price, description, image FROM products WHERE status = 'available' AND amount > 0")
        rows = cursor.fetchall()
        if not rows:
            response = json.dumps({"error": "No products found."})
        else:
            items_data = []
            for row in rows:
                item = {
                    'id': row[0],
                    'name': row[1],
                    'price': row[2],
                    'description': row[3],
                    'image': row[4]
                }
                items_data.append(item)
            response = json.dumps(items_data)
        client_socket.send(response.encode('utf-8'))
    except sqlite3.Error as e:
        print(f"Error retrieving products from the database: {e}")
        error_response = json.dumps({"error": f"Server error while retrieving products: {str(e)}"})
        client_socket.send(error_response.encode('utf-8'))
    except Exception as e:
        print(f"Unexpected error: {e}")
        error_response = json.dumps({"error": "An unexpected error occurred."})
        client_socket.send(error_response.encode('utf-8'))


def filter_by_budget(client_socket, budget, db, self_id):
    """Filter and return items by owner ID"""
    cursor = db.cursor()
    try:
        cursor.execute("""
            SELECT id, name, price, description 
            FROM products 
            WHERE price <= ? AND amount > 0 AND owner_id != ?
        """, (budget, self_id))
        rows = cursor.fetchall()
        items_data = []
        for row in rows:
            item = {
                'id': row[0],
                'name': row[1],
                'price': row[2],
                'description': row[3]
            }
            items_data.append(item)

        if not items_data:
            client_socket.send(json.dumps({"items": [], "total_images": 0}).encode('utf-8'))
            return
        items_json = json.dumps({"items": items_data, "total_images": len(items_data)})
        client_socket.send(items_json.encode('utf-8'))
        for item in items_data:
            send_image(client_socket, item['id'])
    except Exception as e:
        print(f"Error in filter_by_owner: {e}")
        client_socket.send(json.dumps({"error": "Server error. Please try again later."}).encode('utf-8'))


def check_online_status(client_socket, username):
    if username in online_users:
        message = {
            "message":f"{username} is online"
        }
        message_json = json.dumps(message)
        client_socket.send(message_json.encode('utf-8'))
    else:
        message = {
            "message":f"{username} is offline"
        }
        message_json = json.dumps(message)
        client_socket.send(message_json.encode('utf-8'))

def display_rating(id, client_socket, db):
    """Display product name and rating for given product ID"""
    cursor = db.cursor()
    try:
        cursor.execute("""
            SELECT p.name, p.rating 
            FROM products p
            WHERE p.id = ?
        """, (id,))
        result = cursor.fetchone()
        
        if result:
            response = {
                "name": result[0],
                "rating": result[1] if result[1] else "No ratings yet"
            }
        else:
            response = {
                "message": "Product not found"
            }
            
        client_socket.send(json.dumps(response).encode('utf-8'))
        
    except sqlite3.Error as e:
        print(f"Database error retrieving rating: {e}")
        error_response = {
            "message": "Error retrieving rating"
        }
        client_socket.send(json.dumps(error_response).encode('utf-8'))


def search(item,client_socket, db, self_id):
    cursor = db.cursor()
    try:
        cursor.execute("""
            SELECT p.id, p.name, p.price, p.description 
            FROM products p 
            WHERE (p.name LIKE ? OR p.description LIKE ?) 
            AND p.owner_id != ? AND p.amount > 0
        """, ('%' + item + '%', '%' + item + '%', self_id))
        rows = cursor.fetchall()
        items_data = []
        for row in rows:
            item = {
                'id': row[0],
                'name': row[1],
                'price': row[2],
                'description': row[3]
            }
            items_data.append(item)
        items_json = json.dumps(items_data)
        client_socket.send(items_json.encode('utf-8'))
        ack = client_socket.recv(1024).decode('utf-8')
        if ack != "READY_FOR_IMAGES":
            return
        for item in items_data:
            send_image(client_socket, item['id'])
            ack = client_socket.recv(1024).decode('utf-8')
            if ack != "NEXT_IMAGE":
                break
    except sqlite3.Error as e:
        print(f"Database error when retrieving items: {e}")
        client_socket.send("Server error. Please try again later.".encode('utf-8'))
    

def send_message(sender_username, recipient_username, message):
    if recipient_username in online_users:
        recipient_socket = online_users[recipient_username][0]
        message = {
            "message":f"Message from {sender_username}: {message}"
        }
        message_json = json.dumps(message)
        recipient_socket.send(message_json.encode('utf-8'))
    else:
        sender_socket = online_users[sender_username][0]
        message = {
            "message":f"{recipient_username} is currently offline."
        }
        message_json = json.dumps(message)
        sender_socket.send(message_json.encode('utf-8'))


def handle_server():
    """Main server loop to accept client connections"""
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server_socket.bind(("localhost", int(sys.argv[1])))
        server_socket.  listen(100)
    except socket.error as e:
        print(f"Error starting server: {e}")
        return
    db_path = "botique.db"
    create_Tables(db_path)
    while True:
        try:
            client_socket, addr = server_socket.accept()
            client_thread = threading.Thread(target=handle_client, args=(server_socket, client_socket, addr, db_path))
            client_thread.daemon = True
            client_thread.start()
        except Exception as e:
            print(f"Error accepting client connection: {e}")
            server_socket.close()
            break

handle_server()