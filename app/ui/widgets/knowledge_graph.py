import math
import random
from PyQt6.QtWidgets import (QGraphicsView, QGraphicsScene, QGraphicsItem, 
                             QGraphicsEllipseItem, QGraphicsLineItem, QGraphicsSimpleTextItem,
                             QWidget, QVBoxLayout, QPushButton, QGraphicsRectItem)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QRectF, QPointF
from PyQt6.QtGui import QColor, QPen, QBrush, QFont, QPainter, QWheelEvent, QMouseEvent, QRadialGradient, QPolygonF

# --- КОМПОНЕНТЫ ГРАФА ---

class GraphEdge(QGraphicsLineItem):
    def __init__(self, source_node, target_node):
        super().__init__()
        self.source = source_node
        self.target = target_node
        self.setZValue(0)
        self.setPen(QPen(QColor(150, 150, 150, 80), 1.5, Qt.PenStyle.SolidLine))

    def update_position(self):
        self.setLine(self.source.pos().x(), self.source.pos().y(), 
                     self.target.pos().x(), self.target.pos().y())

class GraphNode(QGraphicsItem):
    def __init__(self, node_id, label, node_type, size=30):
        super().__init__()
        self.node_id = node_id
        self.label_text = label
        self.node_type = node_type
        self.base_size = size
        self.radius = size / 2
        
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        self.setZValue(10 if node_type == 'CATEGORY' else 5)
        
        if node_type == 'CATEGORY':
            self.color = QColor("#4a90e2")
            self.font = QFont("Segoe UI", 12, QFont.Weight.Bold)
        else:
            self.color = QColor("#ff8c42")
            self.font = QFont("Segoe UI", 9, QFont.Weight.Normal)

        self.vx = 0
        self.vy = 0
        self.is_dragging = False

    def boundingRect(self):
        return QRectF(-self.radius - 20, -self.radius - 20, 
                      self.base_size + 40, self.base_size + 40)

    def paint(self, painter, option, widget):
        lod = option.levelOfDetailFromTransform(painter.worldTransform())
        
        grad = QRadialGradient(0, 0, self.radius)
        grad.setColorAt(0, self.color.lighter(120))
        grad.setColorAt(1, self.color)
        
        painter.setBrush(QBrush(grad))
        if self.node_type == 'CATEGORY':
            painter.setPen(QPen(Qt.GlobalColor.white, 2))
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            
        painter.drawEllipse(QPointF(0, 0), self.radius, self.radius)

        if (self.node_type == 'CATEGORY') or (lod > 0.6):
            painter.setPen(Qt.GlobalColor.white)
            painter.setFont(self.font)
            text_rect = QRectF(-100, -100, 200, 200)
            
            if self.node_type == 'CATEGORY':
                painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, self.label_text[:12])
            else:
                text_pos = QRectF(-70, self.radius + 2, 140, 20)
                painter.drawText(text_pos, Qt.AlignmentFlag.AlignCenter, self.label_text[:20])

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            if self.scene():
                # Уведомляем сцену, что границы изменились (для пересчета SceneRect)
                self.scene().update() 
                # Обновляем связи
                if hasattr(self.scene(), 'update_edges'):
                    self.scene().update_edges(self)
        return super().itemChange(change, value)

    def mousePressEvent(self, event):
        self.is_dragging = True
        if self.scene() and self.scene().views():
            self.scene().views()[0].wake_up_physics()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self.is_dragging = False
        super().mouseReleaseEvent(event)

# --- МИНИ-КАРТА ---

