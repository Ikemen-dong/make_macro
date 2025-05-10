# eyedropper.py
import sys
import platform
import ctypes
from PyQt5.QtCore import Qt, QPoint, QRect
from PyQt5.QtGui import QGuiApplication, QCursor, QColor, QPixmap, QImage, QPainter
from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout

class _SystemCursor:
    _hidden = False
    @classmethod
    def hide(cls):
        if cls._hidden or platform.system() != "Windows": return
        max_tries, tries = 20, 0
        current_count = ctypes.windll.user32.ShowCursor(False); tries +=1
        # ShowCursor(False) 반환값이 -1보다 작아질 때까지 (숨겨질 때까지) 반복
        while current_count >= -1 and tries < max_tries: 
            current_count = ctypes.windll.user32.ShowCursor(False)
            tries += 1
        if current_count < -1 : cls._hidden = True

    @classmethod
    def show(cls):
        if not cls._hidden or platform.system() != "Windows": return
        max_tries, tries = 20, 0
        current_count = ctypes.windll.user32.ShowCursor(True); tries +=1
        # ShowCursor(True) 반환값이 0 이상이 될 때까지 (보여질 때까지) 반복
        while current_count < 0 and tries < max_tries: 
            current_count = ctypes.windll.user32.ShowCursor(True)
            tries +=1
        if current_count >=0 : cls._hidden = False

