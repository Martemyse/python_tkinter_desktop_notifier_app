import pika
import json
import threading
from PySide6.QtWidgets import QApplication, QLabel, QWidget, QVBoxLayout, QHBoxLayout, QFrame, QPushButton, QLineEdit, QGraphicsDropShadowEffect
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QColor
import sys
import os

RABBITMQ_HOST = 'localhost'
RABBITMQ_PORT = 5672
RABBITMQ_USERNAME = 'guest'
RABBITMQ_PASSWORD = 'guest'

DEBUG = True

def get_local_ip():
    import socket
    if DEBUG:
        return '127.0.0.1'
    else:
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        return local_ip

class NotificationWindow(QWidget):
    def __init__(self, sender_user, content):
        super().__init__()
        self.setWindowTitle(f"Notification from {sender_user}")
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Create layout for the window
        layout = QVBoxLayout()
        layout.setContentsMargins(50, 50, 50, 50)
        self.setLayout(layout)

        # Main content frame with shadow
        content_frame = QFrame(self)
        content_frame.setStyleSheet("background-color: white; border-radius: 10px;")
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 150))
        shadow.setOffset(5, 5)
        content_frame.setGraphicsEffect(shadow)

        content_layout = QVBoxLayout()
        content_frame.setLayout(content_layout)
        layout.addWidget(content_frame)

        # Image at top left
        logo_label = QLabel()
        pixmap = QPixmap(os.path.join(os.getcwd(), 'Logo.png'))
        logo_label.setPixmap(pixmap.scaled(150, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        logo_layout = QHBoxLayout()
        logo_layout.addWidget(logo_label, 0, Qt.AlignLeft)
        content_layout.addLayout(logo_layout)

        # Notification content
        sender_label = QLabel(f"Sporočilo od: {sender_user}")
        sender_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        content_layout.addWidget(sender_label)

        server_label = QLabel("LTH Obvestilo (ecotech.utlth-ol.si)")
        server_label.setStyleSheet("font-size: 12px;")
        content_layout.addWidget(server_label)

        content_text = QLabel(content)
        content_text.setWordWrap(True)
        content_text.setStyleSheet("font-size: 14px;")
        content_layout.addWidget(content_text)

        # Reply section with red border
        reply_frame = QFrame(self)
        reply_frame.setStyleSheet("background-color: #f9f9f9; border: 2px solid red; border-radius: 8px; padding: 10px;")
        reply_layout = QVBoxLayout()
        reply_frame.setLayout(reply_layout)

        reply_label = QLabel("Odgovor (neobvezno)")
        reply_layout.addWidget(reply_label)

        self.reply_entry = QLineEdit()
        self.reply_entry.setStyleSheet("padding: 10px;")
        reply_layout.addWidget(self.reply_entry)
        content_layout.addWidget(reply_frame)

        # Acknowledge button
        button_layout = QHBoxLayout()
        self.acknowledge_button = QPushButton("Sem seznanjen")
        self.acknowledge_button.setStyleSheet("""
            QPushButton {
                background-color: #2196F3; 
                color: white; 
                font-size: 18px; 
                padding: 15px;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
        """)
        button_layout.addStretch()
        button_layout.addWidget(self.acknowledge_button)
        button_layout.addStretch()
        content_layout.addLayout(button_layout)

        self.acknowledge_button.clicked.connect(self.acknowledge_message)

    def acknowledge_message(self):
        user_response = self.reply_entry.text() or "Acknowledged"
        send_response(notification_id, user_response)
        self.close()

def on_notification_received(ch, method, properties, body):
    message = json.loads(body)
    sender_user = message.get('sender_user')
    content = message.get('notification_content')

    app = QApplication(sys.argv)
    notification_window = NotificationWindow(sender_user, content)
    notification_window.showFullScreen()
    app.exec_()

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

    local_ip = get_local_ip()
    routing_key = f"ip_{local_ip.replace('.', '_')}"

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
