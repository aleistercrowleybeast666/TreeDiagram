"""Lightweight Qt views of actual assemblies and computed samples (no solver state)."""
from __future__ import annotations

import math
import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from .geometry import Quaternion_Matrix


class EngineeringView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.design = None
        self.rows = []
        self.index = 0
        self.yaw = .6
        self.setMinimumSize(260, 250)
        self.setToolTip("拖动旋转视角。仅查看已提交模型或已完成结果，不改变求解状态。")
        self._last = None

    def mousePressEvent(self, event):
        self._last = event.position()

    def mouseMoveEvent(self, event):
        if self._last is not None:
            self.yaw += (event.position().x()-self._last.x())*.01
            self._last = event.position()
            self.update()

    def mouseReleaseEvent(self, event):
        self._last = None

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), self.palette().base())
        painter.setPen(self.palette().text().color())
        painter.drawText(16, 26, "轨迹 / 姿态 · ENU" if self.rows else "装配预览 · Body +Z 指向头部")
        if self.design is None:
            painter.drawText(18, 65, "打开离线示例，或导入模型开始。")
            return
        angle = self.yaw
        def project(v):
            return np.array([v[0]*math.cos(angle)-v[1]*math.sin(angle),
                             -v[2]+.28*(v[0]*math.sin(angle)+v[1]*math.cos(angle))])
        if self.rows:
            points = np.array([project(np.asarray(row["position_enu_m"])) for row in self.rows])
            low, high = points.min(axis=0), points.max(axis=0)
            scale = min((self.width()-60)/max(1., high[0]-low[0]),
                        (self.height()-80)/max(1., high[1]-low[1]))
            def pixel(point):
                p = (point-(low+high)/2)*scale + np.array([self.width()/2, self.height()/2+15])
                return QPointF(*p)
            painter.setPen(QPen(QColor("#299eaf"), 2))
            painter.drawPolyline(QPolygonF([pixel(p) for p in points]))
            row = self.rows[min(self.index, len(self.rows)-1)]
            base = project(np.asarray(row["position_enu_m"]))
            direction = project(Quaternion_Matrix(row["q_nb"])[:, 2])
            painter.setPen(QPen(QColor("#eea65a"), 5))
            origin = pixel(base)
            painter.drawLine(origin, origin+QPointF(*(direction*25)))
            painter.setPen(self.palette().text().color())
            painter.drawText(16, self.height()-16, f"t = {row['time_s']:.3f} s   h = {row['position_enu_m'][2]:.2f} m")
            return
        transformed = {}
        for _ in self.design.parts:
            for part in self.design.parts:
                if part.id in transformed or part.parent_id is not None and part.parent_id not in transformed:
                    continue
                position, rotation = np.array(part.position_m), Quaternion_Matrix(part.rotation_wxyz)
                if part.parent_id:
                    p, r = transformed[part.parent_id]
                    position, rotation = p+r@position, r@rotation
                transformed[part.id] = position, rotation
        extents = []
        for part in self.design.parts:
            position, rotation = transformed[part.id]
            extents.extend([project(position+rotation@np.array([0.,0.,sign*part.length_m/2])) for sign in (-1,1)])
        points = np.array(extents)
        center = (points.min(axis=0)+points.max(axis=0))/2
        scale = min((self.height()-150)/max(.2, np.ptp(points[:,1])), (self.width()-60)/max(.3,np.ptp(points[:,0])))
        def pixel(p):
            return QPointF(*((project(p)-center)*scale+np.array([self.width()/2,self.height()/2+15])))
        colors = {"nose":"#49a8c0", "tube":"#738da8", "fins":"#4bb59b", "mass":"#d29d61"}
        for part in self.design.parts:
            position, rotation = transformed[part.id]
            color=QColor(colors.get(part.kind,"#8a90c2"))
            painter.setPen(QPen(color.darker(120),1))
            def point(x,y,z):return pixel(position+rotation@np.array([x,y,z]))
            if part.kind == "fins":
                for angle in np.linspace(0,2*math.pi,4,endpoint=False):
                    x,y=math.cos(angle),math.sin(angle)
                    painter.setBrush(color)
                    painter.drawPolygon(QPolygonF([point(0,0,part.length_m/2),
                        point(x*part.radius_m,y*part.radius_m,-part.length_m/3),
                        point(x*part.radius_m,y*part.radius_m,-part.length_m/2),point(0,0,-part.length_m/2)]))
            else:
                for angle in np.linspace(0,2*math.pi,16,endpoint=False):
                    other=angle+2*math.pi/16
                    x,y=part.radius_m*math.cos(angle),part.radius_m*math.sin(angle)
                    u,v=part.radius_m*math.cos(other),part.radius_m*math.sin(other)
                    painter.setBrush(color.lighter(int(100+20*math.sin(angle+self.yaw))))
                    bottom=-part.length_m/2
                    vertices=[point(x,y,bottom),point(u,v,bottom)]
                    if part.kind=="nose":vertices.append(point(0,0,part.length_m/2))
                    else:vertices.extend([point(u,v,part.length_m/2),point(x,y,part.length_m/2)])
                    painter.drawPolygon(QPolygonF(vertices))
        painter.setPen(self.palette().text().color())
        painter.drawText(16, self.height()-16, "几何外观与气动模型分别定义 · 拖动旋转")


class SignalView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.series = []
        self.units = "m"
        self.setMinimumHeight(210)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), self.palette().base())
        painter.setPen(self.palette().text().color())
        if not self.series:
            painter.drawText(20, 40, "完成运行后显示真实样本。")
            return
        data = [(label, np.asarray(x), np.asarray(y)) for label, x, y in self.series if len(x)]
        if not data:
            return
        xmin, xmax = min(v[1].min() for v in data), max(v[1].max() for v in data)
        ymin, ymax = min(v[2].min() for v in data), max(v[2].max() for v in data)
        span = max(1e-9, ymax-ymin)
        ymin, ymax = ymin-.1*span, ymax+.1*span
        colors = ("#3c91c5", "#da9a47", "#39a98d", "#9978ba")
        left, top, width, height = 65, 48, self.width()-90, self.height()-90
        painter.drawLine(left, top, left, top+height)
        painter.drawLine(left, top+height, left+width, top+height)
        for fraction in (0., .5, 1.):
            y = top+height*(1-fraction)
            painter.drawText(3, int(y+4), f"{ymin+fraction*(ymax-ymin):.3g}")
        painter.drawText(left, self.height()-12, f"{xmin:.2f} s")
        painter.drawText(left+width-70, self.height()-12, f"{xmax:.2f} s")
        painter.drawText(4, 22, self.units)
        for index, (label, x, y) in enumerate(data):
            painter.setPen(QPen(QColor(colors[index%len(colors)]), 2))
            painter.drawText(left+index*145, 24, label)
            points = [QPointF(left+(a-xmin)/max(1e-9,xmax-xmin)*width,
                              top+(ymax-b)/(ymax-ymin)*height) for a,b in zip(x,y)]
            painter.drawPolyline(QPolygonF(points))
