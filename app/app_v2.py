import pika
import json
import threading
import tkinter as tk
import tkinter.ttk as ttk
from PIL import Image, ImageTk
import os
import requests
from requests.exceptions import ConnectTimeout, ConnectionError
import socket
from dotenv import load_dotenv
import atexit

# Global stop event to manage all threads and loops
stop_event = threading.Event()

# Load environment variables from a standard .env file if present
load_dotenv()
API_BASE_URL = os.getenv('API_BASE_URL', 'http://localhost:8000')
RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
RABBITMQ_PORT = int(os.getenv('RABBITMQ_PORT', 5672))
RABBITMQ_USERNAME = os.getenv('RABBITMQ_USERNAME', 'guest')
RABBITMQ_PASSWORD = os.getenv('RABBITMQ_PASSWORD', 'guest')
TOKEN_FILE_PATH = os.getenv('TOKEN_FILE_PATH', 'app/terminal_token.json')
# Heartbeat interval in minutes (default 3). Convert to milliseconds for Tkinter's after().
HEARTBEAT_MINS = int(os.getenv('HEARTBEAT_MINS', '3'))
HEARTBEAT_MS = HEARTBEAT_MINS * 60 * 1000

# Global state
token = None

# Initialize Tkinter
root = tk.Tk()
root.title("Connection Status")
root.protocol("WM_DELETE_WINDOW", lambda: None)  # Disable window close button
status_label = tk.Label(root, text="Initializing...", font=("Helvetica", 12))
status_label.pack()


# Function to load the token from a local file if it exists
def load_local_token():
    global token
    if os.path.exists(TOKEN_FILE_PATH):
        with open(TOKEN_FILE_PATH, 'r') as f:
            data = json.load(f)
            token = data.get('token')
            print(f"Loaded token from file: {token}")
            return True
    return False

# Function to save the token to a local file
def save_local_token(token):
    with open(TOKEN_FILE_PATH, 'w') as f:
        json.dump({'token': token}, f)
    print(f"Token saved locally: {token}")

# Function to update the status in the Tkinter UI
def update_status(new_status):
    status_label.config(text=f"Status: {new_status}")
    root.update_idletasks()
    
def send_sign_out():
    hostname = socket.gethostname()
    try:
        response = requests.post(f'{API_BASE_URL}/terminal_sign_out/', data={'hostname': hostname}, timeout=10)
        print("Sent sign out signal.")
    except Exception as e:
        print(f"Error sending sign out: {e}")

atexit.register(send_sign_out)
    
def send_heartbeat():
    """ Periodically sends a heartbeat signal. """
    if stop_event.is_set():
        return
    hostname = socket.gethostname()
    try:
        response = requests.post(f'{API_BASE_URL}/terminal_heartbeat/', data={'hostname': hostname}, timeout=10)
        if response.status_code == 200:
            print("Heartbeat sent successfully.")
        else:
            print(f"Heartbeat failed: {response.content}")
    except Exception as e:
        print(f"Error sending heartbeat: {e}")
    root.after(HEARTBEAT_MS, send_heartbeat)  # Schedule the next heartbeat

    
def send_status_update(notification_id, status):
    credentials = pika.PlainCredentials(RABBITMQ_USERNAME, RABBITMQ_PASSWORD)
    parameters = pika.ConnectionParameters(host=RABBITMQ_HOST, port=RABBITMQ_PORT, credentials=credentials)

    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()
    exchange_name = 'notifications_responses'
    channel.exchange_declare(exchange=exchange_name, exchange_type='direct', durable=True)

    message = {
        'notification_id': notification_id,
        'status': status
    }

    channel.basic_publish(
        exchange=exchange_name,
        routing_key='django_server',
        body=json.dumps(message),
        properties=pika.BasicProperties(delivery_mode=2)
    )
    connection.close()


def get_external_ip():
    if API_BASE_URL == 'http://localhost:8000':
        # Use localhost IP if running locally
        return '127.0.0.1'
    try:
        external_ip = requests.get('https://api.ipify.org').text
        return external_ip
    except requests.RequestException as e:
        print(f"Error fetching external IP: {e}")
        return None

def pair_with_server():
    global token
    external_ip = get_external_ip()
    hostname = socket.gethostname()

    update_status("Pairing...")
    try:
        response = requests.post(f'{API_BASE_URL}/pair/', data={'external_ip': external_ip, 'hostname': hostname}, timeout=10)
        if response.status_code == 200:
            token = response.json().get('token')
            print(f"Successfully paired with token: {token}")
            save_local_token(token)
            update_status("Paired with server")
            return True
        else:
            print("Pairing failed.")
            update_status("Pairing failed.")
            return False
    except (ConnectTimeout, ConnectionError) as e:
        print(f"Connection error during pairing: {e}")
        update_status("Connection failed, retrying...")
        return False
    except Exception as e:
        print(f"Unexpected error during pairing: {e}")
        update_status("Unexpected error, retrying...")
        return False