class Minimap(QGraphicsView):
    def __init__(self, main_view, parent=None):
        super().__init__(parent)
        self.main_view = main_view
        self.setInteractive(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet("background: rgba(30, 30, 30, 150); border: 1px solid #555; border-radius: 4px;")
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    def drawForeground(self, painter, rect):
        # Рисуем рамку текущего просмотра
        if not self.main_view.scene(): return
        
        viewport_rect = self.main_view.mapToScene(self.main_view.viewport().rect()).boundingRect()
        
        painter.save()
        pen = QPen(QColor("#ff8c42"), 2) # Оранжевая рамка
        painter.setPen(pen)
        painter.setBrush(QBrush(QColor(255, 140, 66, 30)))
        painter.drawRect(viewport_rect)
        painter.restore()

# --- СЦЕНА И ГЛАВНЫЙ ВИДЖЕТ ---

class KnowledgeGraphScene(QGraphicsScene):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.edges = []

    def update_edges(self, node):
        for edge in self.edges:
            if edge.source == node or edge.target == node:
                edge.update_position()
    
    def drawBackground(self, painter, rect):
        # Рисуем сетку для понимания масштаба
        super().drawBackground(painter, rect)
        
        grid_size = 200
        left = int(rect.left()) - (int(rect.left()) % grid_size)
        top = int(rect.top()) - (int(rect.top()) % grid_size)
        
        lines = []
        
        # Вертикальные линии
        x = left
        while x < rect.right():
            lines.append(QGraphicsLineItem(x, rect.top(), x, rect.bottom()))
            x += grid_size
            
        # Горизонтальные линии
        y = top
        while y < rect.bottom():
            lines.append(QGraphicsLineItem(rect.left(), y, rect.right(), y))
            y += grid_size

        painter.setPen(QPen(QColor(60, 60, 60), 1))
        for line in lines:
            painter.drawLine(line.line())

class KnowledgeGraphWidget(QGraphicsView):
    node_selected = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene_obj = KnowledgeGraphScene(self)
        self.setScene(self.scene_obj)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setBackgroundBrush(QBrush(QColor("#1e1e1e")))
        
        # Навигация
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.nodes = []
        self.physics_timer = QTimer()
        self.physics_timer.timeout.connect(self._physics_tick)
        self.active_physics = False
        
        # Overlay UI
        self._init_overlay_ui()

    def _init_overlay_ui(self):
        # Кнопка центрирования
        self.btn_center = QPushButton("🎯", self)
        self.btn_center.setToolTip("Центрировать вид")
        self.btn_center.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_center.setStyleSheet("""
            QPushButton { 
                background-color: #333; color: white; border: 1px solid #555; 
                border-radius: 4px; font-size: 16px; padding: 5px;
            }
            QPushButton:hover { background-color: #444; border-color: #ff8c42; }
        """)
        self.btn_center.clicked.connect(self.fit_to_content)
        self.btn_center.resize(40, 40)
        
        # Мини-карта
        self.minimap = Minimap(self, self)
        self.minimap.setScene(self.scene_obj)
        self.minimap.resize(200, 150)
        self.minimap.hide() # Скрываем, пока нет данных

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Позиционирование кнопок
        self.btn_center.move(20, self.height() - 60)
        # Позиционирование мини-карты (справа снизу)
        self.minimap.move(self.width() - 220, self.height() - 170)

    def wake_up_physics(self):
        self.active_physics = True
        if not self.physics_timer.isActive():
            self.physics_timer.start(20) # 50 FPS

    def load_data(self, knowledge_chunks: list):
        self.scene_obj.clear()
        self.scene_obj.edges.clear()
        self.nodes.clear()
        self.resetTransform()
        
        if not knowledge_chunks:
            self.minimap.hide()
            return
            
        self.minimap.show()
        
        categories = {}
        for chunk in knowledge_chunks:
            key = chunk['chunk_key']
            cat_name = key.split('_')[0].upper() if '_' in key else 'MISC'
            
            if cat_name not in categories:
                cat_node = GraphNode(f"cat_{cat_name}", cat_name, 'CATEGORY', size=50)
                cat_node.setPos(random.uniform(-50, 50), random.uniform(-50, 50))
                self.scene_obj.addItem(cat_node)
                self.nodes.append(cat_node)
                categories[cat_name] = cat_node
            
            node = GraphNode(chunk['id'], chunk['title'], 'PRODUCT', size=20)
            cx, cy = categories[cat_name].pos().x(), categories[cat_name].pos().y()
            node.setPos(cx + random.uniform(-20, 20), cy + random.uniform(-20, 20))
            
            self.scene_obj.addItem(node)
            self.nodes.append(node)
            
            edge = GraphEdge(categories[cat_name], node)
            self.scene_obj.addItem(edge)
            self.scene_obj.edges.append(edge)

        self.wake_up_physics()
        self.fit_to_content()

    def fit_to_content(self):
        if not self.nodes: return
        self.scene_obj.setSceneRect(self.scene_obj.itemsBoundingRect().adjusted(-100, -100, 100, 100))
        self.fitInView(self.scene_obj.itemsBoundingRect(), Qt.AspectRatioMode.KeepAspectRatio)
        # Немного отдаляем, чтобы было место
        self.scale(0.9, 0.9)

    def _physics_tick(self):
        if not self.active_physics: return

        # Динамическое обновление границ мира
        # Мы берем текущие границы узлов и добавляем "воздух" (1000px), 
        # чтобы пользователь видел границы, но они расширялись при разлете.
        content_rect = self.scene_obj.itemsBoundingRect()
        dynamic_rect = content_rect.adjusted(-1000, -1000, 1000, 1000)
        self.scene_obj.setSceneRect(dynamic_rect)
        
        # Обновляем мини-карту
        self.minimap.fitInView(self.scene_obj.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self.minimap.viewport().update()

        total_kinetic = 0
        repulsion = 5000.0
        spring_len = 100.0
        k_spring = 0.05
        damping = 0.85
        center_grav = 0.01

        # Physics Loop
        for i, n1 in enumerate(self.nodes):
            fx, fy = 0, 0
            for j, n2 in enumerate(self.nodes):
                if i == j: continue
                dx = n1.x() - n2.x()
                dy = n1.y() - n2.y()
                dist_sq = dx*dx + dy*dy
                if dist_sq < 0.1: dist_sq = 0.1
                force = repulsion / dist_sq
                dist = math.sqrt(dist_sq)
                fx += (dx / dist) * force
                fy += (dy / dist) * force
            
            fx -= n1.x() * center_grav
            fy -= n1.y() * center_grav
            n1.vx = (n1.vx + fx) * damping
            n1.vy = (n1.vy + fy) * damping

        for edge in self.scene_obj.edges:
            n1, n2 = edge.source, edge.target
            dx = n1.x() - n2.x()
            dy = n1.y() - n2.y()
            dist = math.sqrt(dx*dx + dy*dy)
            force = (dist - spring_len) * k_spring
            if dist == 0: dist = 0.001
            fx = (dx / dist) * force
            fy = (dy / dist) * force
            n1.vx -= fx
            n1.vy -= fy
            n2.vx += fx
            n2.vy += fy

        moved = False
        for n in self.nodes:
            if n.is_dragging: continue
            speed = math.sqrt(n.vx**2 + n.vy**2)
            total_kinetic += speed
            if speed > 10:
                n.vx = (n.vx / speed) * 10
                n.vy = (n.vy / speed) * 10
            if speed > 0.1:
                n.setPos(n.x() + n.vx, n.y() + n.vy)
                moved = True
        
        if total_kinetic < 0.5 and not moved:
            self.active_physics = False
            self.physics_timer.stop()

    def wheelEvent(self, event: QWheelEvent):
        zoom_in = 1.15
        zoom_out = 1 / zoom_in
        old_pos = self.mapToScene(event.position().toPoint())
        
        if event.angleDelta().y() > 0:
            self.scale(zoom_in, zoom_in)
        else:
            self.scale(zoom_out, zoom_out)
            
        new_pos = self.mapToScene(event.position().toPoint())
        delta = new_pos - old_pos
        self.translate(delta.x(), delta.y())
        
        # Обновляем рамку на миникарте при зуме
        self.minimap.viewport().update()

    def mousePressEvent(self, event: QMouseEvent):
        super().mousePressEvent(event)
        item = self.itemAt(event.pos())
        if isinstance(item, GraphNode) and item.node_type == 'PRODUCT':
            if isinstance(item.node_id, int):
                self.node_selected.emit(item.node_id)