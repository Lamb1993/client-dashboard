import webbrowser
from threading import Timer
from app import app   # or whatever your main Flask file is named

def open_browser():
    webbrowser.open("http://127.0.0.1:5000")

if __name__ == "__main__":
    Timer(1, open_browser).start()
    app.run()