def attempt_pairing():
    retry_delay = 5  # Initial retry delay (seconds)

    while not stop_event.is_set():
        if pair_with_server():
            # Start consuming messages in a separate thread
            consumer_thread = threading.Thread(target=start_consuming, daemon=True)
            consumer_thread.start()
            break
        else:
            update_status(f"Pairing failed, retrying in {retry_delay} seconds...")
            if stop_event.wait(timeout=retry_delay):  # Wait with timeout for retry
                break  # If stop_event is set, exit the loop
            retry_delay = min(retry_delay * 2, 60)  # Increase delay up to max of 60 seconds

def start_consuming():
    global token
    while not stop_event.is_set():
        try:
            credentials = pika.PlainCredentials(RABBITMQ_USERNAME, RABBITMQ_PASSWORD)
            parameters = pika.ConnectionParameters(
                host=RABBITMQ_HOST,
                port=RABBITMQ_PORT,
                credentials=credentials,
            )
            
            connection = pika.BlockingConnection(parameters)
            channel = connection.channel()
            exchange_name = 'notifications'
            channel.exchange_declare(exchange=exchange_name, exchange_type='direct', durable=True)
            
            queue_name = f'queue_{token}'
            channel.queue_declare(queue=queue_name, durable=True)
            channel.queue_bind(exchange=exchange_name, queue=queue_name, routing_key=token)
            
            print(f"Listening for notifications on queue {queue_name} with routing key {token}...")
            update_status("Connected and Listening")
            channel.basic_consume(queue=queue_name, on_message_callback=on_notification_received, auto_ack=True)
    
            # Start consuming messages
            channel.start_consuming()
        except pika.exceptions.ChannelClosedByBroker as e:
            print(f"Channel closed by broker: {e}")
            update_status("Token invalid or expired. Re-pairing...")
            if pair_with_server():
                save_local_token(token)
                continue  # Restart consuming with new token
            else:
                update_status("Re-pairing failed, retrying...")
                if stop_event.wait(timeout=5):  # Wait 5 seconds or until stop_event is set
                    break
        except pika.exceptions.AMQPConnectionError as e:
            print(f"RabbitMQ connection error: {e}")
            update_status("Connection lost, reconnecting...")
            if stop_event.wait(timeout=5):  # Retry with a 5-second delay
                break
        except Exception as e:
            print(f"Unexpected error in start_consuming: {e}")
            update_status("Unexpected error, reconnecting...")
            if stop_event.wait(timeout=5):  # Retry with a 5-second delay
                break
            
