"""
Arduino Code Editor and Simulator
"""

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                                QTextEdit, QLabel, QSplitter, QCheckBox, QSpinBox)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont, QColor, QTextCharFormat, QSyntaxHighlighter, QBrush
import re

# Define Arduino pins locally to avoid circular import
ARDUINO_DIGITAL_PINS = [f"D{i}" for i in range(14)]  # D0-D13
ARDUINO_ANALOG_PINS = [f"A{i}" for i in range(6)]    # A0-A5


class ArduinoSyntaxHighlighter(QSyntaxHighlighter):
    """Syntax highlighter for Arduino/C++ code"""
    
    def __init__(self, document):
        super().__init__(document)
        
        # Define formatting styles
        self.keyword_format = QTextCharFormat()
        self.keyword_format.setForeground(QColor(255, 100, 200))
        self.keyword_format.setFontWeight(QFont.Weight.Bold)
        
        self.function_format = QTextCharFormat()
        self.function_format.setForeground(QColor(100, 200, 255))
        
        self.number_format = QTextCharFormat()
        self.number_format.setForeground(QColor(255, 200, 100))
        
        self.string_format = QTextCharFormat()
        self.string_format.setForeground(QColor(100, 255, 100))
        
        self.comment_format = QTextCharFormat()
        self.comment_format.setForeground(QColor(128, 128, 128))
        
        # Keywords
        self.keywords = [
            'void', 'int', 'float', 'char', 'boolean', 'String', 'byte',
            'pinMode', 'digitalWrite', 'digitalRead', 'analogWrite', 'analogRead',
            'delay', 'millis', 'Serial', 'HIGH', 'LOW', 'INPUT', 'OUTPUT',
            'if', 'else', 'for', 'while', 'return', 'true', 'false',
            'setup', 'loop'
        ]
    
    def highlightBlock(self, text):
        # Keywords
        for keyword in self.keywords:
            pattern = f'\\b{keyword}\\b'
            for match in re.finditer(pattern, text):
                self.setFormat(match.start(), match.end() - match.start(), self.keyword_format)
        
        # Numbers
        pattern = r'\b\d+\b'
        for match in re.finditer(pattern, text):
            self.setFormat(match.start(), match.end() - match.start(), self.number_format)
        
        # Strings
        pattern = r'"[^"]*"'
        for match in re.finditer(pattern, text):
            self.setFormat(match.start(), match.end() - match.start(), self.string_format)
        
        # Comments
        pattern = r'//.*'
        for match in re.finditer(pattern, text):
            self.setFormat(match.start(), match.end() - match.start(), self.comment_format)


class CircuitSimulator:
    """Simple circuit simulator"""
    
    def __init__(self):
        self.arduino_pins = {pin: False for pin in ARDUINO_DIGITAL_PINS}
        self.analog_pins = {pin: 0 for pin in ARDUINO_ANALOG_PINS}
        self.components = {}
        self.wires = []
        self.running = False
        self.code = ""
        
    def load_circuit(self, components, wires):
        """Load circuit design"""
        # Store references without checking type (avoid circular import)
        self.components = {c.component_id: c for c in components if hasattr(c, 'component_id')}
        self.wires = wires
        
    def set_pin(self, pin_name, value):
        """Set pin state (HIGH/LOW or analog value)"""
        if pin_name in self.arduino_pins:
            self.arduino_pins[pin_name] = value
        elif pin_name in self.analog_pins:
            self.analog_pins[pin_name] = value
        
        # Propagate through wires
        self._propagate_signals()
    
    def _propagate_signals(self):
        """Propagate signals through circuit"""
        # Find Arduino component
        arduino = None
        for comp in self.components.values():
            if "Arduino" in comp.component_type:
                arduino = comp
                break
        
        if not arduino:
            return
        
        # Check each wire connection
        for wire in self.wires:
            # Check if it's a wire (has wire attributes)
            if not hasattr(wire, 'start_component') or not hasattr(wire, 'end_component'):
                continue
                
            # Get connected pins
            if wire.start_component and wire.end_component:
                start_pin = wire.start_component.get_pin_by_name(wire.start_pin_name)
                end_pin = wire.end_component.get_pin_by_name(wire.end_pin_name)
                
                if not start_pin or not end_pin:
                    continue
                
                # If one component is Arduino, affect the other
                if wire.start_component == arduino:
                    # Arduino output affects end component
                    if start_pin.name in self.arduino_pins:
                        state = self.arduino_pins[start_pin.name]
                        self._affect_component(wire.end_component, end_pin.name, state)
                        
                elif wire.end_component == arduino:
                    # Component affects Arduino input
                    if end_pin.name in self.arduino_pins:
                        # Read from component
                        state = self._read_component(wire.start_component, start_pin.name)
                        self.arduino_pins[end_pin.name] = state
    
    def _affect_component(self, component, pin_name, state):
        """Affect a component with a signal"""
        if component.component_type == "LED":
            if pin_name == "Anode":
                component.state["on"] = state
                component.state["brightness"] = 255 if state else 0
                # Update visual
                if state:
                    component.setBrush(QBrush(QColor(255, 255, 0, 220)))
                else:
                    component.setBrush(QBrush(QColor(200, 150, 0, 200)))
    
    def _read_component(self, component, pin_name):
        """Read state from a component"""
        if component.component_type == "Button":
            return component.state.get("pressed", False)
        return False
    
    def execute_code(self, code):
        """Parse and execute simple Arduino code"""
        self.code = code
        self.running = True
        
        # Very simple interpreter for digitalWrite/analogWrite
        lines = code.split('\n')
        for line in lines:
            line = line.strip()
            
            # digitalWrite(pin, HIGH/LOW)
            if 'digitalWrite' in line:
                match = re.search(r'digitalWrite\s*\(\s*(\w+)\s*,\s*(\w+)\s*\)', line)
                if match:
                    pin = match.group(1)
                    value = match.group(2)
                    if pin in self.arduino_pins:
                        self.set_pin(pin, value == "HIGH")
            
            # analogWrite(pin, value)
            elif 'analogWrite' in line:
                match = re.search(r'analogWrite\s*\(\s*(\w+)\s*,\s*(\d+)\s*\)', line)
                if match:
                    pin = match.group(1)
                    value = int(match.group(2))
                    if pin in self.arduino_pins:
                        self.set_pin(pin, value > 127)


