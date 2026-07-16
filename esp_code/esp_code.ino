#include <Wire.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include "MAX30105.h" 

// --- Block 1: LAN Network & Local Broker Setup ---
const char* ssid = "MrZ";            // Your Hotspot Name
const char* password = "12345678";    // Your Hotspot Password
const char* mqtt_server = "192.168.43.252"; // Your PC's active hotspot IP
const int mqtt_port = 1883;                        
const char* mqtt_topic = "sensor/vascular";

WiFiClient espClient; 
PubSubClient client(espClient);
MAX30105 particleSensor;

// --- Block 2: Sampling Configuration (200 Hz) ---
const uint16_t SAMPLE_RATE = 200;              // 200 Hz for high fidelity
const uint32_t SAMPLE_PERIOD = 1000000UL / SAMPLE_RATE; // Sample period in microseconds (5000 µs)
uint32_t lastSample = 0;

// --- Block 3: Inbound data receiver handler ---
void callback(char* topic, byte* payload, unsigned int length) {
    String message = "";
    for (int i = 0; i < length; i++) {
        message += (char)payload[i];
    }
    message.trim();

    Serial.println("Received from Web: " + message);

    if (message == "1") {
        Serial.println("Handshake '1' matched! Replying with '2' to confirm...");
        client.publish(mqtt_topic, "2");
    }
}

// --- Block 4: Automated Wi-Fi login engine ---
void setup_wifi() {
    delay(10);
    Serial.println();
    Serial.print("Connecting to Hotspot: ");
    Serial.println(ssid);
    
    WiFi.begin(ssid, password);
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }
    Serial.println("\n🟢 Wi-Fi Connected!");
    Serial.print("ESP32 IP Address: ");
    Serial.println(WiFi.localIP());
}

// --- Block 5: Local Server Reconnection Loop ---
void reconnect() {
    while (!client.connected()) {
        Serial.print("Attempting local MQTT connection to PC...");
        String clientId = "ESP32Client-" + String(random(0, 1000));
        
        if (client.connect(clientId.c_str())) { 
            Serial.println("🟢 Connected to Local Broker!");
            client.subscribe(mqtt_topic);
        } else {
            Serial.print("🔴 Failed, rc=");
            Serial.print(client.state());
            Serial.println(" Retrying in 5 seconds...");
            delay(5000);
        }
    }
}

// --- Block 6: Master Hardware & Network Initializer ---
void masterConnectSetup() {
    setup_wifi();
    
    // Explicitly initialize custom I2C pins and fast clock speed
    Wire.begin(21, 22);            // SDA, SCL
    Wire.setClock(400000);         // 400 kHz I2C
    
    Serial.print("Initializing MAX30102...");
    if (!particleSensor.begin(Wire, I2C_SPEED_FAST)) {
        Serial.println("\n❌ MAX30102 was not found. Please check wiring/power!");
        while (1); 
    }
    Serial.println("🟢 MAX30102 Initialized!");

    // Hardware parameters configured for exact 200 Hz operation
    particleSensor.setup(
        80,             // LED Brightness (0–255)
        1,              // Sample Averaging (1 = no averaging for maximum raw data)
        2,              // LED Mode (Red + IR)
        SAMPLE_RATE,    // Sample Rate (200 Hz)
        411,            // Pulse Width (411 µs, 18-bit ADC)
        4096            // ADC Range
    );

    // Precise amplitude settings
    particleSensor.setPulseAmplitudeRed(0x32); 
    particleSensor.setPulseAmplitudeIR(0x32);

    client.setServer(mqtt_server, mqtt_port);
    client.setCallback(callback);
    
    // Initialize timing variable
    lastSample = micros();
}

// --- Block 7: Master Runtime & Sensor Loop ---
void masterConnectLoop() {
    if (!client.connected()) {
        reconnect();
    }
    client.loop();

    // High-precision microsecond sampling interval checks
    if (micros() - lastSample >= SAMPLE_PERIOD) {
        lastSample += SAMPLE_PERIOD;

        uint32_t redValue = particleSensor.getRed();
        uint32_t irValue = particleSensor.getIR();

        // Removed the "irValue < 50000" threshold block.
        // Data streams continuously to allow algorithms to dynamically adapt to finger placement.
        String payload = String(redValue) + "," + String(irValue);
        
        Serial.print("Publishing PPG Data: ");
        Serial.println(payload);
        
        client.publish(mqtt_topic, payload.c_str());
    }
}

void setup() {
    Serial.begin(115200);
    masterConnectSetup();
}

void loop() {
    masterConnectLoop();
}