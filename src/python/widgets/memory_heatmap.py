from __future__ import annotations

import time
import tkinter as tk
from collections.abc import Callable

import customtkinter as ctk


BG = "#06131A"
BORDER = "#285965"
MUTED = "#8CB4BE"
AMBER = "#FFB84D"
SELECTED = "#F5F7FA"


class MemoryHeatmap(ctk.CTkFrame):
    COLUMNS = 16
    ROWS = 8
    CELL_WIDTH = 39
    CELL_HEIGHT = 36
    HEADER_LEFT = 38
    HEADER_TOP = 27

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

        width = self.HEADER_LEFT + self.COLUMNS * self.CELL_WIDTH
        height = self.HEADER_TOP + self.ROWS * self.CELL_HEIGHT
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
        if event.x < self.HEADER_LEFT or event.y < self.HEADER_TOP:
            return

        column = min(
            self.COLUMNS - 1,
            max(0, (event.x - self.HEADER_LEFT) // self.CELL_WIDTH),
        )
        row = min(
            self.ROWS - 1,
            max(0, (event.y - self.HEADER_TOP) // self.CELL_HEIGHT),
        )
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
            x1 = self.HEADER_LEFT + column * self.CELL_WIDTH + 3
            y1 = self.HEADER_TOP + row * self.CELL_HEIGHT + 3
            x2 = x1 + self.CELL_WIDTH - 6
            y2 = y1 + self.CELL_HEIGHT - 6

            outline = "#2F5964"
            width = 1
            if now - self.changed_at[index] < 0.55:
                outline = AMBER
                width = 3
            if index == self.selected_index:
                outline = SELECTED
                width = 3

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
                fill="#F5F7FA" if value < 166 else "#031014",
                font=("Consolas", 10, "bold"),
            )

        for column in range(self.COLUMNS):
            self.canvas.create_text(
                self.HEADER_LEFT + column * self.CELL_WIDTH + self.CELL_WIDTH / 2,
                self.HEADER_TOP / 2,
                text=f"{column:X}",
                fill=MUTED,
                font=("Consolas", 10, "bold"),
            )

        for row in range(self.ROWS):
            self.canvas.create_text(
                self.HEADER_LEFT / 2,
                self.HEADER_TOP + row * self.CELL_HEIGHT + self.CELL_HEIGHT / 2,
                text=f"{row * self.COLUMNS:02X}",
                fill=MUTED,
                font=("Consolas", 9, "bold"),
            )

    @staticmethod
    def _value_color(value: int) -> str:
        ratio = value / 255
        low = (12, 30, 55)
        mid = (0, 119, 145)
        high = (62, 245, 190)
        if ratio < 0.52:
            local = ratio / 0.52
            start, end = low, mid
        else:
            local = (ratio - 0.52) / 0.48
            start, end = mid, high
        red = round(start[0] + (end[0] - start[0]) * local)
        green = round(start[1] + (end[1] - start[1]) * local)
        blue = round(start[2] + (end[2] - start[2]) * local)
        return f"#{red:02X}{green:02X}{blue:02X}"
