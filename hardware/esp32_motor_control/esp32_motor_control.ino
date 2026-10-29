#include <WiFi.h>
#include <WebServer.h>

//==============================
// WiFi Credentials
//==============================
const char* WIFI_SSID = "Yoho";
const char* WIFI_PASSWORD = "ashish12";

//==============================
// L298N Motor Pins
//==============================
const int MOTOR_ENABLE_A = 33;
const int MOTOR_A_IN1    = 26;
const int MOTOR_A_IN2    = 27;

const int MOTOR_B_IN1    = 14;
const int MOTOR_B_IN2    = 12;
const int MOTOR_ENABLE_B = 25;

//==============================
// Direction Switch
// GPIO32 ----- Switch ----- GND
//==============================
const int SWITCH_PIN = 32;

// Stop duration after AI detection (3 seconds)
const unsigned long STOP_DURATION_MS = 3000;

WebServer server(80);

bool motorsRunning = true;
unsigned long stopStartedAt = 0;

//====================================================
// Rotate Clockwise
//====================================================
void clockwise() {
  digitalWrite(MOTOR_A_IN1, HIGH);
  digitalWrite(MOTOR_A_IN2, LOW);

  digitalWrite(MOTOR_B_IN1, HIGH);
  digitalWrite(MOTOR_B_IN2, LOW);

  Serial.println("CLOCKWISE");
}

//====================================================
// Rotate Anticlockwise
//====================================================
void anticlockwise() {
  digitalWrite(MOTOR_A_IN1, LOW);
  digitalWrite(MOTOR_A_IN2, HIGH);

  digitalWrite(MOTOR_B_IN1, LOW);
  digitalWrite(MOTOR_B_IN2, HIGH);

  Serial.println("ANTICLOCKWISE");
}

//====================================================
// Start Motors
//====================================================
void startMotors() {
  if (digitalRead(SWITCH_PIN) == HIGH)
    clockwise();
  else
    anticlockwise();

  digitalWrite(MOTOR_ENABLE_A, HIGH);
  digitalWrite(MOTOR_ENABLE_B, HIGH);

  motorsRunning = true;
}

//====================================================
// Stop Motors
//====================================================
void stopMotors() {
  digitalWrite(MOTOR_ENABLE_A, LOW);
  digitalWrite(MOTOR_ENABLE_B, LOW);

  digitalWrite(MOTOR_A_IN1, LOW);
  digitalWrite(MOTOR_A_IN2, LOW);

  digitalWrite(MOTOR_B_IN1, LOW);
  digitalWrite(MOTOR_B_IN2, LOW);

  motorsRunning = false;
  stopStartedAt = millis();

  Serial.println("MOTORS STOPPED");
}

//====================================================
// JSON Response
//====================================================
String statusJson(const String& message) {
  String state = motorsRunning ? "Running" : "Stopped";

  return "{\"connected\":true,"
         "\"motor_status\":\"" + state +
         "\",\"message\":\"" + message + "\"}";
}

//====================================================
// HTTP API
//====================================================
void handleStatus() {
  server.send(200, "application/json", statusJson("ESP32 Online"));
}

void handleStop() {
  Serial.println("STOP REQUEST RECEIVED");

  stopMotors();

  server.send(
      200,
      "application/json",
      statusJson("Motor stopped"));
}

//====================================================
// GPIO Setup
//====================================================
void setupPins() {
  pinMode(MOTOR_ENABLE_A, OUTPUT);
  pinMode(MOTOR_ENABLE_B, OUTPUT);

  pinMode(MOTOR_A_IN1, OUTPUT);
  pinMode(MOTOR_A_IN2, OUTPUT);

  pinMode(MOTOR_B_IN1, OUTPUT);
  pinMode(MOTOR_B_IN2, OUTPUT);

  pinMode(SWITCH_PIN, INPUT_PULLUP);
}

//====================================================
// WiFi
//====================================================
void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  Serial.print("Connecting to WiFi");

  int retry = 0;

  while (WiFi.status() != WL_CONNECTED && retry < 30) {
    delay(500);
    Serial.print(".");
    retry++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println();
    Serial.println("WiFi Connected");

    Serial.print("IP Address : ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println();
    Serial.println("WiFi Connection Failed");
  }
}

//====================================================
// Setup
//====================================================
void setup() {
  Serial.begin(115200);

  setupPins();
  startMotors();
  connectWiFi();

  server.on("/status", HTTP_GET, handleStatus);
  server.on("/stop", HTTP_POST, handleStop);

  server.begin();

  Serial.println("HTTP Server Started");
}

//====================================================
// Loop
//====================================================
void loop() {
  server.handleClient();

  // Change direction immediately when switch changes
  static int previousState = HIGH;
  int currentState = digitalRead(SWITCH_PIN);

  if (currentState != previousState && motorsRunning) {
    delay(50);
    previousState = currentState;
    startMotors();
  }

  // Restart after AI stop
  if (!motorsRunning &&
      millis() - stopStartedAt >= STOP_DURATION_MS) {
    Serial.println("Restarting Motors");
    startMotors();
  }
}