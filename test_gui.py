import wx

class TestFrame(wx.Frame):
    def __init__(self):
        super().__init__(None, title="Test Window", size=(400, 300))
        panel = wx.Panel(self)
        text = wx.StaticText(panel, label="If you can see this, wxPython is working!")
        
def main():
    app = wx.App()
    frame = TestFrame()
    frame.Show()
    app.MainLoop()

if __name__ == "__main__":
    main()
