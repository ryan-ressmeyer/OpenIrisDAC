
/*
*  dpi-knobs.ino
*  Authored by Ryan Ressmeyer 8/19/23
* 
*  TODO: Reverse engineer and document the hardware better
*  This arduino sketch runs the dpi rotary encoder knobs for
*  bias, gain, and rotation. It communiates with the OpenIrisDac or 
*  cvdpi projects for eye tracking. It works by triggering an event on the
*  falling edge of one of the output pins of *any* rotary encoder.
*  This is achieved using a capacitor and some leds in an arrangement I do not 
*  remember (I'm pretty sure each lead gets an LED and is connected to a capacitor)
*  RE1 -> LED -> CAP -> GND
*  RE2 -> LED -^    \-> Trigger Pin
*/

const byte encoder5A = 1;//outputA digital pin2
const byte encoder5B = 4;//outoutB digital pin3

const byte encoder4A = 5;//outputA digital pin2
const byte encoder4B = 6;//outoutB digital pin3

const byte encoder3A = 7;//outputA digital pin2
const byte encoder3B = 8;//outoutB digital pin3

const byte encoder2A = 9;//outputA digital pin2
const byte encoder2B = 10;//outoutB digital pin3

const byte encoder1A = 11;//outputA digital pin2
const byte encoder1B = 12;//outoutB digital pin3

const byte interruptPin = 0;

volatile int count1 = 0;
int protectedCount1 = 0;
int previousCount1 = 0;
const float x_bias_res = .5;
const float x_bias_offset = 80;
float x_bias = x_bias_offset;

volatile int count2 = 0;
int protectedCount2 = 0;
int previousCount2 = 0;
const float y_bias_res = .5;
const float y_bias_offset = 10;
float y_bias = y_bias_offset;


volatile int count3 = 0;
int protectedCount3 = 0;
int previousCount3 = 0;
const float x_gain_res = .2;
const float x_gain_offset = 20.0;
float x_gain = x_gain_offset;


volatile int count4 = 0;
int protectedCount4 = 0;
int previousCount4 = 0;
const float y_gain_res = .2;
const float y_gain_offset = -20.0;
float y_gain = y_gain_offset;

volatile int count5 = 0;
int protectedCount5 = 0;
int previousCount5 = 0;
const float rotation_res = .1;
const float rotation_offset = 0.0;
float rotation = rotation_offset;

#include <SPI.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

#define SCREEN_WIDTH 128 // OLED display width, in pixels
#define SCREEN_HEIGHT 64 // OLED display height, in pixels

// Declaration for an SSD1306 display connected to I2C (SDA, SCL pins)
// The pins for I2C are defined by the Wire-library. 
// On an arduino UNO:       A4(SDA), A5(SCL)
// On an arduino MEGA 2560: 20(SDA), 21(SCL)
// On an arduino LEONARDO:   2(SDA),  3(SCL), ...
#define OLED_RESET     -1 // Reset pin # (or -1 if sharing Arduino reset pin)
#define SCREEN_ADDRESS 0x3C ///< See datasheet for Address; 0x3D for 128x64, 0x3C for 128x32
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);


void setup() {
  Serial.begin (9600);
  
  // SSD1306_SWITCHCAPVCC = generate display voltage from 3.3V internally
  if(!display.begin(SSD1306_SWITCHCAPVCC, SCREEN_ADDRESS)) {
    Serial.println(F("SSD1306 allocation failed"));
    for(;;); // Don't proceed, loop forever
  }

  updateScreen();

  pinMode(encoder1A, INPUT_PULLUP);
  pinMode(encoder1B, INPUT_PULLUP);
  
  pinMode(encoder2A, INPUT_PULLUP);
  pinMode(encoder2B, INPUT_PULLUP);
  
  
  pinMode(encoder3A, INPUT_PULLUP);
  pinMode(encoder3B, INPUT_PULLUP);
  
  pinMode(encoder4A, INPUT_PULLUP);
  pinMode(encoder4B, INPUT_PULLUP);
  
  pinMode(encoder5A, INPUT_PULLUP);
  pinMode(encoder5B, INPUT_PULLUP);
  
  pinMode(interruptPin, INPUT_PULLUP);
  
  attachInterrupt(digitalPinToInterrupt(interruptPin), isr, FALLING);
  
}