def draw_gradient(canvas, width, height):
    gradient_steps = 100
    for i in range(gradient_steps):
        r = 255
        g = 255 - int(5 * (i / gradient_steps))
        b = 255 - int(10 * (i / gradient_steps))
        color = f'#{r:02x}{g:02x}{b:02x}'
        canvas.create_rectangle(0, i * height // gradient_steps, width, (i + 1) * height // gradient_steps, fill=color, outline=color)

def load_and_display_image(gradient_canvas):
    global tk_image
    try:
        image_path = os.path.join(os.getcwd(), 'Logo.png')
        image = Image.open(image_path)
        tk_image = ImageTk.PhotoImage(image)  # Store in global variable to prevent GC
        logo_label = tk.Label(gradient_canvas, image=tk_image, bg="white")
        logo_label.image = tk_image  # Keep reference
        logo_label.place(x=20, y=20, anchor="nw")
    except Exception:
        # If image is missing or cannot be loaded, skip silently
        pass

def on_notification_received(ch, method, properties, body):
    message = json.loads(body)
    notification_id = message.get('notification_id')
    sender_user = message.get('sender_user')
    content = message.get('notification_content')
    
    # Send 'delivered' status back to the server
    send_status_update(notification_id, status='delivered')

    # Schedule the UI update in the main thread
    root.after(0, show_notification, notification_id, sender_user, content)

def show_notification(notification_id, sender_user, content):
    msg_window = tk.Toplevel(root)
    msg_window.title(f"Notification from {sender_user}")
    msg_window.attributes("-fullscreen", True)
    msg_window.grab_set()
    msg_window.attributes("-topmost", True)
    msg_window.protocol("WM_DELETE_WINDOW", lambda: None)

    gradient_canvas = tk.Canvas(msg_window, width=msg_window.winfo_screenwidth(), height=msg_window.winfo_screenheight(), highlightthickness=0)
    gradient_canvas.pack(fill="both", expand=True)
    draw_gradient(gradient_canvas, msg_window.winfo_screenwidth(), msg_window.winfo_screenheight())

    load_and_display_image(gradient_canvas)  # Load image in main thread

    content_frame = tk.Frame(gradient_canvas, bg="white")
    content_frame.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.8, relheight=0.8)

    shadow_offset = 5
    shadow_frame = tk.Frame(content_frame, bg="#d3d3d3")
    shadow_frame.place(relx=0.5 + shadow_offset / msg_window.winfo_screenwidth(), rely=0.5 + shadow_offset / msg_window.winfo_screenheight(), anchor="center", relwidth=1.0, relheight=1.0)

    card_frame = tk.Frame(content_frame, bg="white", bd=2, relief="flat")
    card_frame.place(relx=0.5, rely=0.5, anchor="center", relwidth=1.0, relheight=1.0)

    sender_label = tk.Label(card_frame, text=f"Sporočilo od: {sender_user}", font=("Helvetica", 16, "bold"), bg="white")
    sender_label.pack(pady=10)

    server_label = tk.Label(card_frame, text="LTH Obvestilo (ecotech.utlth-ol.si)", font=("Helvetica", 12), bg="white")
    server_label.pack(pady=5)
    server_label.bind("<Button-1>", lambda e: os.system("start http://ecotech.utlth-ol.si:8010/"))

    link_label = tk.Label(card_frame, text="Obdelava Ljubljana\nVodja Oddelka: Primož Šušteršič\nLTH Python Aplikacije", font=("Helvetica", 12), fg="blue", bg="white", cursor="hand2")
    link_label.pack(pady=5)
    separator = ttk.Separator(card_frame, orient='horizontal')
    separator.pack(fill='x', pady=10)

    content_text = tk.Label(card_frame, text=content, wraplength=800, font=("Helvetica", 14), bg="white")
    content_text.pack(pady=10)
    
    separator = ttk.Separator(card_frame, orient='horizontal')
    separator.pack(fill='x', pady=10)

    reply_card = tk.Frame(card_frame, bg="#e0f7fa", bd=0)
    reply_card.pack(pady=20, padx=20, fill="x")
    
    reply_label = tk.Label(reply_card, text="Odgovor (neobvezno)", bg="#e0f7fa", font=("Helvetica", 14))
    reply_label.pack(pady=10)

    entry_shadow = tk.Frame(reply_card, bg="#d3d3d3")
    entry_shadow.pack(pady=(0, 10))
    entry_frame = tk.Frame(entry_shadow, bg="white", highlightbackground="red", highlightcolor="red", highlightthickness=2)
    entry_frame.pack(padx=5, pady=5)

    reply_entry = tk.Entry(entry_frame, width=80, font=("Helvetica", 12), bd=0)
    reply_entry.pack(padx=10, pady=10)

    def acknowledge_message():
        # user_response = reply_entry.get() or "Acknowledged"
        # send_response(notification_id, user_response)
        user_response = reply_entry.get()
        if user_response.strip():
            status = 'replied'
        else:
            status = 'read'
            user_response = None  # or set to empty string
            
        send_response(notification_id, user_response, status)
        msg_window.destroy()

    button_shadow = tk.Frame(card_frame, bg="#d3d3d3")
    button_shadow.pack(pady=20)

    acknowledge_button = tk.Button(button_shadow, text="Sem seznanjen", command=acknowledge_message, font=("Helvetica", 22), bg="#2196F3", fg="white", bd=0, activebackground="#1e88e5", padx=20, pady=10)
    acknowledge_button.pack()


def send_response(notification_id, user_response, status):
    credentials = pika.PlainCredentials(RABBITMQ_USERNAME, RABBITMQ_PASSWORD)
    parameters = pika.ConnectionParameters(host=RABBITMQ_HOST, port=RABBITMQ_PORT, credentials=credentials)

    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()
    exchange_name = 'notifications_responses'
    channel.exchange_declare(exchange=exchange_name, exchange_type='direct', durable=True)

    message = {
        'notification_id': notification_id,
        'user_response': user_response,
        'status': status
    }

    channel.basic_publish(
        exchange=exchange_name,
        routing_key='django_server',
        body=json.dumps(message),
        properties=pika.BasicProperties(delivery_mode=2)
    )
    connection.close()

if __name__ == '__main__':
    try:
        pairing_thread = None
        consumer_thread = None

        # If a token already exists locally, start consuming immediately; otherwise, attempt pairing
        if load_local_token():
            consumer_thread = threading.Thread(target=start_consuming, daemon=True)
            consumer_thread.start()
            update_status("Using saved token; connected")
        else:
            pairing_thread = threading.Thread(target=attempt_pairing, daemon=True)
            pairing_thread.start()

        # Schedule the first heartbeat call in the Tkinter event loop
        root.after(0, send_heartbeat)

        # Start the Tkinter main loop
        root.mainloop()
    except KeyboardInterrupt:
        print("Exiting...")
        stop_event.set()
        if pairing_thread is not None:
            pairing_thread.join(timeout=2)
        send_sign_out()
        print("Exited gracefully.")