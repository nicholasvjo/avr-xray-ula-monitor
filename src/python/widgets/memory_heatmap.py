from __future__ import annotations

import time
import tkinter as tk
from collections.abc import Callable

import customtkinter as ctk


BG = "#09171B"
BORDER = "#21434B"
MUTED = "#83A0A8"
AMBER = "#FFB84D"


class MemoryHeatmap(ctk.CTkFrame):
    COLUMNS = 16
    ROWS = 8
    CELL_WIDTH = 34
    CELL_HEIGHT = 31

    def __init__(
        self,
        master,
        on_select: Callable[[int, int], None] | None = None,
    ):
        super().__init__(
            master,
            fg_color=BG,
            border_color=BORDER,
            border_width=1,
            corner_radius=7,
        )
        self.on_select = on_select
        self.data = bytes(128)
        self.changed_at = [0.0] * 128
        self.selected_index = 0

        width = self.COLUMNS * self.CELL_WIDTH
        height = self.ROWS * self.CELL_HEIGHT
        self.canvas = tk.Canvas(
            self,
            width=width,
            height=height,
            bg=BG,
            highlightthickness=0,
            bd=0,
        )
        self.canvas.grid(row=0, column=0, padx=10, pady=10)
        self.canvas.bind("<Button-1>", self._handle_click)
        self._render_cells()

    def update_bytes(self, data: bytes) -> None:
        if len(data) != 128:
            raise ValueError("O heatmap requer exatamente 128 bytes.")

        now = time.monotonic()
        for index, (previous, current) in enumerate(zip(self.data, data)):
            if previous != current:
                self.changed_at[index] = now
        self.data = bytes(data)
        self._render_cells()

    def _handle_click(self, event: tk.Event) -> None:
        column = min(self.COLUMNS - 1, max(0, event.x // self.CELL_WIDTH))
        row = min(self.ROWS - 1, max(0, event.y // self.CELL_HEIGHT))
        index = row * self.COLUMNS + column
        self.selected_index = index
        self._render_cells()
        if self.on_select is not None:
            self.on_select(index, self.data[index])

    def _render_cells(self) -> None:
        self.canvas.delete("all")
        now = time.monotonic()

        for index, value in enumerate(self.data):
            column = index % self.COLUMNS
            row = index // self.COLUMNS
            x1 = column * self.CELL_WIDTH + 2
            y1 = row * self.CELL_HEIGHT + 2
            x2 = x1 + self.CELL_WIDTH - 4
            y2 = y1 + self.CELL_HEIGHT - 4

            outline = "#35545D"
            width = 1
            if now - self.changed_at[index] < 0.55:
                outline = AMBER
                width = 2
            if index == self.selected_index:
                outline = "#EAF2F5"
                width = 2

            self.canvas.create_rectangle(
                x1,
                y1,
                x2,
                y2,
                fill=self._value_color(value),
                outline=outline,
                width=width,
            )
            self.canvas.create_text(
                (x1 + x2) / 2,
                (y1 + y2) / 2,
                text=f"{value:02X}",
                fill="#EAF2F5" if value < 175 else "#041014",
                font=("Consolas", 9, "bold"),
            )

        for column in range(self.COLUMNS):
            self.canvas.create_text(
                column * self.CELL_WIDTH + self.CELL_WIDTH / 2,
                7,
                text=f"{column:X}",
                fill=MUTED,
                font=("Consolas", 7),
            )

    @staticmethod
    def _value_color(value: int) -> str:
        ratio = value / 255
        low = (14, 31, 37)
        mid = (19, 92, 102)
        high = (0, 217, 255)
        if ratio < 0.55:
            local = ratio / 0.55
            start, end = low, mid
        else:
            local = (ratio - 0.55) / 0.45
            start, end = mid, high
        red = round(start[0] + (end[0] - start[0]) * local)
        green = round(start[1] + (end[1] - start[1]) * local)
        blue = round(start[2] + (end[2] - start[2]) * local)
        return f"#{red:02X}{green:02X}{blue:02X}"
