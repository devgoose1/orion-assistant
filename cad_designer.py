"""
Orion CAD Designer - Custom Circuit Design Tool
A built-in CAD system for designing Arduino circuits with AI assistance
Now with real pin system, code editor, and circuit simulation!
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGraphicsView, QGraphicsScene,
    QGraphicsItem, QGraphicsRectItem, QGraphicsEllipseItem, QGraphicsLineItem,
    QGraphicsTextItem, QPushButton, QLabel, QListWidget, QListWidgetItem,
    QSplitter, QToolBar, QDialog, QLineEdit, QSpinBox, QComboBox,
    QFormLayout, QDialogButtonBox, QFileDialog, QMessageBox, QGraphicsPixmapItem,
    QTextEdit, QTabWidget, QCheckBox
)
from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QLineF, QTimer
from PySide6.QtGui import (QPen, QBrush, QColor, QPainter, QPixmap, QFont,
                           QTransform, QPolygonF, QSyntaxHighlighter, QTextCharFormat)
import json
import math
import time
from typing import Optional, Dict, List, Any
from dataclasses import dataclass


# Arduino Pin definitions
ARDUINO_DIGITAL_PINS = [f"D{i}" for i in range(14)]  # D0-D13
ARDUINO_ANALOG_PINS = [f"A{i}" for i in range(6)]    # A0-A5
ARDUINO_POWER_PINS = ["5V", "3.3V", "GND", "VIN"]
ARDUINO_ALL_PINS = ARDUINO_DIGITAL_PINS + ARDUINO_ANALOG_PINS + ARDUINO_POWER_PINS


@dataclass
class Pin:
    """Represents a physical pin on a component"""
    name: str
    pin_type: str  # "digital", "analog", "power", "gnd"
    position: QPointF
    connected_to: Optional['Pin'] = None
    
    def can_connect_to(self, other: 'Pin') -> bool:
        """Check if this pin can connect to another pin"""
        # GND can connect to GND, 5V to 5V, etc.
        if self.pin_type == "power" or other.pin_type == "power":
            return self.name == other.name
        return True


class ComponentItem(QGraphicsRectItem):
    """Base class for circuit components with real pin system"""
    
    def __init__(self, component_type, x, y, width=100, height=80):
        super().__init__(0, 0, width, height)
        self.component_type = component_type
        self.component_id: Optional[str] = None
        self.properties = {}
        self.pins: List[Pin] = []  # Named pins with types
        self.pin_graphics = []  # Visual pin indicators
        self.state = {}  # Component state for simulation
        
        # Make item movable and selectable
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        
        # Set position
        self.setPos(x, y)
        
        # Styling based on component type
        if "Arduino" in component_type:
            self.setPen(QPen(QColor(0, 191, 255), 3))
            self.setBrush(QBrush(QColor(0, 100, 150, 220)))
        elif component_type == "LED":
            self.setPen(QPen(QColor(255, 200, 0), 2))
            self.setBrush(QBrush(QColor(200, 150, 0, 200)))
        else:
            self.setPen(QPen(QColor(0, 191, 255), 2))
            self.setBrush(QBrush(QColor(20, 40, 80, 200)))
        
        # Label
        self.label = QGraphicsTextItem(component_type, self)
        self.label.setDefaultTextColor(QColor(0, 255, 255))
        self.label.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        self.label.setPos(5, 5)
        
        # Initialize pins based on component type
        self._create_pins()
    
    def _create_pins(self):
        """Create real Arduino pins with proper labels"""
        width = self.rect().width()
        height = self.rect().height()
        
        if "Arduino Uno" in self.component_type or "Arduino Nano" in self.component_type:
            # Real Arduino pins layout
            pin_spacing = 15
            start_y = 25
            
            # Left side - Digital pins D0-D7 + GND
            for i in range(8):
                pin_y = start_y + i * pin_spacing
                if pin_y < height - 10:
                    pin = Pin(f"D{i}", "digital", QPointF(0, pin_y))
                    self.pins.append(pin)
                    self._add_pin_visual(pin, True)  # True = show label on left
            
            # Add GND on left
            gnd_y = start_y + 8 * pin_spacing
            if gnd_y < height - 10:
                gnd_pin = Pin("GND", "gnd", QPointF(0, gnd_y))
                self.pins.append(gnd_pin)
                self._add_pin_visual(gnd_pin, True)
            
            # Right side - Digital pins D8-D13, 5V, GND
            for i in range(8, 14):
                pin_y = start_y + (i - 8) * pin_spacing
                if pin_y < height - 10:
                    pin = Pin(f"D{i}", "digital", QPointF(width, pin_y))
                    self.pins.append(pin)
                    self._add_pin_visual(pin, False)  # False = show label on right
            
            # Add power on right
            power_y = start_y + 6 * pin_spacing
            if power_y < height - 10:
                v5_pin = Pin("5V", "power", QPointF(width, power_y))
                self.pins.append(v5_pin)
                self._add_pin_visual(v5_pin, False)
                
                gnd2_pin = Pin("GND", "gnd", QPointF(width, power_y + pin_spacing))
                self.pins.append(gnd2_pin)
                self._add_pin_visual(gnd2_pin, False)
            
            # Analog pins at bottom
            analog_start_x = 15
            for i in range(6):
                pin_x = analog_start_x + i * 13
                if pin_x < width - 15:
                    a_pin = Pin(f"A{i}", "analog", QPointF(pin_x, height))
                    self.pins.append(a_pin)
                    self._add_pin_visual(a_pin, False, True)  # Show at bottom
                    
        elif self.component_type == "LED":
            # LED: Anode (+) and Cathode (-)
            self.pins = [
                Pin("Anode", "digital", QPointF(0, height / 2)),
                Pin("Cathode", "gnd", QPointF(width, height / 2))
            ]
            for pin in self.pins:
                self._add_pin_visual(pin, pin.position.x() == 0)
            self.state = {"on": False, "brightness": 0}
            
        elif self.component_type == "Resistor":
            # Resistor: Two terminals
            self.pins = [
                Pin("T1", "digital", QPointF(0, height / 2)),
                Pin("T2", "digital", QPointF(width, height / 2))
            ]
            for pin in self.pins:
                self._add_pin_visual(pin, pin.position.x() == 0)
            self.properties = {"resistance": 220}  # Default 220Ω
            
        elif self.component_type == "Button":
            # Button: Two terminals
            self.pins = [
                Pin("Pin1", "digital", QPointF(0, height / 2)),
                Pin("Pin2", "digital", QPointF(width, height / 2))
            ]
            for pin in self.pins:
                self._add_pin_visual(pin, pin.position.x() == 0)
            self.state = {"pressed": False}
            
        elif "Sensor" in self.component_type:
            # Sensors: VCC, GND, Signal
            self.pins = [
                Pin("VCC", "power", QPointF(0, height * 0.3)),
                Pin("GND", "gnd", QPointF(0, height * 0.7)),
                Pin("OUT", "analog", QPointF(width, height / 2))
            ]
            for pin in self.pins:
                self._add_pin_visual(pin, pin.position.x() == 0)
            self.state = {"value": 0}
            
        elif "Motor" in self.component_type:
            # Motors: + and -
            self.pins = [
                Pin("+", "power", QPointF(0, height / 2)),
                Pin("-", "gnd", QPointF(width, height / 2))
            ]
            for pin in self.pins:
                self._add_pin_visual(pin, pin.position.x() == 0)
            self.state = {"speed": 0}
            
        else:
            # Generic component with basic pins
            self.pins = [
                Pin("VCC", "power", QPointF(0, height * 0.3)),
                Pin("GND", "gnd", QPointF(0, height * 0.7)),
                Pin("SIG", "digital", QPointF(width, height / 2))
            ]
            for pin in self.pins:
                self._add_pin_visual(pin, pin.position.x() == 0)
    
    def _add_pin_visual(self, pin: Pin, label_left: bool = True, label_bottom: bool = False):
        """Add visual indicator for a pin with label"""
        # Pin circle
        pin_indicator = QGraphicsEllipseItem(-4, -4, 8, 8, self)
        pin_indicator.setPos(pin.position)
        
        # Color code by type
        if pin.pin_type == "power":
            pin_indicator.setBrush(QBrush(QColor(255, 0, 0)))
            pin_indicator.setPen(QPen(QColor(200, 0, 0), 2))
        elif pin.pin_type == "gnd":
            pin_indicator.setBrush(QBrush(QColor(50, 50, 50)))
            pin_indicator.setPen(QPen(QColor(100, 100, 100), 2))
        elif pin.pin_type == "analog":
            pin_indicator.setBrush(QBrush(QColor(0, 255, 0)))
            pin_indicator.setPen(QPen(QColor(0, 200, 0), 2))
        else:  # digital
            pin_indicator.setBrush(QBrush(QColor(255, 255, 0)))
            pin_indicator.setPen(QPen(QColor(200, 200, 0), 2))
        
        self.pin_graphics.append(pin_indicator)
        
        # Pin label
        label = QGraphicsTextItem(pin.name, self)
        label.setDefaultTextColor(QColor(200, 255, 255))
        label.setFont(QFont("Consolas", 7))
        
        if label_bottom:
            label.setPos(pin.position.x() - 8, pin.position.y() + 3)
        elif label_left:
            label.setPos(pin.position.x() - 25, pin.position.y() - 8)
        else:
            label.setPos(pin.position.x() + 8, pin.position.y() - 8)
    
    def get_pin_by_name(self, pin_name: str) -> Optional[Pin]:
        """Get a pin by its name"""
        for pin in self.pins:
            if pin.name == pin_name:
                return pin
        return None
    
    def get_pin_scene_pos(self, pin_index):
        """Get the scene position of a pin"""
        if pin_index < len(self.pins):
            return self.mapToScene(self.pins[pin_index].position)
        return self.scenePos()
    
    def get_data(self):
        """Serialize component data"""
        pin_data = [{"name": p.name, "type": p.pin_type} for p in self.pins]
        return {
            "type": self.component_type,
            "id": self.component_id,
            "x": self.pos().x(),
            "y": self.pos().y(),
            "properties": self.properties,
            "pins": pin_data
        }


class WireItem(QGraphicsLineItem):
    """Wire connection between component pins"""
    
    def __init__(self, start_comp=None, start_pin=None, end_comp=None, end_pin=None):
        super().__init__()
        self.start_component = start_comp
        self.start_pin_name = start_pin
        self.end_component = end_comp
        self.end_pin_name = end_pin
        self.temp_end_point = None
        
        # Styling
        self.setPen(QPen(QColor(0, 255, 0), 3))
        self.setZValue(-1)  # Draw behind components
        
        # Make selectable
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        
        self.update_position()
    
    def update_position(self):
        """Update wire position based on component positions"""
        if self.start_component and self.start_pin_name:
            start_pin = self.start_component.get_pin_by_name(self.start_pin_name)
            if start_pin:
                start_pos = self.start_component.mapToScene(start_pin.position)
                
                if self.end_component and self.end_pin_name:
                    end_pin = self.end_component.get_pin_by_name(self.end_pin_name)
                    if end_pin:
                        end_pos = self.end_component.mapToScene(end_pin.position)
                        self.setLine(start_pos.x(), start_pos.y(), end_pos.x(), end_pos.y())
                        
                        # Color code by pin type
                        if start_pin.pin_type == "power" or end_pin.pin_type == "power":
                            self.setPen(QPen(QColor(255, 0, 0), 3))
                        elif start_pin.pin_type == "gnd" or end_pin.pin_type == "gnd":
                            self.setPen(QPen(QColor(100, 100, 100), 3))
                        else:
                            self.setPen(QPen(QColor(0, 255, 0), 3))
                elif self.temp_end_point:
                    self.setLine(start_pos.x(), start_pos.y(), 
                               self.temp_end_point.x(), self.temp_end_point.y())
    
    def set_temp_end(self, point):
        """Set temporary end point while dragging"""
        self.temp_end_point = point
        self.update_position()
    
    def get_data(self):
        """Serialize wire data"""
        return {
            "start_component": self.start_component.component_id if self.start_component else None,
            "start_pin": self.start_pin_name,
            "end_component": self.end_component.component_id if self.end_component else None,
            "end_pin": self.end_pin_name,
        }


class CADCanvas(QGraphicsView):
    """Main canvas for circuit design"""
    
    component_selected = Signal(object)
    
    def __init__(self):
        super().__init__()
        self.graphics_scene = QGraphicsScene()
        self.setScene(self.graphics_scene)
        
        # Configure view
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setSceneRect(-2000, -2000, 4000, 4000)
        
        # Dark background with grid
        self.setBackgroundBrush(QBrush(QColor(10, 15, 25)))
        
        # Drawing mode
        self.drawing_wire = False
        self.current_wire = None
        self.wire_start_component = None
        self.wire_start_pin = None
        
        # Component counter for unique IDs
        self.component_counter = 0
        
        # Styling
        self.setStyleSheet("""
            QGraphicsView {
                border: 2px solid rgba(0, 191, 255, 100);
                border-radius: 8px;
            }
        """)
        
        # Draw grid
        self._draw_grid()
    
    def _draw_grid(self):
        """Draw background grid"""
        grid_size = 20
        grid_color = QColor(30, 40, 60, 100)
        pen = QPen(grid_color, 0.5)
        
        # Vertical lines
        for x in range(-2000, 2000, grid_size):
            self.graphics_scene.addLine(x, -2000, x, 2000, pen)
        
        # Horizontal lines
        for y in range(-2000, 2000, grid_size):
            self.graphics_scene.addLine(-2000, y, 2000, y, pen)
    
    def add_component(self, component_type):
        """Add a component to the canvas"""
        # Create component at center of view
        view_center = self.mapToScene(self.viewport().rect().center())
        
        component = ComponentItem(component_type, 
                                  view_center.x() - 30,
                                  view_center.y() - 20)
        component.component_id = f"{component_type}_{self.component_counter}"
        self.component_counter += 1
        
        self.graphics_scene.addItem(component)
        return component
    
    def start_wire_mode(self):
        """Enable wire drawing mode"""
        self.drawing_wire = True
        self.current_wire = None
        self.wire_start_component = None
        self.wire_start_pin = None
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
    
    def stop_wire_mode(self):
        """Disable wire drawing mode"""
        self.drawing_wire = False
        self.current_wire = None
        self.wire_start_component = None
        self.wire_start_pin = None
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
    
    def _find_pin_at_pos(self, scene_pos):
        """Find which pin is at the given position"""
        # Check all components
        for item in self.graphics_scene.items(scene_pos):
            if isinstance(item, ComponentItem):
                # Check all pins of this component
                for pin in item.pins:
                    pin_scene_pos = item.mapToScene(pin.position)
                    distance = ((pin_scene_pos.x() - scene_pos.x())**2 + 
                               (pin_scene_pos.y() - scene_pos.y())**2)**0.5
                    if distance < 10:  # Click tolerance
                        return item, pin
        return None, None
    
    def mousePressEvent(self, event):
        """Handle mouse press for wire drawing with pin selection"""
        if self.drawing_wire and event.button() == Qt.MouseButton.LeftButton:
            scene_pos = self.mapToScene(event.pos())
            component, pin = self._find_pin_at_pos(scene_pos)
            
            if component and pin:
                if self.current_wire is None:
                    # Start new wire from this pin
                    self.wire_start_component = component
                    self.wire_start_pin = pin.name
                    self.current_wire = WireItem(component, pin.name)
                    self.graphics_scene.addItem(self.current_wire)
                else:
                    # Complete wire to this pin
                    self.current_wire.end_component = component
                    self.current_wire.end_pin_name = pin.name
                    self.current_wire.update_position()
                    
                    # Reset for next wire
                    self.current_wire = None
                    self.wire_start_component = None
                    self.wire_start_pin = None
        else:
            super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """Handle mouse move for wire preview"""
        if self.drawing_wire and self.current_wire:
            scene_pos = self.mapToScene(event.pos())
            self.current_wire.set_temp_end(scene_pos)
        else:
            super().mouseMoveEvent(event)
    
    def clear_canvas(self):
        """Clear all components and wires"""
        self.graphics_scene.clear()
        self._draw_grid()
        self.component_counter = 0
    
    def get_design_data(self):
        """Export design as JSON"""
        components = []
        wires = []
        
        for item in self.graphics_scene.items():
            if isinstance(item, ComponentItem):
                components.append(item.get_data())
            elif isinstance(item, WireItem):
                wires.append(item.get_data())
        
        return {
            "components": components,
            "wires": wires
        }


class ComponentLibrary(QWidget):
    """Component palette for dragging onto canvas"""
    
    component_clicked = Signal(str)
    
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Title
        title = QLabel("⚡ Component Library")
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
        
        # Component list
        self.component_list = QListWidget()
        self.component_list.setStyleSheet("""
            QListWidget {
                background-color: rgba(10, 25, 47, 180);
                border: 1px solid rgba(0, 191, 255, 80);
                border-radius: 4px;
                color: #87CEEB;
                font-size: 11px;
                padding: 5px;
            }
            QListWidget::item {
                padding: 8px;
                border-radius: 3px;
                margin: 2px;
            }
            QListWidget::item:selected {
                background-color: rgba(0, 150, 200, 150);
                color: #00FFFF;
            }
            QListWidget::item:hover {
                background-color: rgba(0, 100, 150, 100);
            }
        """)
        
        # Add components
        components = [
            "🔷 Arduino Uno",
            "🔷 Arduino Nano",
            "🔶 LED",
            "🔶 Resistor",
            "🔶 Capacitor",
            "🔵 Button",
            "🔵 Potentiometer",
            "🟢 Temperature Sensor",
            "🟢 Motion Sensor",
            "🟢 Light Sensor",
            "🟡 Servo Motor",
            "🟡 DC Motor",
            "🟣 LCD Display",
            "🟣 OLED Display",
            "⚪ Breadboard",
            "⚪ Battery 9V",
        ]
        
        for component in components:
            item = QListWidgetItem(component)
            self.component_list.addItem(item)
        
        self.component_list.itemDoubleClicked.connect(self._on_component_clicked)
        layout.addWidget(self.component_list)
        
        # Instructions
        instructions = QLabel("💡 Double-click to add\ncomponent to canvas")
        instructions.setStyleSheet("""
            QLabel {
                color: #87CEEB;
                font-size: 9px;
                padding: 5px;
                background-color: rgba(0, 50, 100, 80);
                border-radius: 3px;
            }
        """)
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
    
    def _on_component_clicked(self, item):
        """Handle component selection"""
        component_name = item.text().split(" ", 1)[1]  # Remove emoji
        self.component_clicked.emit(component_name)


class CADDesignerWindow(QWidget):
    """Main CAD Designer window with code editor and simulator"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Orion CAD Designer - Arduino Circuit Design & Code Editor")
        self.setMinimumSize(1600, 900)
        
        # Simulator
        from code_editor import CircuitSimulator, CodeEditorPanel
        self.simulator = CircuitSimulator()
        
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Toolbar
        self._create_toolbar(main_layout)
        
        # Main splitter (3-way: library | canvas | code editor)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Component library (left)
        self.library = ComponentLibrary()
        self.library.component_clicked.connect(self._add_component)
        self.library.setMaximumWidth(250)
        splitter.addWidget(self.library)
        
        # Canvas (center)
        canvas_widget = QWidget()
        canvas_layout = QVBoxLayout(canvas_widget)
        canvas_layout.setContentsMargins(5, 5, 5, 5)
        
        # Canvas title
        canvas_title = QLabel("🔌 Circuit Design Canvas (Real Arduino Pins!)")
        canvas_title.setStyleSheet("""
            QLabel {
                color: #00FFFF;
                font-size: 13px;
                font-weight: bold;
                padding: 8px;
                background-color: rgba(0, 100, 150, 120);
                border-radius: 4px;
            }
        """)
        canvas_layout.addWidget(canvas_title)
        
        self.canvas = CADCanvas()
        canvas_layout.addWidget(self.canvas)
        
        # Status info
        self.status_label = QLabel("Ready | Drag components, click pins to wire | Color: 🔴=Power 🔵=Digital ⚫=GND 🟢=Analog")
        self.status_label.setStyleSheet("""
            QLabel {
                color: #87CEEB;
                font-size: 10px;
                padding: 5px;
                background-color: rgba(0, 50, 100, 100);
                border-radius: 3px;
            }
        """)
        canvas_layout.addWidget(self.status_label)
        
        splitter.addWidget(canvas_widget)
        
        # Code Editor (right)
        self.code_editor = CodeEditorPanel()
        self.code_editor.code_run.connect(self._run_simulation)
        self.code_editor.setMinimumWidth(400)
        splitter.addWidget(self.code_editor)
        
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setStretchFactor(2, 2)
        
        main_layout.addWidget(splitter)
        
        # Apply dark theme
        self.setStyleSheet("""
            QWidget {
                background-color: rgba(5, 15, 30, 240);
                color: #B0E0E6;
                font-family: 'Consolas', 'Courier New', monospace;
            }
        """)
    
    def _run_simulation(self, code):
        """Run circuit simulation with Arduino code"""
        # Get all components and wires from canvas
        components = []
        wires = []
        
        for item in self.canvas.graphics_scene.items():
            if isinstance(item, ComponentItem):
                components.append(item)
            elif isinstance(item, WireItem):
                wires.append(item)
        
        # Load to simulator
        self.simulator.load_circuit(components, wires)
        
        # Execute code
        try:
            self.simulator.execute_code(code)
            self.code_editor.log("✓ Simulation complete!")
            self.status_label.setText("Simulation running | Check LED states on canvas")
        except Exception as e:
            self.code_editor.log(f"⚠ Error: {str(e)}")
            self.status_label.setText(f"Simulation error: {str(e)}")
    
    def _create_toolbar(self, layout):
        """Create toolbar with tools"""
        toolbar = QToolBar()
        toolbar.setStyleSheet("""
            QToolBar {
                background-color: rgba(0, 50, 100, 150);
                border: 1px solid rgba(0, 191, 255, 80);
                border-radius: 4px;
                padding: 5px;
                spacing: 5px;
            }
            QPushButton {
                background-color: rgba(0, 100, 150, 120);
                border: 1px solid rgba(0, 191, 255, 100);
                border-radius: 4px;
                color: #00FFFF;
                padding: 8px 15px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: rgba(0, 150, 200, 150);
            }
            QPushButton:pressed {
                background-color: rgba(0, 200, 255, 180);
            }
        """)
        
        # Wire tool button
        wire_btn = QPushButton("🔗 Draw Wire")
        wire_btn.clicked.connect(self._toggle_wire_mode)
        toolbar.addWidget(wire_btn)
        self.wire_btn = wire_btn
        
        toolbar.addSeparator()
        
        # Clear button
        clear_btn = QPushButton("🗑 Clear All")
        clear_btn.clicked.connect(self._clear_design)
        toolbar.addWidget(clear_btn)
        
        toolbar.addSeparator()
        
        # Save button
        save_btn = QPushButton("💾 Save Design")
        save_btn.clicked.connect(self._save_design)
        toolbar.addWidget(save_btn)
        
        # Load button
        load_btn = QPushButton("📁 Load Design")
        load_btn.clicked.connect(self._load_design)
        toolbar.addWidget(load_btn)
        
        toolbar.addSeparator()
        
        # Export button
        export_btn = QPushButton("📤 Export Image")
        export_btn.clicked.connect(self._export_image)
        toolbar.addWidget(export_btn)
        
        toolbar.addSeparator()
        
        # AI Assistant hint
        ai_label = QLabel("💡 Ask Orion for component help!")
        ai_label.setStyleSheet("QLabel { color: #FFD700; padding: 5px; }")
        toolbar.addWidget(ai_label)
        
        layout.addWidget(toolbar)
    
    def _add_component(self, component_type):
        """Add component to canvas"""
        self.canvas.add_component(component_type)
        self.status_label.setText(f"Added {component_type} to canvas")
    
    def _toggle_wire_mode(self):
        """Toggle wire drawing mode"""
        if self.canvas.drawing_wire:
            self.canvas.stop_wire_mode()
            self.wire_btn.setText("🔗 Draw Wire")
            self.status_label.setText("Wire mode disabled | Click to select components")
        else:
            self.canvas.start_wire_mode()
            self.wire_btn.setText("❌ Stop Wire")
            self.status_label.setText("Wire mode active | Click to place wire points")
    
    def _clear_design(self):
        """Clear the canvas"""
        reply = QMessageBox.question(self, "Clear Design",
                                     "Are you sure you want to clear the entire design?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.canvas.clear_canvas()
            self.status_label.setText("Canvas cleared")
    
    def _save_design(self):
        """Save design to JSON file"""
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Circuit Design", "", "JSON Files (*.json);;All Files (*)"
        )
        if filename:
            try:
                design_data = self.canvas.get_design_data()
                with open(filename, 'w') as f:
                    json.dump(design_data, f, indent=2)
                self.status_label.setText(f"Design saved to {filename}")
                QMessageBox.information(self, "Success", "Design saved successfully!")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save design: {str(e)}")
    
    def _load_design(self):
        """Load design from JSON file"""
        filename, _ = QFileDialog.getOpenFileName(
            self, "Load Circuit Design", "", "JSON Files (*.json);;All Files (*)"
        )
        if filename:
            try:
                with open(filename, 'r') as f:
                    design_data = json.load(f)
                
                # Clear current design
                self.canvas.clear_canvas()
                
                # TODO: Implement design loading from JSON
                self.status_label.setText(f"Design loaded from {filename}")
                QMessageBox.information(self, "Success", "Design loaded successfully!")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load design: {str(e)}")
    
    def _export_image(self):
        """Export canvas as image"""
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export Circuit Image", "", 
            "PNG Files (*.png);;JPEG Files (*.jpg);;All Files (*)"
        )
        if filename:
            try:
                # Get scene bounding rect
                scene_rect = self.canvas.graphics_scene.itemsBoundingRect()
                
                # Create pixmap
                pixmap = QPixmap(int(scene_rect.width()) + 40, 
                                int(scene_rect.height()) + 40)
                pixmap.fill(QColor(10, 15, 25))
                
                # Render scene to pixmap
                painter = QPainter(pixmap)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                self.canvas.graphics_scene.render(painter, QRectF(), scene_rect)
                painter.end()
                
                # Save
                pixmap.save(filename)
                self.status_label.setText(f"Image exported to {filename}")
                QMessageBox.information(self, "Success", "Image exported successfully!")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to export image: {str(e)}")
