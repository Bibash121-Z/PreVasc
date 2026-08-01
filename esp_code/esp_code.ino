#include <Wire.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include "MAX30105.h"

// =========================================================================
// Block 1: LAN Network & Local Broker Setup
// =========================================================================

const char* ssid = "MrZ";
const char* password = "12345678";

// IMPORTANT: Change this to your laptop's current active hotspot IP!
const char* mqtt_server = "192.168.43.252";

const int mqtt_port = 1883;
const char* mqtt_topic = "sensor/vascular";
const char* mqtt_control_topic = "sensor/control";

WiFiClient espClient;
PubSubClient client(espClient);
MAX30105 particleSensor;

// =========================================================================
// Block 2: Sampling, Control, & Buffer Configuration (100 Hz)
// =========================================================================

const uint16_t SAMPLE_RATE = 100;
const uint32_t SAMPLE_PERIOD = 1000000UL / SAMPLE_RATE;
uint32_t lastSample = 0;

// Non-blocking control flag for starting/stopping measurements
bool is_measuring = false;

// Batching buffer parameters to protect LAN transmission rate stability
String csvBuffer = "";
uint16_t sampleCounter = 0;
const uint16_t CHUNK_SIZE = 5; // Reduced to 5 to fit standard MQTT JSON payload limits

// =========================================================================
// Block 3: Inbound Data Receiver Handler
// =========================================================================

void callback(char* topic, byte* payload, unsigned int length) {
    String message = "";

    for (int i = 0; i < length; i++) {
        message += (char)payload[i];
    }

    message.trim();

    Serial.print("Received from Topic [");
    Serial.print(topic);
    Serial.print("]: ");
    Serial.println(message);

    // Handshake check on the data topic
    if (String(topic) == mqtt_topic && message == "1") {
        Serial.println("Handshake '1' matched! Replying with '2' to confirm...");
        client.publish(mqtt_topic, "2");
    }

    // START/STOP checks on the control topic
    if (String(topic) == mqtt_control_topic) {
        if (message == "START_MEASURE") {
            is_measuring = true;
            csvBuffer = "";
            sampleCounter = 0;
            lastSample = micros();
            Serial.println("START Command Received. Initiating sensor acquisition loop.");
        } else if (message == "STOP_MEASURE") {
            is_measuring = false;
            Serial.println("STOP Command Received. Halting acquisition loop.");
        }
    }
}

// =========================================================================
// Block 4: Automated Wi-Fi Login Engine
// =========================================================================

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

    Serial.println("\nWi-Fi Connected!");
    Serial.print("ESP32 IP Address: ");
    Serial.println(WiFi.localIP());
}

// =========================================================================
// Block 5: Local Server Reconnection Loop
// =========================================================================

void reconnect() {
    while (!client.connected()) {
        Serial.print("Attempting local MQTT connection to PC/Laptop...");

        String clientId = "ESP32Client-" + String(random(0, 1000));

        if (client.connect(clientId.c_str())) {
            Serial.println("Connected to Local Broker!");

            client.subscribe(mqtt_topic);
            client.subscribe(mqtt_control_topic);

            Serial.println("Subscribed to data and control topics successfully.");
        } else {
            Serial.print("Failed, rc=");
            Serial.print(client.state());
            Serial.println(" Retrying in 5 seconds...");
            delay(5000);
        }
    }
}

// =========================================================================
// Block 6: Master Hardware & Network Initializer
// =========================================================================

void masterConnectSetup() {
    setup_wifi();

    // Explicitly initialize custom I2C pins and fast clock speed
    Wire.begin(21, 22);
    Wire.setClock(400000);

    Serial.print("Initializing MAX30102...");

    if (!particleSensor.begin(Wire, I2C_SPEED_FAST)) {
        Serial.println("\nMAX30102 was not found. Please check wiring/power!");
        while (1);
    }

    Serial.println("MAX30102 Initialized!");

    // Hardware parameters configured for exact 100 Hz operation
    particleSensor.setup(
        80,          // LED Brightness (0–255)
        1,           // Sample Averaging
        2,           // LED Mode (Red + IR)
        SAMPLE_RATE, // Sample Rate
        411,         // Pulse Width
        4096         // ADC Range
    );

    // Precise amplitude settings
    particleSensor.setPulseAmplitudeRed(0x32);
    particleSensor.setPulseAmplitudeIR(0x32);

    client.setServer(mqtt_server, mqtt_port);
    client.setCallback(callback);

    lastSample = micros();
}

// =========================================================================
// Block 7: Master Runtime & Sensor Loop (With Chunking/Batching)
// =========================================================================

void masterConnectLoop() {
    if (!client.connected()) {
        reconnect();
    }

    client.loop();

    // If the browser dashboard hasn't clicked "Start Capture", skip sampling completely
    if (!is_measuring) {
        return;
    }

    // High-precision microsecond sampling interval checks
    if (micros() - lastSample >= SAMPLE_PERIOD) {
        lastSample += SAMPLE_PERIOD;

        // Get fresh sensor metrics
        uint32_t redValue = particleSensor.getRed();
        uint32_t irValue = particleSensor.getIR();
        uint32_t timestamp = micros();

        // Package data points as a JSON object
        String jsonItem = "{\"t\":" + String(timestamp) + ",\"r\":" + String(redValue) + ",\"i\":" + String(irValue) + "}";

        if (sampleCounter == 0) {
            csvBuffer = "[" + jsonItem;
        } else {
            csvBuffer += "," + jsonItem;
        }

        sampleCounter++;

        // Once the buffer reaches the batch chunk target size, ship out a single payload
        if (sampleCounter >= CHUNK_SIZE) {
            csvBuffer += "]"; // Close the JSON array
            client.publish(mqtt_topic, csvBuffer.c_str());

            // Clean out local state buffers for next capture frame
            csvBuffer = "";
            sampleCounter = 0;
        }
    }
}

// =========================================================================
// Arduino Standard Core Handlers
// =========================================================================

void setup() {
    Serial.begin(115200);
    masterConnectSetup();
}

void loop() {
    masterConnectLoop();
}