class CodeEditorPanel(QWidget):
    """Code editor with simulation controls"""
    
    code_run = Signal(str)
    
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Title
        title = QLabel("⚡ Arduino Code Editor")
        title.setStyleSheet("""
            QLabel {
                color: #00FFFF;
                font-size: 12px;
                font-weight: bold;
                padding: 8px;
                background-color: rgba(0, 100, 150, 100);
                border-radius: 4px;
            }
        """)
        layout.addWidget(title)
        
        # Code editor
        self.code_editor = QTextEdit()
        self.code_editor.setStyleSheet("""
            QTextEdit {
                background-color: rgba(10, 20, 30, 230);
                border: 1px solid rgba(0, 191, 255, 80);
                border-radius: 4px;
                color: #FFFFFF;
                font-size: 11px;
                font-family: 'Consolas', 'Courier New', monospace;
                padding: 8px;
            }
        """)
        self.code_editor.setFont(QFont("Consolas", 10))
        
        # Add syntax highlighting
        self.highlighter = ArduinoSyntaxHighlighter(self.code_editor.document())
        
        # Default code template
        self.code_editor.setPlainText("""// Arduino Code
void setup() {
  // Initialize pins
  pinMode(D13, OUTPUT);  // Built-in LED
}

void loop() {
  // Your code here
  digitalWrite(D13, HIGH);
  delay(1000);
  digitalWrite(D13, LOW);
  delay(1000);
}
""")
        layout.addWidget(self.code_editor)
        
        # Control buttons
        controls = QHBoxLayout()
        
        run_btn = QPushButton("▶ Run Code")
        run_btn.clicked.connect(self._run_code)
        run_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 200, 0, 150);
                border: 1px solid rgba(0, 255, 0, 100);
                border-radius: 4px;
                color: #FFFFFF;
                padding: 8px 15px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(0, 255, 0, 180);
            }
        """)
        controls.addWidget(run_btn)
        
        stop_btn = QPushButton("⏹ Stop")
        stop_btn.clicked.connect(self._stop_code)
        stop_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(200, 0, 0, 150);
                border: 1px solid rgba(255, 0, 0, 100);
                border-radius: 4px;
                color: #FFFFFF;
                padding: 8px 15px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(255, 0, 0, 180);
            }
        """)
        controls.addWidget(stop_btn)
        
        controls.addStretch()
        layout.addLayout(controls)
        
        # Console output
        console_label = QLabel("📟 Console Output:")
        console_label.setStyleSheet("color: #87CEEB; font-size: 10px;")
        layout.addWidget(console_label)
        
        self.console = QTextEdit()
        self.console.setReadOnly(True)
        self.console.setMaximumHeight(100)
        self.console.setStyleSheet("""
            QTextEdit {
                background-color: rgba(5, 10, 15, 230);
                border: 1px solid rgba(0, 191, 255, 60);
                border-radius: 4px;
                color: #90EE90;
                font-size: 10px;
                font-family: 'Consolas', monospace;
                padding: 5px;
            }
        """)
        layout.addWidget(self.console)
    
    def _run_code(self):
        """Run the current code"""
        code = self.code_editor.toPlainText()
        self.code_run.emit(code)
        self.console.append("✓ Code execution started...")
    
    def _stop_code(self):
        """Stop code execution"""
        self.console.append("⏹ Stopped")
    
    def log(self, message):
        """Log message to console"""
        self.console.append(message)
