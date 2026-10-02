# file: src/web/internal/dev/foo/webglearth/webglearth.py
# import sys
# from PyQt5.QtWidgets import QApplication, QMainWindow
# from PyQt5.QtWebEngineWidgets import QWebEngineView
# from PyQt5.QtCore import QUrl
# import os

# class GlobeWindow(QMainWindow):
#     def __init__(self, folder):
#         super().__init__()
#         # Use the folder as window title
#         self.setWindowTitle(f"Interactive Globe - {folder}")
#         self.setGeometry(100, 100, 1200, 800)

#         # Create web view
#         self.web_view = QWebEngineView(self)
#         self.setCentralWidget(self.web_view)

#         # Load the HTML file
#         html_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "simulator.html"))
#         self.web_view.load(QUrl.fromLocalFile(html_path))


# if __name__ == "__main__":
#     folder = sys.argv[1] if len(sys.argv) > 1 else "default_folder"
#     app = QApplication(sys.argv)
#     window = GlobeWindow(folder)
#     window.show()
#     sys.exit(app.exec_())
