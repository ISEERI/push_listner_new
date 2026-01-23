import tkinter as tk
from DLMS_UI import DLMSApp

if __name__ == "__main__":
    root = tk.Tk()
    app = DLMSApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()