class Magnifier(QWidget):
    def __init__(self, zoom: int = 10, sample_size: int = 31, parent=None):
        super().__init__(parent, Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.zoom = zoom
        self.sample_size = sample_size 
        if self.sample_size % 2 == 0: self.sample_size +=1 # 홀수로 보정하여 중앙 픽셀 명확화
        self._half_sample = self.sample_size // 2
        
        self.setAttribute(Qt.WA_ShowWithoutActivating) # 활성화 없이 표시
        self.setAttribute(Qt.WA_TranslucentBackground) # 배경 투명 허용

        self.img_label = QLabel(alignment=Qt.AlignCenter) # 확대 이미지 표시 라벨
        self.img_label.setFixedSize(self.sample_size * self.zoom, self.sample_size * self.zoom)
        
        self.hex_label = QLabel("#FFFFFF", alignment=Qt.AlignHCenter) # HEX 색상 코드 라벨
        self.hex_label.setStyleSheet("font:bold 12pt 'Consolas';color:white;background-color:transparent;")
        
        self.rgb_label = QLabel("(255,255,255)", alignment=Qt.AlignHCenter) # RGB 색상 코드 라벨
        self.rgb_label.setStyleSheet("font-size:9pt; color:#DDDDDD;background-color:transparent;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4); layout.setSpacing(1) # 내부 여백 및 위젯 간 간격
        layout.addWidget(self.img_label)
        layout.addWidget(self.hex_label)
        layout.addWidget(self.rgb_label)
        
        self.setStyleSheet("background-color:rgba(30,30,30,230);border:1px solid #777777;border-radius:4px;") # 돋보기 창 스타일
        self.adjustSize() # 내용에 맞게 창 크기 자동 조절
        
        self.current_center_color = QColor(0,0,0) # 현재 캡처된 중앙 픽셀 색상 저장
        self.current_cursor_pos = QPoint(0,0) # 현재 캡처된 커서 위치 저장 (돋보기 기준점)

    def update_preview(self, gpos: QPoint): # gpos는 전역 (가상 데스크톱) 좌표
        self.current_cursor_pos = gpos # 현재 커서 위치 업데이트 (get_current_color_info 위함)
        screen = QGuiApplication.screenAt(gpos) # 커서 위치의 화면 객체 가져오기
        if not screen: screen = QGuiApplication.primaryScreen() # 없으면 주 화면 사용

        # 캡처할 영역의 좌상단 좌표 계산
        x0 = gpos.x() - self._half_sample
        y0 = gpos.y() - self._half_sample
        
        try:
            # 화면의 지정된 영역 캡처 (WId=0은 전체 데스크톱 의미)
            pixmap = screen.grabWindow(0, int(x0), int(y0), self.sample_size, self.sample_size)
        except Exception: return # 캡처 실패 시 중단

        # QPixmap을 QImage로 변환 (픽셀 접근 및 색상 형식 일관성 위함)
        img = pixmap.toImage().convertToFormat(QImage.Format_RGB888)
        # 유효하지 않은 이미지거나, 중앙 픽셀 좌표가 이미지 범위를 벗어나면 중단
        if img.isNull() or not img.valid(self._half_sample, self._half_sample): return

        self.current_center_color = QColor(img.pixel(self._half_sample, self._half_sample))
        r, g, b = self.current_center_color.red(), self.current_center_color.green(), self.current_center_color.blue()

        # QImage를 QPixmap으로 변환 후 확대 (Nearest Neighbor 효과)
        pm_scaled = QPixmap.fromImage(img).scaled(
            self.img_label.width(), self.img_label.height(), 
            Qt.IgnoreAspectRatio, Qt.FastTransformation # 픽셀아트처럼 보이도록 FastTransformation 사용
        )
        
        # QPainter를 사용하여 확대된 QPixmap에 그리드 및 십자선 그리기
        painter = QPainter(pm_scaled)
        painter.setPen(QColor(0, 0, 0, 70)); grid_zoom = self.zoom # 그리드 색상 및 줌 배율
        for i in range(self.sample_size + 1): # 그리드 선 그리기
            pos = i * grid_zoom
            painter.drawLine(pos, 0, pos, pm_scaled.height()) # 수직선
            painter.drawLine(0, pos, pm_scaled.width(), pos) # 수평선
        
        painter.setPen(QColor(255, 0, 0, 200)); cross_len = max(3, self.zoom // 2 -1) # 십자선 길이
        cx, cy = pm_scaled.width() // 2, pm_scaled.height() // 2 # 확대된 이미지의 중앙
        
        # 십자선이 중앙 픽셀을 정확히 가리키도록 (중앙 픽셀을 비워둠)
        painter.drawLine(cx - cross_len, cy, cx - 1, cy) # 왼쪽
        painter.drawLine(cx + 1, cy, cx + cross_len, cy) # 오른쪽
        painter.drawLine(cx, cy - cross_len, cx, cy - 1) # 위쪽
        painter.drawLine(cx, cy + 1, cx, cy + cross_len) # 아래쪽
        painter.end()

        self.img_label.setPixmap(pm_scaled) # 최종 이미지 라벨에 설정
        self.hex_label.setText(f"#{r:02X}{g:02X}{b:02X}") # HEX 코드 업데이트
        self.rgb_label.setText(f"({r},{g},{b})") # RGB 값 업데이트
        
        self._move_smart(gpos) # 돋보기 창 위치 조정

    def _move_smart(self, global_cursor_pos: QPoint): # 이전과 동일 (화면 벗어나지 않게 위치 조정)
        offset = QPoint(20, 20)
        screen = QGuiApplication.screenAt(global_cursor_pos) or QGuiApplication.primaryScreen()
        screen_geom = screen.availableGeometry()
        target_pos = global_cursor_pos + offset
        if target_pos.x() + self.width() > screen_geom.right(): target_pos.setX(global_cursor_pos.x() - self.width() - offset.x())
        if target_pos.y() + self.height() > screen_geom.bottom(): target_pos.setY(global_cursor_pos.y() - self.height() - offset.y())
        target_pos.setX(max(target_pos.x(), screen_geom.left())); target_pos.setY(max(target_pos.y(), screen_geom.top()))
        self.move(target_pos)

    def get_current_color_info(self) -> (QPoint, QColor):
        """돋보기가 마지막으로 업데이트한 커서 위치와 중앙 색상을 반환"""
        return self.current_cursor_pos, self.current_center_color


class Overlay(QWidget): # 이전과 동일
    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_NoSystemBackground, True); self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowOpacity(0.01); self.setCursor(Qt.BlankCursor) 
        virtual_desktop_rect = QRect()
        for screen in QGuiApplication.screens(): virtual_desktop_rect = virtual_desktop_rect.united(screen.geometry())
        if virtual_desktop_rect.isNull(): virtual_desktop_rect = QGuiApplication.primaryScreen().geometry()
        self.setGeometry(virtual_desktop_rect)