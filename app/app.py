import pika
import json
import threading
import tkinter as tk
from tkinter import messagebox, simpledialog
import tkinter.ttk as ttk
from PIL import Image, ImageTk  # PIL to handle image processing (install using `pip install Pillow`)
import sys
import os
import requests

RABBITMQ_HOST = 'localhost' #ecotech on production, localhost --> django baremetal
RABBITMQ_HOST = '10.26.38.132' #docker desktop
RABBITMQ_PORT = 5672
RABBITMQ_USERNAME = 'guest'
RABBITMQ_PASSWORD = 'guest'

DEBUG = False  # Change this based on your environment

def get_local_ip():
    import socket
    if DEBUG:
        return '127.0.0.1'
    else:
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        return local_ip
    
def get_external_ip():
    try:
        # Fetch the external IP using a public API
        external_ip = requests.get('https://api.ipify.org').text
        return external_ip
    except requests.RequestException as e:
        print(f"Error fetching external IP: {e}")
        return None  # Return None or handle error appropriately

def draw_gradient(canvas, width, height):
    '''Simulate a gradient from white to very light blue.'''
    gradient_steps = 100
    for i in range(gradient_steps):
        r = 255
        g = 255 - int(5 * (i / gradient_steps))
        b = 255 - int(10 * (i / gradient_steps))
        color = f'#{r:02x}{g:02x}{b:02x}'
        canvas.create_rectangle(0, i * height // gradient_steps, width, (i + 1) * height // gradient_steps, fill=color, outline=color)

# Add this function to load and display the PNG image in the Tkinter modal
def load_and_display_image(gradient_canvas):
    # Use os.getcwd() to get the current working directory
    image_path = os.path.join(os.getcwd(), 'Logo.png')

    # Open the image using PIL and convert it to a Tkinter-compatible image
    image = Image.open(image_path)
    tk_image = ImageTk.PhotoImage(image)
    
    # Create a label to display the image on top of the canvas
    logo_label = tk.Label(gradient_canvas, image=tk_image, bg="white")
    logo_label.image = tk_image  # Keep a reference to the image to avoid garbage collection
    logo_label.place(x=20, y=20, anchor="nw")  # Place image in the upper-left corner

def on_notification_received(ch, method, properties, body):
    message = json.loads(body)
    notification_id = message.get('notification_id')
    key = message.get('key')
    sender_user = message.get('sender_user')
    content = message.get('notification_content')

    # Create a hidden Tkinter root window
    root = tk.Tk()
    root.withdraw()

    # Create a new modal window to force user acknowledgment
    msg_window = tk.Toplevel(root)
    msg_window.title(f"Notification from {sender_user}")
    msg_window.attributes("-fullscreen", True)  # Fullscreen
    msg_window.grab_set()  # Prevent interaction with other windows
    msg_window.attributes("-topmost", True)  # Keep on top

    # Disable window close
    msg_window.protocol("WM_DELETE_WINDOW", lambda: None)

    # Simulate a gradient background using a canvas
    gradient_canvas = tk.Canvas(msg_window, width=msg_window.winfo_screenwidth(), height=msg_window.winfo_screenheight(), highlightthickness=0)
    gradient_canvas.pack(fill="both", expand=True)
    draw_gradient(gradient_canvas, msg_window.winfo_screenwidth(), msg_window.winfo_screenheight())

    # Schedule the image loading on the main thread
    root.after(0, load_and_display_image, gradient_canvas)

    # Content frame on top of the gradient
    content_frame = tk.Frame(gradient_canvas, bg="white")
    content_frame.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.8, relheight=0.8)

    # Create shadow frame behind the card_frame
    shadow_offset = 5  # Adjust the offset for the shadow
    shadow_frame = tk.Frame(content_frame, bg="#d3d3d3")
    shadow_frame.place(relx=0.5 + shadow_offset / msg_window.winfo_screenwidth(), rely=0.5 + shadow_offset / msg_window.winfo_screenheight(), anchor="center", relwidth=1.0, relheight=1.0)

    # Notification content card
    card_frame = tk.Frame(content_frame, bg="white", bd=2, relief="flat")
    card_frame.place(relx=0.5, rely=0.5, anchor="center", relwidth=1.0, relheight=1.0)

    # Add sender and message details, centered in the card
    sender_label = tk.Label(card_frame, text=f"Sporočilo od: {sender_user}", font=("Helvetica", 16, "bold"), bg="white")
    sender_label.pack(pady=10)

    server_label = tk.Label(card_frame, text="LTH Obvestilo (ecotech.utlth-ol.si)", font=("Helvetica", 12), bg="white")
    server_label.pack(pady=5)
    server_label.bind("<Button-1>", lambda e: os.system("start http://ecotech.utlth-ol.si:8010/"))

    link_label = tk.Label(card_frame, text="Obdelava Ljubljana\nVodja Oddelka: Primož Šušteršič\nLTH Python Aplikacije", font=("Helvetica", 12), fg="blue", bg="white", cursor="hand2")
    link_label.pack(pady=5)
    separator = ttk.Separator(card_frame, orient='horizontal')
    separator.pack(fill='x', pady=10)  # Horizontal separator with some padding

    content_text = tk.Label(card_frame, text=content, wraplength=800, font=("Helvetica", 14), bg="white")
    content_text.pack(pady=10)
    
    separator = ttk.Separator(card_frame, orient='horizontal')
    separator.pack(fill='x', pady=10)  # Horizontal separator with some padding

    # Create a frame to act as the "card" for the reply section
    reply_card = tk.Frame(card_frame, bg="#e0f7fa", bd=0)  # Light gray background
    reply_card.pack(pady=20, padx=20, fill="x")
    
    # Create an optional reply field inside the card
    reply_label = tk.Label(reply_card, text="Odgovor (neobvezno)", bg="#e0f7fa", font=("Helvetica", 14))
    reply_label.pack(pady=10)

    # Create entry frame with red border and shadow
    entry_shadow = tk.Frame(reply_card, bg="#d3d3d3")
    entry_shadow.pack(pady=(0, 10))
    entry_frame = tk.Frame(entry_shadow, bg="white", highlightbackground="red", highlightcolor="red", highlightthickness=2)
    entry_frame.pack(padx=5, pady=5)

    reply_entry = tk.Entry(entry_frame, width=80, font=("Helvetica", 12), bd=0)
    reply_entry.pack(padx=10, pady=10)

    # Handle acknowledgment and send response
    def acknowledge_message():
        user_response = reply_entry.get() or "Acknowledged"  # Use 'Acknowledged' if no response
        send_response(notification_id, user_response)
        msg_window.destroy()  # Close the modal
        root.quit()  # Close the main root window

    # Create shadow for the button
    button_shadow = tk.Frame(card_frame, bg="#d3d3d3")
    button_shadow.pack(pady=20)

    # Add "Acknowledge" button inside the card, centered
    acknowledge_button = tk.Button(button_shadow, text="Sem seznanjen", command=acknowledge_message, font=("Helvetica", 22), bg="#2196F3", fg="white", bd=0, activebackground="#1e88e5", padx=20, pady=10)
    acknowledge_button.pack()

    msg_window.mainloop()

