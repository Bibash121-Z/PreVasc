#include <Wire.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include "MAX30105.h" 

// --- Block 1: LAN Network & Local Broker Setup ---
const char* ssid = "MrZ";            // Replace with your Hotspot Name
const char* password = "12345678";    // Replace with your Hotspot Password
const char* mqtt_server = "192.168.43.252";         // Replace with your PC's real Hotspot IP
const int mqtt_port = 1883;                        
const char* mqtt_topic = "sensor/vascular";

WiFiClient espClient; 
PubSubClient client(espClient);
MAX30105 particleSensor;

unsigned long lastPublishTime = 0;
const unsigned long publishInterval = 100; 

// --- Block 2: Inbound data receiver handler ---
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

// --- Block 3: Automated Wi-Fi login engine ---
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

// --- Block 4: Local Server Reconnection Loop ---
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

// --- Block 5: Master Hardware & Network Initializer ---
void masterConnectSetup() {
    setup_wifi();
    
    Serial.print("Initializing MAX30102...");
    if (!particleSensor.begin(Wire, I2C_SPEED_FAST)) {
        Serial.println("\n❌ MAX30102 was not found. Please check wiring/power!");
        while (1); 
    }
    Serial.println("🟢 MAX30102 Initialized!");

    byte ledBrightness = 60; 
    byte sampleAverage = 4;  
    byte ledMode = 2;        
    byte sampleRate = 100;   
    int pulseWidth = 411;    
    int adcRange = 4096;     

    particleSensor.setup(ledBrightness, sampleAverage, ledMode, sampleRate, pulseWidth, adcRange);

    client.setServer(mqtt_server, mqtt_port);
    client.setCallback(callback);
}

// --- Block 6: Master Runtime & Sensor Loop ---
void masterConnectLoop() {
    if (!client.connected()) {
        reconnect();
    }
    client.loop();

    unsigned long currentMillis = millis();
    if (currentMillis - lastPublishTime >= publishInterval) {
        lastPublishTime = currentMillis;

        uint32_t redValue = particleSensor.getRed();
        uint32_t irValue = particleSensor.getIR();

        if (irValue < 50000) {
           // Serial.println("Finger status: Please place finger on sensor.");
        } else {
            String payload = String(redValue) + "," + String(irValue);
            Serial.print("Publishing PPG Data: ");
            //Serial.println(payload);
            client.publish(mqtt_topic, payload.c_str());
        }
    }
}

void setup() {
    Serial.begin(115200);
    masterConnectSetup();
}

void loop() {
    masterConnectLoop();
}