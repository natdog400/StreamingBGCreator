import sys

from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from backgroundcreator.gui.main_window import MainWindow


SERVER_NAME = "Eevees_BG_Creator_single_instance"


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("<3Eevee's_BG_Creator<3")

    app.setStyleSheet(
        """
        QWidget {
          background: #f6efff;
          color: #2f1b3a;
          selection-background-color: #cdb4ff;
          selection-color: #1d1026;
        }
        QMainWindow::separator {
          background: #d9c9ff;
          width: 1px;
          height: 1px;
        }
        QToolBar {
          background: #efe6ff;
          border: 1px solid #d9c9ff;
          spacing: 6px;
        }
        QToolBar::separator {
          background: #d9c9ff;
          width: 1px;
          margin: 2px 6px;
        }
        QMenuBar {
          background: #efe6ff;
          border-bottom: 1px solid #d9c9ff;
        }
        QMenuBar::item {
          background: transparent;
          padding: 6px 10px;
          border-radius: 8px;
        }
        QMenuBar::item:selected {
          background: #dccbff;
        }
        QMenu {
          background: #f7f1ff;
          border: 1px solid #d9c9ff;
          padding: 6px;
        }
        QMenu::item {
          padding: 6px 12px;
          border-radius: 8px;
        }
        QMenu::item:selected {
          background: #dccbff;
        }
        QDockWidget {
          titlebar-close-icon: none;
          titlebar-normal-icon: none;
        }
        QDockWidget::title {
          background: #e7dcff;
          padding: 8px 10px;
          border: 1px solid #d9c9ff;
          border-bottom: none;
        }
        QDockWidget::widget {
          border: 1px solid #d9c9ff;
          border-top: none;
        }
        QTabWidget::pane {
          border: 1px solid #d9c9ff;
          border-radius: 10px;
          background: #f7f1ff;
          top: -1px;
        }
        QTabBar::tab {
          background: #efe6ff;
          border: 1px solid #d9c9ff;
          padding: 8px 12px;
          margin-right: 6px;
          border-top-left-radius: 10px;
          border-top-right-radius: 10px;
        }
        QTabBar::tab:selected {
          background: #f7f1ff;
          border-bottom-color: #f7f1ff;
        }
        QTabBar::tab:hover:!selected {
          background: #e7dcff;
        }
        QPushButton {
          background: #eadfff;
          border: 1px solid #cdb4ff;
          padding: 8px 10px;
          border-radius: 10px;
        }
        QPushButton:hover {
          background: #e1d3ff;
        }
        QPushButton:pressed {
          background: #d6c2ff;
        }
        QPushButton:disabled {
          background: #efe6ff;
          color: #7a6387;
          border-color: #d9c9ff;
        }
        QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QFontComboBox {
          background: #fffaff;
          border: 1px solid #cdb4ff;
          padding: 6px 8px;
          border-radius: 10px;
        }
        QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QFontComboBox:focus {
          border: 2px solid #b692ff;
        }
        QComboBox::drop-down, QFontComboBox::drop-down {
          border-left: 1px solid #cdb4ff;
          width: 26px;
        }
        QComboBox QAbstractItemView, QFontComboBox QAbstractItemView {
          background: #f7f1ff;
          border: 1px solid #d9c9ff;
          selection-background-color: #dccbff;
          selection-color: #1d1026;
        }
        QListWidget {
          background: #fffaff;
          border: 1px solid #d9c9ff;
          border-radius: 10px;
          padding: 6px;
        }
        QListWidget::item {
          padding: 8px 10px;
          border-radius: 10px;
        }
        QListWidget::item:selected {
          background: #dccbff;
          color: #1d1026;
        }
        QCheckBox {
          spacing: 10px;
        }
        QCheckBox::indicator {
          width: 18px;
          height: 18px;
          border-radius: 5px;
          border: 1px solid #b692ff;
          background: #fffaff;
        }
        QCheckBox::indicator:checked {
          background: #cdb4ff;
          border: 1px solid #9c74ff;
        }
        QScrollBar:vertical {
          background: transparent;
          width: 12px;
          margin: 2px;
        }
        QScrollBar::handle:vertical {
          background: #cdb4ff;
          border-radius: 6px;
          min-height: 20px;
        }
        QScrollBar::handle:vertical:hover {
          background: #b692ff;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
          height: 0px;
        }
        QScrollBar:horizontal {
          background: transparent;
          height: 12px;
          margin: 2px;
        }
        QScrollBar::handle:horizontal {
          background: #cdb4ff;
          border-radius: 6px;
          min-width: 20px;
        }
        QScrollBar::handle:horizontal:hover {
          background: #b692ff;
        }
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
          width: 0px;
        }
        QGraphicsView {
          background: #fffaff;
          border: 1px solid #d9c9ff;
          border-radius: 10px;
        }
        """
    )

    socket = QLocalSocket()
    socket.connectToServer(SERVER_NAME)
    if socket.waitForConnected(150):
        socket.write(b"activate_reset\n")
        socket.flush()
        socket.waitForBytesWritten(150)
        socket.disconnectFromServer()
        return 0

    window = MainWindow()
    window.show()

    server = QLocalServer()
    server.listen(SERVER_NAME)

    def on_new_connection() -> None:
        while server.hasPendingConnections():
            conn = server.nextPendingConnection()
            if conn is None:
                return

            def on_ready_read(conn=conn) -> None:
                try:
                    data = bytes(conn.readAll()).decode("utf-8", errors="ignore")
                except Exception:
                    data = ""
                window._handle_ipc_command(data)
                try:
                    conn.disconnectFromServer()
                except Exception:
                    pass

            conn.readyRead.connect(on_ready_read)

    server.newConnection.connect(on_new_connection)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
