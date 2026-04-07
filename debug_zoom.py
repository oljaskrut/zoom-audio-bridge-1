import win32gui


def list_zoom_windows():
    results = []

    def callback(hwnd, acc):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            cls = win32gui.GetClassName(hwnd)
            if "zoom" in title.lower() or cls.startswith("ZP"):
                acc.append((cls, title))

    win32gui.EnumWindows(callback, results)

    if not results:
        print("No Zoom windows found.")
        print("Make sure Zoom is open and in a meeting.")
    else:
        print(f"Found {len(results)} Zoom window(s):\n")
        for cls, title in results:
            print(f"  Class: {cls}")
            print(f"  Title: {title}")
            print()


if __name__ == "__main__":
    list_zoom_windows()