def send_response(notification_id, user_response):
    credentials = pika.PlainCredentials(RABBITMQ_USERNAME, RABBITMQ_PASSWORD)
    parameters = pika.ConnectionParameters(
        host=RABBITMQ_HOST,
        port=RABBITMQ_PORT,
        credentials=credentials
    )

    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()

    exchange_name = 'notifications_responses'
    channel.exchange_declare(exchange=exchange_name, exchange_type='direct', durable=True)

    message = {
        'notification_id': notification_id,
        'user_response': user_response,
    }

    channel.basic_publish(
        exchange=exchange_name,
        routing_key='django_server',
        body=json.dumps(message),
        properties=pika.BasicProperties(
            delivery_mode=2,
        )
    )

    connection.close()

def start_consuming():
    credentials = pika.PlainCredentials(RABBITMQ_USERNAME, RABBITMQ_PASSWORD)
    parameters = pika.ConnectionParameters(
        host=RABBITMQ_HOST,
        port=RABBITMQ_PORT,
        credentials=credentials
    )

    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()

    exchange_name = 'notifications'
    channel.exchange_declare(exchange=exchange_name, exchange_type='direct', durable=True)

    external_ip = get_external_ip()
    routing_key = f"ip_{external_ip.replace('.', '_')}"
    
    # routing_key = f"client_{unique_token}"
    # print(f"Listening for notifications with routing key: {routing_key}")

    result = channel.queue_declare(queue='', exclusive=True)
    queue_name = result.method.queue

    channel.queue_bind(exchange=exchange_name, queue=queue_name, routing_key=routing_key)

    print(f"Listening for notifications on queue {queue_name} with routing key {routing_key}...")

    channel.basic_consume(queue=queue_name, on_message_callback=on_notification_received)

    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        channel.stop_consuming()
        connection.close()
        sys.exit()

if __name__ == '__main__':
    try:
        threading.Thread(target=start_consuming).start()
    except Exception as e:
        print(f"Error running consumer: {e}")