void loop() {

  bool shouldUpdate = false;
  bool skipSendCal = false;
  if (Serial.available()) 
  {
    shouldUpdate = (bool) processCommands(Serial.readString());
    skipSendCal = shouldUpdate;
  }

  noInterrupts();
  protectedCount1 = count1;
  protectedCount2 = count2;
  protectedCount3 = count3;
  protectedCount4 = count4;
  protectedCount5 = count5;
  interrupts();

  
  if(protectedCount1 != previousCount1) {
    previousCount1 = protectedCount1;
    x_bias = protectedCount1 * x_bias_res + x_bias_offset;
    shouldUpdate = true; 
  }

  if(protectedCount2 != previousCount2) {
    previousCount2 = protectedCount2;
    y_bias = protectedCount2 * y_bias_res + y_bias_offset;
    shouldUpdate = true; 
  }
  
  if(protectedCount3 != previousCount3) {
    previousCount3 = protectedCount3;
    x_gain = protectedCount3 * x_gain_res + x_gain_offset;
    shouldUpdate = true; 
  }
  
  if(protectedCount4 != previousCount4) {
    previousCount4 = protectedCount4;
    y_gain = protectedCount4 * y_gain_res + y_gain_offset;
    shouldUpdate = true; 
  }
  
  if(protectedCount5 != previousCount5) {
    previousCount5 = protectedCount5;
    rotation = protectedCount5 * rotation_res + rotation_offset;
    shouldUpdate = true; 
  }

  if (shouldUpdate)
  { 
    if (!skipSendCal)
      sendCalibration();
    updateScreen();
  }
  
}

void isr() {

  bool e1A = digitalRead(encoder1A);
  bool e1B = digitalRead(encoder1B);
  
  if (!(e1A && e1B))
  {
    if ((!e1A) && (!e1B))
    {
      count1--;
    } else {
      count1++;
    }
  }

  
  bool e2A = digitalRead(encoder2A);
  bool e2B = digitalRead(encoder2B);
  
  if (!(e2A && e2B))
  {
    if ((!e2A) && (!e2B))
    {
      count2--;
    } else {
      count2++;
    }
  }

  bool e3A = digitalRead(encoder3A);
  bool e3B = digitalRead(encoder3B);
  
  if (!(e3A && e3B))
  {
    if ((!e3A) && (!e3B))
    {
      count3--;
    } else {
      count3++;
    }
  }

  bool e4A = digitalRead(encoder4A);
  bool e4B = digitalRead(encoder4B);
  
  if (!(e4A && e4B))
  {
    if ((!e4A) && (!e4B))
    {
      count4--;
    } else {
      count4++;
    }
  }

  bool e5A = digitalRead(encoder5A);
  bool e5B = digitalRead(encoder5B);
  
  if (!(e5A && e5B))
  {
    if ((!e5A) && (!e5B))
    {
      count5++;
    } else {
      count5--;
    }
  }
}

void updateScreen(void) {
  display.clearDisplay();

  display.setTextColor(SSD1306_WHITE); // Draw white text
  display.setCursor(0, 0);     // Start at top-left corner
  display.cp437(true);         // Use full 256 char 'Code Page 437' font

  // Not all the characters will fit on the display. This is normal.
  // Library will draw what it can and the rest will be clipped.
  display.setTextSize(2);      // Normal 1:1 pixel scale
  display.println("dDPI Knobs");
  display.setTextSize(1);      // Normal 1:1 pixel scale
  display.println();
  display.print("    X Bias: ");
  display.println(x_bias);
  display.print("    Y Bias: ");
  display.println(y_bias);
  display.print("    X Gain: ");
  display.println(x_gain);
  display.print("    Y Gain: ");
  display.println(y_gain);
  display.print("    Rotation: ");
  display.println(rotation);

  display.display();
}

void sendCalibration(void) {
    Serial.print("bx");
    Serial.print(x_bias, 4);
    Serial.print(",");
    Serial.print("by");
    Serial.print(y_bias, 4);
    Serial.print(",");
    Serial.print("gx");
    Serial.print(x_gain/1000, 6);
    Serial.print(",");
    Serial.print("gy");
    Serial.print(y_gain/1000, 6);
    Serial.print(",");
    Serial.print("r");
    Serial.print(rotation);
    Serial.println(",");
}

int processCommands(String msg) {
  String cmd;
  int n_commands = 0;

  while (msg.length() > 0) {
    int commaPos = msg.indexOf(',');
    if (commaPos == -1) {
      cmd = msg;
      msg = "";
    } else {
      cmd = msg.substring(0, commaPos);
      msg = msg.substring(commaPos + 1);
    }

    if (cmd.length() > 2) {
      if (cmd.startsWith("bx")) 
      {
        count1 = (int) (cmd.substring(2).toFloat() - x_bias_offset) / x_bias_res;
        n_commands++;
      }
      else if (cmd.startsWith("by"))
      {
        count2 = (int) (cmd.substring(2).toFloat() - y_bias_offset) / y_bias_res;
        n_commands++;
      } 
      else if (cmd.startsWith("gx"))
      {
        count3 = (int) (cmd.substring(2).toFloat() - x_gain_offset) / x_gain_res;
        n_commands++;
      } 
      else if (cmd.startsWith("gy"))
      {
        count4 = (int) (cmd.substring(2).toFloat() - y_gain_offset) / y_gain_res;
        n_commands++;
      }
      else if (cmd.charAt(0) == 'r') 
      {
        count5 = (int) (cmd.substring(1).toFloat() - rotation_offset) / rotation_res;
        n_commands++;
      }
    }
  }
  return n_commands;
}
