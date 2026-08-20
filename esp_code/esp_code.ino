#include <Wire.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include "MAX30105.h"

// ===============================
// Network & Broker Configuration
// ===============================
const char* ssid = "Down";
const char* password = "talakowifi";
const char* mqtt_server = "192.168.1.24";
const int mqtt_port = 1883;

const char* mqtt_topic = "sensor/vascular";
const char* mqtt_control_topic = "sensor/control";

WiFiClient espClient;
PubSubClient client(espClient);
MAX30105 particleSensor;

#define ANALOG_PIN 34 // ADC1_CH6 (Safe with Wi-Fi)

// ===============================
// Sampling & FreeRTOS Specs
// ===============================
const uint16_t SAMPLE_RATE = 500;
const uint32_t SAMPLE_PERIOD = 1000000UL / SAMPLE_RATE; // 2000 us
#define IR_READ_DIVIDER 4 // 125 Hz for PPG

volatile bool is_measuring = false;
const uint16_t CHUNK_SIZE = 25; // Send 25 samples every 50ms (20Hz TX)

struct SensorReading {
    uint32_t timestamp;
    uint32_t red;
    uint32_t ir;
    int pcg;
};

QueueHandle_t sensorQueue;
TaskHandle_t TaskDataAcquisition;
TaskHandle_t TaskNetworkTransmission;

// ===============================
// Inbound MQTT Callback
// ===============================
void callback(char* topic, byte* payload, unsigned int length) {
    String message = "";
    for (int i = 0; i < length; i++) {
        message += (char)payload[i];
    }
    message.trim();

    Serial.print("📥 MQTT Received [");
    Serial.print(topic);
    Serial.print("]: ");
    Serial.println(message);

    if (String(topic) == mqtt_topic && message == "1") {
        Serial.println("👋 Handshake matched! Replying '2'...");
        client.publish(mqtt_topic, "2");
    }

    if (String(topic) == mqtt_control_topic) {
        if (message == "START_MEASURE") {
            xQueueReset(sensorQueue);
            is_measuring = true;
            Serial.println("▶️ START CAPTURE activated!");
        } else if (message == "STOP_MEASURE") {
            is_measuring = false;
            Serial.println("⏹️ STOP CAPTURE halted!");
        }
    }
}

// ===============================
// Wi-Fi / MQTT Engine
// ===============================
void setup_wifi() {
    delay(10);
    Serial.print("Connecting to Wi-Fi: ");
    Serial.println(ssid);
    WiFi.begin(ssid, password);
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }
    Serial.println("\n✅ Wi-Fi Connected!");
    Serial.print("IP Address: ");
    Serial.println(WiFi.localIP());
}

void reconnect() {
    while (!client.connected()) {
        Serial.print("Connecting to MQTT broker...");
        String clientId = "ESP32Client-" + String(random(0, 1000));
        if (client.connect(clientId.c_str())) {
            Serial.println(" Connected!");
            client.subscribe(mqtt_topic);
            client.subscribe(mqtt_control_topic);
        } else {
            Serial.print(" Failed, rc=");
            Serial.print(client.state());
            Serial.println(" Retrying in 5 seconds...");
            vTaskDelay(5000 / portTICK_PERIOD_MS);
        }
    }
}

// ==========================================
// CORE 1: Hardware Timed Data Acquisition
// ==========================================
void core1SensorTask(void * parameter) {
    uint32_t lastSample = micros();
    uint32_t sampleTick = 0;
    uint32_t lastRed = 0;
    uint32_t lastIr = 0;
    SensorReading reading;

    for (;;) {
        if (!is_measuring) {
            vTaskDelay(10 / portTICK_PERIOD_MS);
            lastSample = micros();
            continue;
        }

        if (micros() - lastSample >= SAMPLE_PERIOD) {
            lastSample += SAMPLE_PERIOD;

            reading.pcg = analogRead(ANALOG_PIN);

            if ((sampleTick % IR_READ_DIVIDER) == 0) {
                lastIr = particleSensor.getIR();
            }
            sampleTick++;

            reading.red = 0;
            reading.ir = lastIr;
            reading.timestamp = micros();

            xQueueSend(sensorQueue, &reading, 0);
        }
        yield();
    }
}

// ==========================================
// CORE 0: Network Batcher & Publisher
// ==========================================
void core0NetworkTask(void * parameter) {
    String payloadChunk;
    payloadChunk.reserve(1500);
    SensorReading incomingReading;
    uint16_t batchCounter = 0;

    for (;;) {
        if (!client.connected()) {
            reconnect();
        }
        client.loop(); // Check for incoming messages at the top of the loop

        if (!is_measuring) {
            batchCounter = 0;
            payloadChunk = "";
            vTaskDelay(10 / portTICK_PERIOD_MS);
            continue;
        }

        while (xQueueReceive(sensorQueue, &incomingReading, 0) == pdPASS) {
            payloadChunk += String(incomingReading.timestamp) + "," +
                            String(incomingReading.red) + "," +
                            String(incomingReading.ir) + "," +
                            String(incomingReading.pcg) + ";";
            batchCounter++;

            if (batchCounter >= CHUNK_SIZE) {
                client.publish(mqtt_topic, payloadChunk.c_str());
                payloadChunk = "";
                batchCounter = 0;
                
                // CRITICAL FIX: Force the ESP32 to process incoming STOP commands 
                // immediately after sending a chunk, preventing starvation.
                client.loop(); 
            }
        }
        vTaskDelay(1 / portTICK_PERIOD_MS);
    }
}

// ===============================
// Setup & Loop
// ===============================
void setup() {
    Serial.begin(115200);

    analogReadResolution(12);
    analogSetPinAttenuation(ANALOG_PIN, ADC_11db);

    setup_wifi();

    Wire.begin(21, 22);
    Wire.setClock(400000);

    Serial.print("Initializing MAX30102...");
    if (!particleSensor.begin(Wire, I2C_SPEED_FAST)) {
        Serial.println(" NOT FOUND!");
        while (1);
    }
    Serial.println(" Initialized!");

    particleSensor.setup(60, 1, 2, 400, 411, 4096);
    particleSensor.setPulseAmplitudeRed(0x3C);
    particleSensor.setPulseAmplitudeIR(0x3C);
    particleSensor.clearFIFO();

    client.setServer(mqtt_server, mqtt_port);
    client.setCallback(callback);

    // CRITICAL: Expand the buffer from default 256 bytes to 3000 bytes!
    client.setBufferSize(3000);

    sensorQueue = xQueueCreate(250, sizeof(SensorReading));

    xTaskCreatePinnedToCore(core1SensorTask, "SensorCore", 8192, NULL, 1, &TaskDataAcquisition, 1);
    xTaskCreatePinnedToCore(core0NetworkTask, "NetworkCore", 8192, NULL, 1, &TaskNetworkTransmission, 0);
}

void loop() {
    vTaskDelay(1000 / portTICK_PERIOD_MS);
}