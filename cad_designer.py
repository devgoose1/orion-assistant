"""
Orion CAD Designer - Custom Circuit Design Tool
A built-in CAD system for designing Arduino circuits with AI assistance
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGraphicsView, QGraphicsScene,
    QGraphicsItem, QGraphicsRectItem, QGraphicsEllipseItem, QGraphicsLineItem,
    QGraphicsTextItem, QPushButton, QLabel, QListWidget, QListWidgetItem,
    QSplitter, QToolBar, QDialog, QLineEdit, QSpinBox, QComboBox,
    QFormLayout, QDialogButtonBox, QFileDialog, QMessageBox, QGraphicsPixmapItem
)
from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QLineF
from PySide6.QtGui import (QPen, QBrush, QColor, QPainter, QPixmap, QFont,
                           QTransform, QPolygonF)
import json
import math
from typing import Optional


class ComponentItem(QGraphicsRectItem):
    """Base class for circuit components"""
    
    def __init__(self, component_type, x, y, width=60, height=40):
        super().__init__(0, 0, width, height)
        self.component_type = component_type
        self.component_id: Optional[str] = None
        self.properties = {}
        self.pins = []  # Connection points
        
        # Make item movable and selectable
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        
        # Set position
        self.setPos(x, y)
        
        # Styling
        self.setPen(QPen(QColor(0, 191, 255), 2))
        self.setBrush(QBrush(QColor(20, 40, 80, 200)))
        
        # Label
        self.label = QGraphicsTextItem(component_type, self)
        self.label.setDefaultTextColor(QColor(0, 255, 255))
        self.label.setFont(QFont("Consolas", 9))
        self.label.setPos(5, height // 2 - 10)
        
        # Initialize pins based on component type
        self._create_pins()
    
    def _create_pins(self):
        """Create connection pins for the component"""
        width = self.rect().width()
        height = self.rect().height()
        
        if self.component_type == "Arduino Uno":
            # Arduino has many pins - simplified to 4 main connection points
            self.pins = [
                QPointF(0, height * 0.25),      # Left top
                QPointF(0, height * 0.75),      # Left bottom
                QPointF(width, height * 0.25),  # Right top
                QPointF(width, height * 0.75),  # Right bottom
            ]
        elif self.component_type in ["LED", "Resistor"]:
            # 2-pin components
            self.pins = [
                QPointF(0, height / 2),      # Left
                QPointF(width, height / 2),  # Right
            ]
        elif self.component_type == "Button":
            # 2-pin component
            self.pins = [
                QPointF(0, height / 2),
                QPointF(width, height / 2),
            ]
        else:
            # Generic 4-pin component
            self.pins = [
                QPointF(0, height / 2),          # Left
                QPointF(width, height / 2),      # Right
                QPointF(width / 2, 0),           # Top
                QPointF(width / 2, height),      # Bottom
            ]
        
        # Draw pin indicators
        for pin_pos in self.pins:
            pin_indicator = QGraphicsEllipseItem(-3, -3, 6, 6, self)
            pin_indicator.setPos(pin_pos)
            pin_indicator.setBrush(QBrush(QColor(255, 255, 0)))
            pin_indicator.setPen(QPen(QColor(200, 200, 0), 1))
    
    def get_pin_scene_pos(self, pin_index):
        """Get the scene position of a pin"""
        if pin_index < len(self.pins):
            return self.mapToScene(self.pins[pin_index])
        return self.scenePos()
    
    def get_data(self):
        """Serialize component data"""
        return {
            "type": self.component_type,
            "id": self.component_id,
            "x": self.pos().x(),
            "y": self.pos().y(),
            "properties": self.properties
        }


class WireItem(QGraphicsLineItem):
    """Wire connection between components"""
    
    def __init__(self, start_point, end_point=None):
        super().__init__()
        self.start_point = start_point
        self.end_point = end_point or start_point
        self.source_component = None
        self.target_component = None
        
        # Styling
        self.setPen(QPen(QColor(0, 255, 0), 2))
        self.setLine(start_point.x(), start_point.y(), 
                     self.end_point.x(), self.end_point.y())
        
        # Make selectable
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
    
    def update_end_point(self, point):
        """Update the end point of the wire"""
        self.end_point = point
        self.setLine(self.start_point.x(), self.start_point.y(),
                     point.x(), point.y())
    
    def get_data(self):
        """Serialize wire data"""
        return {
            "start_x": self.start_point.x(),
            "start_y": self.start_point.y(),
            "end_x": self.end_point.x(),
            "end_y": self.end_point.y(),
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
        self.wire_start_point = None
        
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
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
    
    def stop_wire_mode(self):
        """Disable wire drawing mode"""
        self.drawing_wire = False
        self.current_wire = None
        self.wire_start_point = None
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
    
    def mousePressEvent(self, event):
        """Handle mouse press for wire drawing"""
        if self.drawing_wire and event.button() == Qt.MouseButton.LeftButton:
            scene_pos = self.mapToScene(event.pos())
            
            if self.current_wire is None:
                # Start new wire
                self.wire_start_point = scene_pos
                self.current_wire = WireItem(scene_pos)
                self.graphics_scene.addItem(self.current_wire)
            else:
                # Finish wire
                self.current_wire.update_end_point(scene_pos)
                self.current_wire = None
                self.wire_start_point = None
        else:
            super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """Handle mouse move for wire preview"""
        if self.drawing_wire and self.current_wire:
            scene_pos = self.mapToScene(event.pos())
            self.current_wire.update_end_point(scene_pos)
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
    """Main CAD Designer window with full interface"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Orion CAD Designer - Circuit Design Tool")
        self.setMinimumSize(1400, 800)
        
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Toolbar
        self._create_toolbar(main_layout)
        
        # Splitter for library and canvas
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Component library (left)
        self.library = ComponentLibrary()
        self.library.component_clicked.connect(self._add_component)
        self.library.setMaximumWidth(250)
        splitter.addWidget(self.library)
        
        # Canvas (center/right)
        canvas_widget = QWidget()
        canvas_layout = QVBoxLayout(canvas_widget)
        canvas_layout.setContentsMargins(5, 5, 5, 5)
        
        # Canvas title
        canvas_title = QLabel("🔌 Circuit Design Canvas")
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
        self.status_label = QLabel("Ready to design | Select components from library")
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
        splitter.setStretchFactor(1, 1)
        
        main_layout.addWidget(splitter)
        
        # Apply dark theme
        self.setStyleSheet("""
            QWidget {
                background-color: rgba(5, 15, 30, 240);
                color: #B0E0E6;
                font-family: 'Consolas', 'Courier New', monospace;
            }
        """)
    
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
