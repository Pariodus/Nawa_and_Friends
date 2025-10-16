import paho.mqtt.client as mqtt
import sqlite3
import datetime

# --- Database Setup ---
# Connect to the SQLite database file. It will be created if it doesn't exist.
conn = sqlite3.connect('mqtt_messages.db')
c = conn.cursor()

# Create a table to store messages if it doesn't already exist.
c.execute('''
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY,
        timestamp TEXT,
        topic TEXT,
        payload TEXT
    )
''')
conn.commit()

# --- MQTT Callbacks ---
def on_connect(client, userdata, flags, rc):
    """Callback function when a connection is established."""
    print("Connected with result code " + str(rc))
    # Subscribing in on_connect() means that if we lose the connection and
    # reconnect, our subscriptions will be renewed.
    client.subscribe("rpi5/local/#") # Subscribe to all topics under rpi5/local/

def on_message(client, userdata, msg):
    """Callback function when a message is received."""
    # Decode the payload from bytes to a string
    message_payload = msg.payload.decode()
    current_time = datetime.datetime.now().isoformat()
    
    print(f"[{current_time}] Topic: {msg.topic}, Message: {message_payload}")
    
    # Insert the message into the database
    c.execute("INSERT INTO messages (timestamp, topic, payload) VALUES (?, ?, ?)",
              (current_time, msg.topic, message_payload))
    conn.commit()
    
# --- Main Logic ---
# Create an MQTT client instance
client = mqtt.Client()

# Assign the callback functions
client.on_connect = on_connect
client.on_message = on_message

# Connect to the local Mosquitto broker
client.connect("localhost", 1883, 60)

# Loop forever to process network traffic, send keepalive messages, and
# handle reconnects. This is a blocking call.
client.loop_forever()

# Close the database connection when the script exits
conn.close()
