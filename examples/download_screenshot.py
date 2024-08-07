from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Button


class ScreenshotApp(App[None]):
    BINDINGS = [Binding("s", "deliver_screenshot", "Screenshot")]

    def compose(self) -> ComposeResult:
        yield Button("Hello, World!")

    @on(Button.Pressed)
    def on_button_pressed(self) -> None:
        self.action_deliver_screenshot()

    def action_deliver_screenshot(self) -> None:
        print("Delivering screenshot action!")
        filename = self.save_screenshot("screenshot.svg")
        self.deliver_text(filename)


app = ScreenshotApp()
if __name__ == "__main__":
    app.run()
